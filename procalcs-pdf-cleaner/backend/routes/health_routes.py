"""
Health check routes for monitoring and deployment verification.
"""

from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Return 200 for Cloud Run health checks."""
    return jsonify({
        "success": True,
        "data": {
            "service": "procalcs-pdf-cleaner",
            "status": "healthy"
        }
    }), 200
