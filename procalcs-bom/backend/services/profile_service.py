"""
profile_service.py — Client Profile CRUD operations
All Firestore reads and writes for client profiles live here.
Routes call this service — no database logic in routes.
Follows ProCalcs Design Standards v2.0
"""

import logging
from datetime import datetime, timezone
from google.cloud import firestore
from models.client_profile import ClientProfile

logger = logging.getLogger('procalcs_bom')

# Firestore collection name
COLLECTION = 'client_profiles'


# ===============================
# Firestore Client (singleton)
# ===============================

_db = None

def get_db():
    """
    Return Firestore client.
    Initialized once and reused — Cloud Run is stateless
    but the client is safe to reuse within a container instance.
    """
    global _db
    if _db is None:
        _db = firestore.Client()
    return _db


# ===============================
# Read Operations
# ===============================

def get_all_profiles() -> list:
    """
    Return all client profiles from Firestore.
    Returns a list of dicts — routes serialize to JSON.
    """
    try:
        db = get_db()
        docs = db.collection(COLLECTION).stream()
        profiles = []
        for doc in docs:
            data = doc.to_dict()
            if data:
                profiles.append(data)
        logger.info("Fetched %s client profiles", len(profiles))
        return profiles
    except Exception as e:
        logger.error("Failed to fetch all profiles: %s", e)
        raise


def get_profile_by_id(client_id: str) -> dict:
    """
    Return a single client profile by client_id.
    Returns None if not found.
    """
    try:
        db = get_db()
        doc = db.collection(COLLECTION).document(client_id).get()
        if not doc.exists:
            logger.warning("Profile not found for client_id: %s", client_id)
            return None
        return doc.to_dict()
    except Exception as e:
        logger.error("Failed to fetch profile %s: %s", client_id, e)
        raise


# ===============================
# Write Operations
# ===============================

def create_profile(data: dict, created_by: str) -> dict:
    """
    Create a new client profile in Firestore.
    Returns the created profile as a dict.
    Raises ValueError if client_id already exists.
    """
    try:
        client_id = data.get('client_id', '').strip()
        if not client_id:
            raise ValueError("client_id is required.")

        db = get_db()
        doc_ref = db.collection(COLLECTION).document(client_id)

        # Prevent overwriting existing profile
        if doc_ref.get().exists:
            raise ValueError("A profile for client_id '%s' already exists." % client_id)

        now = datetime.now(timezone.utc).isoformat()
        profile = ClientProfile.from_dict(data)
        profile.created_at = now
        profile.updated_at = now
        profile.created_by = created_by

        doc_ref.set(profile.to_dict())
        logger.info("Created profile for client: %s by %s", client_id, created_by)
        return profile.to_dict()

    except ValueError:
        raise
    except Exception as e:
        logger.error("Failed to create profile for %s: %s", data.get('client_id'), e)
        raise


def update_profile(client_id: str, data: dict) -> dict:
    """
    Update an existing client profile.
    Merges changes — does not overwrite untouched fields.
    Returns updated profile as a dict.
    Raises ValueError if profile does not exist.
    """
    try:
        db = get_db()
        doc_ref = db.collection(COLLECTION).document(client_id)

        if not doc_ref.get().exists:
            raise ValueError("No profile found for client_id '%s'." % client_id)

        now = datetime.now(timezone.utc).isoformat()
        data['updated_at'] = now
        data['client_id'] = client_id  # Ensure ID never changes via update

        doc_ref.set(data, merge=True)
        updated = doc_ref.get().to_dict()
        logger.info("Updated profile for client: %s", client_id)
        return updated

    except ValueError:
        raise
    except Exception as e:
        logger.error("Failed to update profile %s: %s", client_id, e)
        raise


def delete_profile(client_id: str) -> bool:
    """
    Delete a client profile by client_id.
    Returns True on success.
    Raises ValueError if profile does not exist.
    """
    try:
        db = get_db()
        doc_ref = db.collection(COLLECTION).document(client_id)

        if not doc_ref.get().exists:
            raise ValueError("No profile found for client_id '%s'." % client_id)

        doc_ref.delete()
        logger.info("Deleted profile for client: %s", client_id)
        return True

    except ValueError:
        raise
    except Exception as e:
        logger.error("Failed to delete profile %s: %s", client_id, e)
        raise
