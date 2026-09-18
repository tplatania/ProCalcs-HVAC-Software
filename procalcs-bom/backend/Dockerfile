# BOM backend runtime image.
#
# Why this exists (2026-09-18): the service was previously built by
# Cloud Run's buildpacks with NO build manifest. Every good deploy
# actually rode a cached dependency layer from an older base image
# (Python 3.12 + system libs present). When a source change invalidated
# that cache, a fresh buildpack build fell onto the google-24 base and
# broke two ways: (1) Pillow tried to compile from source under the new
# default Python 3.14 (no wheel, missing zlib headers); (2) weasyprint
# could not load libpango — the runtime base does not ship it. Buildpacks
# cannot install OS packages, so we pin the environment explicitly here.
#
# python:3.13-slim gives cp313 wheels for Pillow 10.4.0 (no source build)
# and apt for weasyprint's shared libraries.
FROM python:3.13-slim-bookworm

# weasyprint 63 renders via Pango/HarfBuzz/Fontconfig (cairo/gdk-pixbuf
# were dropped upstream but a couple of transitive libs + base fonts keep
# PDF output correct across environments).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libharfbuzz-subset0 \
        libfontconfig1 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Cloud Run sets $PORT (8080). App uses the factory pattern — `app` only
# exists inside create_app(), so gunicorn must call the factory.
ENV PORT=8080
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 "app:create_app()"
