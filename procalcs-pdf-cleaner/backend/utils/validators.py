"""
Input validation for file uploads.
"""

from config import Config


def validate_upload(file):
    """
    Validate an uploaded file for the cleaner endpoint.
    Returns dict with is_valid bool and error message if invalid.
    """
    if file is None:
        return {
            "is_valid": False,
            "error": "No file provided. Please upload a DWG or DXF file."
        }

    if not file.filename:
        return {
            "is_valid": False,
            "error": "File has no name."
        }

    # Check extension
    extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''

    if extension not in Config.ALLOWED_EXTENSIONS:
        allowed = ', '.join(Config.ALLOWED_EXTENSIONS)
        return {
            "is_valid": False,
            "error": f"File type '.{extension}' not supported. Allowed: {allowed}"
        }

    # Check file size (read content length from stream)
    file.seek(0, 2)  # Seek to end
    size_mb = file.tell() / (1024 * 1024)
    file.seek(0)  # Reset to beginning

    if size_mb > Config.MAX_UPLOAD_SIZE_MB:
        return {
            "is_valid": False,
            "error": f"File too large ({size_mb:.1f}MB). Maximum: {Config.MAX_UPLOAD_SIZE_MB}MB"
        }

    return {
        "is_valid": True,
        "extension": extension,
        "size_mb": round(size_mb, 2)
    }
