"""
app.py — Flask application factory for ProCalcs BOM
Follows ProCalcs Design Standards v2.0
"""

import logging
import os
from flask import Flask, jsonify
from flask_cors import CORS

from config import get_config, validate_config


# ===============================
# Logging Setup
# ===============================

def configure_logging(app):
    """
    Configure structured logging.
    Production: JSON format for Cloud Run / GCP.
    Development: Human-readable format.
    """
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'))
    is_production = not app.debug

    if is_production:
        fmt = '{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
    else:
        fmt = '[%(levelname)s] %(name)s — %(message)s'

    logging.basicConfig(level=log_level, format=fmt)
    app.logger.setLevel(log_level)


# ===============================
# App Factory
# ===============================

def create_app():
    """
    Application factory — creates and configures the Flask app.
    Called by gunicorn in production and directly in development.
    """
    app = Flask(__name__)

    # Load config
    config_class = get_config()
    app.config.from_object(config_class)

    # Logging
    configure_logging(app)
    logger = logging.getLogger('procalcs_bom')

    # CORS — allow Designer Desktop and local dev origins
    CORS(app, origins=app.config.get('ALLOWED_ORIGINS', []))

    # Validate required env vars — fail fast
    validate_config(app)

    # Register blueprints
    register_blueprints(app)

    logger.info("ProCalcs BOM started — version %s", app.config.get('VERSION'))
    return app


# ===============================
# Blueprint Registration
# ===============================

def register_blueprints(app):
    """Register all route blueprints."""
    from routes.health_routes import health_bp
    from routes.profile_routes import profile_bp
    from routes.bom_routes import bom_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(profile_bp, url_prefix='/api/v1/profiles')
    app.register_blueprint(bom_bp,     url_prefix='/api/v1/bom')


# ===============================
# Entry Point (local dev only)
# ===============================

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.debug)
