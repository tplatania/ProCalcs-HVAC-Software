"""
PDF-to-CAD cleaner routes.
Accepts DWG/DXF upload, returns cleaned file.
"""

import os
import logging
from flask import Blueprint, request, jsonify, send_file

from config import Config
from services.cleaner_service import clean_dwg_file
from utils.validators import validate_upload

logger = logging.getLogger('pdf_cleaner')
cleaner_bp = Blueprint('cleaner', __name__)


@cleaner_bp.route('/pdf-to-cad', methods=['POST'])
def clean_cad_file():
    """
    Accept DWG/DXF upload, strip non-essential entities,
    return cleaned file ready for Wrightsoft import.
    """
    try:
        # Validate the upload
        file = request.files.get('file')
        validation = validate_upload(file)

        if not validation.get('is_valid'):
            return jsonify({
                "success": False,
                "error": validation.get('error', 'Invalid upload')
            }), 400

        # Save uploaded file to temp
        filename = file.filename
        upload_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(upload_path)

        logger.info("Processing file: %s", filename)

        # Run the cleanup engine
        result = clean_dwg_file(upload_path)

        if not result.get('success'):
            return jsonify({
                "success": False,
                "error": result.get('error', 'Cleanup failed')
            }), 500

        # Return the cleaned file as download
        clean_path = result.get('output_path')
        clean_filename = result.get('output_filename', 'cleaned.dxf')

        return send_file(
            clean_path,
            as_attachment=True,
            download_name=clean_filename
        )

    except Exception as e:
        logger.error("Cleanup failed for upload: %s", e)
        return jsonify({
            "success": False,
            "error": "Something went wrong processing your file. Please try again."
        }), 500
