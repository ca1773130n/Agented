#!/usr/bin/env bash
set -euo pipefail

# Bootstrap script for Agented — installs all prerequisites and project dependencies
# Run: bash scripts/setup.sh (or ./scripts/setup.sh after chmod +x)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }

command_exists() { command -v "$1" &>/dev/null; }

OS="$(uname -s)"

# ---------- Homebrew (macOS only) ----------
ensure_brew() {
    if [[ "$OS" != "Darwin" ]]; then return; fi
    if command_exists brew; then return; fi
    warn "Homebrew not found — installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
    info "Homebrew installed"
}

# ---------- just ----------
ensure_just() {
    if command_exists just; then
        info "just $(just --version 2>/dev/null | head -1) found"
        return
    fi
    warn "just not found — installing..."
    if [[ "$OS" == "Darwin" ]] && command_exists brew; then
        brew install just
    elif command_exists cargo; then
        cargo install just
    else
        curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
    fi
    info "just installed"
}

# ---------- uv ----------
ensure_uv() {
    if command_exists uv; then
        info "uv $(uv --version 2>/dev/null) found"
        return
    fi
    warn "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the env so uv is available in this session
    if [[ -f "$HOME/.local/bin/env" ]]; then
        source "$HOME/.local/bin/env" 2>/dev/null || true
    fi
    export PATH="$HOME/.local/bin:$PATH"
    info "uv installed"
}

# ---------- Node.js / npm ----------
ensure_node() {
    if command_exists node && command_exists npm; then
        info "Node.js $(node --version) found"
        return
    fi
    warn "Node.js not found — installing..."
    if [[ "$OS" == "Darwin" ]] && command_exists brew; then
        brew install node
    elif command_exists uv; then
        # uv can manage Node.js as a tool
        uv tool install node
    else
        error "Cannot auto-install Node.js. Please install it from https://nodejs.org/"
        exit 1
    fi
    info "Node.js installed"
}

# ---------- Python 3.10+ ----------
check_python() {
    # uv manages Python automatically via uv sync, just verify minimum version is available
    if command_exists python3; then
        local ver
        ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        info "Python $ver found (uv will manage project-specific version)"
    else
        warn "No system Python found — uv will download one automatically"
    fi
}

# ---------- Main ----------
echo ""
echo "=== Agented — Project Bootstrap ==="
echo ""

cd "$(dirname "$0")/.."

echo "--- Checking prerequisites ---"
ensure_brew
ensure_just
ensure_uv
ensure_node
check_python
echo ""

echo "--- Installing project dependencies ---"
echo ""

info "Installing backend dependencies..."
(cd backend && uv sync)
info "Backend dependencies installed"

echo ""
info "Installing frontend dependencies..."
(cd frontend && npm install)
info "Frontend dependencies installed"

echo ""
echo "=== Setup complete ==="
echo ""
echo "  Start developing:"
echo "    just dev-backend    # http://localhost:20000"
echo "    just dev-frontend   # http://localhost:3000"
echo ""
echo "  Or deploy:"
echo "    just deploy"
echo ""
