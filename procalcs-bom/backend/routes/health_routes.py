"""
health_routes.py — Health check endpoint
Required by Google Cloud Run for monitoring.
"""

import logging
from flask import Blueprint, jsonify

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
