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
