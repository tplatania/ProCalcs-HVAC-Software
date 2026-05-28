# ==================================================
# ProCalcs BOM — Dockerfile (Cloud Run)
# Build: gcloud run deploy procalcs-hvac-bom --source . --region us-east1
# ==================================================

FROM python:3.12-slim

# WeasyPrint (used by the branded BOM PDF renderer) needs Cairo,
# Pango, GDK-Pixbuf, and the MIME / font tables at runtime. Install
# them once before pip so the layer stays cached across rebuilds.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libcairo2 \
      libgdk-pixbuf-2.0-0 \
      shared-mime-info \
      fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer caching)
WORKDIR /install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The Flask app uses flat imports (`from config import Config`), so we run
# from inside the backend directory and import `app:create_app` directly.
WORKDIR /app
COPY backend/ ./

# Cloud Run sets PORT, default to 8080 for local docker run
ENV PORT=8080
ENV FLASK_ENV=production

EXPOSE 8080

# Run pending Alembic migrations on container start, then launch
# gunicorn. `flask db upgrade` is idempotent — alembic checks the
# current revision in the alembic_version table and no-ops when
# everything's applied. Failures here fail the container start so a
# bad migration doesn't get masked by a 'service running' status.
#
# Day-13 — moved migrations into the runtime path because the
# discovered_mappings (d2c1a8f4e7b0) and contractor_overrides
# (e9b7c1a3f8d2) tables are required by the new features and
# Cloud Run deploys without manual migration steps would have served
# traffic against the old schema.
CMD set -e; \
    FLASK_APP=app.py flask db upgrade; \
    exec gunicorn --bind 0.0.0.0:${PORT} \
        --workers 2 --threads 4 --timeout 120 \
        "app:create_app()"
