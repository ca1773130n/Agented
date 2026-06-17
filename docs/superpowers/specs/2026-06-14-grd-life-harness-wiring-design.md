# GRD evolve → life-harness wiring — design

**Date:** 2026-06-14
**Status:** approved (design)
**Sub-project 1 of 4** in the "wire GRD 0.4.5 + Tesserae 0.9.0" milestone
(others: Tesserae distilled memory; GRD multi-candidate planning; GRD patterns → GENOME-SUGGESTIONS).

## Summary

GRD deprecated `gd evolve` in 0.4.3 (it now no-ops and points at the life-harness).
Agented still wires `gd evolve` (`GrdEvolveSessionHandler`), so that feature is
effectively dead. Replace it by wiring the **life-harness** (`gd harness
round/status/revert`), mirroring round records into Agented's DB and surfacing
them in the UI. Also fix two foundational bugs that block all GRD wiring: the
**binary-detection glob** (looks for `GRD/bin`, real path is lowercase `grd/<ver>/bin`
or the npm `gd` on PATH) and the **0.3.24 → 0.4.x version references**.

## Foundational fixes

### Binary detection — `app/services/grd_cli_service.py`
Current `_detect_one` globs only `…/plugins/*/GRD/bin/{gd.js,grd-tools.js}` (uppercase),
which never matches. Real locations (from recon):
- On PATH: `gd`, `grd-tools` (npm `@jokerized/getresearchdone` symlinks) — most robust.
- Cache: `~/.claude*/plugins/cache/*/grd/*/bin/{gd.js,grd-tools.js}` (lowercase).
- npm global: `~/.nvm/versions/node/*/lib/node_modules/@jokerized/getresearchdone/bin/{…}`.

Fix `detect_binaries()` to, in order: (1) `shutil.which("gd")`/`which("grd-tools")`;
(2) the new lowercase-cache + npm-global globs; (3) the legacy `GRD` globs (back-compat);
(4) the existing settings-table + `CLAUDE_PLUGIN_ROOT` overrides. Record whether the
resolved path is a direct executable (invoke `gd …`) or a `.js` (invoke `node …/gd.js …`),
so callers build argv correctly.

### Version references
Update the `grd_cli_service` docstrings and the `execution_type_handler` "install GRD
v0.3.24+" message to v0.4.x.

## Life-harness wiring

### Runner — `app/services/grd_harness_round_runner.py` (new)
`run_round(project_id, cwd, *, auto=False, dry_run=False, full_eval=False) -> str`
(returns a run/job id): spawns `gd harness round [--auto|--dry-run|--full-eval]` on a
**background daemon thread** (the round spawns a proposer agent; it's long-ish). On
completion: parse the stdout `RoundRecord` JSON; read `.planning/harness/rounds/<round_id>/`
(RECORD.json, patch.json, eval.json) for full detail; `upsert_harness_round(...)` into the
DB; broadcast an SSE `grd_harness_round` delta. Best-effort: failures are logged + recorded
with status `error`, never crash. `revert_round(project_id, cwd, round_id)` runs
`gd harness revert <id>` and updates status. `harness_status(project_id, cwd)` runs
`gd harness status` (live JSON) for the status endpoint.

### DB — `grd_harness_rounds` (new table + migration in `v07_features.py`)
Columns: `id` (`hround-` prefix), `project_id` (FK), `round_id` (gd `YYYYMMDD-HHMMSS`),
`status` (applied|evaluated|rejected|skipped|gathered|error|running), `detail`,
`evidence_count`, `patch_hash`, `confidence`, `summary`, `applied_sha`, `eval_json`,
`patch_json`, `created_at`, `updated_at`. Unique `(project_id, round_id)`; index
`(project_id, created_at DESC)`. CRUD in `app/db/grd_harness_rounds.py`, exported via
`app/db/__init__.py`. Mirrors the existing `grd_ouroboros` mirror pattern.

### Routes — `app_litestar/routes/grd_routes.py` (under `/api/projects/{project_id}`)
- `POST /{project_id}/grd/harness/round` `{auto?, dry_run?, full_eval?}` → triggers a
  round (background), returns `{round_job: id, status: "running"}`.
- `GET /{project_id}/grd/harness/rounds` → list mirrored rounds from DB.
- `GET /{project_id}/grd/harness/rounds/{round_id}` → one round (incl. patch/eval).
- `POST /{project_id}/grd/harness/rounds/{round_id}/revert` → revert an applied round.
- `GET /{project_id}/grd/harness/status` → live `gd harness status`.
Register in `grd_router`.

### Evolve — deprecate, don't delete
Keep `grd_evolve_runs` + `GET …/grd/evolve/runs[/{id}]` read-only (historical). Change
`POST …/grd/evolve/start` to return HTTP 410-style payload `{deprecated: true, use:
"…/grd/harness/round"}` (since `gd evolve` no-ops). Leave the handler/runner code in place
(read-only), comment as deprecated.

### Frontend
- `frontend/src/services/api/grdHarness.ts`: add `runHarnessRound`, `listHarnessRounds`,
  `getHarnessRound`, `revertHarnessRound`, `harnessStatus` (+ a `HarnessRound` type).
- `frontend/src/components/grd/harness/panels/HarnessRoundsPanel.vue` (new): trigger a
  round (review/auto/dry-run), list rounds with status/summary/confidence/eval, revert an
  applied round. Mirror `EvolvePanel.vue` conventions. Mark the evolve panel deprecated
  (banner pointing at the rounds panel).
- i18n: `grdHarnessRounds.*` keys in en/ko/ja/zh.

## Data flow
Operator clicks *Run round* → `POST …/harness/round` → background `gd harness round`
(evidence from the project's `.tesserae/graph.json` Session findings) → record mirrored to
`grd_harness_rounds` + SSE → panel shows the round (status, patch summary, eval, confidence)
with Revert for applied rounds.

## Error handling
Binary not found → routes return a clear 4xx ("GRD CLI not detected — install
@jokerized/getresearchdone or the grd plugin"). Round subprocess failure/timeout →
recorded `status=error` + detail; never crashes. Revert of a non-applied round → 4xx.
Missing `.planning/harness/rounds/<id>/` (e.g. skipped round) → mirror from stdout JSON only.

## Testing
- Runner unit: mock the `gd` subprocess (stdout RoundRecord JSON) + a fake
  `rounds/<id>/` dir → assert DB mirror + parsed status; error path.
- Binary detection unit: `which` precedence + glob fallbacks (monkeypatch shutil.which +
  a tmp plugin tree).
- Route tests (`isolated_db` + `create_test_client`): trigger (mocked runner), list, detail,
  revert, status; evolve-start deprecation.
- Frontend: `HarnessRoundsPanel` (mock api: run + list + revert), `grdHarness` api unit.
- Verify: `just build` + targeted backend suites + frontend `test:run` (no new failures).

## Scope / non-goals (this sub-project)
Out: 0.4.5-only clarification gate + Runbook/Gotcha-as-evidence (needs 0.4.5 installed);
upstream cross-project UI (config-only); the other 3 milestone slices. No destructive
removal of evolve.
