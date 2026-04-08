"""
PDF-to-CAD cleaner routes.

POST /api/v1/tools/pdf-to-cad — accepts a DWG/DXF upload and returns a JSON
envelope describing the cleanup result (kept/stripped counts, INSERT filter
stats, and a download URL keyed by job id).

GET /api/v1/tools/pdf-to-cad/download/<job_id> — streams the cleaned binary
file persisted by the cleanup engine. Files older than 1 hour are purged.
"""

import os
import time
import logging
from flask import Blueprint, request, jsonify, send_file, abort

from config import Config
from services.cleaner_service import clean_dwg_file
from utils.validators import validate_upload

logger = logging.getLogger('pdf_cleaner')
cleaner_bp = Blueprint('cleaner', __name__)

# Temp files older than this are removed before each new upload to keep
# the cleaner host disk bounded. Designers download immediately after upload,
# so an hour is more than enough.
TEMP_FILE_TTL_SECONDS = 60 * 60


def _purge_old_temp_files():
    """Best-effort cleanup of stale cleaned files in TEMP_FOLDER."""
    try:
        now = time.time()
        for entry in os.listdir(Config.TEMP_FOLDER):
            path = os.path.join(Config.TEMP_FOLDER, entry)
            if not os.path.isfile(path):
                continue
            try:
                age = now - os.path.getmtime(path)
                if age > TEMP_FILE_TTL_SECONDS:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


@cleaner_bp.route('/pdf-to-cad', methods=['POST'])
def clean_cad_file():
    """Strip non-essential entities, persist clean output, return JSON stats."""
    try:
        _purge_old_temp_files()

        file = request.files.get('file')
        validation = validate_upload(file)

        if not validation.get('is_valid'):
            return jsonify({
                "success": False,
                "data": None,
                "error": validation.get('error', 'Invalid upload'),
            }), 400

        filename = file.filename
        upload_path = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(upload_path)

        logger.info("Processing file: %s", filename)

        result = clean_dwg_file(upload_path)

        if not result.get('success'):
            return jsonify({
                "success": False,
                "data": None,
                "error": result.get('error', 'Cleanup failed'),
            }), 500

        job_id = result.get('job_id')
        download_url = (
            f"/api/v1/tools/pdf-to-cad/download/{job_id}" if job_id else None
        )

        return jsonify({
            "success": True,
            "data": {
                "job_id": job_id,
                "filename": result.get('output_filename'),
                "kept_count": result.get('kept_count'),
                "stripped_count": result.get('stripped_count'),
                "insert_filter": result.get('insert_filter'),
                "download_url": download_url,
            },
            "error": None,
        })

    except Exception as e:
        logger.error("Cleanup failed for upload: %s", e)
        return jsonify({
            "success": False,
            "data": None,
            "error": "Something went wrong processing your file. Please try again.",
        }), 500


@cleaner_bp.route('/pdf-to-cad/download/<job_id>', methods=['GET'])
def download_cleaned_file(job_id):
    """Stream the persisted cleaned DXF for the given job id."""
    # Reject anything that isn't a plain file id to avoid path traversal.
    if not job_id or '/' in job_id or '\\' in job_id or '..' in job_id:
        abort(400)

    file_path = os.path.join(Config.TEMP_FOLDER, f"{job_id}.dxf")
    if not os.path.isfile(file_path):
        return jsonify({
            "success": False,
            "data": None,
            "error": "Cleanup output expired or not found.",
        }), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=f"{job_id}_clean.dxf",
        mimetype='application/octet-stream',
    )
