# Evaluation Plan: Phase 10 — Analytics & Monitoring Dashboards

**Designed:** 2026-03-04
**Designer:** Claude (grd-eval-planner)
**Method(s) evaluated:** SQL aggregation analytics, APScheduler health monitoring, Chart.js dashboard views, per-bot budget enforcement
**Reference documents:** 10-RESEARCH.md, 10-01-PLAN.md through 10-05-PLAN.md

---

## Evaluation Overview

Phase 10 extends the existing Agented platform with seven analytics and monitoring capabilities (ANA-01 through ANA-07). The work splits into a backend data layer (Plans 01-03: SQL aggregation, health monitoring, budget enforcement) and a frontend presentation layer (Plans 04-05: Chart.js dashboards, alert views, sidebar navigation).

Because this phase builds on existing infrastructure — token_usage, execution_logs, pr_reviews tables are already populated; BudgetService and ProcessManager already exist; Chart.js and APScheduler are already installed — the primary evaluation risk is **correctness of aggregation logic** and **integration of new components into the existing execution pipeline**, not environment setup.

A meaningful portion of the evaluation is achievable now via isolated_db proxy tests (the backend logic). Frontend verification is limited to build-time sanity: Chart.js renders correctly with mock data, TypeScript types are valid, and routes are registered. Visual correctness of charts with live data, end-to-end cost tracking, and real APScheduler health check cycles are deferred to integration-phase verification.

No external benchmarks exist for this domain within the project (BENCHMARKS.md is empty). Performance targets are derived from the existing codebase baseline documented in 10-RESEARCH.md and PROJECT.md quality targets.

### Metric Sources

| Metric | Source | Why This Metric |
|--------|--------|----------------|
| Backend test pass rate | PROJECT.md quality targets (100%) | Gate for all backend changes |
| Frontend build with zero type errors | PROJECT.md quality targets | vue-tsc catches type errors not caught by unit tests |
| Frontend unit test pass rate | PROJECT.md quality targets (100%) | Regression protection for existing tests |
| Analytics aggregation correctness | Plans 10-01/10-02/10-03 proxy tests | Primary correctness signal for SQL GROUP BY logic |
| Health alert detection accuracy | 10-02-PLAN.md proxy tests | Consecutive failures, slow execution, missing fire |
| Budget enforcement correctness | 10-03-PLAN.md proxy tests | Monthly run count and execution time limits |
| Scheduling suggestion ranking | 10-03-PLAN.md proxy tests | Top hours ranked by success rate |
| API response shape | Integration test pattern from TESTING.md | Frontend TypeScript types must match backend JSON |
| Dashboard page load (proxy) | 10-RESEARCH.md experiment design (<2s for 1000 executions) | Responsiveness |
| Health check cycle time | 10-RESEARCH.md recommendation (<5s) | APScheduler job must not block scheduler thread |
| Cost data freshness | ANA-01 requirement (updates within 60s) | Deferred — requires live execution |

### Verification Level Summary

| Level | Count | Purpose |
|-------|-------|---------|
| Sanity (L1) | 9 | Import resolution, JSON validity, build success, no crashes |
| Proxy (L2) | 10 | Aggregation correctness, detection logic, ranking, API response shape |
| Deferred (L3) | 7 | Live execution cost tracking, real APScheduler cycles, visual chart correctness |

---

## Level 1: Sanity Checks

**Purpose:** Verify basic functionality. These MUST ALL PASS before proceeding.

### S1: Backend module imports resolve
- **What:** All new Python modules can be imported without error in a clean environment
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.db.analytics import get_cost_analytics, get_execution_analytics, get_effectiveness_analytics;
  from app.services.analytics_service import AnalyticsService;
  from app.models.analytics import AnalyticsQuery, CostAnalyticsResponse;
  from app.db.health_alerts import create_health_alert, get_recent_alerts;
  from app.services.health_monitor_service import HealthMonitorService;
  from app.services.report_service import ReportService;
  from app.models.health import HealthAlert, WeeklyReport;
  from app.services.scheduling_suggestion_service import SchedulingSuggestionService;
  print('All backend imports OK')
  "
  ```
- **Expected:** `All backend imports OK` with exit code 0
- **Failure means:** A module has a broken import chain (missing dependency, syntax error, circular import). Check the traceback and resolve before running tests.

### S2: Analytics endpoints return valid JSON for empty database
- **What:** All three analytics endpoints handle the empty-data case without 500 errors
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_analytics.py::test_analytics_empty_data -v
  ```
- **Expected:** Test passes; endpoints return 200 with zero counts and empty data arrays
- **Failure means:** Endpoint crashes on empty DB (e.g., division by zero in acceptance_rate, NoneType error from fetchone()). Fix null-guard before proceeding.

### S3: Health monitor endpoints return valid JSON for empty database
- **What:** Health alert and report endpoints handle no-data gracefully
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_health_monitor.py::test_report_empty_data -v
  ```
- **Expected:** Test passes; weekly report returns valid JSON with zero counts for all fields
- **Failure means:** ReportService.generate_weekly_report() raises on empty tables. Add null-guards.

### S4: health_alerts table is created by schema initialization
- **What:** The new health_alerts table is included in init_db() and created without error
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  import tempfile, os
  with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
      db_path = f.name
  import app.config as config
  config.DB_PATH = db_path
  from app.database import init_db
  init_db()
  from app.db.connection import get_connection
  with get_connection() as conn:
      tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
      assert 'health_alerts' in tables, f'health_alerts not found in {tables}'
      print('health_alerts table created OK')
  os.unlink(db_path)
  "
  ```
- **Expected:** `health_alerts table created OK` with exit code 0
- **Failure means:** Schema migration for health_alerts is missing or broken. Add the CREATE TABLE to schema.py and a migration to migrations.py.

### S5: budget_limits table accepts new columns
- **What:** The two new budget columns (max_execution_time_seconds, max_monthly_runs) exist after migration
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_budget_enforcement.py::test_budget_limit_columns_persist -v
  ```
- **Expected:** Test passes; new columns are readable and writable
- **Failure means:** ALTER TABLE migration was not applied, or set_budget_limit() does not write the new fields. Check migrations.py and budgets.py.

### S6: Frontend TypeScript compilation passes
- **What:** vue-tsc reports zero type errors across all new TypeScript/Vue files
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/frontend && npx vue-tsc --noEmit 2>&1 | tail -20
  ```
- **Expected:** No output lines containing `error TS`, exit code 0
- **Failure means:** A type annotation is missing, a property name is wrong, or an API type does not match its usage. Fix the type error before the build step.

### S7: Frontend production build succeeds (all 5 plans)
- **What:** Vite build compiles without errors after all frontend changes from Plans 04 and 05
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented && just build 2>&1 | tail -30
  ```
- **Expected:** Build completes with `built in X.XXs`, zero error lines
- **Failure means:** A Vue component has a template error, a missing import, or an unresolved module. Fix the component before declaring the plan complete.

### S8: New route paths are registered and accessible
- **What:** The three new dashboard routes resolve without 404 in the frontend router
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/frontend && npm run test:run -- --reporter=verbose 2>&1 | grep -E "(PASS|FAIL|analytics|health|report)" | head -20
  ```
- **Expected:** No test failures related to route registration; existing tests continue to pass
- **Failure means:** Route import path is wrong or the view component cannot be lazy-loaded. Verify the path string in dashboard.ts matches the actual file location.

### S9: Full backend test suite passes (no regressions)
- **What:** All existing backend tests continue to pass after new code is added to execution_service.py and budget_service.py
- **Command:**
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest --tb=short -q 2>&1 | tail -20
  ```
- **Expected:** All tests pass. Zero failures, zero errors.
- **Failure means:** A change to execution_service.py or budget_service.py broke an existing test. This is high-risk — isolate the regression immediately before proceeding.

**Sanity gate:** ALL nine sanity checks must pass. Any failure blocks progression to proxy metric evaluation.

---

## Level 2: Proxy Metrics

**Purpose:** Indirect evaluation of correctness and quality using isolated test data.
**IMPORTANT:** Proxy metrics are NOT validated substitutes for full evaluation. Results should be treated as strong indicators, not guarantees, of production correctness.

### P1: Cost analytics aggregation correctness
- **What:** The cost aggregation SQL correctly groups token_usage records by entity and time period, and sums costs accurately
- **How:** Insert 15+ token_usage records across 3 entities and 5 days, then compare query results to the expected sums computed in the test
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_analytics.py::test_cost_analytics_aggregation -v`
- **Target:** Test passes; per-period costs sum to within 0.001 USD of inserted amounts; period count matches days with data
- **Evidence:** Direct verification of the SQL GROUP BY + SUM query. The existing `get_usage_aggregated_summary()` in budgets.py follows the same pattern and is proven correct — this test applies the same verification to the new function.
- **Correlation with full metric:** HIGH — isolated_db uses real SQLite with the same schema as production. The test exercises the exact query path used by the live dashboard.
- **Blind spots:** Does not test with thousands of records (performance) or concurrent queries (locking). Does not test timezone edge cases (strftime uses UTC).
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P2: Execution analytics aggregation correctness
- **What:** The execution analytics SQL correctly counts success, failed, and cancelled executions per period, with correct average duration computation
- **How:** Insert 20+ execution_logs with mixed statuses and timestamps, then assert counts match the inserted data's distribution
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_analytics.py::test_execution_analytics_aggregation -v`
- **Target:** Test passes; success_count + failed_count + cancelled_count = total_executions per period; avg_duration_ms is non-negative where data exists
- **Evidence:** Direct verification of SQL GROUP BY + CASE + COUNT. The julianday() duration calculation is the only non-standard piece; the test verifies it produces a positive, reasonable value.
- **Correlation with full metric:** HIGH — same SQLite path used in production
- **Blind spots:** NULL finished_at values (for running executions) may cause AVG to drop those rows silently. Test should include at least one record with NULL finished_at to verify graceful handling.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P3: Bot effectiveness (PR acceptance rate) calculation
- **What:** The acceptance rate percentage is computed correctly: accepted / total * 100 where accepted = approved + fixed
- **How:** Insert 10+ pr_reviews with known distribution across statuses, then assert acceptance_rate matches the expected formula
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_analytics.py::test_effectiveness_analytics -v`
- **Target:** Test passes; acceptance_rate is correct to 1 decimal place; edge case of 0 total reviews returns 0.0 (not division-by-zero)
- **Evidence:** Follows the exact pattern documented in 10-RESEARCH.md Code Examples section. The pr_reviews table with review_status field already exists; this is a read-only query.
- **Correlation with full metric:** HIGH — acceptance rate is a deterministic formula applied to real DB data
- **Blind spots:** Does not test the time-series variant (get_effectiveness_over_time). Does not test with partial-month data boundaries.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P4: Analytics date range filtering
- **What:** Date filters (start_date, end_date) correctly exclude out-of-range records
- **How:** Insert 60 days of data, query with a 15-day window, assert only records in window are returned
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_analytics.py::test_analytics_date_filtering -v`
- **Target:** Test passes; period count matches the number of days in the query window with data; records outside window produce zero count (not omitted — they should not appear)
- **Evidence:** Date filtering is used by all three analytics endpoints. If filtering is wrong, the dashboard will show misleading aggregations when users change the time range.
- **Correlation with full metric:** HIGH — correctness of date filtering directly determines whether the dashboard shows accurate data for selected time ranges
- **Blind spots:** Does not test the group_by=week and group_by=month variants. Does not test date boundary at midnight.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P5: Consecutive failure detection (no false positives, no false negatives)
- **What:** HealthMonitorService correctly identifies triggers with N consecutive failures, and does NOT flag triggers with a success in the recent stream
- **How:** Two test conditions — 5 consecutive failures (should alert) and pattern [failed, failed, success, failed, failed] (should NOT alert because consecutive streak is broken)
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_health_monitor.py::test_consecutive_failure_detection tests/test_health_monitor.py::test_no_false_positive_on_mixed_results -v`
- **Target:** Both tests pass; alert created exactly when expected, absent when not
- **Evidence:** The false-positive prevention test directly addresses 10-RESEARCH.md Pitfall 3 (alert fatigue). The simple Python loop over 10 records is verified against exact input sequences.
- **Correlation with full metric:** HIGH — the detection logic is tested with exactly the sequences that define the requirement (>= N consecutive failures)
- **Blind spots:** Does not test the 30-minute deduplication window under load. Does not test alert creation when HealthMonitorService runs as a real APScheduler job (that is deferred).
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P6: Missing fire detection applies only to scheduled triggers
- **What:** Missing fire alerts are created for overdue scheduled triggers but NOT for webhook or GitHub triggers regardless of how long ago they last fired
- **How:** Create one scheduled trigger with last_run_at 3 days ago (daily schedule) and one webhook trigger with last_run_at 30 days ago; run health check; assert only the scheduled trigger gets an alert
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_health_monitor.py::test_missing_fire_scheduled_only -v`
- **Target:** Test passes; exactly one alert created (for the scheduled trigger); webhook trigger has no missing_fire alert
- **Evidence:** This directly validates the constraint from 10-RESEARCH.md Pitfall 3: "Only apply missing fire detection to scheduled trigger sources." Failure here would cause alert fatigue for all webhook-triggered bots.
- **Correlation with full metric:** HIGH — the predicate `trigger_source == 'scheduled'` is the exact guard required
- **Blind spots:** Does not test with weekly schedule type (48-hour threshold). Does not test that a scheduled trigger that fired recently produces no alert.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P7: Alert deduplication prevents spam
- **What:** Running the health check twice within 30 minutes for the same failing trigger creates only one alert, not two
- **How:** Insert failing trigger, run health check, run it again, assert alert count = 1
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_health_monitor.py::test_alert_deduplication -v`
- **Target:** Test passes; `get_recent_alerts(trigger_id=X)` returns exactly 1 alert after two consecutive health checks
- **Evidence:** Deduplication logic in create_health_alert() is the sole mechanism preventing alert storms. If it fails, a 5-minute health check interval would generate 288 alerts per day for a single failing bot.
- **Correlation with full metric:** HIGH — the deduplication check is a direct database query by alert_type + trigger_id + created_at window
- **Blind spots:** Does not test the boundary condition (alert exactly 30 minutes old). Does not test that different alert types for the same trigger are NOT deduplicated.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P8: Scheduling suggestions rank correctly by success rate
- **What:** Given controlled execution data with known hour distributions, the suggestion service ranks high-success hours above low-success hours
- **How:** Insert 20+ executions: hours 9-11 with 90% success, hours 2-4 with 50% success. Assert top suggestion hours are in 9-11 range.
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_scheduling_suggestions.py::test_scheduling_suggestions_with_data -v`
- **Target:** Test passes; top-ranked hour suggestion is within the 9-11 AM window; insufficient data (<10 executions) returns empty suggestions with explanatory message
- **Evidence:** 10-RESEARCH.md Open Question 2 defines "optimal" as highest success rate + lowest duration. The ranking algorithm is verified against controlled input with known ordering.
- **Correlation with full metric:** HIGH for ranking correctness; MEDIUM for real-world utility (test data may not represent real usage patterns)
- **Blind spots:** Does not test suggestion quality when all hours have the same success rate (ties). Does not test the day-of-week suggestion ranking.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P9: Monthly run count budget enforcement blocks execution
- **What:** When a trigger has used its monthly run budget, the pre-execution budget check returns a violation and a health alert is created
- **How:** Set max_monthly_runs=5, insert 5 execution logs for the current month, call check_budget(), assert violation returned and budget_exceeded alert exists in health_alerts
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_budget_enforcement.py::test_monthly_run_count_enforcement tests/test_budget_enforcement.py::test_budget_exceeded_creates_health_alert -v`
- **Target:** Both tests pass; budget check returns violation with descriptive message; health alert created with severity='critical' and alert_type='budget_exceeded'
- **Evidence:** ANA-07 requires "graceful cancel + owner notification." The health alert in the health_alerts table is the in-app notification mechanism. This test verifies both enforcement and notification in one path.
- **Correlation with full metric:** HIGH for block logic; MEDIUM for the notification path (tests DB write but not UI display)
- **Blind spots:** The race condition from 10-RESEARCH.md Pitfall 4 (two concurrent executions both passing the check) is explicitly NOT tested — it requires concurrent thread testing which is out of scope.
- **Validated:** No — awaiting deferred validation at phase-10-integration

### P10: Weekly report returns all required fields
- **What:** ReportService.generate_weekly_report() returns a JSON response with all five fields required by ANA-05: prs_reviewed, issues_found, estimated_time_saved_minutes, top_bots, bots_needing_attention
- **How:** Insert test data (execution logs, PR reviews, health alerts), call generate_weekly_report(), assert all fields present with correct values
- **Command:** `cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest tests/test_health_monitor.py::test_weekly_report_generation -v`
- **Target:** Test passes; all 5 required fields present; prs_reviewed matches inserted count; estimated_time_saved_minutes = prs_reviewed * 15 (using default multiplier from ReportService constants)
- **Evidence:** ANA-05 success criterion lists exact fields. The configurable multiplier (15 min/PR, 30 min/audit) from 10-RESEARCH.md Open Question 1 is directly testable with the default constants.
- **Correlation with full metric:** HIGH for field presence and count correctness; LOW for "estimated time saved" accuracy (heuristic multiplier, not real measurement)
- **Blind spots:** Does not test with team_id filter (multi-team report scoping). Does not test the report displayed in the frontend UI.
- **Validated:** No — awaiting deferred validation at phase-10-integration

---

## Level 3: Deferred Validations

**Purpose:** Full evaluation requiring live execution, running APScheduler, or visual inspection that cannot be automated at this stage.

### D1: Cost data updates within 60 seconds of execution — DEFER-10-01
- **What:** After a real bot execution completes, the /admin/analytics/cost endpoint returns updated cost data within 60 seconds (ANA-01 requirement)
- **How:** Trigger a test execution, wait for completion, poll the cost endpoint for up to 90 seconds, assert cost data reflects the new execution
- **Why deferred:** Requires a running Claude/OpenCode CLI process and a live Flask server. The proxy tests use isolated_db which cannot simulate real execution cost recording.
- **Validates at:** phase-10-integration (manual testing with live dev environment)
- **Depends on:** Running Flask backend with real execution pipeline, installed Claude CLI
- **Target:** Cost dashboard reflects new execution data within 60 seconds of process completion
- **Risk if unmet:** ANA-01 core requirement failure. If token_usage records are not written promptly, the dashboard shows stale data. Fallback: add explicit refresh mechanism or shorter polling interval.
- **Fallback:** Verify via SQL query on the live DB that token_usage records are written at execution completion; if so, the dashboard staleness is a frontend polling interval issue.

### D2: Real APScheduler health check cycle — DEFER-10-02
- **What:** HealthMonitorService._check_health() runs on its 5-minute APScheduler interval, detects a real failing trigger, and creates an alert visible in the BotHealthDashboard within 10 minutes
- **How:** Create a trigger configured to a failing command. Let it fire via the scheduler. Wait 10 minutes. Check /admin/health-monitor/alerts.
- **Why deferred:** APScheduler job registration requires create_app() with TESTING=False. The isolated_db tests bypass APScheduler entirely (per TESTING.md: "In testing mode, create_app() skips all background service initialization").
- **Validates at:** phase-10-integration (manual dev environment testing)
- **Depends on:** Live Flask server with TESTING=False, APScheduler running, at least one failing trigger with execution history
- **Target:** Alert appears in /admin/health-monitor/alerts within 10 minutes of consecutive failure threshold being reached
- **Risk if unmet:** Health monitoring is silent in production. Fallback: Add POST /admin/health-monitor/check manual trigger endpoint for immediate check verification.

### D3: Execution time limit mid-execution cancellation — DEFER-10-03
- **What:** A bot exceeding its max_execution_time_seconds limit is gracefully cancelled mid-execution by the _budget_monitor thread via ProcessManager.cancel_graceful()
- **How:** Set a bot's max_execution_time_seconds to 10. Trigger an execution that sleeps for 30 seconds. Assert execution is cancelled between 10-40 seconds and a budget_exceeded health alert is created.
- **Why deferred:** Requires a real subprocess (the mock process in unit tests does not have a real SIGTERM handler) and real threading in the budget monitor loop. Unit tests mock subprocess.Popen.
- **Validates at:** phase-10-integration (manual testing with a sleep-based test script)
- **Depends on:** Live execution pipeline, real subprocess, ProcessManager.cancel_graceful() with real PGID
- **Target:** Execution cancelled within 30-second polling interval + 5-second SIGTERM timeout; health alert created with elapsed time and limit in message
- **Risk if unmet:** Runaway executions consume resources indefinitely. Fallback: The existing SIGKILL fallback in cancel_graceful() is a safety net even if SIGTERM fails.

### D4: Visual correctness of analytics charts — DEFER-10-04
- **What:** CostTrendChart, ExecutionVolumeChart, SuccessRateChart, and BotEffectivenessChart render correctly with real data: axes are labeled, time scale is correct, colors match the design system, and the 80% reference line appears on SuccessRateChart
- **How:** Open /dashboards/analytics in a browser with populated execution data. Inspect each chart visually and via browser DevTools.
- **Why deferred:** Chart.js rendering validation requires a real browser. happy-dom (Vitest environment) does not execute Canvas APIs. Visual correctness cannot be unit tested.
- **Validates at:** phase-10-integration (manual browser inspection)
- **Depends on:** Running frontend dev server, populated analytics data in the backend DB
- **Target:** All 4 charts render without canvas errors in Chrome; time scale shows correct date labels; stacked bars in ExecutionVolumeChart show correct color coding; BotEffectivenessChart doughnut segments add to 100%
- **Risk if unmet:** Dashboard is visually broken but technically "passing" unit tests. Low risk — Chart.js is well-tested and the project has 14 existing chart components as reference.

### D5: Dashboard date range filter updates all charts — DEFER-10-05
- **What:** Clicking 7d/30d/90d date range pills triggers API refetch and all four charts update within 2 seconds
- **How:** Manual interaction test on /dashboards/analytics with populated data. Switch between time ranges and observe chart update latency.
- **Why deferred:** Requires browser interaction with a live frontend+backend. Cannot be simulated in unit tests.
- **Validates at:** phase-10-integration (manual browser testing)
- **Depends on:** Running frontend + backend, sufficient execution history to show different data for different date ranges
- **Target:** All 4 charts re-render within 2 seconds of date range selection (from 10-RESEARCH.md experiment design: <2s for 1000 historical executions)
- **Risk if unmet:** Users cannot explore historical trends effectively. Fallback: Add a loading indicator so users know the charts are updating even if latency is higher than 2s.

### D6: Scheduling suggestions displayed on trigger configuration page — DEFER-10-06
- **What:** On the TriggerDetailPanel for a scheduled trigger with sufficient history, the SchedulingSuggestions component renders suggestions with success rates and rationale text
- **How:** Navigate to a scheduled trigger with >10 executions in the dev environment. Confirm SchedulingSuggestions component appears in the schedule configuration section.
- **Why deferred:** Requires a browser with a scheduled trigger that has execution history. TriggerDetailPanel is a complex component that would need extensive stubs in unit testing.
- **Validates at:** phase-10-integration (manual browser testing)
- **Depends on:** A scheduled trigger with >10 historical executions in the dev DB
- **Target:** SchedulingSuggestions component renders within TriggerDetailPanel for scheduled triggers; shows at least one hour and one day suggestion with success_rate > 0%; insufficient data message shown for triggers with <10 executions
- **Risk if unmet:** ANA-06 success criterion explicitly requires suggestions "displayed on trigger configuration page." Fallback: Verify the component import and rendering in TriggerDetailPanel.vue template manually.

### D7: Health alert badge and auto-refresh — DEFER-10-07
- **What:** The BotHealthDashboard auto-refreshes alert counts every 30 seconds; a new alert that appears server-side is visible in the browser within 35 seconds without page reload
- **How:** Create a health alert via the backend while BotHealthDashboard is open. Observe it appearing within 35 seconds.
- **Why deferred:** Requires real setInterval behavior and a live backend. Unit tests with flushPromises() do not simulate real timer intervals.
- **Validates at:** phase-10-integration (manual browser testing)
- **Depends on:** Live frontend + backend with health alerts being generated
- **Target:** New alert visible within 35 seconds (30s interval + 5s round-trip margin); existing acknowledged alerts retain their state across refreshes
- **Risk if unmet:** Users miss new health alerts until they manually refresh. Low functional impact — health alerts are also accessible via direct API call.

---

## Ablation Plan

**Purpose:** Isolate whether key architectural choices deliver their intended benefit.

### A1: SQL aggregation vs. Python-side aggregation (informational)
- **Condition:** Compare response time of `/admin/analytics/cost` (SQL GROUP BY) vs. a hypothetical Python loop over all rows
- **Expected impact:** SQL GROUP BY should be 5-10x faster for 1000+ records, per Leis et al. (2015) referenced in 10-RESEARCH.md
- **Command:** Not planned as a formal test — document query execution time with EXPLAIN QUERY PLAN to confirm index usage:
  ```bash
  cd /Users/neo/Developer/Projects/Agented/backend && uv run python -c "
  from app.db.connection import get_connection
  with get_connection() as conn:
      plan = conn.execute(\"EXPLAIN QUERY PLAN SELECT strftime('%Y-%m-%d', recorded_at) as period, SUM(total_cost_usd) FROM token_usage WHERE recorded_at >= '2026-01-01' GROUP BY period\").fetchall()
      for row in plan: print(dict(row))
  "
  ```
- **Evidence:** 10-RESEARCH.md Recommendation 1; existing indexes on idx_token_usage_recorded and idx_execution_logs_started_at

### A2: Simple Python loop vs. window function for consecutive failure detection (verified choice)
- **Condition:** The implementation uses a simple Python loop over 10 rows (not a SQL window function). This was a deliberate choice for speed (<5s health check constraint).
- **Expected impact:** Python loop over 10 rows is faster to execute than a complex window query and easier to test; acceptable because health check runs every 5 minutes
- **Evidence:** 10-RESEARCH.md Recommendation 3: "health check jobs must be fast (<5s)"; 10-02-PLAN.md: "Use simple reverse-chronological loop over 10 rows"
- **Verification:** Health check method timing captured in plan completion notes

---

## Baselines

| Baseline | Description | Expected Score | Source |
|----------|-------------|----------------|--------|
| Backend test pass rate | All pytest tests pass | 100% (906/906 from v0.1.0 STATE.md) | v0.1.0 milestone STATE.md |
| Frontend build errors | vue-tsc + vite build | 0 errors | v0.1.0 milestone STATE.md |
| Frontend test pass rate | All vitest tests pass | 100% (344/344 from v0.1.0 STATE.md) | v0.1.0 milestone STATE.md |
| Analytics API response time | GET /admin/analytics/cost for 30-day window | <500ms | 10-RESEARCH.md experiment design (existing budget endpoints are <500ms baseline) |
| Health check job time | One full _check_health() cycle | <5s | 10-RESEARCH.md Recommendation 3; MonitoringService._poll_usage is ~2s currently |
| Chart render time | Initial dashboard chart render | <500ms | 10-RESEARCH.md (existing TokenUsageChart render time as reference) |

---

## Evaluation Scripts

**Location of evaluation code:**
```
backend/tests/test_analytics.py        — Plans 10-01 proxy tests
backend/tests/test_health_monitor.py   — Plans 10-02 proxy tests
backend/tests/test_scheduling_suggestions.py — Plan 10-03 scheduling tests
backend/tests/test_budget_enforcement.py     — Plan 10-03 budget tests
```

**How to run full proxy evaluation (all backend tests for this phase):**
```bash
cd /Users/neo/Developer/Projects/Agented/backend && uv run pytest \
  tests/test_analytics.py \
  tests/test_health_monitor.py \
  tests/test_scheduling_suggestions.py \
  tests/test_budget_enforcement.py \
  -v --tb=short 2>&1 | tee /tmp/phase10-eval-results.txt
```

**How to run full sanity verification (all three suites):**
```bash
cd /Users/neo/Developer/Projects/Agented && just build && \
  cd backend && uv run pytest --tb=short -q && \
  cd ../frontend && npm run test:run
```

---

## Results Template

*To be filled by grd-eval-reporter after phase execution.*

### Sanity Results

| Check | Status | Output | Notes |
|-------|--------|--------|-------|
| S1 — Backend imports | [PASS/FAIL] | | |
| S2 — Analytics empty DB | [PASS/FAIL] | | |
| S3 — Health monitor empty DB | [PASS/FAIL] | | |
| S4 — health_alerts table created | [PASS/FAIL] | | |
| S5 — budget_limits new columns | [PASS/FAIL] | | |
| S6 — Frontend TypeScript compile | [PASS/FAIL] | | |
| S7 — Frontend production build | [PASS/FAIL] | | |
| S8 — New routes registered | [PASS/FAIL] | | |
| S9 — Backend regression tests | [PASS/FAIL] | [N/N tests passing] | |

### Proxy Results

| Metric | Target | Actual | Status | Notes |
|--------|--------|--------|--------|-------|
| P1 — Cost aggregation correctness | Pass (15+ records) | | [MET/MISSED] | |
| P2 — Execution analytics aggregation | Pass (20+ records) | | [MET/MISSED] | |
| P3 — PR acceptance rate calculation | Pass, 0.0 on empty | | [MET/MISSED] | |
| P4 — Date range filtering | Pass (15-day window) | | [MET/MISSED] | |
| P5 — Consecutive failure detection | Pass (both cases) | | [MET/MISSED] | |
| P6 — Missing fire: scheduled-only | Pass | | [MET/MISSED] | |
| P7 — Alert deduplication | 1 alert after 2 checks | | [MET/MISSED] | |
| P8 — Scheduling suggestion ranking | High-success hours ranked first | | [MET/MISSED] | |
| P9 — Monthly run count enforcement | Violation + health alert | | [MET/MISSED] | |
| P10 — Weekly report all fields | All 5 fields present | | [MET/MISSED] | |

### Ablation Results

| Condition | Expected | Actual | Conclusion |
|-----------|----------|--------|------------|
| A1 — SQL GROUP BY index usage | SCAN uses idx_token_usage_recorded | | |
| A2 — Simple loop vs. window function | Loop completes <500ms per trigger | | |

### Deferred Status

| ID | Metric | Status | Validates At |
|----|--------|--------|-------------|
| DEFER-10-01 | Cost data within 60s of execution | PENDING | phase-10-integration |
| DEFER-10-02 | Real APScheduler health check cycle | PENDING | phase-10-integration |
| DEFER-10-03 | Execution time limit cancellation | PENDING | phase-10-integration |
| DEFER-10-04 | Visual correctness of analytics charts | PENDING | phase-10-integration |
| DEFER-10-05 | Dashboard date range filter latency <2s | PENDING | phase-10-integration |
| DEFER-10-06 | Scheduling suggestions on trigger config page | PENDING | phase-10-integration |
| DEFER-10-07 | Health alert auto-refresh within 35s | PENDING | phase-10-integration |

---

## Evaluation Confidence

**Overall confidence in evaluation design:** MEDIUM-HIGH

**Justification:**
- Sanity checks: Adequate — 9 checks cover all new modules, the critical new DB table, TypeScript compilation, build, and regression testing. The isolated_db fixture makes sanity checks reliable.
- Proxy metrics: Well-evidenced — 10 proxy tests directly exercise the SQL aggregation logic and service layer with controlled data. The isolated_db fixture provides real SQLite (not mocks), making these tests reliable proxies for the production query paths.
- Deferred coverage: Comprehensive for the known gaps — all 7 deferred items address real production scenarios that cannot be simulated in unit tests: subprocess behavior, APScheduler job lifecycle, Chart.js canvas rendering, and browser interaction.

**What this evaluation CAN tell us:**
- Whether cost, execution, and effectiveness SQL aggregation is mathematically correct
- Whether health monitoring detection thresholds (consecutive failures, slow execution, missing fire, deduplication) work on controlled data sequences
- Whether budget enforcement (monthly run count + execution time limit) correctly blocks and notifies
- Whether scheduling suggestions rank by success rate as designed
- Whether all new Python modules import cleanly without circular dependencies or missing packages
- Whether the frontend TypeScript types are valid and the build compiles cleanly
- Whether existing backend tests continue to pass (no regressions in execution_service.py, budget_service.py)

**What this evaluation CANNOT tell us:**
- Whether cost data actually updates within 60 seconds after a live execution (DEFER-10-01 — requires live execution pipeline)
- Whether APScheduler runs the health check job correctly in production (DEFER-10-02 — requires TESTING=False app startup)
- Whether mid-execution time limit cancellation works on real subprocesses (DEFER-10-03 — subprocess mocking cannot test SIGTERM handling)
- Whether Chart.js renders correctly in a real browser (DEFER-10-04 — Canvas API is not available in happy-dom)
- Whether dashboard filter interactions feel responsive (DEFER-10-05 — requires real browser + real timer intervals)
- Whether the SchedulingSuggestions component integrates visually into TriggerDetailPanel (DEFER-10-06)
- Whether the race condition from 10-RESEARCH.md Pitfall 4 (concurrent budget checks) is a real problem at production concurrency levels (not tested at any tier)

---

*Evaluation plan by: Claude (grd-eval-planner)*
*Design date: 2026-03-04*
