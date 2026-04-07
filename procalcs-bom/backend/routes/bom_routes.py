"""
bom_routes.py — BOM generation endpoint
Gerald calls POST /api/v1/bom/generate with job design data.
Returns a complete, client-profiled Bill of Materials.
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger('procalcs_bom')
bom_bp = Blueprint('bom', __name__)


# ===============================
# Routes — Placeholder
# ===============================

@bom_bp.route('/generate', methods=['POST'])
def generate_bom():
    """
    Generate a BOM from completed job design data.

    Expected request body:
    {
        "client_id": "beazer-001",
        "job_id": "job-12345",
        "design_data": {
            "duct_runs": [...],
            "fittings": [...],
            "equipment": [...],
            "registers": [...],
            "building": {...}
        }
    }

    Returns structured BOM JSON with client profile applied.
    TODO: implement AI engine and profile lookup.
    """
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({
                "success": False,
                "data": None,
                "error": "Request body is required."
            }), 400

        client_id  = body.get('client_id', '')
        job_id     = body.get('job_id', '')
        design_data = body.get('design_data', {})

        if not client_id or not job_id or not design_data:
            return jsonify({
                "success": False,
                "data": None,
                "error": "client_id, job_id, and design_data are all required."
            }), 400

        # TODO: call bom_service.generate(client_id, job_id, design_data)
        logger.info("BOM generation requested for client %s job %s", client_id, job_id)

        return jsonify({
            "success": True,
            "data": {"message": "BOM engine not yet implemented."},
            "error": None
        }), 200

    except Exception as e:
        logger.error("BOM generation failed for job %s: %s", body.get('job_id', 'unknown'), e)
        return jsonify({
            "success": False,
            "data": None,
            "error": "Something went wrong. Please try again."
        }), 500
