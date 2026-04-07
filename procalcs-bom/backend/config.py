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

    # CORS — Designer Desktop origin
    ALLOWED_ORIGINS = os.environ.get(
        'ALLOWED_ORIGINS',
        'http://localhost:3000,http://localhost:5173'
    ).split(',')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Admin access
    ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')


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
    logger.info("Config validated successfully for environment: %s",
                os.environ.get('FLASK_ENV', 'development'))
