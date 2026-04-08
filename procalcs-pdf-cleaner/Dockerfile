# ==================================================
# ProCalcs PDF Cleaner — Dockerfile (Cloud Run)
# Build: gcloud run deploy procalcs-hvac-cleaner --source . --region us-east1
# ==================================================

FROM python:3.12-slim

# Install dependencies first (layer caching)
WORKDIR /install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Flat imports (`from config import Config`) — run from inside backend/.
WORKDIR /app
COPY backend/ ./

# Cloud Run injects $PORT
ENV PORT=8080
ENV FLASK_ENV=production
ENV LOG_LEVEL=INFO

# ezdxf needs writable upload + temp dirs (the app creates them at startup,
# but we ensure permissions here).
RUN mkdir -p /app/uploads /app/temp

EXPOSE 8080

CMD exec gunicorn --bind 0.0.0.0:${PORT} \
    --workers 2 --threads 4 --timeout 300 \
    "app:create_app()"
