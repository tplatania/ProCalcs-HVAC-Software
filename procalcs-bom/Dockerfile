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

# Use the shell form so $PORT is expanded at runtime (Cloud Run requires this).
CMD exec gunicorn --bind 0.0.0.0:${PORT} \
    --workers 2 --threads 4 --timeout 120 \
    "app:create_app()"
