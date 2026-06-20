set shell := ["bash", "-lc"]

# Path to local ai-accounts monorepo for dev-link mode.
# Default is `../ai-accounts` (sibling of Agented). Override with:
#   AI_ACCOUNTS_PATH=/abs/path just dev-link-ai-accounts
ai_accounts_path := env_var_or_default("AI_ACCOUNTS_PATH", "../ai-accounts")
REQUIRED_NODE_MAJOR := "22"

# Default recipe - show available commands
default:
    @just --list

# Full bootstrap: install prerequisites + project dependencies (safe to re-run)
bootstrap:
    bash scripts/setup.sh

# Check that required tools are installed
check-prereqs: ensure-node
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

# Ensure Node.js meets minimum version (auto-installs/switches via nvm)
# Writes .node-path for other recipes to source
[private]
ensure-node:
    #!/usr/bin/env bash
    set -euo pipefail
    REQUIRED={{REQUIRED_NODE_MAJOR}}
    NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    # Find nvm-installed node >= REQUIRED without sourcing nvm (avoids npmrc prefix conflict)
    find_nvm_node() {
        local versions_dir="$NVM_DIR/versions/node"
        [ -d "$versions_dir" ] || return 1
        local best=""
        for d in "$versions_dir"/v${REQUIRED}.*; do
            [ -x "$d/bin/node" ] && best="$d/bin"
        done
        [ -n "$best" ] && echo "$best"
    }
    # Check current node version
    CURRENT=$(node -v 2>/dev/null | sed 's/^v//' | cut -d. -f1)
    if [ -n "$CURRENT" ] && [ "$CURRENT" -ge "$REQUIRED" ] 2>/dev/null; then
        # Already good — write current node path for consistency
        echo "export PATH=\"$(dirname "$(which node)"):\$PATH\"" > .node-path
        exit 0
    fi
    # Check if nvm already has the right version installed
    NVM_NODE_BIN=$(find_nvm_node)
    if [ -n "$NVM_NODE_BIN" ]; then
        echo "Found Node.js $("$NVM_NODE_BIN/node" -v) via nvm"
        echo "export PATH=\"$NVM_NODE_BIN:\$PATH\"" > .node-path
        exit 0
    fi
    # Need to install via nvm — temporarily remove npmrc prefix that conflicts with nvm
    echo "Node.js v${CURRENT:-not found} detected — need v${REQUIRED}+"
    NPMRC="$HOME/.npmrc"
    HAD_PREFIX=0
    if [ -f "$NPMRC" ] && grep -q '^prefix=' "$NPMRC"; then
        HAD_PREFIX=1
        sed -i.nvmbak '/^prefix=/d' "$NPMRC"
    fi
    restore_npmrc() {
        if [ "$HAD_PREFIX" -eq 1 ] && [ -f "$NPMRC.nvmbak" ]; then
            mv "$NPMRC.nvmbak" "$NPMRC"
        else
            rm -f "$NPMRC.nvmbak"
        fi
    }
    trap restore_npmrc EXIT
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        source "$NVM_DIR/nvm.sh"
    fi
    if type nvm &>/dev/null; then
        echo "Installing Node.js $REQUIRED via nvm..."
        nvm install "$REQUIRED"
        NVM_NODE_BIN=$(find_nvm_node)
        echo "export PATH=\"$NVM_NODE_BIN:\$PATH\"" > .node-path
        echo "Installed Node.js $("$NVM_NODE_BIN/node" -v)"
    else
        echo "ERROR: nvm not found. Install Node.js >= $REQUIRED manually, or install nvm:"
        echo "  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash"
        exit 1
    fi

# Source the correct node version into PATH (used as prefix in recipes)
[private]
use-node := "[ -f .node-path ] && source .node-path;"

# Setup everything (backend + frontend) — requires uv and node/npm
setup: check-prereqs setup-backend setup-frontend

# Setup backend dependencies
setup-backend:
    cd backend && uv sync

# Setup frontend dependencies
setup-frontend: ensure-node
    {{use-node}} cd frontend && npm install

# Install frontend node_modules if missing
[private]
ensure-frontend: ensure-node
    #!/usr/bin/env bash
    [ -f .node-path ] && source .node-path
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
    {{use-node}} cd frontend && npm run build

# Lint gate — ruff check + format-check on the backend. Run before pushing.
# (Wired in v0.6 hardening: ruff was installed but never gated, so 350+ lint
# violations + 190 unformatted files had accumulated. Keep this green.)
lint: ensure-backend
    cd backend && uv run ruff check . && uv run ruff format --check .

# Auto-fix what ruff can (imports, sorting) + format the backend in place.
lint-fix: ensure-backend
    cd backend && uv run ruff check . --fix && uv run ruff format .

# Run Litestar backend API server (development mode, port 20000).
# Wave 80: Flask is retired; Litestar serves :20000 directly via uvicorn.
dev-backend: ensure-backend
    cd backend && uv run python run.py --debug

# Run frontend dev server (port 3000)
# Rebuild ai-accounts/* dist before starting Vite. Without this, edits to
# ai-accounts/packages/*/src/ are invisible until each package's `npm run
# build` regenerates dist/ — Vite consumes the file: pinned packages via
# their compiled `module` entry. If `just deploy` already rebuilt and the
# dist mtime is newer than the most-recent src mtime, the rebuild is a no-op.
ai-accounts-dist-fresh:
    #!/usr/bin/env bash
    set -uo pipefail
    if [ ! -d "{{ai_accounts_path}}/packages" ]; then
        echo "[dist-fresh] ai-accounts not found at {{ai_accounts_path}} — skipping"
        exit 0
    fi
    for pkg in ts-core vue-headless vue-styled; do
        pkg_dir="{{ai_accounts_path}}/packages/$pkg"
        [ -d "$pkg_dir" ] || continue
        # Compare newest src/* mtime to oldest dist/* mtime.
        latest_src=$(find "$pkg_dir/src" -type f -newer "$pkg_dir/dist" -print 2>/dev/null | head -n1)
        if [ -z "$latest_src" ]; then
            echo "[dist-fresh] $pkg dist is up to date"
            continue
        fi
        echo "[dist-fresh] rebuilding @ai-accounts/$pkg (src newer than dist)..."
        (cd "$pkg_dir" && npm run build) || { echo "[dist-fresh] $pkg build failed" >&2; exit 1; }
    done
    # Vite caches bundled file: deps in .vite/deps; clear so the rebuilt
    # output is picked up on next page load.
    rm -rf frontend/node_modules/.vite

dev-frontend: ensure-frontend ai-accounts-dist-fresh
    {{use-node}} cd frontend && npm run dev

# Run ai-accounts Litestar API server (development mode, port 20001)
dev-ai-accounts: ensure-backend
    cd backend && uv run python scripts/run_ai_accounts.py

# Run all three dev servers in parallel (Litestar :20000, ai-accounts sidecar :20001, Vite :3000)
dev-all:
    just kill
    just dev-backend & just dev-ai-accounts & just dev-frontend & wait

# Run the standalone usage daemon in the foreground (token/cost collection +
# rate-limit polling, 24/7, independent of the web backend). Ctrl-C to stop.
usage-daemon: ensure-backend
    cd backend && uv run python scripts/run_usage_daemon.py

# Install + load the usage daemon as a macOS LaunchAgent so tracking runs
# continuously regardless of whether the web app is open. Idempotent.
usage-daemon-install:
    #!/usr/bin/env bash
    set -euo pipefail
    repo="$(pwd)"
    dst="$HOME/Library/LaunchAgents/com.agented.usage-daemon.plist"
    sed "s#REPLACE_ME_REPO_PATH#${repo}#g" scripts/launchd/com.agented.usage-daemon.plist > "$dst"
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    echo "Loaded com.agented.usage-daemon — logs: backend/usage-daemon.log"
    echo "If you also run the web backend, set AGENTED_EXTERNAL_USAGE_DAEMON=1 in its env."

# Stop + remove the usage daemon LaunchAgent.
usage-daemon-uninstall:
    #!/usr/bin/env bash
    dst="$HOME/Library/LaunchAgents/com.agented.usage-daemon.plist"
    launchctl unload "$dst" 2>/dev/null || true
    rm -f "$dst"
    echo "Unloaded + removed com.agented.usage-daemon."

# v0.5.13: validate required env vars (fail loudly on missing).
check-env:
    cd backend && uv run python -m scripts.check_env

# v0.5.13: probe backend liveness/readiness + sidecar; exits nonzero on red.
healthcheck:
    cd backend && uv run python scripts/healthcheck.py

# v0.5.13: build the production container image. Build context is the
# PARENT directory so the sibling ai-accounts/ tree is reachable.
docker-build:
    cd .. && docker build -f Agented/Dockerfile -t agented:latest .

# v0.5.13: bring the production stack up (backend + sidecar).
docker-up:
    docker compose up -d
    @echo "Stack up. Logs: just docker-logs"

# v0.5.13: tear the stack down.
docker-down:
    docker compose down

# v0.5.13: tail logs from both services.
docker-logs:
    docker compose logs -f

# v0.5.15: trigger a snapshot from inside the running backend container.
# Writes to the agented-backups volume (mounted at /app/backups).
docker-backup:
    docker compose exec agented-backend python scripts/backup.py

# v0.6.0: hit running server N times per endpoint; report p50/p95.
profile *args:
    cd backend && uv run python scripts/profile.py {{args}}

# v0.6.0: audit SQLite indices + EXPLAIN-QUERY-PLAN of hot queries.
db-audit *args:
    cd backend && uv run python scripts/db_audit.py {{args}}

# v0.5.15: snapshot both SQLite DBs to AGENTED_BACKUP_DIR + apply
# retention + optional remote sync via BACKUP_REMOTE_CMD.
backup:
    cd backend && uv run python scripts/backup.py

# v0.5.15: restore from a snapshot. Stop the service first.
restore:
    cd backend && uv run python scripts/restore.py

# v0.5.13: production deploy recipe. Distinct from `just deploy` (dev).
# Validates env, builds frontend, kills, starts sidecar + gunicorn daemonized.
# Sidecar readiness wait has a 60s timeout so a crashed sidecar fails loudly
# instead of hanging the recipe forever.
deploy-prod: kill check-env build
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .node-path ] && source .node-path
    echo "Frontend (built): {{justfile_directory()}}/frontend/dist"
    echo "Backend API: http://localhost:20000"
    echo "Sidecar:     http://localhost:20001"
    (cd backend && nohup uv run python scripts/run_ai_accounts.py >sidecar.log 2>&1 &)
    SIDECAR_TIMEOUT=60
    for i in $(seq 1 $SIDECAR_TIMEOUT); do
      if curl -sf http://127.0.0.1:20001/health >/dev/null 2>&1; then
        break
      fi
      if [ "$i" -eq "$SIDECAR_TIMEOUT" ]; then
        echo "ERROR: sidecar did not become ready within ${SIDECAR_TIMEOUT}s." >&2
        echo "Check backend/sidecar.log for the failure cause." >&2
        exit 1
      fi
      sleep 1
    done
    echo "Sidecar ready (logs: backend/sidecar.log)"
    (cd backend && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES nohup uv run gunicorn -c gunicorn.conf.py >backend.log 2>&1 &)
    sleep 2
    echo "Backend started (logs: backend/backend.log)"
    echo "Run \`just healthcheck\` to verify."

# Deploy: build frontend, then start sidecar + backend + frontend dev server
# Frontend: http://localhost:3000 | Backend API: http://localhost:20000 | Sidecar: http://localhost:20001
deploy: kill ensure-backend build
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .node-path ] && source .node-path
    # Rebuild locally-linked @ai-accounts/* packages — they are consumed via
    # `dist/` (per their package.json `main`/`module`/`exports`), so source
    # edits to ai-accounts are invisible until each package's `npm run build`
    # regenerates dist/. Skip the rebuild and you ship stale wizard code.
    if [ -d "{{ai_accounts_path}}/packages" ]; then
      for pkg in ts-core vue-headless vue-styled; do
        if [ -d "{{ai_accounts_path}}/packages/$pkg" ]; then
          echo "Rebuilding @ai-accounts/$pkg..."
          (cd "{{ai_accounts_path}}/packages/$pkg" && npm run build)
        fi
      done
    fi
    # Clear Vite's dep cache so the freshly-rebuilt @ai-accounts/* packages
    # (file:../../ai-accounts/packages/*) are re-bundled on every deploy.
    # Vite treats file: deps as library code and caches them aggressively.
    rm -rf frontend/node_modules/.vite
    echo "Frontend: http://localhost:3000"
    echo "Backend API: http://localhost:20000"
    echo "Sidecar: http://localhost:20001"
    (cd backend && uv run python scripts/run_ai_accounts.py) &
    while ! curl -sf http://127.0.0.1:20001/health >/dev/null 2>&1; do sleep 0.5; done
    echo "Sidecar ready."
    (cd backend && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run gunicorn -c gunicorn.conf.py) &
    BACKEND_PID=$!
    # Don't wait on backend readiness — single gevent worker is blocked during
    # startup (OAuth, cookie extraction). Vite proxies requests and will
    # resolve once init finishes.
    sleep 2
    echo "Backend starting (pid $BACKEND_PID)..."
    cd frontend && exec npm run dev

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

# Reset onboarding: wipe DBs + per-account isolation dirs, restart fresh
# (localStorage auto-clears on welcome page). The sidecar owns
# ai_accounts.db and backend_dirs/bkd-*; wiping only agented.db left the
# wizard "already has accounts" state intact and CLI auth still valid.
reset: kill
    rm -f backend/agented.db backend/agented.db-wal backend/agented.db-shm
    rm -f backend/ai_accounts.db backend/ai_accounts.db-wal backend/ai_accounts.db-shm
    rm -rf backend/backend_dirs
    @echo "Reset complete. Run: just deploy"

# Clean build artifacts
clean:
    rm -rf frontend/dist
    rm -rf backend/*.db

# View API docs URL
docs:
    @echo "API docs: http://localhost:20000/docs"

# Verify all required CLIs are installed at supported versions
# Run before reporting bugs; if any line says "MISSING" or "OLD" the wizard
# will fail at that backend's login step.
doctor:
    #!/usr/bin/env bash
    set -uo pipefail
    fail=0
    check() {
        local name="$1" min="$2" cmd="$3"
        local ver
        if ! command -v "$name" >/dev/null 2>&1; then
            printf "  %-15s %s\n" "$name" "MISSING (need ≥ $min)"
            fail=1
            return
        fi
        ver="$(eval "$cmd" 2>&1 | head -n1 | tr -d '\r')"
        printf "  %-15s %s (need ≥ %s)\n" "$name" "${ver:-?}" "$min"
    }
    echo "== AI backend CLIs =="
    check claude       "2.1.0"   'claude --version 2>&1'
    check codex        "0.121.0" 'codex --version 2>&1'
    check gemini       "0.35.0"  'gemini --version 2>&1'
    check opencode     "0.4.0"   'opencode --version 2>&1'
    check cliproxyapi  "0.16.0"  'cliproxyapi --version 2>&1 || echo "(install: see https://github.com/cliproxyapi)"'
    echo
    echo "== Toolchain =="
    check node         "v22"     'node --version'
    check npm          "10"      'npm --version'
    check uv           "0.5"     'uv --version 2>&1'
    check just         "1.30"    'just --version'
    echo
    echo "== Ports =="
    if lsof -ti:20000 >/dev/null 2>&1; then echo "  20000 (Litestar) — IN USE"; else echo "  20000 (Litestar) — free"; fi
    if lsof -ti:20001 >/dev/null 2>&1; then echo "  20001 (sidecar) — IN USE"; else echo "  20001 (sidecar) — free"; fi
    if lsof -ti:3000  >/dev/null 2>&1; then echo "  3000  (Vite)    — IN USE"; else echo "  3000  (Vite)    — free"; fi
    exit "$fail"

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
