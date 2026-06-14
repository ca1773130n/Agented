# GRD evolve → life-harness wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Replace Agented's dead `gd evolve` integration with the GRD life-harness (`gd harness round/status/revert`), mirroring round records into the DB + UI, and fix the broken GRD binary detection + 0.3.24 version refs.

**Spec:** `docs/superpowers/specs/2026-06-14-grd-life-harness-wiring-design.md`

**Tech:** Python/Litestar/SQLite (raw), pytest; Vue 3 + TS, Vitest, vue-i18n.

---

## Task 1: Fix GRD binary detection + version refs

**Files:** `backend/app/services/grd_cli_service.py`; test `backend/tests/test_grd_binary_detection.py`

- [ ] Test: monkeypatch `shutil.which` to return `/usr/local/bin/gd` → `GrdCliService.detect_binaries()` resolves gd via PATH and marks it a direct executable. Second test: no `which`, but a tmp `…/plugins/cache/x/grd/0.4.4/bin/gd.js` on the glob → resolves it as a `.js` (node-invoked).
- [ ] Run → fails.
- [ ] Implement: in `detect_binaries()`/`_detect_one`, add resolution order: (1) `shutil.which("gd")`/`which("grd-tools")`; (2) globs `~/.claude*/plugins/cache/*/grd/*/bin/{filename}`, `~/.nvm/versions/node/*/lib/node_modules/@jokerized/getresearchdone/bin/{filename}`; (3) legacy `*/GRD/bin/` globs; keep settings + `CLAUDE_PLUGIN_ROOT`. Track `is_executable` (PATH/exec) vs `.js` so `run_gd`/`run_command` build argv as `[path, *args]` vs `["node", path, *args]`. Bump version docstrings → v0.4.x.
- [ ] Run → passes. Commit `fix(grd): detect 0.4.x gd binary (npm/PATH + lowercase cache)`.

## Task 2: `grd_harness_rounds` DB table + CRUD

**Files:** `backend/app/db/migrations/v07_features.py` (new `_migrate_NNN_grd_harness_rounds`), `backend/app/db/grd_harness_rounds.py` (new), `backend/app/db/__init__.py` (export), `backend/app/db/ids.py` (`hround-` prefix); test `backend/tests/services/test_grd_harness_rounds_db.py`

- [ ] Test: `upsert_harness_round(project_id, record_dict)` inserts; re-upsert same `(project_id, round_id)` updates not duplicates; `list_harness_rounds(project_id)` newest-first; `get_harness_round(project_id, round_id)`.
- [ ] Run → fails.
- [ ] Implement migration (mirror `grd_ouroboros` migration style) + table (columns per spec) + CRUD module + `hround-` id + exports.
- [ ] Run → passes. Commit `feat(grd): grd_harness_rounds mirror table + CRUD`.

## Task 3: Harness round runner

**Files:** `backend/app/services/grd_harness_round_runner.py` (new); test `backend/tests/services/test_grd_harness_round_runner.py`

- [ ] Test: `_finalize_round(project_id, cwd, stdout_json, …)` parses a `RoundRecord` JSON + reads a fake `.planning/harness/rounds/<id>/{RECORD,patch,eval}.json` → calls `upsert_harness_round` with merged fields (status, confidence, summary, evidence_count, applied_sha, eval_json, patch_json). Error-path test: malformed stdout → status `error`, no crash.
- [ ] Run → fails.
- [ ] Implement: `run_round(project_id, cwd, *, auto, dry_run, full_eval)` → resolve gd binary (GrdCliService), build argv (`gd harness round […]`), spawn daemon thread that runs subprocess, on exit calls `_finalize_round`. `revert_round(...)` → `gd harness revert <id>`. `harness_status(...)` → `gd harness status` JSON. Broadcast SSE via the project's broadcaster (reuse ChatStateService/ProjectSessionManager `_broadcast` pattern — confirm at edit time).
- [ ] Run → passes. Commit `feat(grd): life-harness round runner (background + DB mirror)`.

## Task 4: Harness routes + evolve deprecation

**Files:** `backend/app_litestar/routes/grd_routes.py`; test `backend/tests/test_grd_harness_routes.py`

- [ ] Test (`isolated_db` + `create_test_client`, monkeypatch the runner): `POST …/grd/harness/round` → 202/200 `{status:"running"}`; `GET …/grd/harness/rounds` → mirrored rounds; `GET …/rounds/{id}`; `POST …/rounds/{id}/revert` (mocked); `GET …/harness/status` (mocked); `POST …/grd/evolve/start` → deprecation payload.
- [ ] Run → fails.
- [ ] Implement the 5 harness endpoints (calling the runner / DB CRUD), register in `grd_router`; change evolve-start to the deprecation pointer.
- [ ] Run → passes. Commit `feat(grd): harness round routes + deprecate evolve start`.

## Task 5: Frontend API + types

**Files:** `frontend/src/services/api/grdHarness.ts` (+ type); test extends `grdHarness.test.ts`

- [ ] Test: `grdHarnessApi.runHarnessRound/listHarnessRounds/getHarnessRound/revertHarnessRound/harnessStatus` call the right paths/methods.
- [ ] Run → fails.
- [ ] Implement methods + `HarnessRound` type (mirror existing `grdHarnessApi` shape).
- [ ] Run → passes. Commit `feat(grd): grdHarnessApi round methods + type`.

## Task 6: i18n `grdHarnessRounds` namespace (en/ko/ja/zh)

- [ ] Add a `grdHarnessRounds` namespace (run-round, status labels, revert, evidence/confidence/summary, deprecation banner) to all 4 locales (line-anchored insert, like the discovery feature). Verify JSON validity + key parity.
- [ ] Commit `feat(grd): grdHarnessRounds i18n (en/ko/ja/zh)`.

## Task 7: `HarnessRoundsPanel.vue` + evolve-panel deprecation

**Files:** `frontend/src/components/grd/harness/panels/HarnessRoundsPanel.vue` (new), `EvolvePanel.vue` (deprecation banner), wire the panel into its host; test `HarnessRoundsPanel.test.ts`

- [ ] Test: mounts; lists rounds (mock api); *Run round* calls `runHarnessRound`; revert calls `revertHarnessRound`.
- [ ] Run → fails.
- [ ] Implement panel (mirror `EvolvePanel.vue`), add a deprecation banner to `EvolvePanel`, mount the new panel where `EvolvePanel` is hosted.
- [ ] Run → passes. Commit `feat(grd): HarnessRoundsPanel + deprecate EvolvePanel`.

## Task 8: Full verification

- [ ] Backend targeted: the 4 new test files + `tests/test_grd*` + conversation/streaming regressions.
- [ ] `just build` (vue-tsc + vite).
- [ ] Frontend `npm run test:run` — no new failures vs the 7-failure baseline.

## Notes
- The gd binary is invoked directly (`gd …`) when resolved via PATH/exec, else `node gd.js …`.
- Reuse the `grd_ouroboros` mirror + evolve runner/routes/panel as templates; read exact anchors at edit time.
- Deprecate-not-delete evolve.
