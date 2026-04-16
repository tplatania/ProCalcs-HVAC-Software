"""
config.py — Centralized configuration for ProCalcs BOM
Single source of truth for all environment-based settings.
Follows ProCalcs Design Standards v2.0
"""

import os
import logging
from dotenv import load_dotenv

# ===============================
# Environment Loading
# ===============================

load_dotenv('.env.local', override=True)  # Local dev overrides
load_dotenv('.env')                        # Base config


# ===============================
# Configuration Class
# ===============================

class Config:
    """Base configuration — all environments inherit from this."""

    # App
    APP_NAME = "ProCalcs BOM"
    VERSION  = "1.0.0"
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Anthropic AI
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL   = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
    ANTHROPIC_MAX_TOKENS = int(os.environ.get('ANTHROPIC_MAX_TOKENS', '4096'))

    # Firestore
    FIRESTORE_PROJECT_ID   = os.environ.get('FIRESTORE_PROJECT_ID', '')
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')

    # CORS — Designer Desktop + Dashboard origins (comma-separated env).
    # Whitespace-tolerant: "a, b,, c " -> ["a", "b", "c"].
    ALLOWED_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            'ALLOWED_ORIGINS',
            'http://localhost:3000,http://localhost:5173'
        ).split(',')
        if o.strip()
    ]

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Admin access
    ADMIN_EMAILS = [
        e.strip()
        for e in os.environ.get('ADMIN_EMAILS', '').split(',')
        if e.strip()
    ]

    # Shared-secret auth — every non-health request must present the same
    # token via X-Procalcs-Service-Token. BFFs (Designer Desktop, Designer
    # Dashboard) keep this in their own env and forward it per request.
    # Leaving this blank disables the check (dev only).
    SERVICE_SHARED_SECRET = os.environ.get('SERVICE_SHARED_SECRET', '')


class DevelopmentConfig(Config):
    """Local development settings."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Google Cloud Run production settings."""
    DEBUG = False
    TESTING = False


# ===============================
# Config Selector
# ===============================

config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
}

def get_config():
    """Return the correct config class based on environment."""
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)

# ===============================
# Startup Validation
# ===============================

def validate_config(app):
    """
    Validate required config on startup.
    Fails fast with clear error messages so missing env vars
    are caught immediately rather than at runtime.
    """
    logger = logging.getLogger('procalcs_bom')
    required = {
        'ANTHROPIC_API_KEY': app.config.get('ANTHROPIC_API_KEY'),
        'FIRESTORE_PROJECT_ID': app.config.get('FIRESTORE_PROJECT_ID'),
        'SECRET_KEY': app.config.get('SECRET_KEY'),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        for key in missing:
            logger.error("Missing required environment variable: %s", key)
        raise RuntimeError(
            "Missing required config: %s. Check .env file." % ', '.join(missing)
        )

    # SERVICE_SHARED_SECRET is a soft-required — warn loudly in non-dev
    # environments but don't refuse to boot (keeps dev workflow frictionless).
    if not app.config.get('SERVICE_SHARED_SECRET'):
        if os.environ.get('FLASK_ENV') == 'production':
            logger.warning(
                "[WARNING] SERVICE_SHARED_SECRET is empty — shared-secret auth "
                "is DISABLED. Any caller can hit the BOM endpoints."
            )
        else:
            logger.info(
                "SERVICE_SHARED_SECRET not set — auth middleware is disabled "
                "(dev mode). Set it to enable shared-secret auth."
            )

    logger.info("Config validated successfully for environment: %s",
                os.environ.get('FLASK_ENV', 'development'))
