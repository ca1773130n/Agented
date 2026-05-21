# PR-D Plan — Dashboards lanes + wizard grouping + Scheduling top-level link

**Spec:** `docs/superpowers/specs/2026-05-21-sidebar-ia-redesign-design.md`
**Audit:** `.planning/sidebar-audit.md` (commit `2d22e15`)
**Marketplace audit:** `.planning/marketplace-audit.md` (commit `934e3b3`)
**Dashboards + wizards audit:** `.planning/dashboards-wizards-audit.md` (commit `7830e70`)

**Plan-review history:**
- Pass 1: codex needs revision — (a) Cost lane Token Usage already has its own Cost Trend; don't extract from Analytics (duplicate). (b) Scheduling 1-item section unjustified — make flat top-level instead. (c) ServiceHealth redirect from `/backends/health` must be explicit. (d) WebMCP `agented_scheduling_get_rotation_status` registration needs a unit test, not just a risk mention. (e) MySkills CTA addition needs a render test. (f) `AiCostDashboard.vue` + `ProviderBenchmarkDashboard.vue` exist in observabilityExtRoutes — call out as explicit out-of-scope.

## Spec amendments

Three corrections from the parent spec, all surfaced by the
dashboards + wizards audit:

1. **`analytics-dashboard` is unmapped** in the parent spec's lane
   plan. Its 4 charts each overlap an existing lane. **Decision:
   decompose into the lanes** (Cost Trend → Cost; Execution Volume
   + Success Rate → Activity; Bot Effectiveness → Health). Delete
   the standalone Analytics page.
2. **`ServiceHealthDashboard.vue` exists and is referenced by
   DashboardsPage** but wasn't in the parent's 13. **Decision: fold
   into Health lane** as a card alongside Health Monitor + Bot Health.
3. **Wizard grouping**: parent spec said "6 wizards become a coherent
   surface". Audit shows 5 of 6 already have "New X" buttons on
   their list pages; only `SkillCreateWizard` lacks one
   (`MySkills.vue` gap). **Decision: don't build a new unified
   Create page** — add the missing CTA on `MySkills.vue` and call
   it done. A new aggregator surface wouldn't earn its slot.

## Goal

13 dashboards (+1 ServiceHealth, -1 Analytics) → **4 lane pages**.
On-Call Escalation folds into a new **flat top-level Scheduling link**
(deep-links to `/dashboards/activity#scheduling`). Sidebar
pollution drops from 9 dashboard sidebar entries → 4 lane entries.

## Lane composition (final)

### Quality lane (`/dashboards/quality`)

Cards (multi-card layout):
- Security Scan (port from `SecurityDashboardPage.vue`)
- PR Review (port from `PrReviewDashboardPage.vue`)
- Anomaly Detection (port from `ExecutionAnomalyDetection.vue`)

### Cost lane (`/dashboards/cost`)

Cards:
- Token Usage (port `TokenUsageDashboard.vue` — already a heavy
  multi-section page including its own "Cost Trend" chart at line
  ~438; keep as the main body of the lane)

**Cost Trend NOT extracted from Analytics** — duplicate; Token
Usage's Cost Trend covers the same data. The Analytics page's Cost
Trend chart is dropped when AnalyticsDashboard is deleted (the
other Analytics charts extract per Health + Activity lanes).

### Health lane (`/dashboards/health`)

Cards:
- Health Monitor (port from `HealthMonitorPage.vue`)
- Bot Health (port from `BotHealth.vue` — the audit §A duplicate;
  consolidating here is the original goal)
- Service Health (port from `ServiceHealthDashboard.vue` — newly
  found 14th surface)
- Bot Effectiveness chart (extracted from `AnalyticsDashboard.vue`)

### Activity lane (`/dashboards/activity`)

Activity has the most cards. **Per audit, sub-group into 2 visual
blocks within the single page**:

**Live ops block:**
- Scheduling Dashboard (port from `SchedulingDashboard.vue` —
  preserve the existing WebMCP tool registration)
- Execution Queue (port from `ExecutionQueueDashboard.vue`)
- Execution Volume chart (extracted from `AnalyticsDashboard.vue`)
- Success Rate chart (extracted from `AnalyticsDashboard.vue`)

**Reports block:**
- Impact Report (port from `TeamImpactReport.vue`)
- Cross-Team Insights (port from `CrossTeamInsightsPage.vue`)
- ROI Leaderboard (port from `TeamLeaderboard.vue`)

## Scheduling (flat top-level, not a section)

Per codex pre-impl review, a 1-item expandable section is
unjustified. **Add Scheduling as a FLAT top-level sidebar link**
(like Watch Tower or Sketch) that deep-links to
`/dashboards/activity#scheduling`. If future sub-items emerge (e.g.
Smart Schedule Optimizer per audit, per-trigger rotation config),
promote to a section then — not now.

This:
- Removes On-Call Escalation from External Integrations (held
  there by PR-B amendment). External Integrations drops to 3 items
  (Slack Notifications, Jira / Linear, Notification Channels — the
  3 real integrations per the audit).
- Deletes the standalone `OnCallEscalation.vue` route + view; merges
  its 4-row static severity-threshold reference + unpersisted
  `escalationPolicy` input into a new "On-Call Policy" sub-card
  inside the SchedulingCard.

## Wizard grouping

Per spec amendment: NOT building a new unified "Create" page.
Instead:

- **Add a "+ Create Skill" CTA** on `frontend/src/views/MySkills.vue`
  (audit identified this as the only wizard without an entry point
  from its parent list page). CTA routes to `skill-create`.
- Verify the existing "New X" CTAs on the other 5 list pages work
  correctly post-PR-B (the Agents / Commands / Hooks / Rules /
  Plugins list pages should already navigate to their respective
  `*-create` / `*-design` routes).

## DashboardsPage (the landing/launcher)

Per audit, this page is the only inbound for Token Usage and
Scheduling tiles beyond the sidebar. **Decision: repurpose as the
4-lane index** (Option A). Replace the existing 13-tile grid with
a clean 4-tile grid (Quality / Cost / Health / Activity) + small
deep-link cards for the now-hidden specifics ("Token Usage" → goes
to /dashboards/cost; "Scheduling" → /dashboards/activity#scheduling).

## Route redirects

Per the PR-C pattern, keep old route entries as function-form
redirects so bookmarks survive:

- `security-dashboard` → `/dashboards/quality#security`
- `pr-review-dashboard` → `/dashboards/quality#pr-review`
- `token-usage` → `/dashboards/cost`
- `rotation-dashboard` → `/dashboards/activity#scheduling`
- `analytics-dashboard` → `/dashboards/cost` (the most representative
  destination given the Cost Trend chart is the headline of analytics)
- `health-dashboard` → `/dashboards/health#health-monitor`
- `bot-health` → `/dashboards/health#bot-health`
- `service-health` (`/backends/health`) → `/dashboards/health#service-health`
- `team-impact-report` → `/dashboards/activity#impact-report`
- `cross-team-insights` → `/dashboards/activity#cross-team-insights`
- `execution-queue-dashboard` → `/dashboards/activity#execution-queue`
- `execution-anomaly-detection` → `/dashboards/quality#anomaly-detection`
- `team-leaderboard` → `/dashboards/activity#roi-leaderboard`
- `on-call-escalation` → `/dashboards/activity#scheduling` (fold)

Function-form redirects, anchor-scroll to the matching card.

## Sidebar changes (`AppSidebar.vue`)

- **Replace** the 13-item Dashboards submenu with a 4-item submenu:
  - All Dashboards → `dashboards` (the new 4-tile landing)
  - Quality → `dashboards-quality`
  - Cost → `dashboards-cost`
  - Health → `dashboards-health`
  - Activity → `dashboards-activity`
- **Add** "Scheduling" as a flat top-level sidebar link (no expandable
  section), deep-links to `/dashboards/activity#scheduling`.
- **Remove** On-Call Escalation from External Integrations (drops
  the section to 3 items).
- **Remove** `team-leaderboard` from Platform (it's a dashboard
  per audit; folded into Activity).
- **Update** the structure test:
  - Dashboards submenu now exactly 5 items (1 landing + 4 lanes)
  - Scheduling flat top-level link exists (no expandable section)
  - External Integrations contains exactly 3 items
  - Platform no longer contains `team-leaderboard`

## Component structure

### Lane page components

Each lane is `frontend/src/views/dashboards/<Lane>Page.vue`:

```
views/dashboards/
  QualityPage.vue
  CostPage.vue
  HealthPage.vue
  ActivityPage.vue
```

Each is a multi-card composition. Cards are sibling subcomponents:

```
views/dashboards/cards/
  SecurityCard.vue          (extracted from SecurityDashboardPage)
  PrReviewCard.vue          (extracted from PrReviewDashboardPage)
  AnomalyDetectionCard.vue  (extracted from ExecutionAnomalyDetection)
  TokenUsageCard.vue        (extracted from TokenUsageDashboard
                             — already includes Cost Trend chart;
                             no separate CostTrendCard needed)
  HealthMonitorCard.vue     (extracted from HealthMonitorPage)
  BotHealthCard.vue         (extracted from BotHealth)
  ServiceHealthCard.vue     (extracted from ServiceHealthDashboard)
  BotEffectivenessCard.vue  (extracted from AnalyticsDashboard)
  SchedulingCard.vue        (extracted from SchedulingDashboard;
                             preserves WebMCP tool registration)
  ExecutionQueueCard.vue    (extracted from ExecutionQueueDashboard)
  ExecutionVolumeCard.vue   (extracted from AnalyticsDashboard)
  SuccessRateCard.vue       (extracted from AnalyticsDashboard)
  ImpactReportCard.vue      (extracted from TeamImpactReport)
  CrossTeamInsightsCard.vue (extracted from CrossTeamInsightsPage)
  RoiLeaderboardCard.vue    (extracted from TeamLeaderboard)
```

The lane pages are thin shells that mount the right cards in the
right order with anchor IDs for deep-linking from redirects.

### Deletions (after all cards extracted)

- `SecurityDashboardPage.vue`
- `PrReviewDashboardPage.vue`
- `TokenUsageDashboard.vue`
- `SchedulingDashboard.vue`
- `AnalyticsDashboard.vue`
- `HealthMonitorPage.vue`
- `BotHealth.vue`
- `ServiceHealthDashboard.vue`
- `TeamImpactReport.vue`
- `CrossTeamInsightsPage.vue`
- `ExecutionQueueDashboard.vue`
- `ExecutionAnomalyDetection.vue`
- `TeamLeaderboard.vue`
- `OnCallEscalation.vue`

14 views deleted.

### Routes touched

14 old routes become function-form redirects; 4 new lane routes added
(`/dashboards` is repurposed, not new)
(4 lanes + the existing `/dashboards` landing repurposed). Net: 14
view files deleted, 16 new card files added, 4 new lane shells
added.

## Tests

### Updated tests

- `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`:
  - Dashboards submenu exactly 5 items
  - Scheduling flat top-level link exists (no expandable section)
  - External Integrations down to 3 items
  - Platform no longer contains team-leaderboard

### New tests

- `frontend/src/views/dashboards/__tests__/lanes.test.ts` —
  smoke tests for each lane page (mount, assert each expected
  card subcomponent renders).
- `frontend/src/views/dashboards/__tests__/DashboardsPage.test.ts` —
  the repurposed 4-tile landing renders + deep-link tiles navigate
  to the right anchor.
- `frontend/src/views/dashboards/cards/__tests__/SchedulingCard.test.ts` —
  mounts SchedulingCard with a stub `useWebMcpTool`; asserts the
  tool name `agented_scheduling_get_rotation_status` is registered
  (the spy was called with that name). Prevents WebMCP regression
  during the extraction.
- `frontend/src/views/__tests__/MySkills.test.ts` (or extend an
  existing MySkills test if one exists) — mounts the list page,
  asserts the new "+ Create Skill" button exists and navigates to
  the `skill-create` route on click.

## Risks + mitigations

1. **16-card extraction is the biggest engineering chunk.** Each
   card must preserve its API calls, its loading/error states, and
   any reactive deps. Mitigation: extract one card at a time using
   the existing view file as the source; subcomponent owns its
   own data fetching (don't try to lift state to the lane page).

2. **WebMCP tool registration in SchedulingDashboard.** Tool name
   `agented_scheduling_get_rotation_status` is used by verification
   agents. Mitigation: the `SchedulingCard.vue` extraction must
   include the `useWebMcpTool` registration; tests must verify the
   tool name is reachable.

3. **Token Usage pulls `rotationApi.getStatus`** for rate-limit
   countdowns — rotation bleeds into Cost lane. Mitigation: the
   `TokenUsageCard.vue` extraction keeps this call; the
   SchedulingCard extraction does the same. Two cards reading the
   same endpoint is fine; the API is idempotent.

4. **Anchor-scroll on redirect** — Vue Router's hash-scroll
   behavior may not consistently fire after async card data loads.
   Mitigation: each card has a stable `id="<slug>"` attribute on its
   root element; on lane page mount, use
   `nextTick` + `scrollIntoView()` if `route.hash` is set, after
   all cards have signaled `loaded`.

5. **OnCallEscalation merge.** The 4-row static reference + the
   local `escalationPolicy` input are merged into the new
   SchedulingCard. The input wasn't persisted to backend per audit,
   so the merge is content-only (no API plumbing changes).
   Mitigation: surface a "TODO: persist policy" comment in the
   merged card so future work doesn't lose the unpersisted state.

6. **DashboardsPage repurpose.** Existing inbound CTAs that link
   to `/dashboards` expect the 13-tile grid. Mitigation: the new
   4-tile + small deep-link card layout still resolves every
   inbound reference; verify by grepping for `name: 'dashboards'`
   pushes across the codebase.

7. **Sidebar Platform → team-leaderboard removal.** The audit
   said `team-leaderboard` is in Platform (an oddity). Removing it
   leaves Platform with one fewer entry; verify it's a clean drop
   (no dependents).

## Test plan

- [ ] `vue-tsc --noEmit` clean
- [ ] `npm run test:run` green (new tests + updated structure test)
- [ ] `npm run build` green
- [ ] WebMCP tool `agented_scheduling_get_rotation_status` still
  registers when the Scheduling card mounts
- [ ] Manual: open `/dashboards/quality`, verify all 3 cards render
- [ ] Manual: open `/dashboards/activity`, verify the 2 visual blocks
  ("Live ops" / "Reports") and all 7 cards
- [ ] Manual: hit `/security-dashboard` directly, verify redirect to
  `/dashboards/quality#security` with scroll-to-card
- [ ] Manual: hit `/on-call-escalation` directly, verify redirect to
  `/dashboards/activity#scheduling` and the on-call policy fields
  are present in the Scheduling card
- [ ] Manual: hit `/backends/health` directly, verify redirect to
  `/dashboards/health#service-health` with scroll-to-card

## Out of scope for PR-D

- Lifting raw `fetch('/admin/...')` calls onto typed clients
  (Anomaly Detection + ROI Leaderboard) — separate cleanup
- Persisting OnCallEscalation's policy input — TODO comment only
- Renaming SuperAgents
- Watch Tower / Sketch flat entries
- `BotTemplateMarketplace` IA position (still out of scope from PR-C)
- Settings → Plugin Marketplaces relocation (still out of scope)
- **`AiCostDashboard.vue` and `ProviderBenchmarkDashboard.vue`**
  (per codex pre-impl review pass 1): these exist in
  `observabilityExtRoutes` but aren't in the audit's 13. Explicitly
  out of scope — they belong to a separate observability surface,
  not the dashboards-lane consolidation. Address in a follow-up if
  ever.

## Version bump

`backend/pyproject.toml` + `frontend/package.json`: 0.7.100 → 0.7.101.
Run `cd backend && uv lock` after pyproject bump.

## Extraction order (per codex pre-impl review)

Recommended ordering to minimize churn risk. **Important per codex
pre-impl review:** lane shells should land in the SAME commit as
their first card — don't ship an empty wrapper that a direct URL
visit could reach with nothing rendered.

1. **Lane shells + first card together** — `QualityPage.vue` with
   first card, `CostPage.vue` with TokenUsageCard, `HealthPage.vue`
   with first card, `ActivityPage.vue` with first card. Don't add
   the sidebar/redirect entries until the lane has at least one
   real card mounting.
2. **Low-dependency cards next**: BotHealth, HealthMonitor,
   ServiceHealth, ROI, CrossTeam, Impact.
3. **Mid-complexity**: Execution Queue, Anomaly Detection.
4. **Multi-source cards**: Security Scan, PR Review.
5. **Charts from Analytics**: Execution Volume, Success Rate, Bot
   Effectiveness.
6. **Heavy port**: Token Usage.
7. **Last (WebMCP risk)**: Scheduling + On-Call merge.
8. After all cards mount cleanly: cut the 14 redirects + delete
   the 14 source view files.

Each step verified with `npm run test:run` and `vue-tsc --noEmit`
before moving to the next.
