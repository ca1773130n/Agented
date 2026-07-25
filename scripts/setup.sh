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

# ---------- Tesserae (federated knowledge graph for Sketch ideation) ----------
# The Sketch ideation chat grounds each turn with FEDERATED Tesserae retrieval
# across all registered projects. Requires the `tesserae` CLI >= 0.13.1 (federation
# status + real model2vec semantic + `--recency-weight` for the grounding ask, which
# Agented passes at 0.8 so "current work" grounding surfaces recent nodes instead of
# old session syntheses; 0.13.0 added an in-process federated-graph memo — faster
# repeat asks — and the compile-time `--extractor llm` default; 0.13.1 added
# `tesserae sources` for compile-scope mgmt — all compile-side, not Agented's
# retrieval calls) on PATH,
# installed with the `semantic` extra (model2vec) — WITHOUT it, retrieval degrades to
# the hash-bucket stub. Best-effort: a missing/old Tesserae degrades the chat to ungrounded.
# 0.18 made `ask` LLM-synthesize by default (`--no-llm` = ranked hits) + added `doctor`
# and daily session-chunks. 0.19 is a backend-EOL cleanup: the `cognee`/`understand-anything`
# backends are removed (typed ResearchGraph + LLM planner have been the default since 0.18,
# already wired) — Agented never selected a tesserae backend, and the removal note prints to
# STDERR, so `doctor --json`/`ask` stdout parsing is unaffected. 0.19.1 is a pidlock bugfix
# (locale-proof daemon identity — live daemons no longer misread as stale; transparent to the
# `doctor` lock-check + `engine --once` refresh Agented wires). 0.20.0 adds MCP `query` +
# `doctor_run` tools (closes the CLI/MCP gap) — MCP-only, and Agented consumes the CLI (already
# wires `query`→KG explorer, `doctor`→Memory Health), so the CLI surface is unchanged.
# 0.20.1 drops the 300-turn session-import cap; 0.20.2 reads full session history in chunks
# (the model no longer truncates long conversations). Both are session-history bug fixes —
# no new CLI surface, so nothing new to wire; pure pin bump so fresh installs get the fixes.
# 0.21.0 lands the per-agent layered-KG / AgentRunbook distillation. 0.22 completes the
# agent-memory CLI (`agents tree/show/drill` + `--agent` scoping — Agented wires `agents drill`
# for the super-agent memory audit). 0.23/0.24 add the engine "sleep cycle": a long-lived
# `engine --all --consolidate` daemon that on idle compresses agent memory, forgets-by-disuse
# (LRU), and discovers cross-agent connections (`associate`). Agented runs that daemon
# (tesserae_engine_daemon.py). The 0.24 `associate` pass needs a real embedding backend, so we
# install the `semantic` extra below.
# 0.25 ("Descent") adds the graph_map structural-navigation tool (Agented wires it as a
# `graph-map` CLI verb + Descent explorer), a .tesserae/hierarchy.json sidecar (written by
# compile; required by graph_map / hierarchical compile_context), and the daemon SUMMARIZE op
# (--summarize-budget). It also adds an opt-in extraction timeout (TESSERAE_EXTRACT_TIMEOUT) so
# a wedged codex child no longer blocks a compile forever.
# 0.25.1 arms that guard BY DEFAULT (1800s/doc), adds `compile --retry-fallbacks` (recovers
# docs that degraded to the deterministic baseline — otherwise they stay deterministic until
# their content changes), and puts `live_member_count` on graph_map cards so a consumer can
# detect a scope whose members no longer exist in the graph. Agented bounds the per-doc guard
# to a quarter of its own subprocess budget (see _extraction_timeout_for).
TESSERAE_MIN="0.25.1"
# Portable "A >= B" for dotted versions — BSD/macOS `sort` lacks `-V`.
_version_ge() {
    local a b IFS=.
    read -ra a <<<"${1//[!0-9.]/}"
    read -ra b <<<"${2//[!0-9.]/}"
    local i x y
    for i in 0 1 2; do
        x=$((10#${a[i]:-0}))
        y=$((10#${b[i]:-0}))
        ((x > y)) && return 0
        ((x < y)) && return 1
    done
    return 0
}
ensure_tesserae() {
    local cur=""
    if command_exists tesserae; then
        # `|| true`: a broken binary must not abort setup under `set -euo pipefail`.
        cur="$(tesserae --version 2>/dev/null | awk '{print $NF}' || true)"
    fi
    if [[ -n "$cur" ]] && _version_ge "$cur" "$TESSERAE_MIN"; then
        info "Tesserae $cur found (>= $TESSERAE_MIN)"
        return
    fi
    local src="$HOME/Developer/Projects/Tesserae"
    if [[ -d "$src" ]] && command_exists uv; then
        warn "Tesserae ${cur:-missing} < $TESSERAE_MIN — installing from $src (semantic extra)..."
        # `[semantic]` = model2vec + numpy (the associate/LRU sleep cycle needs a real
        # embedding backend; without it association is a quiet no-op). NOTE: `uv tool install`
        # rejects the separate `--extra semantic` form on uv 0.10.x ("unexpected argument"),
        # which silently fell through to the failure branch and never installed the extra — use
        # the bracketed path-target suffix, which is stable across uv versions.
        if uv tool install --force "$src[semantic]" >/dev/null 2>&1; then
            info "Tesserae $(tesserae --version 2>/dev/null | awk '{print $NF}') installed"
        else
            warn "Tesserae install failed — Sketch ideation will be ungrounded (optional)"
        fi
    else
        warn "Tesserae >= $TESSERAE_MIN not on PATH and no checkout at $src — Sketch grounding disabled (optional)"
    fi
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
ensure_tesserae
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
