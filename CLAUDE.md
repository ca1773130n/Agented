# CLAUDE.md

**Agented** is a harness-engineering meta-layer for AI coding harnesses
— Claude Code, Codex, Gemini CLI, OpenCode, and similar tools. It
provides end-to-end product development with autonomous agents:
orchestrating multi-harness workflows, managing accounts/credentials,
coordinating products → projects → teams → agents, and wiring
plugins/skills/hooks/commands/rules into the harnesses themselves.

The Litestar backend drives the harnesses via `subprocess.Popen` and
SSE-streams their output. The Vue 3 frontend is the operator console.
A sidecar (ai-accounts) owns AI-backend identity. Triggers (webhooks,
GitHub events, schedules, manual) are the delivery mechanism, not the
product — the product is the autonomous-agent workflow on top.

## Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `AI_ACCOUNTS_API_KEY` | sidecar | unset → reuse Flask admin key | Explicit token used by the ai-accounts Litestar sidecar (`backend/scripts/run_ai_accounts.py`). When unset, the sidecar reads the admin key from `agented.db`'s `user_roles` table. |
| `AI_ACCOUNTS_ALLOW_NOAUTH` | sidecar | unset (refuse) | Set to `1` only when running the sidecar locally without any keyed identity (e.g. immediately after `just reset`). The sidecar refuses to start otherwise — the previous "silent NoAuth fallback" exposed it through Vite's `/api/v1` proxy. |
| `VITE_HOST` | frontend dev server | `127.0.0.1` | Bind interface for `vite dev`. Localhost-only by default. Set to `0.0.0.0` to demo from another device — also set `AI_ACCOUNTS_API_KEY` and `VITE_ALLOWED_HOSTS` in that case. |
| `VITE_ALLOWED_HOSTS` | frontend dev server | unset (any host) | Comma-separated allowlist for the `Host` header. Use with `VITE_HOST=0.0.0.0` for LAN access without permitting arbitrary hostnames. |

## ai-accounts dev linking

`backend/pyproject.toml` and `frontend/package.json` ship with **local
`file:` pins** at `../../ai-accounts/packages/*` so iteration on the
sibling `ai-accounts` repo doesn't require publishing every change.
The `just dev-link-ai-accounts` recipe is the inverse path
(local→local) and is redundant in this configuration; switching back
to registry pins for release flips both pieces in one direction.

Edits to `ai-accounts/packages/*/src` are invisible to the frontend
until `npm run build` regenerates `dist/`. `just deploy` does this
automatically.

## Commands

```bash
# Setup
bash scripts/setup.sh            # Bootstrap (fresh clone)
just setup                       # Install all deps
just dev-backend                 # Backend on :20000
just dev-frontend                # Frontend on :3000
just build                       # Production build (vue-tsc + vite)
just deploy                      # Build + start both
just kill                        # Kill ports 3000/20000/20001 (port-scoped only — never pkill vite/node)

# Tests
cd backend && uv run pytest                                  # All backend
cd backend && uv run pytest tests/test_file.py::test_name -v # Single test
cd frontend && npm run test:run                              # All frontend
cd frontend && npm run test:coverage                         # With coverage gate

# Format
cd backend && uv run ruff format .   # line-length=100, py310
```

## Verification

All three must pass before any task is complete:

1. `just build` (vue-tsc type checking + vite build)
2. `cd backend && uv run pytest`
3. `cd frontend && npm run test:run`

## Architecture

**Backend** (`backend/`) — Litestar served by `gunicorn -c gunicorn.conf.py`
(UvicornWorker, workers=1) on `:20000`. Flask was retired in wave 80;
the Litestar app is the canonical surface. The ai-accounts sidecar
(`scripts/run_ai_accounts.py`) on `:20001` owns AI-backend
accounts/credentials/login flows.

- `app_litestar/main.py` — `create_app()` factory; registers route
  handlers, middleware, exception handlers, CORS, on_startup/shutdown.
- `app_litestar/routes/*.py` — `Router(...)` definitions. `/admin/*`
  management, `/api/*` public, `/health/*` open.
- `app_litestar/middleware.py` — SecurityHeaders (CSP/HSTS/X-Frame),
  RateLimit, RequestContext (request-id + current-user contextvars),
  ApiKey (global X-API-Key + bearer-session gate), RequestLogging.
- `app_litestar/exception_handlers.py` — JSON ErrorResponse shape +
  SPA 404 fallback. Exception handler registry covers
  `IntegrityError`, `OperationalError`, `ValueError`, and a
  last-resort `Exception` handler that pipes to `error_capture`.
- `app_litestar/lifecycle.py` — DB seed, backend detection, scheduler
  init + periodic jobs, queue/message-bus dispatchers, CLIProxy
  bootstrap. Honors `AGENTED_LITESTAR_SKIP_STARTUP=1` for tests.
- `app/database.py` — Raw SQLite, `get_connection()` context manager,
  no ORM.
- `app/services/` — Business logic. `ExecutionService` runs CLI
  harnesses via `subprocess.Popen`.
- `app/models/` — Pydantic v2 + msgspec Struct request/response.
- `app/__init__.py` — empty package marker (Flask factory deleted in
  wave 82).
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`,
  `prod-`, `proj-`, `plug-` + 6-char suffix).
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`.

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4.

- `src/services/api.ts` — API client with per-domain objects
  (`botApi`, `agentApi`, etc.).
- No state library — `ref`/`reactive`, props/emits, `provide`/`inject`.
- SSE streaming for real-time logs/conversations via Litestar `Stream`.
- Vitest + happy-dom + @vue/test-utils.
- Vite proxies `/api/v1/*` → `:20001` (sidecar) and
  `/api/*`, `/admin/*`, `/health/*`, `/schema/*` → `:20000` (Litestar).

## Conventions

- Python: Ruff `line-length=100`, target `py310`.
- Backend tests: `isolated_db` fixture (patches `DB_PATH` to temp
  file). For Litestar route tests, the TestClient logger doesn't
  propagate to `caplog` reliably — use a `monkeypatch` spy on
  `module.logger.warning` instead.
- Frontend: Geist font, dark theme, CSS custom props in `App.vue`.
- Tests for the tour state machine maintain ≥ 90% branch coverage on
  `useTourMachine.ts` (enforced by `vitest.config.ts` thresholds).

## Context-Mode MCP tools — MANDATORY routing for shell + HTTP + analysis

This repo is wired to context-mode MCP. Routing rules below are NOT
suggestions — they prevent large outputs from flooding the context
window. A single unrouted command can dump 50+ KB and waste the rest
of the session.

### Tool selection hierarchy

```
ctx_batch_execute(commands, queries)   # PRIMARY — multiple commands + auto-index + search in ONE call
ctx_execute(language, code)            # Run code in sandbox; only stdout enters context
ctx_execute_file(path, language, code) # Analyze a file without pulling its bytes into context
ctx_search(queries)                    # Query indexed content; pass multiple questions in ONE call
ctx_fetch_and_index(url, source)       # Fetch URL, chunk, index (raw HTML stays out of context)
ctx_index(content, source)             # Store content in FTS5 KB for later search
ctx_doctor() / ctx_stats() / ctx_upgrade()
```

### When NOT to use Bash/Read/Grep/WebFetch

- **Bash >20 lines of output** → use `ctx_execute(language="shell", code=...)`
- **Read for analysis** (not for editing) → use `ctx_execute_file`
- **Read is correct ONLY** when the file will be `Edit`'d afterward
- **Grep with large result sets** → `ctx_execute(language="shell", code="grep ...")`
- **WebFetch** is blocked — use `ctx_fetch_and_index` + `ctx_search`
- **curl / wget** in Bash is blocked — use `ctx_fetch_and_index` or
  `ctx_execute(language="javascript", code="const r = await fetch(...)")`
- **Inline HTTP in Bash** (`requests.get`, `http.get`, etc.) is blocked —
  use `ctx_execute` to run the call in sandbox

Bash is reserved for short-output operations: `git`, `mkdir`, `rm`,
`mv`, `ls`, `cd`, navigation, short-output CLI calls.

## Tesserae MCP — agent memory system (per-project compiled KG)

Tesserae is the **canonical agent memory system** for projects with a
Tesserae workspace configured (Settings → Memory System). For each
enabled project it compiles a typed knowledge graph from:

- Source code (CodeFile, CodeMethod, CodeClass, etc.)
- Project docs (Markdown ingested via `tesserae project ingest`)
- Agent session history (auto-imported on every completed Agented session
  via the `tesserae_integration` handler — see
  `backend/app/services/tesserae_integration.py`)

The graph is queryable via MCP — agents should query Tesserae for past
decisions, insights, takeaways, and project-history context BEFORE
asking the user or re-deriving things.

### When to query Tesserae

- "What did we decide about X?" → `tesserae_ask` or `search_facts`
- "What past sessions touched this area?" → `find_session_findings`
- "Show me concepts related to X" → `graph_ppr` (seed with symbol/concept names)
- "What's in the project's compiled graph for this file?" →
  `find_code_symbol_mentions` or `node_context`
- "Browse past sessions" → `list_sessions` / `timeline`
- "What's the project doing semantically?" → `graph_summary` /
  `list_communities`

### Tools

```
tesserae_ask(question)               # PRIMARY — semantic Q&A over the compiled graph
search_facts(query)                  # Find typed claims / decisions / takeaways
search_nodes(query, kind?)           # Find typed nodes (CodeFile, Decision, etc.)
graph_ppr(seed_nodes)                # Personalized PageRank from seeds
graph_summary()                      # High-level: node/edge counts, top concepts
list_sessions() / timeline()         # Browse / time-order session history
find_session_findings(session_id)    # Per-session takeaways + decisions + insights
find_code_symbol_mentions(symbol)    # Where is this symbol referenced in sessions/docs?
node_context(node_id)                # Full context for a single graph node
raw_source(node_id)                  # Raw source bytes for a code node
fresh_insights()                     # Recently surfaced insights
list_communities()                   # Graph community detection results
wiki_page(slug)                      # Read a generated wiki page
schema()                             # Node + edge type schema
list_projects() / activate_project() # Project registry — switch active project
embedding_status()                   # Embedding pipeline health
```

### Operator activation per project

A project opts in via Settings → Memory System (or directly via
`UPDATE projects SET tesserae_project_root = '/abs/path'`). Once
enabled, every completed agent session is auto-imported into the
project's Tesserae workspace. Operator runs `tesserae project compile`
after major doc/code changes to refresh the compiled graph.

### Don't double-store memory

Tesserae is the canonical store for **session-derived memory** —
decisions, takeaways, insights, past-session references.
``agent_working_memory`` stays for **tiny, always-loaded context**
(< 1 KB JSON blob, pasted verbatim into every system prompt). The
two tiers are complementary, NOT competitive — don't write the same
fact to both.

## CodeGraph MCP tools — use FIRST for code-symbol and code-search work

This repo is indexed by CodeGraph (SQLite knowledge graph of every symbol,
file, and edge — file watcher keeps it within ~1s of the working tree).
**Always reach for CodeGraph MCP before falling back to `grep`/`find`/`Read`
for symbol lookup, "where is X used", architectural questions, or anything
that smells like code search.**

```
codegraph_context(task)         # PRIMARY — composes search + node + callers +
                                # callees in one call. Use for "how does X work",
                                # architecture, trace, where-is-X questions.
codegraph_search(query, kind?)  # Fast symbol-name lookup. Returns locations only.
codegraph_node(symbol, code?)   # One symbol's signature / source / docstring.
codegraph_callers(symbol)       # Inbound: what calls X?
codegraph_callees(symbol)       # Outbound: what does X call?
codegraph_impact(symbol)        # Blast radius if X changes.
codegraph_explore(symbols)      # Several related symbols in ONE call (prefer
                                # over many codegraph_node calls).
codegraph_files(path?, pattern?) # Tree / flat / grouped file listing.
codegraph_status()              # Index health + counts.
```

Routing rules:

- "What is the symbol named X?" → `codegraph_search`
- "What's the deal with this task / feature / area?" → `codegraph_context`
  (composes everything you need in one call — prefer over chaining
  search + node + callers + callees yourself)
- "What calls this?" / "What does this call?" → `codegraph_callers` /
  `codegraph_callees`
- "What would changing this break?" → `codegraph_impact`
- "Show me this symbol's source" → `codegraph_node`
- "Survey several related symbols" → `codegraph_explore` (capped, ONE call)
- "What's in directory X?" → `codegraph_files`

Don't delegate code-search to a subagent if CodeGraph can answer the
question directly — CodeGraph **is** the pre-built search index, so a
grep/Read loop or a subagent search just repeats the work. Fall back to
raw `Read`/`grep` only to confirm a specific detail CodeGraph didn't
cover.

## MCP layering — which graph for which question

The three MCP indexes are NOT interchangeable; reach for the one whose
domain matches the question:

| Question shape | Use |
|---|---|
| "Where is symbol X / file Y?" | **CodeGraph** (code structure) |
| "What past sessions touched X / what did we decide about X?" | **Tesserae** (session + doc + code KG) |
| "Run a shell command, run code, fetch a URL" | **Context-Mode** (sandboxed execution + indexing) |

Avoid duplicating questions across the three. Code-structure questions
that go to Tesserae get a slower / fuzzier answer than CodeGraph; past-
session questions that go to CodeGraph get nothing.

## GRD planning

`.planning/` contains roadmaps, codebase analysis, and phase plans:

- `.planning/config.json` — GRD config.
- `.planning/milestones/v0.5.0/` — onboarding tour, complete.
- `.planning/milestones/v0.5.1/` — patch: OB-24 anchor + coverage gate.
- `.planning/milestones/v0.5.2/` — silent-failure cleanup pass 1.
- `.planning/milestones/v0.5.3/` — silent-failure cleanup pass 2 +
  modal-interaction E2E.
- `.planning/milestones/v0.6.0/` — TBD.

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`,
  `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`,
  `/superpowers:writing-plans`, `/superpowers:executing-plans`,
  `/superpowers:test-driven-development`.
- **Simplify**: `/simplify` — post-change code review.
- **Commit**: `/commit-commands:commit`, `/commit-commands:commit-push-pr`.
