set shell := ["bash", "-lc"]

# Path to local ai-accounts monorepo for dev-link mode.
# Default is `../ai-accounts` (sibling of Agented). Override with:
#   AI_ACCOUNTS_PATH=/abs/path just dev-link-ai-accounts
ai_accounts_path := env_var_or_default("AI_ACCOUNTS_PATH", "../ai-accounts")

# Default recipe - show available commands
default:
    @just --list

# Full bootstrap: install prerequisites + project dependencies (safe to re-run)
bootstrap:
    bash scripts/setup.sh

# Check that required tools are installed
check-prereqs:
    #!/usr/bin/env bash
    set -euo pipefail
    missing=0
    for cmd in uv node npm; do
        if ! command -v "$cmd" &>/dev/null; then
            echo "✗ $cmd not found"
            missing=1
        else
            echo "✓ $cmd found"
        fi
    done
    if [ "$missing" -eq 1 ]; then
        echo ""
        echo "Run 'bash scripts/setup.sh' or 'just bootstrap' to install missing prerequisites."
        exit 1
    fi

# Setup everything (backend + frontend) — requires uv and node/npm
setup: check-prereqs setup-backend setup-frontend

# Setup backend dependencies
setup-backend:
    cd backend && uv sync

# Setup frontend dependencies
setup-frontend:
    cd frontend && npm install

# Install frontend node_modules if missing
[private]
ensure-frontend:
    #!/usr/bin/env bash
    if [ ! -d frontend/node_modules ]; then
        echo "node_modules not found — running npm install..."
        cd frontend && npm install
    fi

# Install backend .venv if missing
[private]
ensure-backend:
    #!/usr/bin/env bash
    if [ ! -d backend/.venv ]; then
        echo ".venv not found — running uv sync..."
        cd backend && uv sync
    fi

# Build frontend for production
build: ensure-frontend
    cd frontend && npm run build

# Run backend API server (development mode, port 20000)
dev-backend: ensure-backend
    cd backend && uv run python run.py --debug

# Run frontend dev server (port 3000)
dev-frontend: ensure-frontend
    cd frontend && npm run dev

# Run ai-accounts Litestar API server (development mode, port 20001)
dev-ai-accounts: ensure-backend
    cd backend && uv run python scripts/run_ai_accounts.py

# Run all three dev servers in parallel (Flask :20000, Litestar :20001, Vite :3000)
dev-all:
    just kill
    just dev-backend & just dev-ai-accounts & just dev-frontend & wait

# Deploy: build frontend, then start both servers via Gunicorn
# Frontend: http://localhost:3000 | Backend API: http://localhost:20000
deploy: kill ensure-backend build
    @echo "Starting backend via Gunicorn on port 20000..."
    @echo "Frontend: http://localhost:3000"
    @echo "Backend API: http://localhost:20000"
    @echo ""
    cd backend && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run gunicorn -c gunicorn.conf.py &
    @while ! curl -sf http://127.0.0.1:20000/health/readiness >/dev/null 2>&1; do sleep 1; done; echo "Backend ready."
    cd frontend && npm run dev

# Run both dev servers (requires terminal multiplexer)
dev:
    @echo "Run 'just dev-backend' and 'just dev-frontend' in separate terminals"
    @echo "Frontend: http://localhost:3000"
    @echo "Backend API: http://localhost:20000"

# Generate an API key for authentication
generate-key *ARGS: ensure-backend
    cd backend && uv run python scripts/generate_key.py {{ARGS}}

# Kill only this project's dev processes (port-scoped; will NOT touch other vite/node projects)
kill:
    -lsof -ti:3000,20000,20001 2>/dev/null | xargs -r kill -9 2>/dev/null || true

# Reset onboarding: wipe DB, restart fresh (localStorage auto-clears on welcome page)
reset: kill
    rm -f backend/agented.db backend/agented.db-wal backend/agented.db-shm
    @echo "Reset complete. Run: just deploy"

# Clean build artifacts
clean:
    rm -rf frontend/dist
    rm -rf backend/*.db

# View API docs URL
docs:
    @echo "API docs: http://localhost:20000/docs"

# -----------------------------------------------------------------------------
# ai-accounts dev-link: point frontend + backend at a local ai-accounts clone
# without editing package.json / pyproject.toml. Manifests stay pinned to the
# published versions (production default); this only affects node_modules and
# the backend venv.
#
# Workflow:
#   just dev-link-ai-accounts    # switch to local clone
#   just dev-backend             # restart backend, picks up local code
#   just dev-frontend            # vite HMR picks up local ts-core/vue-* code
#   ...iterate in the other session on /Users/neo/Developer/Projects/ai-accounts...
#   just dev-unlink-ai-accounts  # revert to published versions
# -----------------------------------------------------------------------------

# Install the local ai-accounts clone into Agented's node_modules + backend venv
# in-place (no manifest edits). Override location with AI_ACCOUNTS_PATH=/abs/path.
dev-link-ai-accounts:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d "{{ai_accounts_path}}/packages/core" ]; then
        echo "✗ ai-accounts not found at {{ai_accounts_path}}"
        echo "  Override with: AI_ACCOUNTS_PATH=/abs/path just dev-link-ai-accounts"
        exit 1
    fi
    AIA="$(cd "{{ai_accounts_path}}" && pwd)"
    echo "→ Linking ai-accounts from $AIA"

    # Build TS packages so their dist/ is current before linking
    (cd "$AIA" && pnpm -r --filter '@ai-accounts/*' build)

    # Frontend: --no-save so package.json keeps its published version pin
    echo "→ Frontend: npm install --no-save (local paths)"
    (cd frontend && npm install --no-save \
        "$AIA/packages/ts-core" \
        "$AIA/packages/vue-headless" \
        "$AIA/packages/vue-styled")

    # Backend: editable install into the venv, no pyproject.toml/uv.lock edits
    echo "→ Backend: uv pip install --force-reinstall --no-deps -e (editable)"
    (cd backend && uv pip install --force-reinstall --no-deps \
        -e "$AIA/packages/core" \
        -e "$AIA/packages/litestar")

    echo ""
    echo "✓ ai-accounts dev-linked. Restart dev servers to pick up changes:"
    echo "    just kill && just dev-backend &"
    echo "    just dev-frontend"

# Restore Agented to the published ai-accounts packages pinned in the manifests.
dev-unlink-ai-accounts:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "→ Frontend: npm install (restores published versions)"
    (cd frontend && npm install)
    echo "→ Backend: uv sync --reinstall-package ai-accounts-core --reinstall-package ai-accounts-litestar"
    (cd backend && uv sync --reinstall-package ai-accounts-core --reinstall-package ai-accounts-litestar)
    echo ""
    echo "✓ ai-accounts restored to published versions. Restart dev servers."

# Report current ai-accounts dep source (published vs local editable)
dev-link-status:
    #!/usr/bin/env bash
    echo "=== frontend @ai-accounts/* ==="
    for pkg in ts-core vue-headless vue-styled; do
        if [ -e "frontend/node_modules/@ai-accounts/$pkg/package.json" ]; then
            ver=$(python3 -c "import json; print(json.load(open('frontend/node_modules/@ai-accounts/$pkg/package.json'))['version'])" 2>/dev/null || echo "?")
            # npm install --no-save leaves a realpath different from the symlink target
            real=$(cd "frontend/node_modules/@ai-accounts/$pkg" && pwd -P 2>/dev/null || echo "?")
            echo "  @ai-accounts/$pkg@$ver"
            echo "    realpath: $real"
        else
            echo "  @ai-accounts/$pkg  NOT INSTALLED"
        fi
    done
    echo ""
    echo "=== backend ai-accounts-* ==="
    (cd backend && uv pip show ai-accounts-core 2>/dev/null | grep -E '^(Name|Version|Location|Editable project location):' || echo "  ai-accounts-core NOT INSTALLED")
    echo ""
    (cd backend && uv pip show ai-accounts-litestar 2>/dev/null | grep -E '^(Name|Version|Location|Editable project location):' || echo "  ai-accounts-litestar NOT INSTALLED")
