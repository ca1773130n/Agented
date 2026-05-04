# v0.5.13: multi-stage container image for Agented.
#
# Builds frontend → installs backend deps → ships a slim runtime that
# serves Litestar via gunicorn on :20000. Frontend dist is served as
# static assets by the backend in container mode (no separate Vite).

# Stage 1 — frontend builder
FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# ai-accounts is a sibling repo in dev; for container builds we install
# the version pinned in package-lock without the file: redirect.
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY frontend/ .
RUN npm run build

# Stage 2 — backend deps builder
FROM python:3.10-slim AS backend-builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /build
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Stage 3 — runtime
FROM python:3.10-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENTED_ENV=production \
    GUNICORN_BIND=0.0.0.0:20000
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Bring deps from the builder stage.
COPY --from=backend-builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"
# Backend source.
COPY backend/ ./backend/
# Frontend dist (served as static assets).
COPY --from=frontend-builder /build/dist /app/frontend/dist

WORKDIR /app/backend

EXPOSE 20000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python scripts/healthcheck.py || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py"]
