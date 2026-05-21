# Static-Smell Triage — 10 sidebar pages

Follow-up to `.planning/sidebar-audit.md` (`2d22e15`). The audit's
"static-smell" tag was assigned because no `*Api.*` symbol appeared in
`<script setup>`. On closer inspection **every page on this list uses
raw `fetch('/admin/...')` calls** rather than the typed `api.*` client,
which the original audit's grep didn't catch. So all 10 pages are
wired to at least a stub backend route — none qualify for outright
DELETE under the criteria. Verdicts below reflect whether the backing
route is real (KEEP) or a stub (STUB-PROMOTE), and whether any
non-sidebar inbound refs exist.

No non-sidebar inbound references were found for any of the 10 routes
(searched `frontend/src/` excluding `router/routes/*` and
`components/layout/AppSidebar.vue`). "Inbound refs" below therefore
means "sidebar only" unless stated.

Totals: **DELETE 0 / KEEP 4 / STUB-PROMOTE 6.**

---

## team-leaderboard (`views/TeamLeaderboard.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 403-line page that fetches `/admin/analytics/team-leaderboard?period=...` and renders periods + rows. Backend handler exists but returns `{"teams": []}` — a stub. UI is real; data plane is hollow.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/reports.ts:35`).
- **Last touched:** 2026-05-11 (`8943ead`) — TS-error sweep, not a substantive change; previous substantive touch was March 2026.
- **Has backend route?** partial (`/admin/analytics/team-leaderboard` exists in `backend/app_litestar/routes/leaf_crud_c.py:186` but returns an empty stub).

## execution-anomaly-detection (`views/ExecutionAnomalyDetection.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 441-line page that fetches `/admin/executions/anomalies` and POSTs `/acknowledge`. Backend file `executions.py` explicitly labels these "anomaly stubs" — POST acknowledge does `del anomaly_id` (no-op). UI is wired; backend is a placeholder waiting for the anomaly-detector to land.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/observabilityExt.ts:42`).
- **Last touched:** 2026-03-19 (`bba509e`).
- **Has backend route?** partial (`/admin/executions/anomalies` + `/admin/executions/anomalies/{id}/acknowledge` in `backend/app_litestar/routes/executions.py:452+` — declared as stubs in the module docstring).

## team-budgets (`views/TeamBudgetsPage.vue`)

- **Status:** KEEP
- **Rationale:** 391-line page that fetches `/admin/budgets`, plus `/test-alert` and PUT `/admin/budgets/{teamId}`. The `budgets_router` in `backend/app_litestar/routes/budgets.py` is a **real** CRUD surface backed by `app.db.budgets` + `BudgetService` (not a stub) — it powers trigger-time enforcement too. Page is the primary admin UI for that surface.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/misc.ts:19`), but the backend itself is consumed by `triggers.py` for budget gating.
- **Last touched:** 2026-03-20 (`7c8b652`).
- **Has backend route?** yes (`/admin/budgets/*` — list, get, set, delete, check — in `backend/app_litestar/routes/budgets.py:289`).

## execution-quota-controls (`views/ExecutionQuotaControls.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 449-line CRUD UI against `/admin/executions/quotas`. Full GET/POST/PUT/DELETE handlers exist (`executions.py:485-504`) but every write handler `del`s its parameters and returns no-op dicts — flagged as "quota stubs" in the module docstring. Frontend is the most complete piece of this feature.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/executions.ts:64`).
- **Last touched:** 2026-03-19 (`304b8cb`).
- **Has backend route?** partial (`/admin/executions/quotas` CRUD in `backend/app_litestar/routes/executions.py:485+` — declared as stubs).

## report-digests (`views/ReportDigestsPage.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 529-line page (largest of the batch) fetching `/admin/reports/digests` with create + per-team-id PUT. Backend `report_digests_router` exists at `backend/app_litestar/routes/leaf_crud_c.py:289` with `list_digests` returning `{"digests": []}` and update/create echoing input — comment at line 255 reads "/admin/reports/digests/* (3) — stubs". UI is the only real artifact.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/reports.ts:7`).
- **Last touched:** 2026-03-20 (`7c8b652`).
- **Has backend route?** partial (`/admin/reports/digests` in `backend/app_litestar/routes/leaf_crud_c.py:259+` — stubs).

## mobile-execution-monitor (`views/MobileExecutionMonitor.vue`)

- **Status:** KEEP
- **Rationale:** 360-line mobile-first variant that fetches `/admin/executions?limit=30` — the **real** executions endpoint also used by the main executions list. Not a stub; this is a legitimate alternate view of live data and could ship today as a small-screen surface. Different concern from "is the feature finished" — the page works end-to-end.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/executions.ts:71`).
- **Last touched:** 2026-03-19 (`8571feb`).
- **Has backend route?** yes (`/admin/executions` is the canonical executions listing route, real data).

## bot-sla-uptime (`views/BotSlaUptimePage.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 320-line page fetching `/admin/bots/sla`. Handler is one line at `backend/app_litestar/routes/misc.py:91` with docstring `"""Stub — bot SLA / uptime is not yet tracked."""` returning `{"bots": []}`. UI is built but the metric pipeline doesn't exist.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/bots.ts:127`).
- **Last touched:** 2026-03-20 (`6461fd5`).
- **Has backend route?** partial (`/admin/bots/sla` exists in `backend/app_litestar/routes/misc.py:91` as an explicit stub).

## system-errors (`views/SystemErrorsPage.vue`)

- **Status:** KEEP
- **Rationale:** **Surprise — this was flagged but is the most-real page on the list.** 709-line view (largest), uses a `useSystemErrors` composable instead of raw fetches (so it didn't show up in the `api.*` grep _or_ a `fetch(` grep against the .vue file). Backend `Router(path="/admin/system", ...)` in `backend/app_litestar/routes/admin_tooling.py:224` exposes 7 handlers backed by the real `app.db.system_errors` table (`list_system_errors`, `get_system_error_with_fixes`, `update_system_error_status`). Touched 2026-05-10 in the date-formatter migration — actively maintained.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/observabilityExt.ts:7`).
- **Last touched:** 2026-05-10 (`f5518f5`).
- **Has backend route?** yes (`/admin/system/*` — 7 handlers in `backend/app_litestar/routes/admin_tooling.py:126+`).

## structured-output (`views/StructuredOutputPage.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 443-line page calling `/admin/bots/structured-output`, `/schema`, and `/test`. **No backend route exists for any of those paths** — every call will 404. By the literal DELETE criteria this qualifies (no backend, no inbound refs, hasn't been touched since March 16). But the UI is substantive (schema editor + test runner) and points at a coherent feature; deleting it loses real design work. Recommend STUB-PROMOTE and either build the backend or formally cut both halves together in a separate ShipOrCut decision.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/prompts.ts:7`).
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Has backend route?** no.

## bot-runbooks (`views/BotRunbooksPage.vue`)

- **Status:** STUB-PROMOTE
- **Rationale:** 470-line CRUD UI calling `/admin/bots/runbooks` (list) and `/admin/bots/{botId}/runbook[/{runbookId}]` (write). **No backend route exists.** Page also has the highest stub/placeholder marker count of the batch (5 matches). Same reasoning as `structured-output`: literal DELETE criteria fit, but UI is substantive and represents intentional design — flag for ShipOrCut as a feature pair.
- **Inbound refs:** sidebar only (router entry at `frontend/src/router/routes/bots.ts:106`).
- **Last touched:** 2026-03-19 (`bba509e`).
- **Has backend route?** no.

---

## Notes for PR-A

- **No outright deletions** from this batch — all 10 pages have at
  least a stub backend or real handler. The original "static-smell"
  signal was a false positive caused by these views bypassing the
  `api.*` client.
- **Recommended PR-A action:** sidebar IA redesign can safely
  reorganize all 10 entries; none need to be removed in PR-A.
- **Recommended ShipOrCut backlog** (in priority order — biggest UI
  investment with no backend first):
  1. `bot-runbooks` (470 LOC UI, zero backend) — build it or cut both.
  2. `structured-output` (443 LOC UI, zero backend) — same.
  3. `report-digests` (529 LOC UI, stub backend) — finish the stubs.
  4. `execution-quota-controls` (449 LOC, stub backend).
  5. `execution-anomaly-detection` (441 LOC, stub backend).
  6. `team-leaderboard` (403 LOC, stub backend).
  7. `bot-sla-uptime` (320 LOC, stub backend).
- **Surprise:** `system-errors` is the only flagged page that's fully
  wired front-to-back on real data. It only "smelled" static because
  the composable hid its fetches from a quick `fetch(` grep.
