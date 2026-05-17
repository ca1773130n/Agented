# Forge Context Injection for Project Sessions

**Date:** 2026-05-16
**Status:** Approved (goal-driven, scope locked via AskUserQuestion)
**Owner:** session reliability / DX

## Problem

Terminal sessions on the Project Management page are headless: `POST
/api/projects/{id}/sessions` spawns `claude --print --input-format
stream-json` (or codex/gemini/opencode) with the raw user prompt and
nothing else. Operators have no way to wire the Forge artifacts they
already curate (rules, skills, hooks, commands, MCP servers, plugins)
into the session, nor to attach ad-hoc context (files, snippets, URLs,
project-entity references) when sending a prompt.

The existing `claude_config_overlay.prepare_session_overlay` already
proves the overlay pattern (per-session `CLAUDE_CONFIG_DIR` tmp dir
with symlinked passthrough items + merged `settings.json`). Agented's
DB-stored rules/hooks/commands are not materialized there. No
backend sees `--append-system-prompt`. The PR-diff context injection
at `execution_service.py:357` is a one-off prepend.

## Goal

Three injection points, one source of truth:

1. **Project bindings** — per-project sticky defaults for which Forge
   artifacts apply to every session of that project.
2. **Session start** — operator inherits bindings, can opt out / add
   for this session.
3. **Per-prompt tray** — volatile attachments (file paths, snippets,
   URLs, entity refs) prepended to a single message.

## Scope (v1)

- **Backends with full overlay + system-prompt:** claude.
- **Backends with prompt-prepend only:** codex, gemini, opencode.
  (Native overlay for these is a follow-up; the abstraction supports
  it.)
- **Forge artifact kinds:** rule, skill, hook, command, mcp_server,
  plugin.
- **Attachment kinds:** file (repo-relative path, 64 KB cap),
  snippet (free text), url (fetched + summarized, 1 h cache), entity
  (`product|project|team|trigger|plan` ID, serialized).
- **Persistence:** project bindings only. Session overrides and
  per-prompt attachments are volatile (request-scoped).

Out of scope: agent/bot personas, token-budget-aware truncation,
audit/replay of attachments, opencode MCP wiring.

## Data model

```sql
CREATE TABLE project_forge_bindings (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,          -- rule|skill|hook|command|mcp_server|plugin
  asset_id    TEXT NOT NULL,
  role        TEXT,                   -- kind-specific; null = default
  enabled     INTEGER NOT NULL DEFAULT 1,
  position    INTEGER NOT NULL DEFAULT 0,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, kind, asset_id)
);
CREATE INDEX idx_pfb_project_enabled
  ON project_forge_bindings(project_id, enabled);
```

Migration v121 in `backend/app/db/migrations/v07_features.py`.

## Backend architecture

`backend/app/services/context_compiler_service.py`

```python
@dataclass
class ContextBundle:
    system_prompt_text: str
    overlay_files: dict[str, str]
    overlay_symlinks: dict[str, str]
    mcp_servers: dict[str, dict]
    prompt_prepend: str

class ContextCompilerService:
    @classmethod
    def compile(
        cls,
        project_id: str,
        *,
        session_overrides: Optional[dict] = None,
        attachments: Optional[list[dict]] = None,
    ) -> ContextBundle: ...
```

Inputs:

- DB project bindings (filtered to `enabled=1`, ordered by `position`).
- `session_overrides` — opt-out of inherited bindings, add session-only ones.
- `attachments` — per-prompt volatile bag.

Output: a `ContextBundle` consumed by per-backend renderers.

`backend/app/services/context_renderers/` — one module per backend:

- `claude_renderer.py` — extends `claude_config_overlay`,
  appends `--append-system-prompt <text>` to cmd, materializes
  hooks/commands/skills into the overlay, MCP into `mcp.json`.
- `codex_renderer.py` — prepends a `=== Operator Context ===`
  block to the prompt; CODEX_HOME overlay deferred.
- `gemini_renderer.py` — same pattern; GEMINI_HOME deferred.
- `opencode_renderer.py` — same pattern; OPENCODE_HOME deferred.

All renderers expose:

```python
def apply(cmd: list[str], env: dict, bundle: ContextBundle,
          session_id: str) -> tuple[list[str], dict]: ...
```

## Wire-up

- `grd_routes.create_session` — accept new `forge_context` body
  field (`{overrides, attachments}`). Server calls
  `ContextCompilerService.compile(project_id, ...)`, picks renderer
  by `cmd[0]`, mutates `cmd` + `env` before `handler.start(...)`.
- `grd_routes.session_input` — accept optional `attachments` field;
  prepend rendered text to `text` before forwarding to claude stdin
  (or other CLI).
- `claude_config_overlay.prepare_session_overlay(..., bundle=None)`
  — new param. When set, write the bundle's `overlay_files` and
  symlink `overlay_symlinks` into the temp dir; merge `mcp_servers`
  into `mcp.json`.
- `execution_service.py:357` — re-route the PR-diff injection
  through `ContextCompilerService` (as an attachment kind="diff")
  so we have one path.

## Routes (new)

- `GET    /admin/projects/{id}/forge-bindings`
- `PUT    /admin/projects/{id}/forge-bindings` — replace all
- `POST   /admin/projects/{id}/forge-bindings` — add one
- `DELETE /admin/projects/{id}/forge-bindings/{binding_id}`
- `POST   /admin/projects/{id}/forge-context/preview` — returns the
  compiled bundle (system_prompt_text + prompt_prepend) without
  spawning anything. Used by the preview drawer.

## Frontend

- `frontend/src/components/forge/ProjectForgeBindingsPanel.vue`
  (new) — surfaced in the existing Project detail page. Tabbed by
  kind. Multi-select against the user's existing Forge libraries.
- `frontend/src/components/sessions/SessionContextTray.vue` (new)
  — sits above the chat input in `ProjectSessionPanel.vue`. Chip
  list of pending attachments + add buttons (📎 / 💬 / 🔗 / @).
- `frontend/src/components/sessions/ContextPreviewDrawer.vue` (new)
  — slide-over showing compiled system prompt + prepend; calls
  `/forge-context/preview`.
- `frontend/src/components/sessions/SessionStartDialog.vue` —
  extend to show inherited bindings with per-binding toggles +
  "Add for this session" picker.
- `frontend/src/services/api/projects.ts` — add
  `projectApi.forgeBindings.list/replace/add/remove`,
  `projectApi.forgeContext.preview`.
- `frontend/src/composables/useProjectSession.ts` — extend
  `sendInput()` and `createSession()` to forward `attachments` /
  `forgeContext` payloads.

## Testing

- `backend/tests/services/test_context_compiler_service.py` —
  fixture project with one of each binding kind, assert bundle shape.
- `backend/tests/services/test_context_renderers.py` —
  parametrized over the four backends.
- `backend/tests/routes/test_forge_bindings_routes.py` — CRUD +
  permission checks (owner-only via `get_for_user`).
- `frontend/src/components/sessions/__tests__/SessionContextTray.test.ts`
  — chip add/remove + preview-drawer trigger.

## Rollout

Additive. Empty bindings + no attachments → identical CLI invocation
to today. Zero regression risk for existing sessions.
