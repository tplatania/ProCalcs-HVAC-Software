"""
health_routes.py — Health check + catalog-health passthrough
Required by Google Cloud Run for monitoring.
"""

import logging
from flask import Blueprint, jsonify

from services import wrightsoft_catalog as wsc

logger = logging.getLogger('procalcs_bom')

# Two blueprints share one payload:
#   health_bp            → /health           (Cloud Run probe, no prefix)
#   versioned_health_bp  → /api/v1/health    (client-facing, matches /api/v1/*)
health_bp = Blueprint('health', __name__)
versioned_health_bp = Blueprint('versioned_health', __name__)


def _health_payload():
    return jsonify({
        "success": True,
        "data": {"status": "healthy", "service": "procalcs-bom"},
        "error": None,
    }), 200


# ===============================
# Health Check
# ===============================

@health_bp.route('/health', methods=['GET'])
def health_check():
    """Cloud Run probe. Exempt from shared-secret auth."""
    return _health_payload()


@versioned_health_bp.route('/health', methods=['GET'])
def versioned_health_check():
    """Client-facing health. Also exempt from shared-secret auth."""
    return _health_payload()


# ===============================
# Catalog Health (Day-15 carryover)
# ===============================
#
# SPA-facing passthrough that surfaces the latest catalog ImportBatch
# counts under the bom service's existing auth surface. Lets the
# Dashboard "Catalog Health" card show row counts at a glance without
# punching a second auth boundary through to procalcs-catalog.

@versioned_health_bp.route('/catalog-health', methods=['GET'])
def catalog_health():
    """Return {batch_id, imported_at, imported_by, counts}.

    Falls back to {available: false} when the catalog API isn't
    configured / reachable so the SPA renders a sensible empty state."""
    client = wsc._get_client()
    if client is None:
        return jsonify({
            "success": True,
            "data": {"available": False, "reason": "catalog API not configured"},
            "error": None,
        }), 200
    try:
        envelope = client.latest_batch() or {}
        batch = envelope.get("data") if isinstance(envelope, dict) else None
        if not batch:
            return jsonify({
                "success": True,
                "data": {"available": False, "reason": "no batches loaded yet"},
                "error": None,
            }), 200
        return jsonify({
            "success": True,
            "data": {
                "available":   True,
                "batch_id":    batch.get("id"),
                "imported_at": batch.get("imported_at"),
                "imported_by": batch.get("imported_by"),
                "counts":      batch.get("counts") or {},
            },
            "error": None,
        }), 200
    except Exception as exc:  # noqa: BLE001 — best-effort surface
        logger.warning("catalog_health failed: %s", exc)
        return jsonify({
            "success": True,
            "data": {"available": False, "reason": "catalog API unreachable"},
            "error": None,
        }), 200
