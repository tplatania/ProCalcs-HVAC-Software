"""
ProCalcs PDF Cleaner — Flask Application Factory
"""

import os
import logging
from flask import Flask
from flask_cors import CORS

from config import Config


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    # ===============================
    # Logging Setup
    # ===============================
    log_level = getattr(logging, Config.LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger = logging.getLogger('pdf_cleaner')

    # ===============================
    # Startup Validation
    # ===============================
    Config.validate()

    # Ensure working directories exist
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.TEMP_FOLDER, exist_ok=True)

    # ===============================
    # Register Blueprints
    # ===============================
    from routes.health_routes import health_bp
    from routes.cleaner_routes import cleaner_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(cleaner_bp, url_prefix='/api/v1/tools')

    logger.info("PDF Cleaner started — port %s", Config.PORT)
    return app


if __name__ == '__main__':
    application = create_app()
    application.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=not Config.is_production()
    )
