# Default recipe - show available commands
default:
    @just --list

# Setup everything (backend + frontend)
setup: setup-backend setup-frontend

# Setup backend dependencies
setup-backend:
    cd backend && uv sync

# Setup frontend dependencies
setup-frontend:
    cd frontend && npm install

# Build frontend for production
build:
    cd frontend && npm run build

# Run backend API server (development mode, port 20000)
dev-backend:
    cd backend && uv run python run.py --debug

# Run frontend dev server (port 3000)
dev-frontend:
    cd frontend && npm run dev

# Deploy: build frontend, then start both servers
# Frontend: http://localhost:3000 | Backend API: http://localhost:20000
deploy: kill build
    @echo "Starting backend on port 20000 and frontend on port 3000..."
    @echo "Frontend: http://localhost:3000"
    @echo "Backend API: http://localhost:20000"
    @echo ""
    cd backend && uv run python run.py &
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
