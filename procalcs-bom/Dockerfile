# ==================================================
# ProCalcs BOM — Dockerfile
# Deploys to Google Cloud Run
# Build: gcloud run deploy procalcs-bom --source . --region us-east1
# ==================================================

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer caching)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy frontend build output (built separately by CI/CD)
COPY frontend/dist/ ./frontend/dist/

# Environment defaults (overridden by Cloud Run env vars)
ENV FLASK_ENV=production
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8080", \
     "--workers", "2", "--threads", "4", "--timeout", "120", \
     "backend.app:create_app()"]
