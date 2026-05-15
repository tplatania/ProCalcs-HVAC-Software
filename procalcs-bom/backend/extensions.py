"""
extensions.py — Flask extension singletons.

Kept in a separate module so model files can import `db` without pulling
in the whole app factory (avoids circular imports between app.py, models,
and routes).

Pattern matches Ask-Your-HVAC-Pro's `backend/config.py::db` usage but
moves the singleton out of config to keep config purely declarative.

Cloud SQL connection
====================
When ``INSTANCE_CONNECTION_NAME`` is set in env (Cloud Run staging /
prod), ``configure_db`` switches SQLAlchemy from a regular
``DATABASE_URL`` to the official google-cloud-sql-python-connector via
a creator callable. The connector handles IAM auth, mTLS, and
in-process connection pooling against the Cloud SQL Auth Proxy
sidecar that ``--add-cloudsql-instances`` mounts on Cloud Run.

Local dev / pytest still get the original SQLite-or-DATABASE_URL path
so nothing about test setup or local-only flows changes.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

logger = logging.getLogger("procalcs_bom.extensions")

# Initialized in app.py via init_app(app). Models import `db` from here
# and define classes against db.Model.
db: SQLAlchemy = SQLAlchemy()
migrate: Migrate = Migrate()

# Held at module level so we can close the connector cleanly if the
# process ever asks for shutdown (Cloud Run typically doesn't, but
# tests do). None until configure_db() decides we're in Cloud SQL mode.
_cloud_sql_connector: Optional[object] = None


def configure_db(app: Flask) -> None:
    """Init the SQLAlchemy engine. Two modes:

    1. Cloud SQL via Connector (production / Cloud Run staging) —
       triggered by INSTANCE_CONNECTION_NAME env var. Uses pg8000 +
       cloud-sql-python-connector for IAM-aware mTLS connections via
       the sidecar mounted by --add-cloudsql-instances. SQLAlchemy
       sees a `creator=` callable that returns one DBAPI connection
       per pool checkout.

    2. DATABASE_URL fallback (local dev, pytest, anywhere else) —
       app.config['SQLALCHEMY_DATABASE_URI'] is the standard URL
       (sqlite:///… or postgresql+pg8000://…). db.init_app() does
       its normal thing.
    """
    global _cloud_sql_connector

    instance_conn = app.config.get("INSTANCE_CONNECTION_NAME") or ""
    db_user       = app.config.get("DB_USER") or ""
    db_pass       = app.config.get("DB_PASS") or ""
    db_name       = app.config.get("DB_NAME") or ""

    use_cloud_sql = bool(instance_conn and db_user and db_name)

    if use_cloud_sql:
        # Lazy import — keeps the dependency optional for callers
        # that aren't on Cloud SQL (tests, local dev).
        try:
            from google.cloud.sql.connector import Connector, IPTypes
        except ImportError as exc:  # noqa: BLE001
            raise RuntimeError(
                "INSTANCE_CONNECTION_NAME is set but cloud-sql-python-connector "
                "isn't installed. Add `cloud-sql-python-connector[pg8000]` to "
                "requirements.txt."
            ) from exc

        _cloud_sql_connector = Connector()

        def _connect():
            """SQLAlchemy creator callable. Returns one pg8000 DBAPI
            connection per call; the connector manages mTLS + IAM."""
            return _cloud_sql_connector.connect(
                instance_conn,
                "pg8000",
                user=db_user,
                password=db_pass,
                db=db_name,
                # PRIVATE when running on Cloud Run with VPC; PUBLIC for
                # the staging path where Cloud Run sidecar handles the
                # connection. Default PUBLIC works for both via the
                # Cloud SQL Auth Proxy that --add-cloudsql-instances
                # mounts.
                ip_type=IPTypes.PUBLIC,
            )

        # Pass the creator into SQLAlchemy. The dialect URL has to be
        # provided so SQLAlchemy knows which Dialect class to use; the
        # actual URL host/port are ignored because creator wins.
        app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+pg8000://"
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "creator": _connect,
            # Modest pool — Cloud Run instance concurrency caps the
            # need; per-instance burst is rare.
            "pool_size": 5,
            "max_overflow": 2,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }
        logger.info(
            "Cloud SQL Connector active — instance=%s db=%s user=%s",
            instance_conn, db_name, db_user,
        )
    else:
        logger.info(
            "Cloud SQL not configured — using SQLALCHEMY_DATABASE_URI=%s",
            app.config.get("SQLALCHEMY_DATABASE_URI"),
        )

    db.init_app(app)


def shutdown_cloud_sql_connector() -> None:
    """Close the connector if one was created. Useful in tests; Cloud
    Run normally just kills the process."""
    global _cloud_sql_connector
    if _cloud_sql_connector is not None:
        try:
            _cloud_sql_connector.close()
        except Exception:  # noqa: BLE001
            pass
        _cloud_sql_connector = None
