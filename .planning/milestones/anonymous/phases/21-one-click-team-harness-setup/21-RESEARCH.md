# Phase 21: One-click Team Harness Setup - Research

**Researched:** 2026-06-13
**Domain:** Backend integration — idempotent orchestration service over existing Agented primitives (status column + SSE, forge bundles, SA instances, tesserae, autonomy policy, 4-renderer materialization)
**Confidence:** HIGH — every seam confirmed at file:line against the live codebase. No academic literature applies (pure integration phase).

## Summary

Phase 21 is a **pure integration phase**. It assembles already-shipped primitives into one idempotent `TeamHarnessSetupService.setup(project_id)` driven by a single ProjectDashboard button with step-level SSE progress. Almost nothing is net-new logic; the work is *wiring* — a status column, six step functions calling existing DB/service helpers, an SSE route mirroring `agents_and_tracing.stream_trace`, and a Vue surface mirroring the existing `grdInitStatus` chip.

The existing EVAL.md is largely sound but carries **three stale/incorrect seam citations** that the planner must NOT inherit (detailed in "EVAL Corrections" below): the grd_init_status baseline anchor, the renderer registry name, and the assumption that `create_team_instances` forwards a `driver` kwarg.

**Primary recommendation:** Build `TeamHarnessSetupService` as a thin sequential orchestrator. Each step is a small function that (a) checks a fingerprint/existence to decide skip-vs-run, (b) calls an existing helper, (c) writes a `harness_setup_steps` row. Wrap each step in try/except so a failure records `failed` and leaves the log intact. Re-runs reconcile because every underlying helper is already an upsert or PRAGMA-guarded/`ON CONFLICT` write.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. Constraints are taken from the phase requirements/success criteria verbatim:

### Locked Decisions
- REQ-19: `projects.harness_setup_status` (none/running/ready/failed) + "Setup Team Harness" button on ProjectDashboard with step-level SSE progress (grd_init pattern).
- REQ-20: `TeamHarnessSetupService` — six idempotent steps: GRD init, team topology + SAs (`driver=grd`), bundle binding, tesserae enable, default policies (evolution autonomy conservative; takeaway auto-apply per-project ON, scoped to skill-from-repetition / `discovered_procedure`), 4-harness materialization + per-backend compile smoke check. Re-run reconciles; steps independently retryable; no destructive deletes.
- REQ-21: Project-tailored bundle selection driven by map-codebase / STACK.md output (language/framework-conditional).

### Claude's Discretion
- Exact route paths, step-key naming, fingerprint scheme, SSE event envelope shape.
- Whether `harness_setup_steps` is a new table (recommended) or a JSON blob on projects (not recommended — loses per-step retry granularity).

### Deferred Ideas (OUT OF SCOPE)
- Live 4-backend dogfood (DEFER-21-01) and session auto-import idempotency (DEFER-21-02) — deferred to phase-21-08.

---

## EVAL Corrections (planner MUST read first)

The existing 21-EVAL.md cites several seams that are WRONG or stale. Corrected here so the planner does not inherit bad assumptions:

| EVAL claim | Reality (verified) | Impact |
|---|---|---|
| "grd_init_status … ~backend/app/db/migrations/v07_features.py:1181" and Baselines table "v07_features.py:1181" | `grd_init_status` is added by `_migrate_v54_project_grd_init_status` in **v05_features.py:38** (registered at v05_features.py:1528, id 54). v07:1181 is `_migrate_157_forge_origin`. | Planner must copy the PRAGMA-guard pattern from **v05_features.py:38-44**, not v07:1181. |
| "Migrations 159 and 160" / "next free migration 159/160" | Highest existing migration is **158** (`_migrate_158_driver_columns`, v07_features.py:1167; registered ~v07_features.py:1189 list). **Next free is 159** (and 160 if a second migration is needed). EVAL's "159/160" is correct; its parenthetical "(verify 159/160)" resolves to: 159 = first new, 160 = second new. | Use 159 for `harness_setup_status` column + steps table. If split into two migrations, 159 + 160. |
| "the `RENDERERS` dict / `renderer_for(backend)`" | The dict is named **`_REGISTRY`** (private), in `context_renderers/__init__.py:19-24`. The public accessor `renderer_for(backend)` at **:27** is the supported entry point. There is no public `RENDERERS`. | Plan must call `renderer_for("claude"|"codex"|"gemini"|"opencode")`, not reference `RENDERERS`. |
| Seam 2: "`create_team_instances` … where the `driver` kwarg flows (driver=grd)" | `InstanceService.create_team_instances(cls, project_id, team_id)` (**instance_service.py:52**) takes **NO driver kwarg**. The `driver` column lives on `project_sa_instances` (set via `project_sa_instances.add_instance(..., driver=...)` at **project_sa_instances.py:24** and `get_instance_driver` at **:61**). | Setting `driver=grd` requires either extending `create_team_instances`/`create_sa_instance` to forward `driver`, OR a post-create `update` of each SA instance's driver column. The planner must choose; the kwarg does NOT currently flow. This is the single most likely place to under-spec. |
| Seam 5: `_auto_apply_policy` "at repeated_request_gate.py:125" | CONFIRMED — `_auto_apply_policy(project_id)` at **repeated_request_gate.py:125**; reads `enabled` + `policy_json` and checks `"discovered_procedure" in kinds` at **:156**. EVAL correct here. | — |

---

## Confirmed Seams (file:line + signatures)

### Seam 0 — Status column + SSE route + dashboard wiring (REQ-19, SC1)

**Status column pattern (copy this):**
- Migration prior-art: `_migrate_v54_project_grd_init_status` — **v05_features.py:38-44**:
  ```python
  cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
  if "grd_init_status" not in cols:
      conn.execute("ALTER TABLE projects ADD COLUMN grd_init_status TEXT DEFAULT 'none'")
  ```
  Mirror exactly for `harness_setup_status TEXT DEFAULT 'none'`. Register as migration **159** in `V07_MIGRATIONS` (v07_features.py:1189 list).
- Steps table: new `harness_setup_steps` with PK `(project_id, step_key)` — recommended migration 159 or 160. Columns: `project_id, step_key, status TEXT, detail TEXT, fingerprint TEXT, updated_at`. PK gives idempotent upsert; `INSERT ... ON CONFLICT(project_id, step_key) DO UPDATE` (same shape as `upsert_policy` at project_autonomy_config.py:25).

**Status helpers (mirror these):**
- `GrdPlanningService.get_init_status(cls, project_id) -> str` at **grd_planning_service.py:149** — returns `project.get("grd_init_status") or "none"`. Build `get_harness_setup_status` identically (read via `get_project`, coalesce to `"none"`).
- Write path: `update_project(project_id, grd_init_status=...)` at **projects.py:60** (kwarg-per-column). **`update_project` does NOT yet accept `harness_setup_status`** — must add a `harness_setup_status: str = None` parameter + the `if ... is not None` block (projects.py:~109-111 is the pattern to copy). Alternatively add a dedicated `set_harness_setup_status` helper that does a direct `UPDATE projects SET harness_setup_status=?`.
- `projects.py:60` `update_project` full kwarg list confirmed: name, description, status, product_id, github_repo, owner_team_id, local_path, grd_sync_at, github_host, manager_super_agent_id, grd_init_status.

**SSE route pattern (copy this):**
- `agents_and_tracing.py` — `from litestar.response import Stream` (**:11**); `@get(".../stream", media_type="text/event-stream", sync_to_thread=False)` (**:182**); `async def event_generator(): ... yield f"event: X\ndata: {json.dumps(...)}\n\n"` (**:201-224**); `return Stream(event_generator(), media_type="text/event-stream")` (**:228**). This is the canonical SSE shape — use the same `event:`/`data:` framing for step events.
- Route registration: `grd_routes.py` uses `from litestar import Router, delete, get, post, put` (**:19**); endpoints like `@post("/{project_id:str}/planning/invoke", status_code=201)` (**:718**) and `@get("/{project_id:str}/planning/status")` (**:732**, returns `{"grd_init_status": ...}`). New harness-setup endpoints belong here or in `projects.py` route module; mirror the `_ensure_project` guard used by `planning_status`.
- Prior-art SSE route TEST: `backend/tests/routes/test_forge_bindings_routes.py` (confirmed present; only file under tests/routes/ matching forge/grd) — use as the TestClient template.

**Dashboard wiring (mirror grdInitStatus):**
- `ProjectDashboard.vue`: `grdInitStatus = ref<string>('none')` (**:91**); fetched and set at **:298-300**; `watch(grdInitStatus, ...)` at **:304**; status chip badges rendered at **:519-521** (`initializing`/`ready`/`failed`). Existing buttons: harness-btn (**:527**), setup-btn (**:537**). Add a `harnessSetupStatus = ref('none')` + a "Setup Team Harness" button + a step panel fed by an `EventSource`. There is currently **no ProjectDashboard test file** — P8 creates the first.

### Seam 2 — SA instances + driver=grd (REQ-20 step b, SC1/SC2)

- `InstanceService.create_team_instances(cls, project_id, team_id) -> Optional[Dict]` at **instance_service.py:52** — single entry point; creates a `project_team_instances` row + one SA instance per super-agent member. **No driver kwarg.** Also `create_sa_instance(cls, project_id, super_agent_id)` at **:181**.
- `project_sa_instances.add_instance(..., driver: str = None)` at **project_sa_instances.py:24** — the `driver` column is written here (**:34, :44**).
- `get_instance_driver(instance_id) -> Optional[str]` at **project_sa_instances.py:61** — the read used by S4/the EVAL assertion.
- Driver update path: `project_sa_instances.py:104` (`driver: str = None` → `if driver is not None: updates.append("driver = ?")` at :119-121).
- **PITFALL:** to satisfy `driver=grd`, the planner must thread `driver` through `create_team_instances` → `create_sa_instance` → `add_instance`, OR post-create `update(..., driver="grd")` each instance. Decide and specify in the plan; this kwarg does not flow today.
- Driver column origin migration: `_migrate_158_driver_columns` (v07_features.py:1167) — adds `projects.default_driver` and `project_sa_instances.driver`. `get_project_default_driver` at **projects.py:141**.

### Seam 3 — Bundle binding + forge-creator floor (REQ-20 step c / REQ-21, SC3)

- `get_forge_bundle_by_name(name) -> Optional[dict]` at **forge_bundles.py:74**.
- `bind_bundle_to_project(project_id, bundle_id) -> int` at **forge_bundles.py:152** — delegates to `project_forge_bindings.upsert_binding` (forge_bundles.py:23) for atomicity.
- Global floor: `forge_creator_seed.py` — `BUNDLE_NAME = "forge-creator"` (confirmed); seeds 5 creator skills via `create_forge_bundle` / `add_bundle_item`. Always bind this as the floor (fallback when STACK.md yields no language-specific bundle). Prior-art test: `test_forge_creator_seed.py`.
- `project_forge_bindings` table: `upsert_binding` (project_forge_bindings.py — INSERT at :113, has a `fingerprint` column added at :44, position via `MAX(position)+1` at :158). Re-bind is idempotent through `upsert_binding`. DELETE paths exist (:187, :204) — **must NOT be called** on re-run (no destructive deletes).

### Seam 4 — Tesserae enable (REQ-20 step d)

- `set_tesserae_root(project_id, root: Path) -> None` at **tesserae_integration.py:103** — `UPDATE projects SET tesserae_project_root=?`; **explicitly idempotent** ("Idempotent re-set is fine"); also best-effort binds the per-project Tesserae MCP server (`_ensure_tesserae_mcp_binding`).
- `get_tesserae_root(project_id) -> Optional[Path]` at **tesserae_integration.py:76** — reads `tesserae_project_root` column.
- `unset_tesserae_root_bindings(project_id)` at **tesserae_integration.py:131** — DESTRUCTIVE-adjacent (disables binding). **Must NOT be called on re-run** (P2 monkeypatches this to raise).
- Column `projects.tesserae_project_root` added by `_migrate_141_projects_tesserae` (v07_features.py:604).

### Seam 5 — Autonomy + auto-apply policy (REQ-20 step e, SC2)

- `AutonomyPolicy` (Pydantic) — **models/autonomy_policy.py**: `enabled: bool = False` (review-mode default), `confidence_threshold=0.85`, `max_ops_per_round=5`, `allowed_kinds=["rule","memory"]`, `block_deletes=True`, `cooldown_seconds=3600`, `rate_limit_per_day=10`.
- `upsert_policy(project_id, policy)` at **project_autonomy_config.py:25** — `ON CONFLICT(project_id) DO UPDATE` → idempotent. `get_policy(project_id) -> Optional[AutonomyPolicy]` at **:11**.
- `_auto_apply_policy(project_id) -> bool` at **repeated_request_gate.py:125** — reads `project_autonomy_config`; if a row exists, honors `enabled` AND requires `"discovered_procedure" in kinds` (**:156**); falls back to default if no row.
- Evolution autonomy gate: `autonomous_apply_eligible(round_row, policy, *, recent_auto_applies, recent_within_cooldown) -> AutonomyDecision` at **harness_autonomy.py:41** — multi-gate (kill_switch / enabled / eval_present / confidence / blast_radius / allowed_kinds / executable_kinds_opt_in / block_deletes / cooldown / rate). Kill-switch `AGENTED_AUTONOMY=0` at **harness_autonomy.py:25**.
- **DUAL-CONSUMER TENSION (key open question):** both consumers read the SAME `project_autonomy_config` row. The phase wants evolution-autonomy CONSERVATIVE (so `autonomous_apply_eligible` stays cautious) but takeaway auto-apply ON scoped to `discovered_procedure` (so `_auto_apply_policy` returns True). `_auto_apply_policy` requires `enabled=True` AND `discovered_procedure ∈ allowed_kinds`. Setting `enabled=True` ALSO flips the `enabled` gate ON for evolution autonomy. The conservatism for evolution must then come from the OTHER gates: keep `block_deletes=True` (default), low `confidence_threshold`/`max_ops_per_round`/`rate_limit_per_day` are already conservative, and `allowed_kinds` limited to `["discovered_procedure"]` (or `["discovered_procedure","memory"]`) — which means evolution rounds proposing `rule`/`hook` patches get blocked by the `allowed_kinds` gate. **Recommended policy row:** `AutonomyPolicy(enabled=True, allowed_kinds=["discovered_procedure"], block_deletes=True, max_ops_per_round=1, rate_limit_per_day=conservative)`. The planner must verify this satisfies both consumers and document it; P7 asserts both `get_policy` row shape AND `_auto_apply_policy(project_id) is True`.
- Migration: `_migrate_146_project_autonomy_config` (v07_features.py:980); schema `_project_autonomy.py`.

### Seam 6 — 4-renderer materialize + compile smoke (REQ-20 step f, SC2/SC5)

- `materialize_primitives(project: dict, kinds: list[str], workspace_path: Path) -> MaterializationResult` at **forge_materialization_service.py:183** — writes bound primitives into `workspace_path/.claude`; deterministic, no git. `_MANIFEST_REL = ".claude/agented-forge/manifest.json"` (:25); `_NEVER_DELETE = {manifest, .claude/settings.json, .claude/mcp.json}` (:27) — built-in destructive-safety.
- Renderers: `renderer_for(backend) -> Optional[Renderer]` at **context_renderers/__init__.py:27**; backing dict `_REGISTRY` (:19) keyed `claude/codex/gemini/opencode` (NOT `RENDERERS`). `Renderer.render(...)` mutates `(cmd, env)` given a `ContextBundle`.
- **Compile-smoke meaning:** for each of the 4 backends, call `renderer_for(b)` and exercise `.render(...)` against the materialized bundle; assert it returns non-None / non-empty without raising. The renderers transform `(cmd, env, bundle, session_id)`, so the "compile" check is "renderer runs cleanly over the projection," not a subprocess compile.
- Prior-art test: `backend/tests/test_forge_materialization.py` (confirmed present) — golden-file pattern for exactly this.

### Seam 7 — Idempotency mechanisms (SC4)

Every underlying write is already reconcile-safe:
| Table | Mechanism | Anchor |
|---|---|---|
| `harness_setup_steps` (new) | PK `(project_id, step_key)` + `ON CONFLICT DO UPDATE` | this phase |
| `project_forge_bindings` | `upsert_binding` (dedup by project+ref) | project_forge_bindings.py:113 |
| `project_sa_instances` | created under `cls._lock`; existence check before create | instance_service.py:52 |
| `project_autonomy_config` | `ON CONFLICT(project_id) DO UPDATE` | project_autonomy_config.py:28 |
| `projects.tesserae_project_root` | plain idempotent `UPDATE` | tesserae_integration.py:103 |
| `.claude/` projection | deterministic write + `_NEVER_DELETE` set | forge_materialization_service.py:27 |

**PITFALL:** SA instance creation is the one step NOT inherently dedup'd by a unique constraint — `create_team_instances` will create new instances each call unless the step first checks for existing instances for the team. The plan's step (b) MUST query existing instances (by `project_id`+`team_id`) and skip/reconcile rather than blindly calling `create_team_instances`.

### STACK.md / map-codebase tailoring (REQ-21, SC3)

- STACK.md location for THIS repo: **`.planning/codebase/STACK.md`** (confirmed present alongside ARCHITECTURE/CONVENTIONS/STRUCTURE/TESTING/CONCERNS/INTEGRATIONS). Produced by `/grd:map-codebase`.
- Format confirmed: `## Languages` section (e.g. "Python 3.10+", "TypeScript 5.4") and `## Frameworks` section (markdown headings). Parse these two sections to derive language keys.
- `GrdPlanningService.auto_init_project` (grd_planning_service.py:165) runs `/grd:map-codebase` then `/grd:new-project` via PTY — this is the GRD-init step (a) prior art; step (a) of the service reconciles to this (skip if `.planning/` exists).
- **Mapping derivation:** parse `## Languages` → match against seeded language-keyed bundle names via `get_forge_bundle_by_name(f"forge-{lang}")` (or similar convention); fall back to `forge-creator` floor when no match. The language→bundle mapping is a small static dict the plan defines; language-specific bundles may not be seeded yet, so **forge-creator is the guaranteed floor** and the only one P3 can assert unconditionally.

---

## Recommended Plan Decomposition

Seven implementation plans + one deferred validation plan, in three waves. Edges reflect data dependencies, not just sequence.

| Plan | Title | Wave | Depends on | Scope |
|---|---|---|---|---|
| 21-01 | Migration 159 + status helpers | 1 | — | `harness_setup_status` column (copy v05:38 pattern), `harness_setup_steps` table PK `(project_id, step_key)`, `get/set_harness_setup_status`, extend `update_project`. Tests: `test_harness_setup_status_migration.py` (S1, S2). |
| 21-02 | `TeamHarnessSetupService` skeleton + step framework | 1 | 21-01 | Service module, `HARNESS_SETUP_STEP_KEYS` (6), per-step try/except → StepResult, status state machine none→running→ready/failed, step-row upsert, fingerprint compare. Import smoke (S3). |
| 21-03 | Steps a+b: GRD init reconcile + team topology + SAs `driver=grd` | 2 | 21-02 | Step a (skip if `.planning/` exists, else GRD init), step b (existing-instance check + `create_team_instances` with driver threading OR post-update). Tests: driver=grd (S4), idempotency for these steps. **Resolve the driver-kwarg gap here.** |
| 21-04 | Steps c+d: STACK.md-tailored bundle binding + tesserae enable | 2 | 21-02 | Parse `.planning/codebase/STACK.md` Languages section → bundle selection w/ forge-creator floor; `bind_bundle_to_project`; `set_tesserae_root`. Tests: bundle_selection 3 fixtures (P3), tesserae idempotent. |
| 21-05 | Step e: default policies (dual-consumer) | 2 | 21-02 | `upsert_policy(AutonomyPolicy(enabled=True, allowed_kinds=["discovered_procedure"], block_deletes=True, ...))`; verify both `_auto_apply_policy` True and conservative evolution. Tests: autonomy_policy (P7). |
| 21-06 | Step f: 4-renderer materialize + compile smoke | 2 | 21-02 | `materialize_primitives` to tmp workspace; `renderer_for` over 4 backends; assert non-empty/no-raise. Tests: renderer_compile (P4), mirror `test_forge_materialization.py`. |
| 21-07 | Routes (POST trigger + GET status + SSE stream) + ProjectDashboard surface | 3 | 21-02..06 | POST `/admin/projects/{id}/harness-setup` (202, flips running, spawns thread like grd chat at grd_routes.py:709), GET status, GET `/stream` (Stream pattern agents_and_tracing.py:228). Vue button + chip + step panel + EventSource + i18n (en/ko/ja/zh). Tests: route/SSE (P5), ProjectDashboard (P8). |
| 21-08 | Deferred dogfood + house gates | 3 (deferred) | 21-07 | DEFER-21-01..04: live 4-backend run, session auto-import idempotency, `just build`, pytest watchdog + frontend. |

Wave-1 (21-01, 21-02) is the foundation. Wave-2 (21-03..06) are the four independent step groups (can be built in parallel after the skeleton lands). Wave-3 (21-07) wires the surface; 21-08 closes deferred validations.

**Cross-cutting idempotency tests** (P1 fresh/partial/full matrix, P2 no-destructive) belong in `test_team_harness_setup_service.py` and should be authored in 21-02 and extended as each step lands.

---

## Common Pitfalls

1. **SA-instance step is not constraint-dedup'd.** `create_team_instances` will duplicate instances on re-run unless step (b) checks for existing team instances first. Highest idempotency risk in the phase.
2. **`driver=grd` does not flow through `create_team_instances`.** Must extend the call chain or post-update — do not assume the kwarg exists.
3. **Dual-consumer policy collision (Seam 5).** `enabled=True` is required for takeaway auto-apply but also arms evolution autonomy's `enabled` gate. Constrain conservatism via `allowed_kinds=["discovered_procedure"]` + `block_deletes=True` + low rate/blast limits. Verify both gate readers.
4. **Destructive helpers exist and must stay un-called on re-run:** `unset_tesserae_root_bindings` (tesserae_integration.py:131), `project_forge_bindings` DELETE paths (:187/:204), instance deletion. P2 monkeypatches these to raise.
5. **Wrong migration baseline.** Copy the PRAGMA-guard from v05_features.py:38, NOT the EVAL's v07:1181 (that's forge_origin). Next free migration is 159.
6. **Renderer registry is `_REGISTRY` (private).** Use `renderer_for(backend)`; never reference a `RENDERERS` symbol — it doesn't exist.
7. **`materialize_primitives` signature is `(project: dict, kinds: list[str], workspace_path: Path)`** — pass the project dict (from `get_project`), the kinds list, and a tmp/real workspace path. Not `(project_id, ...)`.

## Verification Strategy

| Item | Tier | Rationale |
|---|---|---|
| Migration schema + default "none" (S1, S2) | L1 Sanity | Direct PRAGMA/helper check |
| Service import + 6 step keys (S3) | L1 | Import smoke |
| driver=grd on SA instances (S4) | L1 | Direct `get_instance_driver` assert |
| Ruff clean (S5) | L1 | Style gate |
| Idempotency matrix / no-destructive / bundle / renderer / route+SSE / failed-step / policy (P1-P8) | L2 Proxy | Unit/integration against `isolated_db`; binary pass/fail |
| Live 4-backend dogfood, session auto-import, just build, pytest+frontend (D1-D4) | L3 Deferred | Need real project + 4 backends + subprocess chain |

The EVAL's tiering (5 sanity / 8 proxy / 4 deferred) is sound and directly reusable. Targets are all binary ("all green" / "no new failures" / structural assert) — no numeric thresholds, correct for an integration phase.

## Production Considerations (from KNOWHOW.md)

No phase-level KNOWHOW.md found. From project memory/CLAUDE.md:
- **All LLM/harness features support 4 backends** — the per-backend compile smoke (step f) already honors this by iterating claude/codex/gemini/opencode.
- **Sweep the bug class** — if the SA-instance dedup bug exists, check every caller of `create_team_instances`.
- **i18n parity** — 21-07 must add the `harnessSetup.*` namespace to all four locales (en/ko/ja/zh), key-identical.
- **`just kill` is port-scoped** and the serial pytest suite hangs at ~40-48% — D4 uses the watchdog + targeted-set procedure from CLAUDE.md.

## Open Questions

1. **Dual-consumer policy exact values** — does `enabled=True, allowed_kinds=["discovered_procedure"]` fully satisfy "evolution conservative + takeaway auto-apply ON"? Resolve in 21-05 by reading both `autonomous_apply_eligible` and `_auto_apply_policy` against the proposed row. Recommendation: yes, with `block_deletes=True` + `max_ops_per_round=1`.
2. **Driver threading vs post-update** — extend `create_team_instances` signature (cleaner, broader blast radius) vs per-instance `update(driver="grd")` (narrower). Recommendation: post-update in step (b) to keep the change local to this phase.
3. **Language→bundle convention** — are language-keyed bundles (`forge-python`, etc.) seeded? If not, forge-creator floor is the only assertable selection; P3's language-conditional case is MEDIUM confidence until a naming convention is fixed. Resolve in 21-04.

## Sources

### Primary (HIGH confidence — verified at file:line)
- v05_features.py:38-44, :1528 — grd_init_status migration pattern
- v07_features.py:1167 (mig 158), :1189 (V07_MIGRATIONS list) — migration numbering
- grd_planning_service.py:149, :165 — get_init_status, auto_init_project (GRD init prior art)
- projects.py:60, :141 — update_project, get_project_default_driver
- agents_and_tracing.py:11,182,201-228 — SSE Stream pattern
- grd_routes.py:19,709,718,732 — Router + thread-spawn + status endpoint
- instance_service.py:52,181 — create_team_instances / create_sa_instance
- project_sa_instances.py:24,61,104 — add_instance(driver), get_instance_driver
- forge_bundles.py:74,152 — get_forge_bundle_by_name, bind_bundle_to_project
- project_forge_bindings.py:113,187,204 — upsert_binding, DELETE paths
- forge_creator_seed.py — BUNDLE_NAME="forge-creator"
- tesserae_integration.py:76,103,131 — get/set_tesserae_root, unset bindings
- project_autonomy_config.py:11,25 — get_policy, upsert_policy
- models/autonomy_policy.py — AutonomyPolicy fields
- repeated_request_gate.py:125,156 — _auto_apply_policy, discovered_procedure
- harness_autonomy.py:25,41 — AGENTED_AUTONOMY, autonomous_apply_eligible
- forge_materialization_service.py:25,27,183 — materialize_primitives, _NEVER_DELETE
- context_renderers/__init__.py:19,27 — _REGISTRY, renderer_for
- ProjectDashboard.vue:91,298,304,519-537 — grdInitStatus wiring
- .planning/codebase/STACK.md — Languages/Frameworks format
- tests/test_forge_materialization.py, tests/routes/test_forge_bindings_routes.py — prior-art test templates

## Metadata
**Confidence breakdown:**
- Seam anchors: HIGH — all confirmed at file:line in the live tree.
- Plan decomposition: HIGH — maps 1:1 to the six steps + EVAL tiers.
- Dual-consumer policy resolution: MEDIUM — recommended values pending read-through verification in 21-05.
- Language→bundle tailoring: MEDIUM — depends on whether language-keyed bundles are seeded.

**Research date:** 2026-06-13
**Valid until:** 30 days (stable internal codebase)
