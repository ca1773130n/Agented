# Tesserae Distilled Memory (Runbook/Gotcha) — Design

**Milestone:** "Wire GRD 0.4.5 + Tesserae 0.9.0" → sub-project #2 of 4.
**Branch:** `feat/grd-life-harness-wiring` (continues the milestone branch).
**Date:** 2026-06-15

## Goal

Wire Tesserae 0.9.0's **AgentRunbook distilled memory** (Event/Runbook/Gotcha
nodes) into Agented: let operators enable distillation per project, run it
during compile, and feed the distilled pools into the harness KG-signal
pipeline via multi-pool retrieval — without disturbing the deadline-gated
live leader-chat `ask` path.

## Grounding (verified against installed Tesserae 0.9.0)

- `tesserae compile --project <root> [--distill | --no-distill]` produces the
  Event/Runbook/Gotcha layers. Resolution order: CLI flag > config
  `distillation.enabled` > `TESSERAE_RUNBOOK_DISTILLATION` env > OFF.
  `min_sessions` is hardcoded to 2 in Tesserae (not configurable).
- `tesserae context "<q>" --project <root> --multi-pool` does multi-pool
  retrieval (reserves slots for Runbook/Gotcha/Event memory) and prints a
  **cited context doc as text** to stdout (or `--output FILE`). It takes
  `--budget` (char budget, default 32000), **not** `--top-k`, and has **no
  `--json`**. Multi-pool is NOT available on `tesserae ask`.
- **Linkage payoff:** the GRD life-harness wired in sub-project #1 already
  consumes `Runbook→takeaway` / `Gotcha→insight` from `.tesserae/graph.json`.
  Enabling `--distill` on Agented's compile therefore enriches #1's harness
  rounds automatically.

### Discovered latent bug (OUT OF SCOPE — flag, do not fix here)

`tesserae_integration._run_tesserae_subcommand` builds `tesserae project <op>`.
In 0.9.0 the `project` command group is a deprecation stub ("project has
moved"); `tesserae project compile --help` exits 2. So `init_workspace` and
`build_site` (and, before this change, `compile_workspace`) are broken on
0.9.0. The modern top-level commands are `tesserae init` / `tesserae compile`
(there is no top-level `build-site` — `serve` auto-builds). This sub-project
fixes only the **compile** path (required for `--distill`); `init`/`build-site`
remain on the deprecated helper and are reported as a follow-up.

## Design

### 1. Per-project toggle (control surface)
- Migration `_migrate_166_projects_tesserae_distill`: add
  `projects.tesserae_distill_enabled INTEGER DEFAULT 0` (idempotent
  PRAGMA-guarded ADD COLUMN, mirroring `_migrate_141`).
- Helper in `tesserae_integration.py`: `get_distill_enabled(project_id) -> bool`
  (reads the column; False when unset/missing).
- Route `POST /admin/system/memory/tesserae/projects/{id}/distill` with body
  `{"enabled": bool}` → inline `UPDATE projects SET tesserae_distill_enabled`;
  returns the refreshed per-project state row.
- `_tesserae_per_project_state()` SELECT adds `tesserae_distill_enabled`;
  each entry gains `"distill_enabled": bool(...)`.

### 2. Compile with distillation (modern CLI form)
- `compile_workspace(project_id)` rebuilt to run the modern command directly
  (new private `_run_tesserae(op, args, *, cwd, timeout)` that does NOT prepend
  `project`, returning the same `TesseraeOpResult`):
  `tesserae compile --project <root> [--distill | --no-distill]`
  `--distill` when `get_distill_enabled(project_id)` is True, else `--no-distill`
  (explicit, so a project toggle reliably overrides any global config/env).
- `init_workspace` / `build_site` keep the old helper (flagged bug, separate).

### 3. Consume via multi-pool (KG-signal path only)
- New `context_tesserae(project_id, question, *, multi_pool=True, budget=None)
  -> Optional[str]` mirroring `ask_tesserae`'s direct-subprocess shape:
  `tesserae context "<q>" --project <root> [--multi-pool] [--budget N]`,
  returns stdout text or None on any failure.
- `harness_kg_signals.gather_kg_signals`: when `get_distill_enabled(project_id)`
  is True, query via `context_tesserae(project_id, q, multi_pool=True)`;
  otherwise keep `ask_tesserae(project_id, q, top_k=5)`. The downstream text
  handling is identical (it already treats the answer as opaque text).

### 4. Frontend
- `memory-system.ts`: `setTesseraeDistill(projectId, enabled)` →
  `POST .../distill`; add `distill_enabled?: boolean` to `TesseraeProjectState`.
- `MemorySystemSettings.vue`: per-project distill checkbox (disabled unless the
  project is Tesserae-enabled), calling `setTesseraeDistill` + reloading the row.
- i18n `settings.memory.distillLabel` + `toastDistillEnabled/Disabled` (and a
  short help line) across en/ko/ja/zh (key-identical).

## Scope / non-goals
- Live leader-chat `ask` path UNCHANGED (deadline-gated, rarely fires; `ask`
  has no multi-pool anyway).
- `init`/`build-site` `project`-prefix breakage: reported, not fixed here.
- `tesserae config status` diagnostic surfacing: deferred (minor).
- `min_sessions`: not configurable (Tesserae hardcodes 2).

## Tests
- Backend: compile argv includes `--distill` iff toggle on, `--no-distill`
  otherwise, and uses `tesserae compile` (not `project compile`);
  `context_tesserae` argv (multi-pool/budget/project) + None on failure;
  `gather_kg_signals` dispatches to context vs ask by toggle; distill route +
  column round-trip.
- Frontend: the per-project distill toggle calls `setTesseraeDistill` and
  reflects state; disabled when the project is not Tesserae-enabled.

## Verification
`just build`; backend targeted pytest (tesserae integration + kg-signals +
memory routes + new tests); frontend `npm run test:run` (no new failures vs the
7-failure baseline).
