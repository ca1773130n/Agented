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

# Deploy: build frontend, then start both servers via Gunicorn
# Frontend: http://localhost:3000 | Backend API: http://localhost:20000
deploy: kill ensure-backend build
    @echo "Starting backend via Gunicorn on port 20000..."
    @echo "Frontend: http://localhost:3000"
    @echo "Backend API: http://localhost:20000"
    @echo ""
    cd backend && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run gunicorn -c gunicorn.conf.py &
    cd frontend && npm run dev

# Run both dev servers (requires terminal multiplexer)
dev:
    @echo "Run 'just dev-backend' and 'just dev-frontend' in separate terminals"
    @echo "Frontend: http://localhost:3000"
    @echo "Backend API: http://localhost:20000"

# Kill any existing frontend/backend processes
kill:
    -lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    -lsof -ti:20000 | xargs kill -9 2>/dev/null || true
    -pkill -f "npm run dev" 2>/dev/null || true
    -pkill -f "vite" 2>/dev/null || true

# Clean build artifacts
clean:
    rm -rf frontend/dist
    rm -rf backend/*.db

# View API docs URL
docs:
    @echo "API docs: http://localhost:20000/docs"
