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
        if 'file' in request.files:
            upload = request.files['file']
            file_bytes = upload.read()
            if not file_bytes:
                return jsonify({"success": False, "data": None,
                                "error": "Empty file upload"}), 400
            client_id = (request.form.get('client_id') or '').strip()
            job_id    = (request.form.get('job_id') or '').strip()
            output_mode = (request.form.get('output_mode') or 'full').strip() or 'full'
            try:
                lines = parse_wrightsoft_bom_rows(
                    file_bytes, filename=upload.filename or "",
                )
            except ValueError as exc:
                return jsonify({"success": False, "data": None,
                                "error": str(exc)}), 400
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
        bom = build_bom_from_wrightsoft_lines(
            lines=lines,
            profile=profile,
            job_id=job_id,
            output_mode=output_mode,
        )

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
                    "source_pipeline": "wrightsoft_bom",
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

        return jsonify({"success": True, "data": bom, "error": None}), 200

    except Exception as e:
        logger.error("bom_from_wrightsoft failed: %s", e, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to build BOM from Wrightsoft input."}), 500
