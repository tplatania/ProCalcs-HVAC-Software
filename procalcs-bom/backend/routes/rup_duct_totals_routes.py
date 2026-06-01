"""
rup_duct_totals_routes.py — REST surface for the Day-14 Phase 4
per-RUP known-duct-LF cache.

Mounted under /api/v1/rup-duct-totals. The SPA's BOM Engine page
upserts here when the user clicks Continue with totals filled in,
and the /parse-rup endpoint reads here directly (no separate GET
needed) so re-uploads pre-populate the form in a single round trip.

Endpoints:
    GET    /api/v1/rup-duct-totals/<rup_hash>   → fetch cached totals
    POST   /api/v1/rup-duct-totals              → upsert
                                                  body: {rup_hash, known_lengths_ft,
                                                         source_filename?}

Envelope: {success, data, error} like the rest of the BOM API.
"""

import logging

from flask import Blueprint, jsonify, request

from extensions import db
from models.rup_duct_totals import RupDuctTotals


logger = logging.getLogger("procalcs_bom")
rup_duct_totals_bp = Blueprint("rup_duct_totals", __name__)


def _actor() -> str | None:
    return (
        request.headers.get("X-Actor-Email")
        or request.headers.get("X-Client-Id")
    )


# ─── GET — fetch cached totals for one hash ────────────────────────

@rup_duct_totals_bp.route("/<rup_hash>", methods=["GET"])
def get_totals(rup_hash: str):
    rup_hash = (rup_hash or "").strip().lower()
    if not rup_hash or len(rup_hash) != 64:
        return jsonify({
            "success": False, "data": None,
            "error": "rup_hash must be the 64-char SHA-256 hex of the RUP bytes.",
        }), 400
    try:
        row = RupDuctTotals.lookup(rup_hash)
    except Exception as exc:  # noqa: BLE001
        logger.error("rup_duct_totals lookup failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "DB lookup failed."}), 500
    if row is None:
        # 404 — no cached totals for this RUP yet
        return jsonify({"success": True, "data": None, "error": None}), 200
    return jsonify({"success": True, "data": row.to_dict(), "error": None}), 200


# ─── POST — upsert ─────────────────────────────────────────────────

@rup_duct_totals_bp.route("", methods=["POST"])
@rup_duct_totals_bp.route("/", methods=["POST"])
def upsert_totals():
    body = request.get_json(silent=True) or {}
    rup_hash = (body.get("rup_hash") or "").strip().lower()
    known = body.get("known_lengths_ft") or {}
    src   = body.get("source_filename")

    if not rup_hash or len(rup_hash) != 64:
        return jsonify({"success": False, "data": None,
                        "error": "rup_hash must be the 64-char SHA-256 hex."}), 400
    if not isinstance(known, dict):
        return jsonify({"success": False, "data": None,
                        "error": "known_lengths_ft must be an object."}), 400
    # Reject obviously-malformed shapes early so the cache stays clean.
    for bucket in ("round_supply", "round_return", "rect_supply", "rect_return"):
        b = known.get(bucket)
        if b is not None and not isinstance(b, dict):
            return jsonify({"success": False, "data": None,
                            "error": f"known_lengths_ft.{bucket} must be an object."}), 400

    try:
        row = RupDuctTotals.upsert(
            rup_hash=rup_hash,
            known_lengths_ft=known,
            source_filename=src,
            updated_by=_actor(),
        )
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("rup_duct_totals upsert failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None,
                        "error": "Save failed."}), 500

    return jsonify({"success": True, "data": row.to_dict(), "error": None}), 200
