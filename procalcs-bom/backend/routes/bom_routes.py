"""
bom_routes.py — BOM generation endpoint
Gerald calls POST /api/v1/bom/generate with job design data.
Returns a complete, client-profiled Bill of Materials.
Follows ProCalcs Design Standards v2.0
"""

import logging
from flask import Blueprint, jsonify, request, Response, g
from services.bom_service import generate
from services.bom_from_wrightsoft import (
    build_bom_from_wrightsoft_lines,
    parse_wrightsoft_bom_rows,
)
from services.pdf_service import render_bom_pdf
from services.bom_xls_service import render_bom_xlsx
from services.materials_rules import generate_rule_lines, compute_scope, summarize_scope
from services.profile_service import get_profile_by_id
from models.client_profile import ClientProfile
from utils.validators import validate_bom_request
from utils.rup_parser import parse_rup_bytes

logger = logging.getLogger('procalcs_bom')
bom_bp = Blueprint('bom', __name__)


# Max .rup file size — 20 MB covers a 50-AHU commercial project.
# The Enos sample is 6.6 MB for a large 8-AHU residence.
MAX_RUP_BYTES = 20 * 1024 * 1024


def _looks_like_rup(file_bytes: bytes) -> bool:
    """Heuristic .rup detector for the /from-wrightsoft auto-route.
    Wrightsoft .rup files start with a UTF-16-LE header that includes
    the string 'Wrightsoft' or the product code 'rsu'/'rcs' near the
    front of the file. We sniff the first 4KB so a misnamed upload
    (Tom dragging the file without an extension) still routes correctly.
    """
    if not file_bytes:
        return False
    head = file_bytes[:4096]
    try:
        text = head.decode("utf-16-le", errors="ignore").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(tok in text for tok in (
        "wrightsoft", "right-suite", "rightsuite", "manual j", "manual d",
    ))


def _catalog_xref_for_binary(file_bytes: bytes) -> dict:
    """Day-10 — count how many Wrightsoft catalog generic IDs appear
    in the .rup binary text. Empirically always near-zero because
    Wrightsoft computes its BOM at output time rather than storing it
    in the file, but the explicit number is what tells designers
    why we need a separate Wrightsoft BOM export to be deterministic.

    Returns:
        {
          "bom_is_in_binary": bool      — True iff a meaningful number
                                          of catalog IDs were found
          "generic_ids_in_catalog": int — denominator (always 3014 today)
          "generic_ids_found": int      — how many catalog IDs appear in
                                          the file's text
          "found_sample": list[str]     — first 10 hits, for the SPA
                                          to show as evidence
          "recommendation": str         — what the designer should do
        }
    """
    try:
        text = file_bytes.decode("utf-16-le", errors="replace")
    except Exception:
        text = ""
    try:
        from services.wrightsoft_catalog import load_mapped_parts, _cache
        load_mapped_parts()
        catalog_generics = set((_cache.mapped_by_generic or {}).keys())
    except Exception as exc:
        logger.warning("catalog_xref: could not load mapped_parts: %s", exc)
        catalog_generics = set()

    found = [g for g in catalog_generics if g in text]
    # We treat "BOM is in binary" as needing > 25% catalog coverage.
    # In practice we see 0-5 hits out of 3014 (<0.2%) so this always
    # resolves False today — but the threshold leaves room for a
    # future Wrightsoft variant that does embed the BOM.
    is_in_binary = len(found) > (len(catalog_generics) * 0.25)
    if is_in_binary:
        recommendation = (
            "Catalog IDs detected in the binary — the deterministic "
            "pipeline can run directly from this file via the new "
            "Wrightsoft BOM endpoint."
        )
    else:
        recommendation = (
            "This .rup binary does not contain the project's BOM. "
            "Wrightsoft computes the BOM at output time. For a "
            "deterministic result, export the BOM in Wrightsoft "
            "(Reports → Bill of Materials) and upload via /api/v1/bom/"
            "from-wrightsoft instead of /generate."
        )
    return {
        "bom_is_in_binary":        is_in_binary,
        "generic_ids_in_catalog":  len(catalog_generics),
        "generic_ids_found":       len(found),
        "found_sample":            sorted(found)[:10],
        "recommendation":          recommendation,
    }


# ===============================
# POST — Generate BOM
# ===============================

@bom_bp.route('/generate', methods=['POST'])
def generate_bom():
    """
    Generate a BOM from completed job design data.

    Request body:
    {
        "client_id": "beazer-001",
        "job_id": "job-12345",
        "output_mode": "full",   (optional — defaults to client profile setting)
        "design_data": {
            "duct_runs": [...],
            "fittings": [...],
            "equipment": [...],
            "registers": [...],
            "building": {
                "type": "single_level",
                "duct_location": "attic"
            }
        }
    }
    """
    try:
        body = request.get_json(silent=True)

        # Validate input
        errors = validate_bom_request(body)
        if errors:
            return jsonify({
                "success": False,
                "data": None,
                "error": " | ".join(errors)
            }), 400

        client_id   = body.get('client_id', '').strip()
        job_id      = body.get('job_id', '').strip()
        design_data = body.get('design_data', {})
        output_mode = body.get('output_mode')

        logger.info("BOM requested — client: %s  job: %s  mode: %s",
                    client_id, job_id, output_mode or 'profile default')

        bom = generate(client_id, job_id, design_data, output_mode)

        return jsonify({"success": True, "data": bom, "error": None}), 200

    except ValueError as e:
        # Missing profile or bad input
        return jsonify({"success": False, "data": None, "error": str(e)}), 404

    except RuntimeError as e:
        # AI failure or processing error
        logger.error("BOM generation runtime error for job %s: %s",
                     body.get('job_id', 'unknown') if body else 'unknown', e)
        return jsonify({
            "success": False,
            "data": None,
            "error": "BOM generation failed. Please try again."
        }), 500

    except Exception as e:
        logger.error("Unexpected error in generate_bom: %s", e)
        return jsonify({
            "success": False,
            "data": None,
            "error": "Something went wrong. Please try again."
        }), 500


# ===============================
# POST — Parse .rup file
# ===============================

@bom_bp.route('/parse-rup', methods=['POST'])
def parse_rup():
    """
    Parse a Wrightsoft Right-Suite Universal .rup file upload into the
    BOM engine's design_data shape.

    Per docs/GERALD_HANDOFF_RUP_UPLOAD.md this is step 1 of a two-step UX:
      1. Designer uploads .rup → this endpoint returns structured design_data
      2. Designer reviews the preview → POSTs that design_data + client_id
         to /api/v1/bom/generate for the actual priced BOM.

    Accepts multipart/form-data with a single 'file' field, or a raw
    application/octet-stream body with the .rup bytes.

    Returns:
        {
          "success": true,
          "data": {
            "project":   {...},
            "building":  {type, duct_location},
            "equipment": [...],
            "duct_runs": [],     # hybrid — AI infers from raw_rup_context
            "fittings":  [],     # hybrid — AI infers from raw_rup_context
            "registers": [],     # hybrid — AI infers from raw_rup_context
            "rooms":     [...],
            "metadata":  {...},
            "raw_rup_context": "..."
          },
          "error": null
        }
    """
    try:
        # Accept either a multipart upload or a raw body
        file_bytes = b''
        source_name = 'uploaded.rup'

        if 'file' in request.files:
            upload = request.files['file']
            source_name = upload.filename or source_name
            file_bytes = upload.read()
        elif request.data:
            file_bytes = request.data
            if request.headers.get('X-Filename'):
                source_name = request.headers['X-Filename']

        if not file_bytes:
            return jsonify({
                "success": False,
                "data": None,
                "error": "No .rup file provided. Send as multipart 'file' field or raw body."
            }), 400

        if len(file_bytes) > MAX_RUP_BYTES:
            return jsonify({
                "success": False,
                "data": None,
                "error": f".rup file exceeds {MAX_RUP_BYTES // 1024 // 1024} MB limit."
            }), 413

        # Fast header sanity check — a real Wrightsoft file begins with the
        # UTF-16 LE bytes for ".WSrsu.WSF.0004.APP=..."
        if not file_bytes.startswith(b'.\x00W\x00S'):
            return jsonify({
                "success": False,
                "data": None,
                "error": "File does not look like a Wrightsoft .rup project file."
            }), 400

        logger.info("Parsing .rup upload: %s (%d bytes)", source_name, len(file_bytes))
        design_data = parse_rup_bytes(file_bytes, source_name=source_name)

        # Day-10 — attach the catalog cross-reference verdict so the
        # SPA's BOM Engine page can nudge the user to the deterministic
        # Wrightsoft BOM upload BEFORE running AI estimation. One round
        # trip beats two; the xref is cheap (one set membership check
        # per generic, ~3,000 of them, < 5ms on a typical file).
        try:
            design_data["catalog_xref"] = _catalog_xref_for_binary(file_bytes)
        except Exception as exc:  # noqa: BLE001
            # Non-fatal — log + drop the key. Parse-rup still succeeds.
            logger.warning("parse-rup catalog_xref failed: %s", exc)

        # Day-14 Phase 4 — content-hash of the RUP so the SPA can look
        # up cached known-duct-LF totals for re-uploads of the same
        # file. Also bundle any cached totals straight into the
        # duct_summary so the form pre-populates without a second
        # round trip.
        try:
            from models.rup_duct_totals import RupDuctTotals, compute_rup_hash
            rup_hash = compute_rup_hash(file_bytes)
            design_data["rup_hash"] = rup_hash
            cached = RupDuctTotals.lookup(rup_hash)
            if cached and cached.known_lengths_ft:
                ds = design_data.get("duct_summary") or {}
                ds["known_lengths_ft"] = cached.known_lengths_ft
                ds["known_lengths_cached_at"] = (
                    cached.updated_at.isoformat() + "Z"
                    if cached.updated_at else None
                )
                ds["known_lengths_cached_by"] = cached.updated_by
                design_data["duct_summary"] = ds
        except Exception as exc:  # noqa: BLE001
            logger.warning("parse-rup duct-totals lookup failed: %s", exc)

        return jsonify({
            "success": True,
            "data": design_data,
            "error": None
        }), 200

    except Exception as e:
        logger.error("parse_rup failed: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "data": None,
            "error": "Failed to parse the .rup file. The file may be corrupt or an unsupported Wrightsoft version."
        }), 500


# ===============================
# POST — Render BOM → PDF
# ===============================

@bom_bp.route('/render-pdf', methods=['POST'])
def render_pdf():
    """
    Render an already-generated BOM dict into a branded PDF.

    Input: the BOM response object from /generate wrapped in {"bom": ...}.
    Output: application/pdf bytes with a suggested filename.

    Deliberately separate from /generate so clicking Download PDF
    doesn't trigger a new AI call. The SPA caches the BOM response
    after generating and posts it here for rendering — that's ~200ms
    versus the ~15s Claude round trip.
    """
    try:
        body = request.get_json(silent=True) or {}
        bom = body.get('bom')
        if not isinstance(bom, dict) or not bom.get('line_items'):
            return jsonify({
                "success": False,
                "data": None,
                "error": "Request body must be {\"bom\": <BomResponse with line_items>}.",
            }), 400

        pdf_bytes = render_bom_pdf(bom)
        filename = f"{(bom.get('job_id') or 'bom').replace('/', '-')}.pdf"

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        logger.error("render_pdf failed: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "data": None,
            "error": "PDF render failed. Please try again.",
        }), 500


# ===============================
# POST — Render BOM → XLSX
# ===============================

@bom_bp.route('/render-xls', methods=['POST'])
def render_xls():
    """
    Render an already-generated BOM dict into an .xlsx workbook.

    Input: the BOM response object from /generate or /from-wrightsoft
    wrapped in {"bom": ...}.
    Output: application/vnd.openxmlformats... bytes with a suggested
    filename. Same shape contract as /render-pdf — no AI call,
    deterministic, ~100ms server-side.

    Designers paste the resulting sheet's SKU + qty columns directly
    into supplier ordering portals, so the format prioritizes a clean
    section grouping with per-section subtotals over decorative
    styling.
    """
    try:
        body = request.get_json(silent=True) or {}
        bom = body.get('bom')
        if not isinstance(bom, dict) or not bom.get('line_items'):
            return jsonify({
                "success": False,
                "data": None,
                "error": "Request body must be {\"bom\": <BomResponse with line_items>}.",
            }), 400

        xlsx_bytes = render_bom_xlsx(bom)
        filename = f"{(bom.get('job_id') or 'bom').replace('/', '-')}.xlsx"

        return Response(
            xlsx_bytes,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        logger.error("render_xls failed: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "data": None,
            "error": "XLSX render failed. Please try again.",
        }), 500


# ===============================
# POST — Rules-only preview (no AI, no profile pricing)
# ===============================

@bom_bp.route('/rules-preview', methods=['POST'])
def rules_preview():
    """
    Run the deterministic materials_rules engine against a parsed
    design_data and return only the line items the rules engine would
    emit. No Anthropic call, no contractor profile, no totals — this
    is the catalog-driven baseline that every BOM /generate response
    will eventually layer on top of.

    Request body:
        { "design_data": <parsed RUP envelope>,
          "output_mode": "full"  (optional, default "full") }

    Response:
        {
          "success": true,
          "data": {
            "scope":   {<scope flags>},      # diagnostic
            "line_items": [...],
            "item_count": N,
            "totals": {"total_cost": <float>}
          }
        }

    Designed for designers + Richard's team to inspect what the rules
    layer alone produces against any RUP — see docs/eval-2026-04-29
    for the gap analysis this endpoint is meant to close.
    """
    try:
        body = request.get_json(silent=True) or {}
        design_data = body.get('design_data')
        if not isinstance(design_data, dict):
            return jsonify({
                "success": False,
                "data": None,
                "error": "Request body must include 'design_data' as an object.",
            }), 400

        output_mode = body.get('output_mode') or 'full'

        scope = compute_scope(design_data)
        lines = generate_rule_lines(design_data, output_mode=output_mode)
        total_cost = round(sum(float(l.get("total_cost") or 0) for l in lines), 2)

        return jsonify({
            "success": True,
            "data": {
                "scope": summarize_scope(scope),
                "line_items": lines,
                "item_count": len(lines),
                "totals": {"total_cost": total_cost},
                "output_mode": output_mode,
            },
            "error": None,
        }), 200

    except Exception as e:  # noqa: BLE001
        logger.error("rules_preview failed: %s", e, exc_info=True)
        return jsonify({
            "success": False,
            "data": None,
            "error": "Rules-preview failed. Please try again.",
        }), 500


# ===============================
# POST — Inspect .rup binary blocks (Day-3 diagnostic)
# ===============================
#
# Surfaces the ZEQUIP ↔ ECDUCTSYS row-by-row pairing so we can match
# what's in a Wrightsoft project against what the binary parser sees
# — built specifically to slot Richard's incoming McGinty screenshot
# against the 28 ZEQUIP records. Tester uploads a .rup, gets back a
# table-shaped JSON ready for SPA display.

@bom_bp.route('/rup-inspect', methods=['POST'])
def rup_inspect():
    """Diagnostic: decode the equipment-related binary blocks in a
    .rup upload and return them as a table. Powers the Run-Inspect
    SPA page used to cross-reference Wrightsoft UI screenshots
    against our parser's view of the same project.

    Response:
        {
          "success": true,
          "data": {
            "source_file":  "McGinty Residence.rup",
            "summary": {
              "zequip_total":     28,
              "ecductsys_total":  28,
              "labeled_count":    4,
              "label_distribution": {"FURNACE 1": 4}
            },
            "rows": [
              {"index": 0, "zequip_record_id": 2046,
               "ecductsys_label": "FURNACE 1"},
              ...
            ]
          }
        }
    """
    import struct
    from collections import Counter
    from utils.rup_parser import _block_bodies, _utf16_strings_in_block

    try:
        file_bytes = b''
        source_name = 'uploaded.rup'
        if 'file' in request.files:
            upload = request.files['file']
            source_name = upload.filename or source_name
            file_bytes = upload.read()
        elif request.data:
            file_bytes = request.data
            if request.headers.get('X-Filename'):
                source_name = request.headers['X-Filename']

        if not file_bytes:
            return jsonify({
                "success": False, "data": None,
                "error": "No .rup file provided.",
            }), 400
        if len(file_bytes) > MAX_RUP_BYTES:
            return jsonify({
                "success": False, "data": None,
                "error": f".rup file exceeds {MAX_RUP_BYTES // 1024 // 1024} MB limit.",
            }), 413
        if not file_bytes.startswith(b'.\x00W\x00S'):
            return jsonify({
                "success": False, "data": None,
                "error": "File does not look like a Wrightsoft .rup project file.",
            }), 400

        # Decode ZEQUIP records → list of {index, record_id}
        zequip_bodies = _block_bodies(file_bytes, "ZEQUIP")
        zequip_meta = []
        for i, body in enumerate(zequip_bodies):
            try:
                rid = struct.unpack_from("<I", body, 4)[0] if len(body) >= 8 else None
            except Exception:
                rid = None
            zequip_meta.append({"index": i, "record_id": rid})

        # Decode ECDUCTSYS labels (first UTF-16 string per record, or None)
        ec_bodies = _block_bodies(file_bytes, "ECDUCTSYS")
        ec_labels = []
        for body in ec_bodies:
            strs = _utf16_strings_in_block(body, min_len=3)
            unique = []
            for s in strs:
                if s not in unique:
                    unique.append(s)
            ec_labels.append(unique[0] if unique else None)

        # Pair by index (1:1 in every project sampled — Easy/Avg/Edge/McGinty)
        rows = []
        for i, zm in enumerate(zequip_meta):
            label = ec_labels[i] if i < len(ec_labels) else None
            rows.append({
                "index":            i,
                "zequip_record_id": zm["record_id"],
                "ecductsys_label":  label,
            })

        label_distribution = Counter(l for l in ec_labels if l)

        # Day-10 — Wrightsoft-catalog cross-reference. Verifies whether
        # the project's BOM is reachable from the .rup binary alone, or
        # whether the deterministic pipeline needs Wrightsoft's own BOM
        # export. Empirically this is always "0/3014 found" because
        # Wrightsoft computes the BOM at print/report time rather than
        # storing it in the project file — but the explicit signal is
        # the honest answer to "why aren't we just reading the BOM out
        # of the file?" (Tom's Day-9 question).
        catalog_xref = _catalog_xref_for_binary(file_bytes)

        return jsonify({
            "success": True,
            "data": {
                "source_file":      source_name,
                "summary": {
                    "zequip_total":       len(zequip_bodies),
                    "ecductsys_total":    len(ec_bodies),
                    "labeled_count":      sum(1 for l in ec_labels if l),
                    "label_distribution": dict(label_distribution),
                },
                "rows": rows,
                # Deterministic-pipeline signal. False on every Wrightsoft
                # .rup we've sampled — the BOM is derived at output time,
                # not stored.
                "catalog_xref": catalog_xref,
            },
            "error": None,
        }), 200

    except Exception as e:  # noqa: BLE001
        logger.error("rup_inspect failed: %s", e, exc_info=True)
        return jsonify({
            "success": False, "data": None,
            "error": "RUP inspection failed.",
        }), 500


# ===============================
# POST — Build BOM from Wrightsoft's own generic-parts export
# ===============================
#
# Day-9 endpoint addressing Tom's "use the produced information"
# question. Two input modes:
#
#   a) multipart upload of a Wrightsoft BOM export (.csv / .xls /
#      .xlsx) — parsed via parse_wrightsoft_bom_rows
#   b) JSON body {"client_id": "...",
#                 "job_id": "...",
#                 "lines": [{"generic_id": "PEX0750", "quantity": 100,
#                            "description": "..."}, ...]} — for
#      automated harnesses or curl smoke tests
#
# Either way, each line goes through wrightsoft_catalog's mapping
# table (mapped_parts.csv) to translate generic_id → contractor's
# manufacturer SKU, then through the same pricing/markup helpers
# /generate uses. Output matches /generate's response shape so the
# downstream PDF + Run History + comparator pipeline works unchanged.

@bom_bp.route('/from-wrightsoft', methods=['POST'])
def bom_from_wrightsoft():
    """Build a BOM from Wrightsoft's own generic-parts output.

    Multipart: 'file' field with Wrightsoft CSV/XLS export +
               'client_id' + 'job_id' form fields.
    JSON:      {"client_id": str, "job_id": str,
                "lines": [{"generic_id": str, "quantity": float,
                           "description": str?}],
                "output_mode": str?}
    """
    try:
        # ── Multipart upload branch ───────────────────────────────────
        source_pipeline_override = None  # set to "wrightsoft_rup" for .rup
        _rup_extras = {}  # Day-21 — structural extras snapshotted from
                          # line[0] before build_bom_from_wrightsoft_lines
                          # strips unknown keys. Populated in the .rup
                          # branch below; stays {} for .xls uploads.
        if 'file' in request.files:
            upload = request.files['file']
            file_bytes = upload.read()
            if not file_bytes:
                return jsonify({"success": False, "data": None,
                                "error": "Empty file upload"}), 400
            client_id = (request.form.get('client_id') or '').strip()
            job_id    = (request.form.get('job_id') or '').strip()
            output_mode = (request.form.get('output_mode') or 'full').strip() or 'full'
            fname = (upload.filename or "").lower()
            # Day-16 — accept .rup directly (Tom's preferred upload).
            # The .rup binary is the underlying design file; we extract
            # equipment + duct + register + fitting counts via the same
            # parser that powers /diagnostics/rup-inspect and shape them
            # into the line-item contract this endpoint expects.
            if fname.endswith(".rup") or _looks_like_rup(file_bytes):
                # Day-23 smoke-suite finding: junk bytes named *.rup
                # sailed through to an empty 200 BOM. Same header
                # sanity check /parse-rup uses.
                if not file_bytes.startswith(b'.\x00W\x00S'):
                    return jsonify({
                        "success": False, "data": None,
                        "error": "File does not look like a Wrightsoft "
                                 ".rup project file.",
                    }), 400
                try:
                    from services.bom_from_rup import build_lines_from_rup
                    # Day-22 — Rheia register-driven takeoff fires for
                    # contractors whose profile supplier is Rheia (the
                    # Rheia section is absent from the .rup binary and
                    # must be derived; see bom_from_rup for the rules).
                    _rheia = False
                    try:
                        _p = get_profile_by_id(client_id) if client_id else None
                        _sup = ""
                        if isinstance(_p, dict):
                            # Firestore doc nests it: supplier.supplier_name
                            _sup = ((_p.get("supplier") or {}).get("supplier_name")
                                    or _p.get("supplierName")
                                    or _p.get("supplier_name")
                                    or "")
                        elif _p is not None:
                            _sup = getattr(_p, "supplier_name", "") or ""
                        _rheia = "rheia" in str(_sup).lower()
                        logger.info("rup rheia-gate: client=%s supplier=%r -> %s",
                                    client_id, _sup, _rheia)
                    except Exception as _exc:  # noqa: BLE001 — never block the BOM
                        logger.warning("rup rheia-gate failed for %s: %s",
                                       client_id, _exc)
                        _rheia = False
                    lines = build_lines_from_rup(file_bytes,
                                                 source_name=upload.filename or "",
                                                 rheia_takeoff=_rheia)
                    source_pipeline_override = "wrightsoft_rup"
                    # Day-16 follow-up — detect ducts-only files at the
                    # route level so the hint survives the line-item
                    # builder (which strips unknown keys).
                    if not any(li.get("section_hint") == "Equipment"
                               for li in lines):
                        _rup_ducts_only_hint = True
                    else:
                        _rup_ducts_only_hint = False
                    # Day-21 — bom_from_rup attaches structural extras
                    # (rup_balduct per-register CFMs from Increment 2,
                    # rup_unbuilt_hint from §1.4, rup_duct_geometry
                    # placeholder from K scaffold) to line[0]. Snapshot
                    # them here before build_bom_from_wrightsoft_lines
                    # transforms each line and strips unknown keys.
                    _rup_extras = {}
                    if lines:
                        for key in ("rup_balduct", "rup_unbuilt_hint",
                                     "rup_duct_geometry", "rup_file_type_hint"):
                            val = lines[0].get(key)
                            if val is not None:
                                _rup_extras[key] = val
                except Exception as exc:  # noqa: BLE001
                    logger.error("rup parse failed: %s", exc, exc_info=True)
                    return jsonify({"success": False, "data": None,
                                    "error": f"Could not parse .rup file: {exc}"}), 400
            else:
                try:
                    lines = parse_wrightsoft_bom_rows(
                        file_bytes, filename=upload.filename or "",
                    )
                except ValueError as exc:
                    return jsonify({"success": False, "data": None,
                                    "error": str(exc)}), 400
                # Day-23 smoke-suite finding: unrecognized bytes fell
                # through to the xls parser, yielded zero rows, and
                # returned a confusing empty 200 BOM. Reject instead.
                if not lines:
                    return jsonify({
                        "success": False, "data": None,
                        "error": "File is neither a Wrightsoft .rup nor "
                                 "a recognizable BOM export — no line "
                                 "items found.",
                    }), 400
                _rup_ducts_only_hint = False
                _rup_extras = {}

        else:
            # ── JSON body branch ──────────────────────────────────────
            body = request.get_json(silent=True) or {}
            client_id = (body.get('client_id') or '').strip()
            job_id    = (body.get('job_id') or '').strip()
            output_mode = (body.get('output_mode') or 'full').strip() or 'full'
            lines = body.get('lines') or []
            if not isinstance(lines, list):
                return jsonify({"success": False, "data": None,
                                "error": "'lines' must be a list"}), 400

        # Day-16 follow-up — optional second .rup file co-uploaded
        # alongside the .xls/.csv to add room/duct-system context the
        # .xls export strips. Surfaced as rup_context on the response
        # so the SPA can render a "Rooms served" chip strip without
        # touching the per-line items.
        rup_context = None
        rup_equipment_lines: list = []  # Day-17 — merged into `lines` below
        rup_upload = request.files.get('rup_context') if request.files else None
        if rup_upload and source_pipeline_override != "wrightsoft_rup":
            try:
                rup_bytes = rup_upload.read()
                if rup_bytes and (
                    (rup_upload.filename or "").lower().endswith(".rup")
                    or _looks_like_rup(rup_bytes)
                ):
                    from utils.rup_parser import parse_rup_bytes
                    from services.bom_from_rup import _MFR_NAME_TO_SRC
                    design = parse_rup_bytes(
                        rup_bytes, source_name=rup_upload.filename or "")
                    # Day-17 — Wrightsoft's BOM.xls export doesn't carry
                    # equipment (AHU/condenser/furnace/ERV). When the
                    # user attaches the source .rup, the EQUIP block
                    # has them. Convert each into the same lines-list
                    # shape build_bom_from_wrightsoft_lines consumes,
                    # tagged section_hint=Equipment so the rules engine
                    # places them in the Equipment section. Identical
                    # construction to bom_from_rup.build_bom_from_rup
                    # so AHRI / DFUnit lookups fire the same way.
                    for unit in design.get("equipment", []) or []:
                        model = (unit.get("model") or "").strip()
                        if not model:
                            continue
                        mfr_name = unit.get("manufacturer") or ""
                        src = (
                            _MFR_NAME_TO_SRC.get(mfr_name)
                            or _MFR_NAME_TO_SRC.get(mfr_name.title())
                            or "WSF"
                        )
                        qty = float(unit.get("count") or 1)
                        type_label = (unit.get("type") or "equipment").replace("_", " ").title()
                        rup_equipment_lines.append({
                            "generic_id":   model,
                            "quantity":     qty,
                            "description":  f"{type_label} — {mfr_name} {model}".strip(" —"),
                            "src":          src,
                            "section_hint": "Equipment",
                            "unit":         "EA",
                        })
                    # Extract clean room list — prefer the BALDUCT-derived
                    # rooms parsed into raw_rup_context (Day-14), fall
                    # back to the text-regex rooms collection.
                    rooms: list[str] = []
                    raw = design.get("raw_rup_context") or ""
                    import re as _re
                    in_rooms = False
                    for raw_line in raw.splitlines():
                        if raw_line.startswith("=== ROOMS"):
                            in_rooms = True
                            continue
                        if in_rooms:
                            if raw_line.startswith("==="):
                                break
                            name = raw_line.strip()
                            if name and not _re.fullmatch(r"[a-z]{1,3}\d{1,3}", name):
                                rooms.append(name)
                    if not rooms:
                        rooms = [r.get("name", "") for r in (design.get("rooms") or [])
                                 if r.get("name")]
                    duct = design.get("duct_summary") or {}
                    rup_context = {
                        "filename":           rup_upload.filename or "",
                        "rooms":              rooms[:200],
                        "room_count":         len(rooms),
                        "duct_type_counts":   duct.get("type_counts") or {},
                        "round_diameters":    duct.get("round_diameters_present") or [],
                        "rect_sizes":         duct.get("rect_sizes_present") or [],
                        "equipment_count":    len(design.get("equipment") or []),
                    }
            except Exception as exc:  # noqa: BLE001 — best-effort enrichment
                logger.warning("rup_context parse skipped: %s", exc)
                rup_context = None

        if not client_id or not job_id:
            return jsonify({"success": False, "data": None,
                            "error": "client_id and job_id are required"}), 400

        # ── Resolve contractor profile ────────────────────────────────
        profile_data = get_profile_by_id(client_id)
        if not profile_data:
            return jsonify({"success": False, "data": None,
                            "error": f"No profile found for client_id '{client_id}'"}), 404
        profile = ClientProfile.from_dict(profile_data)

        # ── Build BOM through the mapping pipeline ────────────────────
        # Day-17 — if a .rup was attached, prepend its equipment rows
        # so the Equipment section populates on what would otherwise
        # be a duct-only BOM (Wrightsoft's BOM.xls excludes equipment).
        # Day-22 — dedupe by generic_id: the route-level empirical
        # equipment (CERIData design block) and bom_from_rup's
        # structural EQUIP lines describe the same units, which
        # emitted each model twice on .rup uploads (HKTSD05X1 ×2 on
        # the T333 smoke draft). First occurrence wins — the route's
        # empirical rows lead and carry the richer description.
        merged_lines = (rup_equipment_lines + lines) if rup_equipment_lines else lines
        if source_pipeline_override == "wrightsoft_rup":
            # Unconditional on the .rup path: duplicates also arise
            # INSIDE build_lines_from_rup (design-block vs structural
            # EQUIP extraction), not only from the route-level merge.
            seen_ids: set = set()
            deduped: list = []
            for li in merged_lines:
                gid = (li.get("generic_id") or "").strip().upper()
                if gid and li.get("section_hint") == "Equipment":
                    if gid in seen_ids:
                        continue
                    seen_ids.add(gid)
                deduped.append(li)
            merged_lines = deduped
        bom = build_bom_from_wrightsoft_lines(
            lines=merged_lines,
            profile=profile,
            job_id=job_id,
            output_mode=output_mode,
        )
        if rup_equipment_lines:
            bom["rup_equipment_merged"] = len(rup_equipment_lines)

        # ── Persist as a bom_run so the BOM shows up in Run History
        # next to /generate output. Best-effort: a DB failure must
        # NOT swallow the successful BOM result — same contract as
        # services.bom_service.generate.
        try:
            from models import BomRun
            from extensions import db
            from flask import has_request_context
            created_by_email = None
            if has_request_context():
                user = getattr(g, "current_user", None)
                if user is not None:
                    created_by_email = getattr(user, "email", None)
            run = BomRun.record(
                client_id=client_id,
                job_id=job_id,
                output_mode=output_mode,
                parsed_design_data={
                    "source_pipeline": source_pipeline_override or "wrightsoft_bom",
                    "wrightsoft_lines": lines,
                },
                generated_bom=bom,
                created_by_email=created_by_email,
            )
            db.session.commit()
            bom["run_id"] = run.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wrightsoft-BOM persistence failed for job %s — %s",
                           job_id, exc)

        # Day-16 — surface that this BOM came from a .rup parse path
        # so the SPA can show a "best-effort .rup parse — for canonical
        # BOM upload the Wrightsoft .xls export" notice.
        if source_pipeline_override:
            bom["source_pipeline"] = source_pipeline_override
            bom["rup_best_effort_notice"] = (
                "BOM built from .rup binary (best-effort). For the canonical "
                "rollup, upload the Wrightsoft BOM export (.xls / .csv) "
                "produced by File → Bill of Materials in Wrightsoft."
            )
            # Day-21 — promote structural extras snapshotted from
            # line[0] before the line builder stripped them. Feeds the
            # SPA's Duct Cuts card (rup_balduct), the un-built hint
            # banner (rup_unbuilt_hint), and the future geometry
            # payload (rup_duct_geometry, once K's spec drops).
            for _k, _v in (_rup_extras or {}).items():
                bom.setdefault(_k, _v)
            # Day-16 follow-up — set the file-type hint when no
            # equipment lines came out of the parser (Manual D / ADU
            # Ducts files). Computed at route level (not inside
            # bom_from_rup) because build_bom_from_wrightsoft_lines
            # strips unknown keys from line dicts.
            if _rup_ducts_only_hint:
                bom["rup_file_type_hint"] = (
                    "no equipment found — this looks like a Manual D "
                    "or ducts-only file. For the full residential BOM "
                    "with equipment, upload a Manual J file."
                )

        # Day-16 follow-up — attach optional .rup-derived context to
        # the .xls/.csv response so the SPA can show "Rooms served"
        # + duct system shape without changing per-line data.
        if rup_context:
            bom["rup_context"] = rup_context

        return jsonify({"success": True, "data": bom, "error": None}), 200

    except Exception as e:
        logger.error("bom_from_wrightsoft failed: %s", e, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to build BOM from Wrightsoft input."}), 500


# ===============================
# POST — Wrightsoft BOM v2: bundle-driven path (Day-19)
# ===============================
#
# The Windows extraction station runs RightSuite's COM interface
# (`IRRXDocument.ValidateProject`) and produces a per-zone equipment
# schedule as JSON. This endpoint accepts that JSON alongside the
# Wrightsoft `.xls` line-items export and merges the COM-derived
# equipment into the .xls-driven BOM. Fuller / more accurate than
# the .rup byte-parsing path — Wrightsoft names manufacturers and
# specs directly (no regex prefix table, no empirical byte scanning,
# no AHRI round-trip for capacity/SEER/HSPF/AFUE).
#
# Multipart:
#   file             — Wrightsoft BOM export (.xls / .csv), required
#   equipment_bundle — ValidateProject JSON, required
#   client_id        — string, required
#   job_id           — string, required
#   output_mode      — full | materials_only | ... (default: full)
#   project_name     — string, optional; select one project when the
#                      bundle contains multiple. When omitted and the
#                      bundle has exactly one project, that one is used.
#
# Response shape identical to /from-wrightsoft with extra top-level
# markers so the SPA can render the "v2" affordances:
#   data.source_pipeline = "wrightsoft_bundle_v2"
#   data.com_equipment_count = <int>  — how many equipment lines
#                                       came from ValidateProject
#   data.com_project_name = <str>     — which project was selected

@bom_bp.route('/from-wrightsoft-bundle', methods=['POST'])
def bom_from_wrightsoft_bundle():
    try:
        # ── Required inputs ──────────────────────────────────────
        if 'file' not in request.files:
            return jsonify({"success": False, "data": None,
                            "error": "Missing 'file' (Wrightsoft .xls export)"}), 400
        if 'equipment_bundle' not in request.files:
            return jsonify({"success": False, "data": None,
                            "error": "Missing 'equipment_bundle' (ValidateProject JSON)"}), 400

        xls_upload = request.files['file']
        bundle_upload = request.files['equipment_bundle']
        xls_bytes = xls_upload.read()
        bundle_bytes = bundle_upload.read()

        if not xls_bytes:
            return jsonify({"success": False, "data": None,
                            "error": "Empty Wrightsoft .xls upload"}), 400
        if not bundle_bytes:
            return jsonify({"success": False, "data": None,
                            "error": "Empty equipment_bundle upload"}), 400

        client_id   = (request.form.get('client_id') or '').strip()
        job_id      = (request.form.get('job_id') or '').strip()
        output_mode = (request.form.get('output_mode') or 'full').strip() or 'full'
        project_name = (request.form.get('project_name') or '').strip() or None

        if not client_id or not job_id:
            return jsonify({"success": False, "data": None,
                            "error": "client_id and job_id are required"}), 400

        # ── Parse the equipment bundle ───────────────────────────
        import json as _json
        try:
            bundle = _json.loads(bundle_bytes.decode('utf-8-sig'))
        except Exception as exc:
            return jsonify({"success": False, "data": None,
                            "error": f"equipment_bundle is not valid JSON: {exc}"}), 400

        from services.wrightsoft_bundle_adapter import parse_validateproject_bundle
        try:
            equipment_lines = parse_validateproject_bundle(
                bundle, project_name=project_name)
        except ValueError as exc:
            return jsonify({"success": False, "data": None,
                            "error": str(exc)}), 400

        resolved_project = project_name or (
            list(bundle.keys())[0] if isinstance(bundle, dict) and len(bundle) == 1
            else project_name
        )

        # ── Parse the .xls line items ────────────────────────────
        try:
            xls_lines = parse_wrightsoft_bom_rows(
                xls_bytes,
                filename=xls_upload.filename or "",
            )
        except Exception as exc:
            logger.error("wrightsoft xls parse failed: %s", exc, exc_info=True)
            return jsonify({"success": False, "data": None,
                            "error": f"Could not parse Wrightsoft .xls: {exc}"}), 400

        # ── Prepend equipment lines to the xls lines ─────────────
        # Same shape as build_bom_from_wrightsoft_lines expects; the
        # equipment lines flow through the SKU translation / pricing
        # pipeline identically to xls-derived rows.
        merged_lines = equipment_lines + xls_lines

        # ── Resolve profile + build ──────────────────────────────
        profile_data = get_profile_by_id(client_id)
        if not profile_data:
            return jsonify({"success": False, "data": None,
                            "error": f"No profile found for client_id '{client_id}'"}), 404
        profile = ClientProfile.from_dict(profile_data)

        bom = build_bom_from_wrightsoft_lines(
            lines=merged_lines,
            profile=profile,
            job_id=job_id,
            output_mode=output_mode,
        )

        # ── Persist as bom_run so ?run=<id> works and Run History
        # picks it up. Same best-effort contract as /from-wrightsoft.
        try:
            from models import BomRun
            from extensions import db
            from flask import has_request_context
            created_by_email = None
            if has_request_context():
                user = getattr(g, "current_user", None)
                if user is not None:
                    created_by_email = getattr(user, "email", None)
            run = BomRun.record(
                client_id=client_id,
                job_id=job_id,
                output_mode=output_mode,
                parsed_design_data={
                    "source_pipeline":  "wrightsoft_bundle_v2",
                    "wrightsoft_lines": merged_lines,
                    "com_project_name": resolved_project,
                },
                generated_bom=bom,
                created_by_email=created_by_email,
            )
            db.session.commit()
            bom["run_id"] = run.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wrightsoft-bundle persistence failed for job %s — %s",
                           job_id, exc)

        # ── v2 markers so the SPA can render bundle-specific UI ──
        bom["source_pipeline"] = "wrightsoft_bundle_v2"
        bom["com_equipment_count"] = len(equipment_lines)
        bom["com_project_name"] = resolved_project

        return jsonify({"success": True, "data": bom, "error": None}), 200

    except Exception as e:
        logger.error("bom_from_wrightsoft_bundle failed: %s", e, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to build BOM from Wrightsoft bundle."}), 500


# ===============================
# GET — Catalog coverage diagnostic (Day-11)
# ===============================
#
# Returns the coverage report from services.wrightsoft_catalog so the
# SPA can render a Catalog Coverage page. Lets Richard's team see at
# a glance which Wrightsoft categories have the worst supplier-mapping
# coverage — drives the prioritization of what to add to
# mapped_parts.csv next.

@bom_bp.route('/catalog-coverage', methods=['GET'])
def catalog_coverage():
    """Per-category + per-supplier coverage of Tom's bundled
    mapped_parts.csv. No filters; the report itself is cheap (<10ms
    on ~3,000 generics) and the SPA does any client-side filtering."""
    try:
        from services.wrightsoft_catalog import coverage_report
        report = coverage_report()
        return jsonify({"success": True, "data": report, "error": None}), 200
    except Exception as exc:
        logger.error("catalog_coverage failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to build catalog coverage report"}), 500


# ===============================
# GET — DFUnit equipment library browser (Day-12)
# ===============================
#
# Browse / filter the 963-row DFUnit equipment catalog Tom bundled in
# his Wrightsoft handoff (ductless heads, mini-splits, heat pumps).
# Used by the SPA DFUnit Explorer page so designers can poke through
# the equipment library without having to download the CSV.
#
# Read-only — DFUnit.csv ships with the app, not user-editable.

@bom_bp.route('/dfunit', methods=['GET'])
def dfunit_browse():
    """List DFUnit rows with optional filters.

    Query params:
        manufacturer   4-char code (CARR, MITS, DAIK, …) — exact
        sys_type       'H' (heat pump) or 'A' (AC) — exact
        unit_type      OS / IW / IC / OM / ID / IA / IF / IU — exact
        q              free-text — substring match on Model / Series
        min_clg_btu    cooling capacity floor (BTU)
        max_clg_btu    cooling capacity ceiling (BTU)
        min_htg_btu    heating capacity floor (BTU)
        max_htg_btu    heating capacity ceiling (BTU)
        limit          int, default 200, max 1000

    Returns: {
        "items":    [<projected DFUnit spec dict>],
        "total":    int,            # matched before limit
        "returned": int,            # length of items
        "facets":   {               # for SPA filter dropdowns
            "manufacturers": [str],
            "unit_types":    [str],
            "sys_types":     [str],
        }
    }
    """
    try:
        from services.wrightsoft_catalog import load_dfunit, dfunit_line_spec

        rows = load_dfunit()

        manufacturer = (request.args.get('manufacturer') or '').strip().upper()
        sys_type     = (request.args.get('sys_type')     or '').strip()
        unit_type    = (request.args.get('unit_type')    or '').strip()
        q            = (request.args.get('q')            or '').strip().lower()

        def _opt_float(name: str):
            v = request.args.get(name)
            if v in (None, ''):
                return None
            try:
                return float(v)
            except ValueError:
                return None

        min_clg = _opt_float('min_clg_btu')
        max_clg = _opt_float('max_clg_btu')
        min_htg = _opt_float('min_htg_btu')
        max_htg = _opt_float('max_htg_btu')

        try:
            limit = int(request.args.get('limit') or '200')
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 1000))

        def _row_float(r, k):
            try:
                v = r.get(k)
                return float(v) if v not in (None, '') else None
            except (TypeError, ValueError):
                return None

        def _keep(r):
            if manufacturer and (r.get('Manufacturer') or '').upper() != manufacturer:
                return False
            if sys_type and (r.get('SysType') or '') != sys_type:
                return False
            if unit_type and (r.get('UnitType') or '') != unit_type:
                return False
            if q:
                hay = ' '.join([
                    str(r.get('Model') or ''),
                    str(r.get('Series') or ''),
                ]).lower()
                if q not in hay:
                    return False
            clg = _row_float(r, 'ClgCap')
            htg = _row_float(r, 'HtgCap')
            if min_clg is not None and (clg is None or clg < min_clg):
                return False
            if max_clg is not None and (clg is None or clg > max_clg):
                return False
            if min_htg is not None and (htg is None or htg < min_htg):
                return False
            if max_htg is not None and (htg is None or htg > max_htg):
                return False
            return True

        matched = [r for r in rows if _keep(r)]
        total = len(matched)
        items = [
            # Include the model + series alongside the projected spec
            # so the SPA table can render them in their own columns.
            {
                **dfunit_line_spec(r),
                "series": r.get("Series") or None,
            }
            for r in matched[:limit]
        ]

        # Facets — derived from the full (unfiltered) catalog so the
        # SPA's dropdowns are stable regardless of current filter state.
        manufacturers = sorted({(r.get('Manufacturer') or '').strip()
                                for r in rows if (r.get('Manufacturer') or '').strip()})
        unit_types    = sorted({(r.get('UnitType') or '').strip()
                                for r in rows if (r.get('UnitType') or '').strip()})
        sys_types     = sorted({(r.get('SysType') or '').strip()
                                for r in rows if (r.get('SysType') or '').strip()})

        return jsonify({
            "success": True,
            "data": {
                "items":    items,
                "total":    total,
                "returned": len(items),
                "facets": {
                    "manufacturers": manufacturers,
                    "unit_types":    unit_types,
                    "sys_types":     sys_types,
                },
            },
            "error": None,
        }), 200
    except Exception as exc:
        logger.error("dfunit_browse failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to load DFUnit catalog"}), 500


# ===============================
# GET — Wrightsoft mapping browser (Day-12)
# ===============================
#
# Search mapped_parts.csv directly. Lets reviewers verify what the
# deterministic pipeline would emit for a given generic_id, or which
# generics a particular supplier covers, without having to run a
# full BOM through /from-wrightsoft.

@bom_bp.route('/mappings', methods=['GET'])
def mappings_browse():
    """List mapped_parts.csv rows with optional filters.

    Query params:
        generic_id   exact match (case-insensitive)
        supplier     4-char source code (WSF, CARR, …) — exact
        q            free-text — substring on generic_id / description /
                     manufacturer_partnum / category
        category     exact Wrightsoft category code (DSRND, RHALL, …)
        limit        int, default 200, max 2000

    Returns: { "items": [...], "total": int, "returned": int,
               "facets": {"suppliers": [str], "categories": [str]} }
    """
    try:
        from services.wrightsoft_catalog import (
            load_mapped_parts, load_generic_parts, category_for_generic,
        )

        rows = load_mapped_parts()
        generics = load_generic_parts()

        generic_id = (request.args.get('generic_id') or '').strip().upper()
        supplier   = (request.args.get('supplier')   or '').strip().upper()
        category   = (request.args.get('category')   or '').strip().upper()
        q          = (request.args.get('q')          or '').strip().lower()

        try:
            limit = int(request.args.get('limit') or '200')
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 2000))

        def _keep(r):
            # mapped_parts.csv column is `generic_item`, not generic_id.
            gid_raw = r.get('generic_item') or ''
            gid = gid_raw.upper()
            if generic_id and gid != generic_id:
                return False
            if supplier and (r.get('preferred_source') or '').upper() != supplier:
                return False
            if category:
                cat = (category_for_generic(gid_raw) or '').upper()
                if cat != category:
                    return False
            if q:
                hay = ' '.join([
                    gid,
                    str(r.get('manufacturer_partnum') or ''),
                    str(generics.get(gid_raw, {}).get('description') or ''),
                ]).lower()
                if q not in hay:
                    return False
            return True

        matched = [r for r in rows if _keep(r)]
        total = len(matched)

        items = []
        for r in matched[:limit]:
            gid_raw = r.get('generic_item') or ''
            items.append({
                "generic_id":           gid_raw,
                "description":          generics.get(gid_raw, {}).get('description'),
                "category":             category_for_generic(gid_raw),
                "supplier":             r.get('preferred_source'),
                "manufacturer_partnum": r.get('manufacturer_partnum'),
                "quantity_variant":     r.get('quantity_variant'),
            })

        # Facets derived from the full catalog so dropdowns are stable.
        suppliers = sorted({(r.get('preferred_source') or '').strip()
                            for r in rows if (r.get('preferred_source') or '').strip()})
        categories = sorted({
            (category_for_generic(r.get('generic_item') or '') or '').strip()
            for r in rows
        } - {''})

        return jsonify({
            "success": True,
            "data": {
                "items":    items,
                "total":    total,
                "returned": len(items),
                "facets": {
                    "suppliers":  suppliers,
                    "categories": categories,
                },
            },
            "error": None,
        }), 200
    except Exception as exc:
        logger.error("mappings_browse failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to load mappings"}), 500
