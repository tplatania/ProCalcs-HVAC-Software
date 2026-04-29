"""
app.py — Flask application factory for ProCalcs BOM
Follows ProCalcs Design Standards v2.0
"""

import logging
import os
from flask import Flask, jsonify, request
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

    # Global request-body size limit — applies to every route.
    # /parse-rup still enforces its own 20 MB check; this backstops /generate
    # and /render-pdf so a hostile client can't post unbounded JSON.
    app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25 MB

    # Logging
    configure_logging(app)
    logger = logging.getLogger('procalcs_bom')

    # CORS — allow Designer Desktop and local dev origins
    CORS(app, origins=app.config.get('ALLOWED_ORIGINS', []))

    # Validate required env vars — fail fast
    validate_config(app)

    # Shared-secret auth middleware — runs before every request
    register_auth_middleware(app)

    # Register blueprints
    register_blueprints(app)

    logger.info("ProCalcs BOM started — version %s", app.config.get('VERSION'))
    return app


# ===============================
# Blueprint Registration
# ===============================

def register_blueprints(app):
    """Register all route blueprints."""
    from routes.health_routes import health_bp, versioned_health_bp
    from routes.profile_routes import profile_bp
    from routes.bom_routes import bom_bp
    from routes.sku_catalog_routes import sku_catalog_bp

    # Keep /health for Cloud Run probes AND expose /api/v1/health so a
    # second API consumer can hit the versioned namespace consistently.
    app.register_blueprint(health_bp)
    app.register_blueprint(versioned_health_bp, url_prefix='/api/v1')
    app.register_blueprint(profile_bp,     url_prefix='/api/v1/profiles')
    app.register_blueprint(bom_bp,         url_prefix='/api/v1/bom')
    app.register_blueprint(sku_catalog_bp, url_prefix='/api/v1/sku-catalog')


# ===============================
# Auth Middleware (Shared Secret)
# ===============================

# Paths that bypass the shared-secret check — health probes and the app
# root only. Everything under /api/v1/bom and /api/v1/profiles requires
# the token.
_AUTH_EXEMPT_PATHS = {'/health', '/api/v1/health', '/'}


def register_auth_middleware(app):
    """
    Require X-Procalcs-Service-Token on every non-health request.
    The shared secret is read from SERVICE_SHARED_SECRET. If the
    secret is empty (dev / misconfigured deploy), the middleware
    fails open with a loud warning so local dev still works.
    """
    logger = logging.getLogger('procalcs_bom')

    @app.before_request
    def _verify_service_token():
        # Short-circuit CORS preflight so browsers can negotiate.
        if request.method == 'OPTIONS':
            return None

        if request.path in _AUTH_EXEMPT_PATHS:
            return None

        expected = app.config.get('SERVICE_SHARED_SECRET', '') or ''
        if not expected:
            # Dev fallback — already warned at startup in validate_config.
            return None

        presented = request.headers.get('X-Procalcs-Service-Token', '')
        if presented != expected:
            client_id = request.headers.get('X-Client-Id', 'unknown')
            logger.warning(
                "Unauthorized request — path=%s client_id=%s",
                request.path, client_id,
            )
            return jsonify({
                "success": False,
                "data": None,
                "error": "unauthorized",
            }), 401

        # Attribution log so multi-client traffic is distinguishable
        # in Cloud Run logs without needing a full request-ID system.
        client_id = request.headers.get('X-Client-Id')
        if client_id:
            logger.info("request client_id=%s path=%s", client_id, request.path)
        return None


# ===============================
# Entry Point (local dev only)
# ===============================

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=app.debug)
