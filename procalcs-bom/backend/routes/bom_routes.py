"""
bom_routes.py — BOM generation endpoint
Gerald calls POST /api/v1/bom/generate with job design data.
Returns a complete, client-profiled Bill of Materials.
Follows ProCalcs Design Standards v2.0
"""

import logging
from flask import Blueprint, jsonify, request
from services.bom_service import generate
from utils.validators import validate_bom_request

logger = logging.getLogger('procalcs_bom')
bom_bp = Blueprint('bom', __name__)


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
