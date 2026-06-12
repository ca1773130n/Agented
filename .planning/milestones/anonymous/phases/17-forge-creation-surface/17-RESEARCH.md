# Phase 17: Forge Creation Surface - Research

**Researched:** 2026-06-13
**Domain:** Backend forge primitive subsystem (SQLite + Litestar + `.claude/` materialization)
**Confidence:** HIGH — every recommendation is grounded in code read this session (paths + symbols + line refs below).

## Summary

Phase 17 extends an existing, well-factored forge subsystem. The work is **mechanical pattern-mirroring**, not greenfield design. Six concerns: (1) a one-line provenance bug in `replace_for_project`; (2) a new `subagent` primitive kind mirroring rule/hook/command; (3) cross-kind `forge_bundles`; (4) a 4-backend renderer + `.claude/agents/` materialization slot; (5) an atomic create+bind+materialize endpoint with compensating cleanup; (6) a `forge-creator` seed bundle + session-completion auto-import handler.

The codebase has no formal transaction/saga abstraction — `get_connection()` is a per-call context manager that commits on exit. Atomicity (success criterion 2) must be implemented as **explicit ordered compensation** in a service function, not a DB transaction, because materialization writes files (not rows). The biggest sharp edge: the legacy `agents` table + `create_agent` (used by `HarnessLoaderService._import_agents`) is **NOT** the new `subagent` forge primitive — they must stay distinct. Confusing them will corrupt success criterion 1.

**Primary recommendation:** Mirror the rule/command pattern exactly for `subagent` (new `subagents` table, `subag-` prefix via `generate_id`, DB module `backend/app/db/subagents.py`, CRUD route module, `VALID_KINDS` entry, a `_get_asset`/materialize branch, and a renderer hook). Fix `replace_for_project` first (independent, lowest-risk). Build the atomic endpoint as a service that calls existing create→`add_binding`→`materialize_primitives` and reverses them on failure.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. Constraints are taken from the design spec (`docs/superpowers/specs/2026-06-13-team-harness-self-improvement-design.md`, §"Phase 1") and the milestone requirements. Treat the spec's Phase 1 design decisions as **locked**.

### Locked Decisions (from spec §Phase 1 + cross-cutting)
- New `subagent` kind: `subagents` table (`subag-` prefix), CRUD mirroring `rules_plugins_hooks_commands.py`, `VALID_KINDS` entry, materialize to `.claude/agents/<name>.md`.
- Atomic `POST /admin/projects/{project_id}/forge/create` `{kind, payload, bind, materialize}` with compensating cleanup.
- `replace_for_project` must preserve `source_scope/source_shared_binding_id/fingerprint/conflict_policy`.
- `forge_bundles` (+ `forge_bundle_items(kind, asset_id, position)`); `skill_sets` stays untouched (skills-only legacy).
- Five global-scope creator skills composed into `forge-creator` bundle, agentskills.io-compatible SKILL.md.
- Session-completion handler (`execution_events.register_session_handler`) diffs `.claude/` vs forge manifest, imports via `HarnessLoaderService` + atomic API, records origin content-hash + source session id; **only auto-binds Agented-driven-session artifacts** (others queue for review).
- All-four-backends rule: renderer work covers claude/codex/gemini/opencode.

### Claude's Discretion
- Exact `subagents` schema columns (mirror `commands`/`rules` shape).
- Compensation ordering and where the atomic service lives.
- Bundle-bind transactionality approach.
- How "Agented-driven session" is detected (see Open Questions).

### Deferred Ideas (OUT OF SCOPE — Phase 2+)
- Sketch → primitive routing (Phase 2). Frontend surfaces (no frontend in Phase 17).
- GRD driver, autoresearch wiring, one-click setup, repeated-request detection (Phases 3–6).

## Architecture Patterns (grounded in actual code)

### The forge primitive pattern (what `subagent` must mirror)
Each kind = (a) a DB module with CRUD, (b) re-exports through `backend/app/db/__init__.py`, (c) a Litestar route module, (d) a `VALID_KINDS` membership, (e) a `_get_asset` branch + materialize branch in `forge_materialization_service.py`, (f) a renderer branch.

- **`VALID_KINDS`** — `backend/app/db/project_forge_bindings.py:24`: `{"rule", "skill", "hook", "command", "mcp_server", "plugin"}`. Re-exported as `VALID_FORGE_BINDING_KINDS` (`backend/app/db/__init__.py:557`). Add `"subagent"`. Migration 121's binding table accepts new kinds without schema change (spec §2), so **no binding-table migration needed** for the new kind.
- **CRUD route shape** — `backend/app_litestar/routes/rules_plugins_hooks_commands.py:1-120` (`create_rule` at ~line 80): `@post("/")` reads `data: dict`, calls `db_create_rule(...)`, returns `{"message": ..., "rule": get_rule(id)}`. Router registered with a path prefix. The new subagent routes mirror this; register the router in the same place rules/commands routers are registered.
- **DB module shape** — `backend/app/db/skills.py` (`add_user_skill`/`update_user_skill`/`delete_user_skill`) and the command/rule equivalents. Use `get_connection()` (`backend/app/db/connection.py`) context manager; commit inside.
- **ID generation** — `backend/app/db/ids.py:159` `generate_id(prefix, length=6)`. Add `SUBAGENT_ID_PREFIX = "subag-"` and `generate_subagent_id()` mirroring `generate_team_id()` (`ids.py:202`).

### Materialization pattern
`backend/app/services/forge_materialization_service.py`, `materialize_primitives(project, kinds, workspace_path)`:
- command → `.claude/commands/<safe>.md` (frontmatter via `_frontmatter` + body).
- rule → `.claude/agented-forge/rules/<safe>.md`.
- hook → `.claude/hooks/<safe>.sh` (chmod 0o755) + `.claude/settings.json` hooks block (marker `_agented_asset_id`).
- mcp_server → `.claude/mcp.json`.
- skill → `.claude/skills/<safe>/SKILL.md` (body written on disk by evolver `_create_skill`; materializer only records it).
- `_get_asset(kind, asset_id)` dispatches per kind (rule/hook/command int ids; mcp_server str; skill int). **Add a `subagent` branch.**
- `_finalize_manifest` reconciles only the materialized kinds' buckets; `_NEVER_DELETE = {_MANIFEST_REL, ".claude/settings.json", ".claude/mcp.json"}`. The subagent bucket is per-asset-file like commands, so manifest reconciliation works unchanged once a `subagent` write branch is added.

**Subagent target:** `.claude/agents/<safe>.md`, full body = frontmatter + content. Frontmatter fields per `HarnessLoaderService._import_agents` (`harness_loader_service.py:195-260`): `name, description, role, model, color, tools, system_prompt, goals, triggers, skills, autonomous`. For round-trip fidelity, materialize with at least `name`, `description`, and the Agented markers (`agented-kind: subagent`, `agented-asset-id`, `agented-source: forge`) like commands do.

### Per-backend renderers
`backend/app/services/context_renderers/{base,claude,codex,gemini,opencode}.py` (+ `__init__.py`). `ContextCompilerService.compile` (`context_compiler_service.py`) drives them; claude uses `--append-system-prompt` + per-session overlay files, codex/gemini/opencode use a prompt-prepend block (`context_compiler_service.py:7-9`). For `subagent`: claude renderer overlays an `agents/` dir entry; codex/gemini/opencode have no subagent concept → **prompt-prefix fallback** (inject the subagent body as a named context block), consistent with how those renderers already degrade. Golden-file tests must cover all four (`backend/tests/test_forge_materialization.py` is the existing golden harness).

### Session-completion bus
`backend/app/services/execution_events.py`: `register_session_handler(callback)` (line 38); callback signature `(session_kind, session_id, project_id, status, output)` (line 18); `emit_session_complete` fans out (line 48). Handlers registered at startup in `backend/app_litestar/lifecycle.py:454-485` (annotator `on_session_complete`, takeaway `on_takeaway_extract`, tesserae `on_tesserae_export`), each in its own try/except. **Add a fourth registration** for the import handler following that exact pattern. Five session kinds flow through this bus (spec §2). Transcript access: `_FETCHERS` + `parse_claude_stream` in `harness_failure_annotator.py:304-323`.

## Per-Plan Implementation Guidance

### 17-01 — `replace_for_project` fix (do first; independent, lowest risk)
**Bug confirmed.** `backend/app/db/project_forge_bindings.py` `replace_for_project` (≈line 167) deletes all bindings then re-INSERTs with a **6-column list** `(project_id, kind, asset_id, role, enabled, position)` — dropping `source_scope`, `source_shared_binding_id`, `fingerprint` (and never setting `conflict_policy`, which then falls to its column DEFAULT `'local_wins'`). The `add_binding` upsert (same file) DOES carry these columns — copy that column set. The function does NOT call `_ensure_propagation_columns(conn)` before the DELETE/INSERT; `add_binding` does. Add that call too, and read the incoming `b.get("source_scope")`/`b.get("fingerprint")`/etc. with sensible defaults (`'project'`, `None`, `'local_wins'`).
**Files:** `backend/app/db/project_forge_bindings.py` only.
**Tests:** repo-layer test that round-trips a binding with all four provenance fields set through `replace_for_project` and asserts preservation (regression for criterion 3).

### 17-02 — subagent CRUD + kind registration
**New files:** `backend/app/db/subagents.py` (CRUD mirroring `skills.py`/command CRUD; columns: `id TEXT PK 'subag-…'`, `name`, `description`, `content` (full `.claude/agents/*.md` body incl. frontmatter), `enabled INT`, `project_id`, `source_path`, `created_at`, `updated_at`); `backend/app_litestar/routes/project_subagents.py` (or extend `rules_plugins_hooks_commands.py`).
**Edits:** migration `155` in `backend/app/db/migrations/v07_features.py` (highest existing is 154; append `(155, "subagents", _migrate_155_subagents)` to `V07_MIGRATIONS` at ~line 1094 — note tuples are numerically keyed not file-ordered); add `"subagent"` to `VALID_KINDS` (`project_forge_bindings.py:24`); add `SUBAGENT_ID_PREFIX`/`generate_subagent_id` to `ids.py`; re-export CRUD from `backend/app/db/__init__.py` (~line 556 forge block / ~line 737 skills block); register route in the app factory. Add `_get_asset` `subagent` branch in `forge_materialization_service.py` (int or str id — pick str to match `subag-` prefix; note the existing comment "rule/hook/command take INT ids; mcp_server takes STR").
**Pitfall (HIGH):** Do not reuse the legacy `agents` table / `create_agent`. `subagents` is a new forge primitive table. `HarnessLoaderService._import_agents` writes the *legacy* `agents` table — keep import-to-forge-subagent separate (see 17-06).

### 17-03 — `forge_bundles` + cross-kind bundle bind
**New files:** `backend/app/db/forge_bundles.py` (CRUD), `backend/app_litestar/routes/forge_bundles.py` (or fold into the forge router).
**Schema (migration 156):** `forge_bundles(id TEXT PK 'bundle-…', name UNIQUE, description, scope TEXT DEFAULT 'project', created_at)`; `forge_bundle_items(bundle_id FK, kind TEXT, asset_id TEXT, position INT, PRIMARY KEY(bundle_id, kind, asset_id))`.
**Endpoint:** `POST /admin/projects/{id}/forge/bundles/{bundle_id}/bind` → loop items, call `add_project_forge_binding` (idempotent upsert) for each in one `get_connection()` block; on any item failure, the whole call should report failure (collect successes for the caller / or wrap in a single connection + manual rollback since `add_binding` opens its own connection — see Open Questions on nested connections).
**Constraint:** `skill_sets` (`backend/app/db/skill_sets.py`, migration 87) MUST stay byte-for-byte unchanged — assert this in a test.

### 17-04 — 4-backend renderer + `.claude/agents/` materialization
**Edits:** `forge_materialization_service.py` add a `subagent` write branch → `.claude/agents/<safe>.md`, `result.written.append(WrittenFile(rel, "subagent", id))`; renderers `context_renderers/{claude,codex,gemini,opencode}.py` add subagent handling (claude: agents overlay; others: prompt-prefix block). Add `"subagent"` wherever the renderer kind list / `ContextCompilerService` enumerates kinds.
**Tests:** extend `backend/tests/test_forge_materialization.py` with a golden `.claude/agents/<name>.md` assertion + a 4-backend renderer golden snapshot.

### 17-05 — atomic create + compensating cleanup
**New file:** `backend/app/services/forge_create_service.py` with `create_and_bind_and_materialize(project_id, kind, payload, bind, materialize)`. **No DB-transaction option spans files**, so implement explicit compensation:
1. create row (per-kind create fn) — remember `asset_id`.
2. if `bind`: `add_project_forge_binding(...)` — remember `binding_id`.
3. if `materialize`: resolve workspace via `ProjectWorkspaceService.resolve_working_directory`; call `materialize_primitives(project, [kind], workspace_path)` — remember written `rel_paths`.
On exception at any step, reverse in LIFO: unlink written files (and let `_finalize_manifest` clean buckets), `remove_project_forge_binding(binding_id)`, delete the asset row. Wrap each compensation in try/except so cleanup itself can't mask the original error; re-raise the original.
**Route:** `POST /admin/projects/{project_id}/forge/create` in the forge router; validate `kind in VALID_FORGE_BINDING_KINDS`.
**Tests:** route test success path; **injected mid-flow failure** (monkeypatch `materialize_primitives` to raise) asserting no orphaned row, no binding, no repo file (criterion 2).
**Pitfall:** materialization is per-kind and reconciles the whole bound set for that kind — on rollback, deleting just the new file is correct, but re-running `_finalize_manifest` for the kind keeps the manifest consistent.

### 17-06 — forge-creator seed + session auto-import
**Seed:** five global-scope (`scope='project'`? — spec says global; use a sentinel project or a `scope='global'` skill row) creator skills: `skill-creator, rule-creator, hook-creator, command-creator, subagent-creator`. Each agentskills.io-compatible SKILL.md with **When to Use / Procedure / Pitfalls / Verification** sections instructing the in-session agent to scaffold files under `.claude/` (no in-session API auth). Compose into a `forge-creator` bundle. Seed at startup (idempotent — there is no existing on-disk SKILL.md fixture; create the canonical templates as part of this plan). Skills body lives on disk under `.claude/skills/<name>/SKILL.md` per the materializer's skill branch; `add_user_skill(skill_name, skill_path, ...)` records the row.
**Import handler:** new `backend/app/services/forge_import_handler.py` `on_session_complete_import(session_kind, session_id, project_id, status, output)`; register in `lifecycle.py` alongside the other three (own try/except). Logic: resolve workspace, diff `.claude/` tree against the forge manifest (`_load_manifest`), for each new/changed primitive file compute a content-hash, import via `HarnessLoaderService` import helpers + the 17-05 atomic API, record provenance (origin content-hash + `session_id`). **Only auto-bind if the session is Agented-driven** (see Open Questions); otherwise queue for review.
**Provenance store:** add columns or a `forge_import_provenance(asset_id, kind, origin_hash, source_session_id, imported_at)` table (migration 157).
**Tests:** import-handler test against a fixture `.claude/` tree (new files imported+bound for an Agented session; foreign files queued/skipped).

## Common Pitfalls
1. **Legacy `agents` vs forge `subagent`** (HIGH) — distinct tables; don't cross-wire. `_import_agents` is legacy.
2. **`replace_for_project` missing `_ensure_propagation_columns`** — call it before DELETE/INSERT or a fresh DB lacks the columns.
3. **Nested `get_connection()`** — `add_binding` opens its own connection/commit; a bundle-bind loop that wants true atomicity can't simply pass a shared conn unless you add a conn-accepting internal variant. Simplest: accept per-item idempotent upserts and treat partial failure as a 207-style report, OR add an internal `_add_binding(conn, ...)`.
4. **mcp.json / settings.json are `_NEVER_DELETE`** — subagent files are normal per-asset files, safe to reconcile.
5. **id type coercion** — bindings store `asset_id` as str; `subag-` ids are already strings (cleaner than int kinds).

## Verification Strategy

| Item | Tier | Rationale |
|------|------|-----------|
| `replace_for_project` preserves 4 provenance cols | L1 Sanity | direct repo round-trip assert |
| subagent CRUD + `VALID_KINDS` | L1 Sanity | route + repo tests |
| `.claude/agents/<name>.md` + 4-backend render | L1 Sanity | golden-file (`test_forge_materialization.py`) |
| atomic create success | L1 Sanity | route test |
| compensating cleanup (injected failure) | L2 Proxy | monkeypatch mid-flow, assert no orphans |
| bundle cross-kind bind | L1 Sanity | repo + route test |
| `skill_sets` unchanged | L1 Sanity | schema-diff assert |
| session auto-import diff+provenance | L2 Proxy | fixture `.claude/` tree handler test |
| House gates (`just build`, pytest, frontend no-new-fail) | L3 Deferred | full-suite watchdog procedure |

**L1 checks to always include:** new tables created by migrations 155–157; `"subagent" in VALID_FORGE_BINDING_KINDS`; golden `.claude/agents/` output byte-stable.

## Experiment Design
Not an ML phase — "experiment" = dogfood per house rule "Dogfood new pipelines against live data": run ≥3 real `.claude/`-scaffolding sessions through the import handler before declaring 17-06 done (avoids format-mismatch bugs unit fixtures miss).
- **Independent variable:** session source (Agented-driven vs foreign clone).
- **Dependent:** auto-bound vs queued; provenance hash recorded.
- **Control:** same `.claude/` file content.

## Production Considerations (from KNOWHOW.md)
KNOWHOW.md / LANDSCAPE.md / PAPERS.md do **not exist** for this milestone (empty research dir). From repo CLAUDE.md + MEMORY.md house rules:
- **All-four-backends** — renderer work must cover claude/codex/gemini/opencode (memory: "LLM features must support all 4 backends").
- **Sweep the bug class** — when fixing `replace_for_project`, grep every binding-write site for the same dropped-column pattern (memory: "Sweep for bug class on every fix").
- **Security** — auto-imported `.claude/` content is a system-prompt injection vector ×4 harnesses; the Agented-driven-session gate is the Phase 17 mitigation (full scan is Phase 6). Foreign-repo content must NOT auto-bind.
- **Backend suite hang** — full serial pytest hangs ~40-48%; use the 12-min watchdog + targeted-suite substitution and disclose in PR.

## Open Questions
1. **"Agented-driven session" detection** — spec says use session-id provenance, but the exact column/flag isn't confirmed in `project_sessions`. **Recommendation:** check `project_sessions`/`super_agent_sessions` for a `source`/`super_agent_id`/`driver` field during planning; the bus already passes `session_kind` (five kinds) — likely treat `project_session`/`super_agent`/`team_session`/`goal_loop` as Agented-driven and external clone-import (`HarnessLoaderService.load_from_github`) as foreign. Confirm before implementing 17-06.
2. **Global-scope skill rows** — `user_skills` has no `scope` column shown; spec wants "global-scope creator skills." Confirm whether global = a reserved sentinel project_id or a new scope flag; decide in 17-06 planning.
3. **Bundle-bind atomicity** — accept idempotent partial-success report vs. add a conn-accepting internal `_add_binding`. Recommend the internal variant for true atomicity (criterion 4 says "in one call").

## Sources
### Primary (HIGH — code read this session)
- `backend/app/db/project_forge_bindings.py` (`VALID_KINDS:24`, `add_binding`, `replace_for_project` bug, `_ensure_propagation_columns`)
- `backend/app/services/forge_materialization_service.py` (`materialize_primitives`, `_get_asset`, `_finalize_manifest`, `_NEVER_DELETE`)
- `backend/app_litestar/routes/rules_plugins_hooks_commands.py` (CRUD route pattern)
- `backend/app_litestar/routes/project_forge_bindings.py` (forge binding router)
- `backend/app/db/skills.py`, `backend/app/db/skill_sets.py`, `backend/app/db/__init__.py:556-562,737-747`
- `backend/app/db/ids.py:159,202` (`generate_id`)
- `backend/app/db/migrations/v07_features.py` (`V07_MIGRATIONS`, highest=154; 121=project_forge_bindings)
- `backend/app/services/execution_events.py:18,38,48` + `backend/app_litestar/lifecycle.py:454-485`
- `backend/app/services/harness_loader_service.py:195-419` (`_import_agents/_import_skills/_import_hooks/_import_commands`)
- `backend/app/services/context_renderers/{base,claude,codex,gemini,opencode}.py`, `context_compiler_service.py`
- `backend/app/services/harness_failure_annotator.py:304-323` (`_FETCHERS`, `parse_claude_stream`)
- `backend/tests/test_forge_materialization.py` (golden harness)
- `docs/superpowers/specs/2026-06-13-team-harness-self-improvement-design.md` §Phase 1

### Secondary
- agentskills.io SKILL.md format — spec asserts "When to Use / Procedure / Pitfalls / Verification"; no on-disk fixture exists to verify against (LOW; create canonical templates in 17-06).

## Citation Recovery
| Component | Source | Status | Priority |
|-----------|--------|--------|----------|
| agentskills.io SKILL.md schema | spec assertion | Unresolved (no fixture) | Normal |
| Agented-driven-session flag | code (to confirm) | Unresolved | Critical |

**Unresolved critical dependencies:** 1 (session-provenance flag — resolve in 17-06 planning).

## Metadata
**Confidence breakdown:** Architecture HIGH (code-read); replace_for_project bug HIGH (confirmed); subagent pattern HIGH; bundles MEDIUM (new schema, no precedent); auto-import session-detection MEDIUM (open question); SKILL.md format LOW (no fixture).
**Research date:** 2026-06-13 — **Valid until:** 2026-07-13 (stable codebase).
