---
phase: 10-analytics-monitoring-dashboards
plan: 05
subsystem: frontend
tags: [analytics, health-monitoring, scheduling, budgets, dashboard, vue]
dependency_graph:
  requires: ["10-02", "10-03"]
  provides: ["BotHealthDashboard", "TeamImpactReport", "SchedulingSuggestions", "BudgetLimitsExtended", "analyticsApi"]
  affects: ["AppSidebar", "TriggerDetailPanel", "dashboard routes"]
tech_stack:
  added: []
  patterns: ["analyticsApi module", "HealthAlertList with filter pills", "30s auto-refresh polling", "SchedulingSuggestions trigger integration"]
key_files:
  created:
    - frontend/src/services/api/analytics.ts
    - frontend/src/components/analytics/HealthAlertList.vue
    - frontend/src/components/analytics/SchedulingSuggestions.vue
    - frontend/src/components/analytics/BudgetLimitsExtended.vue
    - frontend/src/views/BotHealthDashboard.vue
    - frontend/src/views/TeamImpactReport.vue
  modified:
    - frontend/src/services/api/types.ts
    - frontend/src/services/api/index.ts
    - frontend/src/router/routes/dashboard.ts
    - frontend/src/components/layout/AppSidebar.vue
    - frontend/src/components/triggers/TriggerDetailPanel.vue
decisions:
  - "analyticsApi created as separate module (not merged into monitoring.ts) for domain clarity"
  - "SchedulingSuggestions integrated directly into TriggerDetailPanel scheduled section for immediate visibility"
  - "BudgetLimitsExtended created as standalone component rather than modifying BudgetLimitForm (which is a modal with different UX pattern)"
metrics:
  duration: "11min"
  completed: "2026-03-05"
---

# Phase 10 Plan 05: Frontend Views for Health, Reports, Scheduling, and Budgets Summary

Frontend views consuming health monitoring, weekly report, scheduling suggestion, and budget enforcement APIs with sidebar navigation and route registration.

## Task Summary

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Extend API client and create health alert + report views | 1d02e27 | analytics.ts, types.ts, HealthAlertList.vue, BotHealthDashboard.vue, TeamImpactReport.vue, dashboard.ts |
| 2 | Create scheduling suggestions, extend budget form, add sidebar nav | 7fe8a10 | SchedulingSuggestions.vue, BudgetLimitsExtended.vue, AppSidebar.vue, TriggerDetailPanel.vue |

## What Was Built

**Analytics API Client** (`frontend/src/services/api/analytics.ts`):
- 6 endpoints: fetchHealthAlerts, fetchHealthStatus, acknowledgeAlert, runHealthCheck, fetchWeeklyReport, fetchSchedulingSuggestions
- 7 new types: HealthAlert, HealthAlertsResponse, HealthStatusResponse, WeeklyReport, SchedulingSuggestion, SchedulingSuggestionsResponse

**BotHealthDashboard** (`frontend/src/views/BotHealthDashboard.vue`):
- Status summary with critical/warning/total alert counts
- HealthAlertList with filter pills (All/Critical/Warning/Acknowledged)
- Severity badges (critical=red, warning=amber) and acknowledge action
- 30-second auto-refresh polling with manual "Run Health Check" button
- Relative timestamps via date-fns formatDistanceToNow

**TeamImpactReport** (`frontend/src/views/TeamImpactReport.vue`):
- Period display header with formatted date range
- Stats cards: PRs Reviewed, Issues Found, Time Saved (formatted as hours/minutes)
- Top Performing Bots ranked list with execution counts
- Bots Needing Attention list with failure rate badges (red >50%, amber >20%)

**SchedulingSuggestions** (`frontend/src/components/analytics/SchedulingSuggestions.vue`):
- Shows recommended hours (up to 3) and days (up to 2) with success rate, duration, count
- Success rate color coding: green >=80%, amber 60-80%, red <60%
- Insufficient data info box when message is present
- Integrated into TriggerDetailPanel.vue scheduled trigger section

**BudgetLimitsExtended** (`frontend/src/components/analytics/BudgetLimitsExtended.vue`):
- Max execution time (seconds) and max monthly runs fields
- Positive integer validation with inline errors
- Help text explaining enforcement behavior

**Navigation**:
- /dashboards/health and /dashboards/team-report routes registered
- AppSidebar: "Bot Health" and "Impact Report" links in Dashboards section

## Decisions Made

1. **Separate analyticsApi module**: Created as its own file rather than adding to monitoring.ts, since health monitor endpoints serve a different domain (bot health vs. token rate limiting)
2. **SchedulingSuggestions in TriggerDetailPanel**: Integrated directly in the scheduled trigger section rather than as a separate page, per roadmap success criterion requiring suggestions on the trigger configuration page
3. **BudgetLimitsExtended as standalone**: Created as a new component rather than modifying BudgetLimitForm.vue, which is a modal-based form with different entity selection UX

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- Frontend build (vue-tsc + vite): PASS
- Frontend tests: 409/409 PASS
- Backend tests: 940/940 PASS

## Self-Check: PASSED

All created files verified to exist, all commits verified in git log.
