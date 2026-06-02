# Phase 1 — Sidebar Hard-Cuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (tasks are sequential and edit shared files — AppSidebar.vue, locale catalogs — so inline/sequential execution is required, NOT parallel subagents). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove 13 non-functional or duplicate "feature-checklist" surfaces (sidebar slot + route + Vue view + orphaned tests + dead backend stubs), shrinking the sidebar and the codebase without breaking anything load-bearing.

**Architecture:** Pure deletion sweep, ordered so every commit leaves `just build` + `pytest` + `npm run test:run` green. Sidebar references are removed *before* the routes they point at; views are deleted with their tests; dead backend stubs (`misc.py` SLA, `executions.py` quotas, leaf_crud digests) are removed last. A sidebar structure-guard test is inverted first (TDD red→green) to lock the intent.

**Tech Stack:** Vue 3 + TS (`frontend/`), Litestar + raw SQLite (`backend/`), Vitest, pytest, vue-i18n (en/ko/ja/zh).

**Source spec:** `docs/superpowers/specs/2026-06-02-sidebar-prune-and-harden-design.md` §3A/§3B.

---

## Removal set (13 features)

Routes: `bot-runbooks`, `bot-sla-uptime`, `execution-quota-controls`, `report-digests`,
`mobile-execution-monitor`, `dependency-impact-bot`, `webhook-recorder`,
`provider-benchmark-dashboard`, `bot-clone-fork`, `cross-team-bot-sharing`,
`incident-response-playbooks`, `inline-prompt-editor`, `bot-output-piping`.

Verification commands (used throughout):
- Frontend: `cd frontend && npm run test:run` and `npm run build`
- Backend: `cd backend && uv run pytest -q`
- Reference sweep: `grep -rn "<route-name>\|<ViewName>" frontend/src backend --include=*.ts --include=*.vue --include=*.py`

---

### Task 1: Invert the sidebar structure guard (TDD red), then strip sidebar entries

**Files:**
- Test: `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`
- Modify: `frontend/src/components/layout/AppSidebar.vue`

- [ ] **Step 1: Make the guard assert the 13 routes are GONE (red).**
  In `AppSidebar.structure.test.ts`, remove the 13 route names from any "expected present" list and add an assertion that none of them render. Add this block (adjust the existing rendered-names helper name if different):

```ts
const REMOVED_ROUTES = [
  'bot-runbooks','bot-sla-uptime','execution-quota-controls','report-digests',
  'mobile-execution-monitor','dependency-impact-bot','webhook-recorder',
  'provider-benchmark-dashboard','bot-clone-fork','cross-team-bot-sharing',
  'incident-response-playbooks','inline-prompt-editor','bot-output-piping',
];
it('does not expose any pruned (Phase 1) routes', () => {
  const html = wrapper.html(); // or the existing rendered-sidebar string
  for (const name of REMOVED_ROUTES) {
    expect(wrapper.findAll(`[data-route="${name}"]`).length).toBe(0);
  }
  // also assert the navTo targets are absent from the component source contract
});
```
  If the existing test asserts an exact route-name array, just delete the 13 entries from that array instead — that is sufficient as the red/green guard.

- [ ] **Step 2: Run it — expect FAIL.** `cd frontend && npm run test:run -- AppSidebar.structure` → FAIL (routes still present).

- [ ] **Step 3: Strip all sidebar references in `AppSidebar.vue`.** Remove, for each of the 13 routes:
  - its `expandedSections` key (lines ~51-74) if the route was a group toggle (`bot-output-piping` etc. are submenu items, not toggles — skip);
  - its `<button … @click="navTo('<route>')">` submenu item in the template;
  - its entry in the relevant `isXSectionActive()` route-name list and in `autoExpandForRoute()`.
  Affected blocks: Triggers submenu (`webhook-recorder`, `dependency-impact-bot`, `bot-clone-fork`→cloneForkBot, `cross-team-bot-sharing`, `incident-response-playbooks`, `inline-prompt-editor`→livePromptSandbox, `bot-output-piping`→outputPiping, `bot-runbooks`); Platform submenu (`bot-sla-uptime`, `execution-quota-controls`, `report-digests`, `mobile-execution-monitor`); Analytics submenu (`provider-benchmark-dashboard`). Update the `isTriggersSectionActive`, `isPlatformSectionActive`, `isAnalyticsSectionActive` arrays accordingly.

- [ ] **Step 4: Run guard — expect PASS.** `cd frontend && npm run test:run -- AppSidebar.structure` → PASS.

- [ ] **Step 5: Full frontend gate + commit.**
```bash
cd frontend && npm run test:run && npm run build
git add frontend/src/components/layout/AppSidebar.vue frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts
git commit -m "refactor(sidebar): remove 13 non-functional/duplicate feature slots (Phase 1)"
```

---

### Task 2: Delete routes + view files + orphaned frontend tests

**Files (routes to remove the matching `{ … name: '<route>' … }` block from):**
- `frontend/src/router/routes/bots.ts` — `cross-team-bot-sharing` (:21), `dependency-impact-bot` (:28), `bot-clone-fork` (:56), `bot-output-piping` (:63), `bot-runbooks` (:77), `bot-sla-uptime` (:98)
- `frontend/src/router/routes/executions.ts` — `execution-quota-controls` (:63), `mobile-execution-monitor` (:70)
- `frontend/src/router/routes/reports.ts` — `report-digests` (:7)
- `frontend/src/router/routes/triggersExt.ts` — `webhook-recorder` (:7)
- `frontend/src/router/routes/observabilityExt.ts` — `provider-benchmark-dashboard` (:33)
- `frontend/src/router/routes/notifications.ts` — `incident-response-playbooks` (:49)
- `frontend/src/router/routes/prompts.ts` — `inline-prompt-editor` (:28)

**Files to delete (views + tests):**
- 13 view files: `BotRunbooksPage.vue BotSlaUptimePage.vue ExecutionQuotaControls.vue ReportDigestsPage.vue MobileExecutionMonitor.vue DependencyImpactBot.vue WebhookRecorder.vue ProviderBenchmarkDashboard.vue BotCloneForkPage.vue CrossTeamBotSharing.vue IncidentResponsePlaybooksPage.vue InlinePromptEditor.vue BotOutputPipingPage.vue` (all under `frontend/src/views/`)
- `frontend/src/views/__tests__/ExecutionQuotaControls.test.ts`
- `frontend/src/views/__tests__/ReportDigestsPage.test.ts`

**Files to edit (drop dangling references):**
- `frontend/src/tests/scenario-full-workflow.test.ts` — remove the `bot-clone-fork` step/assertion.
- `frontend/src/components/base/NotEnabledBanner.vue` and `frontend/src/services/api/error-handler.ts` — remove any `execution-quota-controls` / `report-digests` / view-name entries (grep them; delete the list items).

- [ ] **Step 1: Reference sweep (pre-flight).** For each route, run the reference-sweep grep above and confirm only router/scenario/NotEnabledBanner/error-handler/test hits remain (all handled here).
- [ ] **Step 2: Delete the route blocks** listed above (remove the whole `{ … },` object).
- [ ] **Step 3: Delete the 13 view files + 2 orphaned test files** (`git rm`).
- [ ] **Step 4: Edit scenario-full-workflow.test.ts + NotEnabledBanner.vue + error-handler.ts** to drop the references.
- [ ] **Step 5: Frontend gate.** `cd frontend && npm run test:run && npm run build` → PASS (no unresolved imports, no dead routes).
- [ ] **Step 6: Commit.**
```bash
git add -A frontend/src
git commit -m "refactor(routes): delete 13 pruned views + routes + orphaned tests (Phase 1)"
```

---

### Task 3: Remove orphaned i18n nav keys (all 4 locales)

**Files:** `frontend/src/locales/{en,ko,ja,zh}.json`

Keys to remove from `nav.*` in **every** locale (key-identical):
`botRunbooks`, `botSlaUptime`, `executionQuotas`, `digestReports`, `mobileMonitor`,
`dependencyUpdates`, `webhookRecorder`, `providerBenchmarks`, `cloneForkBot`,
`crossTeamSharing`, `incidentPlaybooks`, `livePromptSandbox`, `outputPiping`
(plus any `*Desc`/tooltip siblings that grep reveals for these — some keys appeared twice).

- [ ] **Step 1: Grep each key** across the 4 locales: `grep -rn "botRunbooks\|botSlaUptime\|executionQuotas\|digestReports\|mobileMonitor\|dependencyUpdates\|webhookRecorder\|providerBenchmarks\|cloneForkBot\|crossTeamSharing\|incidentPlaybooks\|livePromptSandbox\|outputPiping" frontend/src/locales`.
- [ ] **Step 2: Delete those lines** from all four `*.json` (keep JSON valid — watch trailing commas).
- [ ] **Step 3: Gate.** `cd frontend && npm run test:run && npm run build` → PASS (locale-parity test stays green because keys removed from all four).
- [ ] **Step 4: Commit.**
```bash
git add frontend/src/locales
git commit -m "chore(i18n): drop nav keys for 13 pruned features (en/ko/ja/zh)"
```

---

### Task 4: Remove dead backend stubs + their tests

**Files:**
- `backend/app_litestar/routes/misc.py` — delete `bot_sla()` handler (`@get("/admin/bots/sla")`, lines ~89-91) and its registration in the route-handler list (line ~258 `bot_sla,`).
- `backend/app_litestar/routes/executions.py` — delete the quota handlers: `execution_quotas()` GET (`@get("/executions/quotas")` ~485) and the 501 mutating quota handlers (`@post("/executions/quotas")` ~493 and siblings flagged "quota") plus their registrations. **Leave** the anomaly stubs (lines ~472-482) — they belong to a different (consolidated) route, not this cut.
- report-digests backend: `grep -rn "digest" backend/app_litestar/routes/leaf_crud_c.py backend/app_litestar/routes/leaf_crud_h.py` to find the digest endpoint(s); delete the handler(s) + registration.
- Backend tests: `grep -rln "sla\|quota\|digest" backend/tests` → remove or adjust assertions covering the deleted endpoints (delete tests that exist *only* to assert the stub's 501/empty behavior).

- [ ] **Step 1: Locate exact handlers** with the greps above.
- [ ] **Step 2: Delete the SLA, quota, and digest handlers + registrations.**
- [ ] **Step 3: Remove/adjust backend tests** asserting those endpoints.
- [ ] **Step 4: Backend gate.** `cd backend && uv run pytest -q` → PASS.
- [ ] **Step 5: Commit.**
```bash
git add backend
git commit -m "refactor(backend): remove dead SLA/quota/digest stub endpoints (Phase 1)"
```

---

### Task 5: Final verification + reference-sweep cleanup

- [ ] **Step 1: Whole-repo sweep** for any lingering reference to the 13 routes or 13 view names:
```bash
grep -rn "bot-runbooks\|bot-sla-uptime\|execution-quota-controls\|report-digests\|mobile-execution-monitor\|dependency-impact-bot\|webhook-recorder\|provider-benchmark-dashboard\|bot-clone-fork\|cross-team-bot-sharing\|incident-response-playbooks\|inline-prompt-editor\|bot-output-piping" frontend/src backend --include=*.ts --include=*.vue --include=*.py
```
  Expected: no hits (or only this plan/spec docs). Fix any stragglers.
- [ ] **Step 2: Three-gate.** `cd frontend && npm run build && npm run test:run` then `cd backend && uv run pytest -q` → all PASS.
- [ ] **Step 3: If anything was fixed in Step 1, commit it.**
```bash
git add -A && git commit -m "chore: final reference-sweep cleanup after Phase 1 prune"
```

---

## Notes / follow-ups (NOT this plan)
- `bot_pipes` table + `leaf_crud_e.py` pipe routes (backing `bot-output-piping`) are retired in a separate follow-up to avoid a data migration here.
- Phase 2 (merges + relocations) and Phase 3 (IA restructure) get their own plans after Phase 1 lands and is codex-reviewed green.
