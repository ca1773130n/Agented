set shell := ["bash", "-lc"]

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

# Run backend API server (development mode, port 20000)
dev-backend: ensure-backend
    cd backend && uv run python run.py --debug

# Run frontend dev server (port 3000)
dev-frontend: ensure-frontend
    {{use-node}} cd frontend && npm run dev

# Deploy: build frontend, then start both servers via Gunicorn
# Frontend: http://localhost:3000 | Backend API: http://localhost:20000
deploy: kill ensure-backend build
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f .node-path ] && source .node-path
    echo "Frontend: http://localhost:3000"
    echo "Backend API: http://localhost:20000"
    echo ""
    (cd backend && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run gunicorn -c gunicorn.conf.py) &
    BACKEND_PID=$!
    # Don't wait for readiness — the single gevent worker is blocked during
    # startup (OAuth, cookie extraction). Vite proxies to backend and will
    # serve the frontend immediately; API calls succeed once backend finishes init.
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

# Kill any existing frontend/backend processes
kill:
    -lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    -lsof -ti:20000 | xargs kill -9 2>/dev/null || true
    -pkill -f "npm run dev" 2>/dev/null || true
    -pkill -f "vite" 2>/dev/null || true

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
