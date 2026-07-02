# v0.5.13: multi-stage container image for Agented.
#
# Build context MUST be the PARENT directory of Agented so the
# sibling `ai-accounts/` repo is reachable — the image `COPY`s
# `ai-accounts/` at build time. (The backend `pyproject.toml` and
# frontend `package.json` now use published registry deps, but the
# build still needs the sibling tree present.)
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
# pnpm is required because ai-accounts is a pnpm workspace using
# `workspace:*` cross-package deps. plain npm cannot resolve those.
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /build
# Copy ai-accounts source so the file: deps in Agented's package.json
# resolve.
COPY ai-accounts/ /build/ai-accounts/
# Install + build ai-accounts packages via pnpm so workspace:* deps
# resolve. The frontend imports from @ai-accounts/*/dist (per each
# package's main/module/exports).
WORKDIR /build/ai-accounts
RUN pnpm install --frozen-lockfile --ignore-scripts || pnpm install --ignore-scripts
RUN pnpm -r --filter "@ai-accounts/ts-core" --filter "@ai-accounts/vue-headless" --filter "@ai-accounts/vue-styled" run build
# Now bring in Agented frontend and build it via npm (its own package.json).
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
# Copy ai-accounts so the file:../../ path deps resolve. autoresearch-core is
# now a published PyPI dependency (>=0.1.1), resolved by uv from the registry —
# no local source copy needed.
COPY ai-accounts/ /build/ai-accounts/
COPY Agented/backend/pyproject.toml Agented/backend/uv.lock* /build/Agented/backend/
WORKDIR /build/Agented/backend
RUN uv sync --frozen --no-dev --no-editable || uv sync --no-dev --no-editable

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
