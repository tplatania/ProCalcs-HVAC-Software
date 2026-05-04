"""
extensions.py — Flask extension singletons.

Kept in a separate module so model files can import `db` without pulling
in the whole app factory (avoids circular imports between app.py, models,
and routes).

Pattern matches Ask-Your-HVAC-Pro's `backend/config.py::db` usage but
moves the singleton out of config to keep config purely declarative.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialized in app.py via init_app(app). Models import `db` from here
# and define classes against db.Model.
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()
