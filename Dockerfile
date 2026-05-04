# v0.5.13: multi-stage container image for Agented.
#
# Build context MUST be the PARENT directory of Agented so the
# sibling `ai-accounts/` repo is reachable. Both backend
# (`pyproject.toml`) and frontend (`package.json`) reference
# `../../ai-accounts/packages/*` as path deps, which can't be
# resolved without the sibling tree present.
#
# Build invocation:
#   cd ..
#   docker build -f Agented/Dockerfile -t agented:latest .
#
# Or via just:
#   just docker-build
#
# Or via docker compose (compose file declares build.context: ..):
#   just docker-up

ARG PYTHON_VERSION=3.12

# Stage 1 — frontend builder (resolves @ai-accounts/* file: deps)
FROM node:20-alpine AS frontend-builder
WORKDIR /build
# Copy ai-accounts source so the file: deps in package.json resolve.
COPY ai-accounts/ /build/ai-accounts/
# Build ai-accounts packages so their dist/ is populated. Frontend
# imports from @ai-accounts/*/dist (per package main/module/exports).
RUN for pkg in ts-core vue-headless vue-styled; do \
        if [ -d "/build/ai-accounts/packages/$pkg" ]; then \
            (cd "/build/ai-accounts/packages/$pkg" && npm install --ignore-scripts && npm run build); \
        fi; \
    done
# Now bring in Agented frontend and build it.
COPY Agented/frontend/package.json Agented/frontend/package-lock.json* /build/Agented/frontend/
WORKDIR /build/Agented/frontend
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY Agented/frontend/ /build/Agented/frontend/
RUN npm run build

# Stage 2 — backend deps builder
FROM python:${PYTHON_VERSION}-slim AS backend-builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /build
# Copy ai-accounts so the file:../../ path deps resolve.
COPY ai-accounts/ /build/ai-accounts/
COPY Agented/backend/pyproject.toml Agented/backend/uv.lock* /build/Agented/backend/
WORKDIR /build/Agented/backend
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Stage 3 — runtime
FROM python:${PYTHON_VERSION}-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENTED_ENV=production \
    GUNICORN_BIND=0.0.0.0:20000 \
    AGENTED_DB_PATH=/app/data/agented.db
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# Bring deps from the builder stage.
COPY --from=backend-builder /build/Agented/backend/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"
# Backend source.
COPY Agented/backend/ /app/backend/
# Frontend dist (served as static assets).
COPY --from=frontend-builder /build/Agented/frontend/dist /app/frontend/dist
# Persistent data dir (volume-mounted in compose).
RUN mkdir -p /app/data && chown -R nobody:nogroup /app/data || true

WORKDIR /app/backend

EXPOSE 20000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python scripts/healthcheck.py --liveness-only || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py"]
