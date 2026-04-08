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
from utils.rup_parser import parse_rup_bytes

logger = logging.getLogger('procalcs_bom')
bom_bp = Blueprint('bom', __name__)


# Max .rup file size — 20 MB covers a 50-AHU commercial project.
# The Enos sample is 6.6 MB for a large 8-AHU residence.
MAX_RUP_BYTES = 20 * 1024 * 1024


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
