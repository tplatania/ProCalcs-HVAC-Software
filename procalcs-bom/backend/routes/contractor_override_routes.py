"""
contractor_override_routes.py — REST surface for the Day-13
per-contractor manual correction table.

Mounted under /api/v1/contractor-overrides. Shared-secret auth same
as the rest of /api/v1. The SPA's inline-edit drawer on the Wrightsoft
BOM page hits POST to upsert a row; the overrides list page reads
GET to render Richard's running ledger of corrections per contractor.

Endpoints:
    GET    /api/v1/contractor-overrides?client_id=…  → list, newest-first
    POST   /api/v1/contractor-overrides              → upsert one row
    DELETE /api/v1/contractor-overrides/<id>         → drop a single override

All responses follow the {success, data, error} envelope the rest of
the BOM API uses so the SPA hooks unwrap uniformly.
"""

import logging

from flask import Blueprint, jsonify, request

from extensions import db
from models.contractor_override import ContractorOverride


logger = logging.getLogger("procalcs_bom")
contractor_override_bp = Blueprint("contractor_override", __name__)


def _actor() -> str | None:
    """Identify the requesting user for the audit trail. The SPA's
    upstreamHeaders helper forwards X-Actor-Email from the authenticated
    session; falls back to X-Client-Id when present."""
    return (
        request.headers.get("X-Actor-Email")
        or request.headers.get("X-Client-Id")
    )


# ─── GET — list ────────────────────────────────────────────────────

@contractor_override_bp.route("", methods=["GET"])
@contractor_override_bp.route("/", methods=["GET"])
def list_overrides():
    """Return every override for a contractor, newest-first.

    Required query: client_id.
    """
    client_id = (request.args.get("client_id") or "").strip()
    if not client_id:
        return jsonify({
            "success": False,
            "data": None,
            "error": "client_id query parameter is required",
        }), 400
    try:
        rows = ContractorOverride.list_for_contractor(client_id)
        return jsonify({
            "success": True,
            "data": {
                "client_id": client_id,
                "items":     [r.to_dict() for r in rows],
                "count":     len(rows),
            },
            "error": None,
        }), 200
    except Exception as exc:  # noqa: BLE001
        logger.error("list_overrides failed: %s", exc, exc_info=True)
        return jsonify({
            "success": False, "data": None,
            "error": "Failed to load contractor overrides",
        }), 500


# ─── POST — upsert ─────────────────────────────────────────────────

@contractor_override_bp.route("", methods=["POST"])
@contractor_override_bp.route("/", methods=["POST"])
def upsert_override():
    """Upsert one (client_id, supplier, sku) → corrections row.

    Body JSON:
        {
          "client_id":          str   (required)
          "supplier":           str   (required) — Wrightsoft Src code
          "sku":                str   (required) — Wrightsoft Name
          "corrected_sku":      str | null (optional)
          "corrected_supplier": str | null (optional)
          "unit_price":         float | null (optional)
          "notes":              str | null (optional)
        }

    Pass empty string for a field to clear a previously-set value;
    omit the key (or pass null) to leave it unchanged.
    """
    body = request.get_json(silent=True) or {}

    client_id = (body.get("client_id") or "").strip()
    supplier  = (body.get("supplier")  or "").strip()
    sku       = (body.get("sku")       or "").strip()
    if not client_id or not supplier or not sku:
        return jsonify({
            "success": False, "data": None,
            "error": "client_id, supplier, and sku are required",
        }), 400

    # Type-check unit_price separately so a bad value produces a
    # readable 400 instead of a 500.
    raw_price = body.get("unit_price", None)
    unit_price: float | None
    if raw_price is None or raw_price == "":
        unit_price = None
    else:
        try:
            unit_price = float(raw_price)
        except (TypeError, ValueError):
            return jsonify({
                "success": False, "data": None,
                "error": "unit_price must be a number",
            }), 400
        if unit_price < 0:
            return jsonify({
                "success": False, "data": None,
                "error": "unit_price cannot be negative",
            }), 400

    try:
        row = ContractorOverride.upsert(
            contractor_id=client_id,
            supplier=supplier,
            sku=sku,
            corrected_sku=body.get("corrected_sku"),
            corrected_supplier=body.get("corrected_supplier"),
            unit_price=unit_price,
            notes=body.get("notes"),
            updated_by=_actor(),
        )
        db.session.commit()
        # Day-25 telemetry — the input side of the learning loop.
        try:
            from models.usage_event import UsageEvent
            UsageEvent.record(
                event="override_saved",
                actor_email=_actor(),
                client_id=client_id,
                detail={
                    "supplier": supplier, "sku": sku,
                    "has_price": unit_price is not None,
                    "has_sku_fix": bool(body.get("corrected_sku")),
                },
            )
        except Exception:
            logger.warning("override_saved usage-event failed", exc_info=True)
            db.session.rollback()
        return jsonify({
            "success": True, "data": row.to_dict(), "error": None,
        }), 200
    except ValueError as exc:
        return jsonify({
            "success": False, "data": None, "error": str(exc),
        }), 400
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("upsert_override failed: %s", exc, exc_info=True)
        return jsonify({
            "success": False, "data": None,
            "error": "Failed to save contractor override",
        }), 500


# ─── POST — bulk CSV/XLSX import (Day-16) ──────────────────────────
#
# Round-trip from "contractor sends a pricing Excel" to "future BOMs
# price correctly" in one upload. Tolerates header variation and
# dollar-formatted prices; reports per-row outcomes so Richard can
# correct his sheet without guessing what failed.

@contractor_override_bp.route("/import", methods=["POST"])
def import_overrides():
    """Bulk-upsert overrides from a CSV / XLS / XLSX upload.

    Form fields:
        file        — multipart upload, .csv / .xls / .xlsx
        client_id   — contractor whose overrides we're loading

    Expected headers (case-insensitive, common synonyms accepted):
        supplier            (or 'src')
        sku                 (or 'name' / 'wrightsoft_sku')
        unit_price          (or 'price' / 'cost' / 'unit_cost')
        corrected_sku       (optional)
        corrected_supplier  (optional)
        notes               (optional)

    Returns: {inserted, updated, skipped, errors: [{row, reason}, …]}
    """
    if "file" not in request.files:
        return jsonify({"success": False, "data": None,
                        "error": "Missing 'file' upload"}), 400

    client_id = (request.form.get("client_id") or "").strip()
    if not client_id:
        return jsonify({"success": False, "data": None,
                        "error": "Missing 'client_id'"}), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"success": False, "data": None,
                        "error": "Empty filename"}), 400

    try:
        rows = _parse_overrides_upload(upload.read(), upload.filename)
    except ValueError as exc:
        return jsonify({"success": False, "data": None,
                        "error": str(exc)}), 400

    actor = _actor()
    inserted = updated = skipped = 0
    errors: list[dict] = []

    for i, row in enumerate(rows, start=2):  # row 1 = header
        supplier = _str_or_none(row.get("supplier") or row.get("src"))
        sku      = _str_or_none(row.get("sku") or row.get("name")
                                or row.get("wrightsoft_sku"))
        price_in = row.get("unit_price") or row.get("price") \
                   or row.get("cost") or row.get("unit_cost")
        unit_price = _parse_money(price_in)
        corrected_sku      = _str_or_none(row.get("corrected_sku"))
        corrected_supplier = _str_or_none(row.get("corrected_supplier"))
        notes              = _str_or_none(row.get("notes"))

        if not supplier or not sku:
            skipped += 1
            errors.append({"row": i,
                           "reason": "missing supplier or sku"})
            continue
        if unit_price is None and not corrected_sku \
                and not corrected_supplier and not notes:
            # Pure no-op row — nothing to override.
            skipped += 1
            errors.append({"row": i,
                           "reason": "no override fields populated"})
            continue

        try:
            existing = ContractorOverride.lookup(
                contractor_id=client_id, supplier=supplier, sku=sku)
            ContractorOverride.upsert(
                contractor_id=client_id,
                supplier=supplier,
                sku=sku,
                corrected_sku=corrected_sku,
                corrected_supplier=corrected_supplier,
                unit_price=unit_price,
                notes=notes,
                updated_by=actor,
            )
            if existing is None:
                inserted += 1
            else:
                updated += 1
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            skipped += 1
            errors.append({"row": i, "reason": str(exc)[:200]})

    try:
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("import_overrides commit failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Failed to persist overrides"}), 500

    return jsonify({
        "success": True,
        "data": {
            "client_id": client_id,
            "inserted":  inserted,
            "updated":   updated,
            "skipped":   skipped,
            "errors":    errors[:50],  # cap at 50 to keep payload sane
            "total_seen": inserted + updated + skipped,
        },
        "error": None,
    }), 200


def _str_or_none(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_money(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Strip $ and thousands commas; keep decimal point and leading minus.
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _parse_overrides_upload(file_bytes: bytes, filename: str) -> list[dict]:
    """Return a list of header-keyed dicts (lowercased keys) from a
    .csv / .xls / .xlsx upload. Raises ValueError with a human-readable
    message when the file shape is unusable."""
    import io
    import csv

    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = [
            {(k or "").strip().lower(): v for k, v in r.items()}
            for r in reader
        ]
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError("XLS/XLSX upload not supported in this env") from exc
        wb = load_workbook(filename=io.BytesIO(file_bytes),
                           data_only=True, read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [(str(h) if h is not None else "").strip().lower()
                   for h in next(rows_iter, []) or []]
        rows = []
        for r in rows_iter:
            if r is None:
                continue
            rows.append({h: v for h, v in zip(headers, r) if h})
    else:
        raise ValueError(
            "Unrecognized file format — accepts .csv / .xls / .xlsx")

    if not rows:
        raise ValueError("Empty upload — no rows after header")
    return rows


# ─── DELETE — drop a single override ───────────────────────────────

@contractor_override_bp.route("/<int:override_id>", methods=["DELETE"])
def delete_override(override_id: int):
    """Drop one override by primary key. Returns 404 if it doesn't
    exist (caller may have already deleted it from another tab)."""
    try:
        row = db.session.get(ContractorOverride, override_id)
        if row is None:
            return jsonify({
                "success": False, "data": None,
                "error": f"Override {override_id} not found",
            }), 404
        db.session.delete(row)
        db.session.commit()
        return jsonify({
            "success": True,
            "data": {"deleted_id": override_id},
            "error": None,
        }), 200
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("delete_override failed: %s", exc, exc_info=True)
        return jsonify({
            "success": False, "data": None,
            "error": "Failed to delete contractor override",
        }), 500
