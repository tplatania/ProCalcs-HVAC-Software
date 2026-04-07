"""
health_routes.py — Health check endpoint
Required by Google Cloud Run for monitoring.
"""

import logging
from flask import Blueprint, jsonify

logger = logging.getLogger('procalcs_bom')
health_bp = Blueprint('health', __name__)


# ===============================
# Health Check
# ===============================

@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Returns 200 OK if the service is running.
    Used by Cloud Run health checks and uptime monitors.
    """
    return jsonify({
        "success": True,
        "data": {"status": "healthy", "service": "procalcs-bom"},
        "error": None
    }), 200
