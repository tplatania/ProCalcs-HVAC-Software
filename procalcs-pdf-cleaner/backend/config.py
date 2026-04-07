"""
ProCalcs PDF Cleaner — Centralized Configuration
Single source of truth for all settings.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv('.env.local', override=True)
load_dotenv('.env')

logger = logging.getLogger('pdf_cleaner')


class Config:
    """Application configuration loaded from environment variables."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback-change-me')
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')

    # Server
    PORT = int(os.environ.get('PORT', 5001))
    HOST = os.environ.get('HOST', '0.0.0.0')

    # ODA File Converter
    ODA_CONVERTER_PATH = os.environ.get('ODA_CONVERTER_PATH', '')

    # Upload limits
    MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', 50))
    ALLOWED_EXTENSIONS = os.environ.get(
        'ALLOWED_EXTENSIONS', 'dwg,dxf'
    ).split(',')

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Paths
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'uploads'
    )
    TEMP_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'temp'
    )

    @classmethod
    def is_production(cls):
        """Check if running in production environment."""
        return cls.FLASK_ENV == 'production'

    @classmethod
    def validate(cls):
        """Validate required config on startup. Fail fast."""
        errors = []

        if cls.is_production() and cls.SECRET_KEY == 'dev-fallback-change-me':
            errors.append('SECRET_KEY must be set in production')

        if cls.is_production() and not cls.ODA_CONVERTER_PATH:
            errors.append('ODA_CONVERTER_PATH required in production')

        if cls.ODA_CONVERTER_PATH and not os.path.exists(cls.ODA_CONVERTER_PATH):
            logger.warning(
                "ODA converter not found at %s — DWG output disabled",
                cls.ODA_CONVERTER_PATH
            )

        if errors:
            for error in errors:
                logger.error("Config error: %s", error)
            raise RuntimeError(
                f"Configuration errors: {'; '.join(errors)}"
            )

        logger.info("Configuration validated successfully")
