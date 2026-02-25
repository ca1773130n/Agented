# External Integrations

**Analysis Date:** 2026-02-25

## AI Provider CLIs (Subprocess-Based)

The core execution model shells out to AI CLI tools via `subprocess.Popen`. These are not SDK integrations — they are CLI subprocess invocations.

**Claude Code (`claude`):**
- CLI binary invoked via `subprocess` with `-p` (non-interactive) flag
- Output formats: `--output-format json`, `--output-format stream-json --verbose`
- Auth: OAuth tokens read from `~/.claude/.credentials.json` or macOS Keychain (`Claude Code-credentials`)
- Session files parsed from `~/.claude/projects/*/` (JSONL format) for usage tracking
- Detected via: `shutil.which("claude")` in `backend/app/services/backend_detection_service.py`

**OpenCode (`opencode`):**
- CLI binary invoked with `run --prompt ...` (non-interactive)
- Output format: `--format json`
- Auth: config files in standard OpenCode locations
- Model discovery via `opencode models` CLI command
- Detected via: `shutil.which("opencode")`

**Codex (`codex`):**
- CLI binary invoked with `exec` (non-interactive)
- Output format: `--json`
- Auth: OAuth tokens from `~/.codex/auth.json`
- Usage polling: PTY-based `/status` command via `backend/app/services/pty_service.py`
- Detected via: `shutil.which("codex")`

**Gemini (`gemini`):**
- CLI binary invoked with `-p` (non-interactive)
- Output format: `--output-format json`
- Auth: OAuth tokens from `~/.gemini/oauth_creds.json` or macOS Keychain (`gemini-cli-oauth`)
- Token refresh via Google OAuth endpoint when expired
- Detected via: `shutil.which("gemini")`

**All backend CLI execution flows through:**
- `backend/app/services/execution_service.py` — trigger-based bot execution
- `backend/app/services/execution_type_handler.py` — per-backend execution dispatch
- `backend/app/services/process_manager.py` — subprocess lifecycle management

## CLIProxyAPI (Local Proxy)

**Purpose:** OpenAI-compatible HTTP proxy that routes requests to local Claude Code OAuth credentials. Enables account routing for multi-account setups.

- Binary: `cliproxyapi` (auto-installed if missing via `CLIProxyManager.install_if_needed()`)
- Config: `~/.cli-proxy-api/config.yaml`
- Credentials: `~/.cli-proxy-api/claude-{email}.json`
- Default port: `8317`
- Endpoint: `http://127.0.0.1:8317/v1` (OpenAI-compatible)
- Manager: `backend/app/services/cliproxy_manager.py`
- Chat streaming: `backend/app/services/cliproxy_chat_service.py` (via `httpx`)
- OAuth login flow: headless Chromium via `playwright` (`CLIProxyManager._run_playwright_oauth()`)
- Token decryption: AES-CBC using Chrome Safe Storage Keychain key via `cryptography` library

## Provider Usage APIs

Rate limit and usage data is fetched directly from provider APIs using OAuth tokens. All calls use Python stdlib `urllib.request` in `backend/app/services/provider_usage_client.py`.

**Anthropic (Claude):**
- Endpoint: `GET https://api.anthropic.com/api/oauth/usage`
- Auth: `Authorization: Bearer {oauth_token}`, header `anthropic-beta: oauth-2025-04-20`
- Returns: `five_hour`, `seven_day`, `seven_day_sonnet` usage windows
- Token source: macOS Keychain `Claude Code-credentials` or `~/.claude/.credentials.json`

**OpenAI (Codex):**
- Endpoint: `GET https://chatgpt.com/backend-api/wham/usage`
- Auth: `Authorization: Bearer {oauth_token}`, optional `ChatGPT-Account-Id` header
- Token source: `~/.codex/auth.json`
- Fallback: PTY-based `/status` command in `codex` CLI

**Google (Gemini):**
- Endpoint: `POST https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota`
- Auth: `Authorization: Bearer {oauth_token}`
- Body: `{"project": "cloud-code-assist"}`
- Token source: macOS Keychain `gemini-cli-oauth` or `~/.gemini/oauth_creds.json`
- Token refresh: Google OAuth token refresh endpoint when credentials are expired
- Well-known OAuth client credentials: `_GEMINI_CLI_CLIENT_ID` / `_GEMINI_CLI_CLIENT_SECRET` (public, from Gemini CLI source)

## LiteLLM (LLM Abstraction)

Used for direct LLM API calls in chat/conversation features (not for bot execution).

- Library: `litellm` 1.81+
- Usage locations:
  - `backend/app/services/conversation_streaming.py` — streaming chat completions
  - `backend/app/services/cliproxy_chat_service.py` — direct API path when CLIProxy unavailable
  - `backend/app/services/sketch_routing_service.py` — sketch prompt routing
- Auth modes (checked in order):
  1. Explicit `api_base` (proxy mode)
  2. CLIProxyAPI (managed or auto-detected) via `X-Account-Email` header for account routing
  3. `ANTHROPIC_API_KEY` environment variable (direct API)
  4. Claude CLI subprocess fallback

## GitHub Integration

**GitHub CLI (`gh`):**
All GitHub operations use the `gh` CLI binary (not a REST SDK). Implemented in `backend/app/services/github_service.py`.

- Operations: `gh repo view`, `gh repo clone`, `gh pr create`, `gh auth setup-git`
- Branch management: create, push, delete via `git` + `gh auth setup-git` for credentials
- Supports GitHub.com and GitHub Enterprise Server URLs
- Auth: `gh` CLI's own OAuth token (managed externally by user)

**GitHub Webhooks:**
- Endpoint: `POST /api/webhooks/github/`
- Route: `backend/app/routes/github_webhook.py`
- Signature verification: HMAC-SHA256 via `X-Hub-Signature-256` header
- Secret: `GITHUB_WEBHOOK_SECRET` environment variable
- Event: `pull_request` → triggers PR review bots
- Rate limiting: per-repo, minimum 60 seconds between actionable events

**General Webhooks:**
- Endpoint: `/api/webhooks/` (GET/POST/PUT/DELETE/PATCH)
- Route: `backend/app/routes/webhook.py`
- Signature verification: `X-Webhook-Signature-256` header (HMAC-SHA256)
- Supports challenge-response verification patterns
- Max payload: 10 MB

## Git Operations

Direct `git` CLI subprocess calls (no libgit2 or PyGit2) throughout:

- `backend/app/services/github_service.py` — clone, branch, commit, push, PR creation
- `backend/app/services/worktree_service.py` — `git worktree add/remove/list` for GRD plan execution isolation (max 5 concurrent worktrees per project)
- `backend/app/services/project_workspace_service.py` — `git fetch`, `git pull` for project repo sync (every 30 minutes via APScheduler)

## MCP (Model Context Protocol) Servers

The platform manages MCP server configurations for AI CLI tools.

- DB table: `mcp_servers` (seeded with presets in `backend/app/db/migrations.py`)
- Preset example: `@playwright/mcp` — Playwright browser automation MCP server
- Routes: `backend/app/routes/mcp_servers.py`
- Sync service: `backend/app/services/mcp_sync_service.py` — writes MCP config to CLI config directories

## WebMCP (Browser-Based MCP)

Frontend exposes tools to AI agents via the W3C WebMCP spec (`navigator.modelContext`).

- Polyfill: `@mcp-b/global` 1.5 (imported in `frontend/src/main.ts`)
- Types: `@mcp-b/webmcp-types` 0.2
- Tool registry: `frontend/src/webmcp/tool-registry.ts`
- Generic tools registered at app startup: `frontend/src/webmcp/generic-tools.ts`
- Page-specific tools registered per-view via `useWebMcpTool` composable: `frontend/src/composables/useWebMcpTool.ts`
- No-ops in non-supporting browsers (feature-detected at runtime)

## Skill Marketplace

- Routes: `backend/app/routes/marketplace.py`
- Service: `backend/app/services/skill_marketplace_service.py`
- HTTP client: `urllib.request` to fetch skill packages from remote URLs
- Used in `backend/app/services/skills_sh_service.py`

## macOS Keychain

Used for reading OAuth credentials on macOS without file access.

- Tool: `security find-generic-password` CLI (via `subprocess`)
- Service names queried:
  - `Claude Code-credentials` (default Claude account)
  - `Claude Code-credentials-{sha256(config_path)[:8]}` (non-default Claude accounts)
  - `gemini-cli-oauth` (Gemini)
  - `Chrome Safe Storage` (for CLIProxyAPI AES key derivation)
- Implemented in `backend/app/services/provider_usage_client.py` and `backend/app/services/cliproxy_manager.py`
- Gracefully falls back to file-based credentials on Linux / when Keychain unavailable

## Session Data Sources

Local CLI session files are polled every 10 minutes by `SessionCollectionService`:

- **Claude Code sessions:** `~/.claude/projects/*/` — JSONL files, one per session
- **Codex sessions:** `~/.codex/` — JSONL files
- Parser: `backend/app/services/session_collection_service.py`
- Cost computation: `backend/app/services/session_cost_service.py`

## GRD CLI Integration

- Binary: `grd-tools.js` (Node.js CLI tool, external dependency)
- Detection: `backend/app/services/grd_cli_service.py` checks settings DB, then `CLAUDE_PLUGIN_ROOT` env var, then known install glob paths
- Used for: writing plan status and GRD planning operations
- Routes: `backend/app/routes/grd.py`
- Gracefully degrades: GRD write operations unavailable if binary not found

## Data Storage

**Databases:**
- SQLite, single file (`backend/agented.db`)
- No external database

**File Storage:**
- Local filesystem only
- Bot execution reports: `{PROJECT_ROOT}/.claude/skills/weekly-security-audit/reports/`
- Project symlinks: `{PROJECT_ROOT}/project_links/`
- CLIProxyAPI config/credentials: `~/.cli-proxy-api/`
- Claude Code config: `~/.claude/`

**Model Storage:**
- Not applicable (no trained models; uses external CLI tools)

## Experiment Tracking

**Service:** None — not applicable (not an ML training platform)

## Monitoring & Observability

**Error Tracking:** None (no Sentry, Datadog, etc.)

**Logging:**
- Python stdlib `logging` with `basicConfig` in `backend/run.py`
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Execution logs stored in SQLite (DB-backed, not file-based)

**Internal Monitoring:**
- `MonitoringService` polls provider APIs on schedule and stores snapshots in SQLite
- Rate limit threshold transitions trigger internal alerts (in-memory, no external push)

## CI/CD & Deployment

**CI Pipeline:** None detected (no `.github/workflows/`, no CI config files)

**Hosting:**
- Backend: `gunicorn` or Flask dev server on port 20000
- Frontend: Vite preview/dev server on port 3000, or served as static files from `frontend/dist/`

## Environment Configuration Summary

**Required for production:**
- `GITHUB_WEBHOOK_SECRET` — GitHub webhook HMAC verification (webhooks rejected if unset)

**Optional but functional:**
- `AGENTED_DB_PATH` — SQLite path override
- `SECRET_KEY` — Flask session key (auto-generated if unset)
- `CORS_ALLOWED_ORIGINS` — CORS restriction (defaults to `*`)
- `ANTHROPIC_API_KEY` — Direct Anthropic API key (fallback when CLIProxy unavailable)
- `CLAUDE_PLUGIN_ROOT` — GRD binary discovery path

---

*Integration audit: 2026-02-25*
