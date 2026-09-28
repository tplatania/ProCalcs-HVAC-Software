"""
profile_routes.py — Client Profile CRUD endpoints
Manages per-client pricing, part names, markup, and preferences.
Richard and Windell use these via the admin UI.
Follows ProCalcs Design Standards v2.0
"""

import logging
from flask import Blueprint, jsonify, request
from services.profile_service import (
    get_all_profiles,
    get_profile_by_id,
    create_profile,
    update_profile,
    delete_profile,
)
from services.client_scope import allowed_client_ids, can_access_client

logger = logging.getLogger('procalcs_bom')
profile_bp = Blueprint('profiles', __name__)


# ===============================
# GET — List all profiles
# ===============================

@profile_bp.route('/', methods=['GET'])
def list_profiles():
    """Return all active client profiles."""
    try:
        profiles = get_all_profiles()
        allowed = allowed_client_ids()
        if allowed is not None:
            profiles = [
                profile for profile in profiles
                if (profile.get('client_id') or profile.get('id')) in allowed
            ]
        return jsonify({"success": True, "data": profiles, "error": None}), 200
    except Exception as e:
        logger.error("list_profiles failed: %s", e)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to load profiles."}), 500


# ===============================
# GET — Single profile
# ===============================

@profile_bp.route('/<string:client_id>', methods=['GET'])
def get_profile(client_id):
    """Return a single client profile by ID."""
    if not can_access_client(client_id):
        return jsonify({"success": False, "data": None,
                        "error": "client access denied"}), 403
    try:
        profile = get_profile_by_id(client_id)
        if not profile:
            return jsonify({"success": False, "data": None,
                            "error": "Profile not found."}), 404
        return jsonify({"success": True, "data": profile, "error": None}), 200
    except Exception as e:
        logger.error("get_profile failed for %s: %s", client_id, e)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to load profile."}), 500


# ===============================
# POST — Create profile
# ===============================

@profile_bp.route('/', methods=['POST'])
def create_new_profile():
    """Create a new client profile."""
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"success": False, "data": None,
                            "error": "Request body is required."}), 400
        if not can_access_client((body.get('client_id') or '').strip()):
            return jsonify({"success": False, "data": None,
                            "error": "client access denied"}), 403

        created_by = body.get('created_by', 'unknown')
        profile = create_profile(body, created_by)
        return jsonify({"success": True, "data": profile, "error": None}), 201

    except ValueError as e:
        return jsonify({"success": False, "data": None, "error": str(e)}), 400
    except Exception as e:
        logger.error("create_profile failed: %s", e)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to create profile."}), 500


# ===============================
# PUT — Update profile
# ===============================

@profile_bp.route('/<string:client_id>', methods=['PUT'])
def update_existing_profile(client_id):
    """Update an existing client profile."""
    if not can_access_client(client_id):
        return jsonify({"success": False, "data": None,
                        "error": "client access denied"}), 403
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"success": False, "data": None,
                            "error": "Request body is required."}), 400

        updated = update_profile(client_id, body)
        return jsonify({"success": True, "data": updated, "error": None}), 200

    except ValueError as e:
        return jsonify({"success": False, "data": None, "error": str(e)}), 404
    except Exception as e:
        logger.error("update_profile failed for %s: %s", client_id, e)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to update profile."}), 500


# ===============================
# DELETE — Remove profile
# ===============================

@profile_bp.route('/<string:client_id>', methods=['DELETE'])
def delete_existing_profile(client_id):
    """Delete a client profile. Requires confirmation."""
    if not can_access_client(client_id):
        return jsonify({"success": False, "data": None,
                        "error": "client access denied"}), 403
    try:
        delete_profile(client_id)
        return jsonify({"success": True,
                        "data": {"deleted": client_id},
                        "error": None}), 200

    except ValueError as e:
        return jsonify({"success": False, "data": None, "error": str(e)}), 404
    except Exception as e:
        logger.error("delete_profile failed for %s: %s", client_id, e)
        return jsonify({"success": False, "data": None,
                        "error": "Unable to delete profile."}), 500
