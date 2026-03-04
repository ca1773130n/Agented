# Phase 10: Analytics & Monitoring Dashboards - Research

**Researched:** 2026-03-04
**Domain:** Application analytics, time-series visualization, bot health monitoring, budget enforcement
**Confidence:** HIGH

## Summary

Phase 10 builds analytics and monitoring dashboards on top of a mature existing infrastructure. The codebase already has extensive foundations: a `token_usage` table with full cost tracking, a `budget_limits` table with soft/hard limits, a `BudgetService` with cost estimation and pre-execution budget checks, a `MonitoringService` with rate limit tracking and threshold alerting, 14 existing Chart.js monitoring components (including `TokenUsageChart`, `RateLimitTrendChart`, `CombinedUsageChart`), and a comprehensive `execution_logs` table with duration, status, and token data. The `pr_reviews` table already tracks review status (`pending`, `approved`, `changes_requested`, `fixed`) with `fixes_applied` counts.

The primary work is extending existing patterns rather than building from scratch. The seven requirements (ANA-01 through ANA-07) decompose into: (1) enriching existing cost/usage dashboards with per-entity time-series views, (2) adding acceptance rate computation to the existing PR review stats, (3) building new execution analytics aggregation queries and charts, (4) implementing a health monitoring state machine with consecutive failure tracking, (5) generating weekly team impact digest reports, (6) analyzing execution timestamps for scheduling recommendations, and (7) enforcing per-bot budget limits with mid-execution cancellation.

**Primary recommendation:** Leverage the existing `budgets.py` CRUD module, `BudgetService`, and Chart.js component patterns. Add new SQLite aggregation views for analytics, extend the `MonitoringService` with bot health state tracking, and reuse the `ProcessManager.cancel_graceful()` mechanism for budget-triggered cancellation.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Chart.js | ^4.5.1 | All dashboard charting | Already in use across 14 components with established dark-theme styling patterns |
| chartjs-adapter-date-fns | ^3.0.0 | Time-scale axis for time-series charts | Already a dependency; enables `type: 'time'` on x-axis with date-fns parsing |
| date-fns | ^4.1.0 | Date manipulation for period calculations | Already a dependency; lightweight alternative to moment.js |
| SQLite (via raw connection) | Built-in | All analytics queries and aggregations | Project uses raw SQLite with `get_connection()` context manager -- no ORM |
| APScheduler | >=3.10.0 | Scheduled health checks and report generation | Already used for trigger scheduling, monitoring polls, and cleanup jobs |
| Flask-OpenAPI3 | >=3.0.0 | API endpoints with auto-docs | Already used for all routes; new analytics endpoints follow same `APIBlueprint` pattern |
| Pydantic v2 | >=2.0.0 | Request/response validation | Already used for all route models |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Vue 3 composables | ^3.5.24 | Shared chart logic | Extract common chart config (colors, fonts, tooltips) into a `useChartConfig` composable |
| SSE (EventSource) | Built-in | Real-time alert notifications | For streaming health alerts to the frontend |

### Alternatives Considered
| Instead of | Could Use | Tradeoff | Why Not |
|------------|-----------|----------|---------|
| Raw SQLite aggregation | SQLite materialized views | Faster reads, stale data | SQLite does not support materialized views natively; pre-computed summary tables with periodic refresh would add complexity not warranted at current scale |
| Chart.js | Apache ECharts | More chart types, larger bundle | Chart.js already established with 14 components and consistent styling |
| In-app alerts only | Email/Slack integration | Better reach, external dependency | Phase description says "at minimum, displayed in-app; optionally via configured channel" -- start with in-app, add webhook-based notifications as optional |

## Architecture Patterns

### Recommended Project Structure

**Backend additions:**
```
backend/app/
├── db/
│   ├── analytics.py          # New: execution analytics aggregation queries
│   └── budgets.py             # Existing: extend with per-bot max_runs, max_time fields
├── services/
│   ├── analytics_service.py   # New: analytics computation, trend analysis, scheduling suggestions
│   ├── health_monitor_service.py  # New: bot health state machine, consecutive failure tracking
│   ├── impact_report_service.py   # New: weekly team impact digest generation
│   └── budget_service.py      # Existing: extend with mid-execution enforcement
├── routes/
│   ├── analytics.py           # New: analytics API endpoints
│   └── budgets.py             # Existing: extend with per-bot budget endpoints
└── models/
    └── analytics.py           # New: Pydantic models for analytics request/response
```

**Frontend additions:**
```
frontend/src/
├── views/
│   ├── AnalyticsDashboard.vue       # New: execution analytics page
│   ├── BotHealthDashboard.vue       # New: health monitoring page
│   └── TeamImpactReport.vue         # New: team impact report page
├── components/
│   └── analytics/
│       ├── ExecutionVolumeChart.vue  # New: time-series execution count chart
│       ├── SuccessRateChart.vue      # New: success/failure ratio chart
│       ├── DurationTrendChart.vue    # New: average duration chart
│       ├── ModelUsageChart.vue       # New: model usage breakdown
│       ├── AcceptanceRateCard.vue    # New: PR acceptance rate display
│       ├── HealthAlertList.vue       # New: bot health alert list
│       ├── SchedulingSuggestions.vue # New: scheduling recommendation UI
│       └── BotBudgetCard.vue        # New: per-bot budget display
├── services/api/
│   ├── analytics.ts                 # New: analytics API client
│   └── types.ts                     # Existing: extend with analytics types
└── router/routes/
    └── dashboard.ts                 # Existing: add new dashboard routes
```

### Pattern 1: SQLite Aggregation Queries for Analytics

**What:** Use SQLite's built-in aggregate functions (`COUNT`, `SUM`, `AVG`, `GROUP BY`, `strftime`) to compute analytics directly in SQL, matching the existing pattern in `budgets.py`.

**When to use:** For all time-series aggregation (execution volume, success rate, duration trends, cost breakdowns).

**Reference:** Existing pattern in `get_usage_aggregated_summary()` in `backend/app/db/budgets.py`.

**Example:**
```python
# Source: Existing pattern from backend/app/db/budgets.py lines 240-293
def get_execution_analytics(
    group_by: str = "day",
    trigger_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Get execution analytics grouped by time period."""
    if group_by == "day":
        date_fmt = "%Y-%m-%d"
    elif group_by == "week":
        date_fmt = "%Y-W%W"
    else:
        date_fmt = "%Y-%m"

    query = f"""
        SELECT
            strftime('{date_fmt}', started_at) as period,
            COUNT(*) as total_executions,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'timeout' THEN 1 ELSE 0 END) as timed_out,
            ROUND(AVG(duration_ms), 0) as avg_duration_ms,
            ROUND(AVG(CASE WHEN status = 'success' THEN duration_ms END), 0) as avg_success_duration_ms,
            COALESCE(SUM(total_cost_usd), 0) as total_cost_usd,
            COUNT(DISTINCT trigger_id) as unique_bots
        FROM execution_logs
        WHERE 1=1
    """
    # ... parameter binding follows existing pattern
```

### Pattern 2: Health State Machine

**What:** Track bot health using a state machine with in-memory state and persistent alert history. Compute consecutive failure counts from `execution_logs` rather than maintaining separate counters.

**When to use:** For ANA-04 bot health monitoring.

**Example:**
```python
# Compute consecutive failures from execution history
def get_consecutive_failure_count(trigger_id: str) -> int:
    """Count consecutive failures from most recent execution backwards."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT status FROM execution_logs
            WHERE trigger_id = ?
            ORDER BY started_at DESC
            LIMIT 20
        """, (trigger_id,))
        count = 0
        for row in cursor:
            if row["status"] in ("failed", "timeout"):
                count += 1
            else:
                break
        return count
```

### Pattern 3: Chart.js Component Pattern (Reuse Existing)

**What:** Follow the exact pattern used in `FindingsChart.vue`, `TokenUsageChart.vue`, and `RateLimitTrendChart.vue`: register all Chart.js registerables, use canvas ref, destroy on unmount, watch props for re-render.

**When to use:** For all new chart components.

**Reference:** `frontend/src/components/security/FindingsChart.vue`, `frontend/src/components/monitoring/TokenUsageChart.vue`.

**Key conventions from existing charts:**
- Dark theme colors: `#8855ff` (violet), `#00d4ff` (cyan), `#ff3366` (crimson), `#ffaa00` (amber), `#00ff88` (emerald)
- Font: `'Geist Mono', 'SF Mono', monospace` for labels
- Grid: `rgba(255, 255, 255, 0.06)`
- Tooltip background: `rgba(18, 18, 26, 0.95)`
- Animation: `duration: 800, easing: 'easeOutQuart'`

### Pattern 4: Per-Bot Budget Enforcement with Mid-Execution Cancellation

**What:** Extend existing `BudgetService.check_budget()` to include per-bot limits (max execution time, max tokens, max monthly runs). Use a background thread that monitors running executions and calls `ProcessManager.cancel_graceful()` when limits are hit.

**When to use:** For ANA-07 per-bot budget enforcement.

**Reference:** Existing `ProcessManager.cancel_graceful()` in `backend/app/services/process_manager.py` already implements SIGTERM-then-SIGKILL pattern.

### Anti-Patterns to Avoid

- **Polling for analytics data:** Do not have the frontend poll analytics endpoints on short intervals. Analytics data changes only on execution completion. Use event-driven refresh (after execution complete SSE event) or user-initiated refresh.

- **Building a custom charting abstraction:** Do not create a generic chart wrapper component. The existing pattern of purpose-built chart components (one per visualization) with explicit Chart.js configuration is clear and maintainable. Each chart has distinct data shapes and display requirements.

- **Storing computed analytics in separate tables:** Do not pre-compute analytics into summary tables unless query performance becomes an issue. SQLite aggregate queries over indexed `execution_logs` are fast for the expected data volumes (hundreds to low thousands of executions). The existing `get_usage_aggregated_summary()` demonstrates this approach works.

- **External alerting service dependency:** Do not require external services (PagerDuty, Slack) for health alerts to function. The phase spec says "at minimum, displayed in-app." Build in-app alerting first; optional webhook-based notification can be added as a configurable output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Time-series date formatting | Custom date parsing for chart axes | `chartjs-adapter-date-fns` with `type: 'time'` axis | Already a project dependency; handles timezone, locale, and formatting edge cases |
| Process cancellation | Custom signal handling for budget enforcement | `ProcessManager.cancel_graceful()` | Already implements SIGTERM-then-SIGKILL with configurable grace period |
| Scheduling (periodic health checks) | Custom timer threads for periodic tasks | `APScheduler` via `SchedulerService` | Already initialized in app factory; handles coalesce, max instances, cron triggers |
| Cost estimation | Custom token-to-cost calculator | `BudgetService.MODEL_PRICING` + `estimate_cost()` | Already has model pricing for Claude, Gemini variants; extend for new models |
| Consecutive failure counting | In-memory counter with persistence | SQL query on `execution_logs ORDER BY started_at DESC` | Execution history is already persisted; computing from source is more reliable than maintaining a separate counter that can drift |

**Key insight:** The codebase already has ~80% of the infrastructure needed for this phase. The risk is in re-building what exists rather than extending it. Every new feature should first check whether an existing service, database function, or component can be extended.

## Common Pitfalls

### Pitfall 1: Chart Memory Leaks
**What goes wrong:** Chart.js instances not destroyed before re-creation, causing memory leaks on data updates.
**Why it happens:** Forgetting to call `chartInstance.destroy()` before creating a new chart, or not cleaning up on component unmount.
**How to avoid:** Follow the existing pattern in `FindingsChart.vue`: always destroy in `renderChart()` before creating, and destroy in `onUnmounted()`.
**Warning signs:** Browser memory usage climbing over time when viewing analytics dashboards.

### Pitfall 2: SQLite Date Function Pitfalls
**What goes wrong:** `strftime` returns `NULL` for invalid date strings, silently excluding rows from aggregation.
**Why it happens:** Execution logs may have inconsistent timestamp formats (some with 'Z', some without, some with timezone offsets).
**How to avoid:** The existing `_utc_suffix()` helper in `monitoring.py` normalizes timestamps. Apply similar normalization to all date-based queries. Use `datetime()` SQLite function for comparison rather than string comparison.
**Warning signs:** Analytics showing fewer executions than expected for a time period.

### Pitfall 3: Budget Enforcement Race Condition
**What goes wrong:** An execution starts between the budget check and the actual subprocess launch, causing the budget to be exceeded.
**Why it happens:** The check-then-act pattern is inherently racy in concurrent environments.
**How to avoid:** Use the existing budget check in `ExecutionService` as a gate, but also implement a post-completion reconciliation check. Accept that the budget is a "best effort" cap, not an exact limit. The phase spec says "gracefully cancelled mid-execution" -- this implies tolerance for slight overages.
**Warning signs:** Total spend slightly exceeding hard limit.
**Reference:** Google SRE Workbook on monitoring and alerting recommends accepting some error budget rather than blocking all operations.

### Pitfall 4: Alert Fatigue
**What goes wrong:** Health monitoring generates too many alerts, causing users to ignore them all.
**Why it happens:** Low thresholds (e.g., N=2 consecutive failures), no cooldown between alerts, or alerting on transient issues.
**How to avoid:** Make failure threshold configurable with a sensible default (N=3). Implement alert cooldown (don't re-alert for the same bot within a configurable window). Group related alerts.
**Warning signs:** Users disabling health monitoring entirely.
**Reference:** [SRE Monitoring Best Practices](https://l3an.dev/blog/sre-monitoring-best-practices/) emphasizes reducing noise and fatigue.

### Pitfall 5: Expensive Analytics Queries
**What goes wrong:** Analytics queries scanning the entire `execution_logs` table on every dashboard load, causing slow page loads.
**Why it happens:** No date range restriction, missing indexes, or joining too many tables.
**How to avoid:** Always require date range parameters (default to last 30 days). The existing index `idx_execution_logs_started_at` on `execution_logs(started_at DESC)` should cover most queries. Add a composite index on `(trigger_id, started_at DESC)` if per-bot queries are slow.
**Warning signs:** Dashboard taking >2 seconds to load.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Number of execution log records (100, 1000, 10000)
- Date range width (7 days, 30 days, 90 days)
- Number of distinct bots (2, 10, 50)

**Dependent variables:**
- Analytics query execution time (ms)
- Chart render time (ms)
- Memory usage of chart instances

**Controlled variables:**
- SQLite WAL mode (existing configuration)
- Browser: Chrome latest
- Chart.js version: 4.5.1

**Baseline comparison:**
- Method: Existing `get_usage_aggregated_summary()` query performance
- Expected performance: <100ms for 1000 records with index
- Our target: All analytics queries complete in <200ms for up to 10000 execution records

**Statistical rigor:**
- Number of runs: 3 per configuration
- Measure p50 and p95 query times
- Validate with `EXPLAIN QUERY PLAN` that indexes are used

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Query latency (ms) | Core UX metric | Time analytics SQL queries | <100ms (existing budget queries) |
| Chart render time (ms) | Perceived performance | Measure from data-received to chart-displayed | <500ms for 30 data points |
| Alert accuracy (%) | Health monitoring quality | True positives / (true positives + false positives) | Track manually during testing |
| Budget enforcement latency (s) | How fast cancellation occurs after limit hit | Time from limit detection to SIGTERM | <60 seconds per spec |
| PR acceptance rate accuracy | Effectiveness metric correctness | Compare computed rate against manual audit | N/A (new metric) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Analytics queries return correct aggregations | Level 1 (Sanity) | Can test with seeded data in isolated_db |
| Cost dashboard displays per-bot/team/project data | Level 2 (Proxy) | Verify with at least 10 seeded execution records |
| PR acceptance rate computation is correct | Level 1 (Sanity) | Test with known set of PR reviews |
| Health monitor detects N consecutive failures | Level 1 (Sanity) | Seed N failed executions, verify alert fires |
| Health monitor detects 3x average duration | Level 2 (Proxy) | Seed historical data, run slow execution |
| Health monitor detects missing-fire interval | Level 2 (Proxy) | Requires time manipulation or test with short intervals |
| Charts render with real data from 10+ executions | Level 2 (Proxy) | Frontend test with mocked API returning 10+ records |
| Weekly impact report generates correct digest | Level 2 (Proxy) | Seed team data, verify report content |
| Scheduling suggestions analyze historical data | Level 2 (Proxy) | Seed execution timestamps, verify recommendations |
| Budget enforcement cancels bot mid-execution | Level 2 (Proxy) | Start execution, verify cancellation signal sent |
| Cost data updates within 60s of execution | Level 2 (Proxy) | Verify token usage recorded on execution completion |
| Full dashboard integration with production data | Level 3 (Deferred) | Requires real execution history |

**Level 1 checks to always include:**
- Analytics SQL queries produce expected results with seeded test data
- PR acceptance rate formula: `(resolved_count + fixed_count) / total_reviews * 100`
- Consecutive failure count matches expected from seeded execution history
- Budget limit comparison logic handles edge cases (null limits, zero spend)

**Level 2 proxy metrics:**
- Seed 10+ execution records, verify all chart data endpoints return valid time-series data
- Seed budget limits, trigger execution, verify budget check prevents/allows
- Create team with agents, seed execution history, verify impact report generates

**Level 3 deferred items:**
- Performance under production data volumes
- Real notification delivery (email/Slack)
- Cross-browser chart rendering consistency
- Multi-user concurrent dashboard access

## Production Considerations

### Known Failure Modes

- **SQLite write contention during analytics reads:** Analytics queries are read-only but SQLite's WAL mode allows concurrent reads. However, heavy write operations (many simultaneous executions recording token usage) could cause brief read delays.
  - Prevention: Analytics queries use read-only connections; WAL mode is already enabled
  - Detection: Monitor query latency via Python logging

- **APScheduler job overlap for health checks:** If a health check job takes longer than the polling interval, APScheduler's `max_instances=1` setting prevents overlap, but the health check for that cycle is skipped.
  - Prevention: Keep health check queries fast (use indexed lookups)
  - Detection: Log when health check exceeds expected duration

- **Budget enforcement timing gap:** Between budget check and process launch, another execution might start. Between token usage recording and budget comparison, values could be stale.
  - Prevention: Accept this is best-effort; budget limits are guardrails, not guarantees
  - Detection: Post-execution reconciliation check; alert if budget exceeded by >10%

### Scaling Concerns

- **Execution log volume:** At current scale (likely <1000 executions/month), direct SQL aggregation is fast. At >10,000 executions/month, consider pre-computed daily summary tables refreshed via APScheduler cron job.
  - At current scale: Direct SQL aggregation
  - At production scale: Pre-computed summary tables with incremental refresh

- **Chart rendering with large datasets:** Chart.js can handle ~1000 data points before rendering slows. For time-series spanning months with hourly granularity, downsample to daily/weekly aggregation on the backend.
  - At current scale: Return all data points
  - At production scale: Backend-side downsampling with configurable granularity

### Common Implementation Traps

- **Trap:** Computing acceptance rate in Python by loading all PR reviews and counting in a loop.
  - Correct approach: Compute in SQL with `SUM(CASE WHEN ...)` / `COUNT(*)`, matching the existing `get_pr_review_stats()` pattern.

- **Trap:** Creating a single monolithic analytics endpoint that returns all dashboard data.
  - Correct approach: Separate endpoints per data domain (execution volume, cost breakdown, health status). The frontend can parallel-fetch them on dashboard mount.

- **Trap:** Hardcoding the consecutive failure threshold N.
  - Correct approach: Store in `settings` table (same as `monitoring_config`) with a configurable default.

## Code Examples

Verified patterns from the existing codebase:

### Chart.js Dark-Theme Configuration (from existing components)
```typescript
// Source: frontend/src/components/security/FindingsChart.vue lines 36-44
const colors = {
  critical: '#ff3366',  // --accent-crimson
  high: '#ffaa00',      // --accent-amber
  medium: '#00d4ff',    // --accent-cyan
  low: '#00ff88',       // --accent-emerald
  grid: 'rgba(255, 255, 255, 0.06)',
  text: 'rgba(255, 255, 255, 0.5)',
  textMuted: 'rgba(255, 255, 255, 0.35)',
};
```

### Time-Series Chart with date-fns Adapter
```typescript
// Source: Chart.js official docs + existing RateLimitTrendChart.vue pattern
import 'chartjs-adapter-date-fns';

chartInstance = new Chart(canvasRef.value, {
  type: 'line',
  data: { datasets: [{ data: timeSeriesData }] },
  options: {
    scales: {
      x: {
        type: 'time',
        time: {
          unit: 'day',
          displayFormats: { day: 'MMM d' },
        },
        ticks: { color: 'rgba(255, 255, 255, 0.35)' },
      },
    },
  },
});
```

### APScheduler Job Registration (from existing MonitoringService)
```python
# Source: backend/app/services/monitoring_service.py lines 110-133
SchedulerService._scheduler.add_job(
    func=cls._run_health_check,
    trigger="interval",
    minutes=5,
    id="bot_health_check",
    replace_existing=True,
)
```

### Budget Check Pre-Execution (from existing BudgetService)
```python
# Source: backend/app/services/budget_service.py lines 308-360
result = BudgetService.check_budget(entity_type, entity_id)
if not result["allowed"]:
    logger.warning(f"Budget exceeded for {entity_type}/{entity_id}: {result['reason']}")
    # Cancel or reject execution
```

### APIBlueprint Route Pattern (from existing routes)
```python
# Source: backend/app/routes/budgets.py lines 26-27
tag = Tag(name="analytics", description="Execution analytics and trend dashboards")
analytics_bp = APIBlueprint("analytics", __name__, url_prefix="/admin/analytics", abp_tags=[tag])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| In-memory execution tracking only | Database-persisted execution_logs with token_usage | Phase 6 (v0.1.0) | Enables historical analytics; existing tables have proper indexes |
| No budget enforcement | BudgetService with soft/hard limits | Phase 6 (v0.1.0) | Foundation for per-bot budget caps; extends naturally |
| No rate limit monitoring | MonitoringService with APScheduler polling | Phase 5 (v0.1.0) | Established pattern for health check polling reuse |
| Manual cost estimation | BudgetService.estimate_cost() with model pricing | Phase 6 (v0.1.0) | Existing cost model for all supported backends |

**Deprecated/outdated:**
- In-memory-only execution status tracking was replaced by database-backed `execution_logs` table. All analytics should query the database, not in-memory state.

## Open Questions

1. **PR acceptance rate definition**
   - What we know: The `pr_reviews` table has `review_status` (pending, approved, changes_requested, fixed) and `fixes_applied` count. The `pr_status` field tracks open/merged/closed.
   - What's unclear: The exact definition of "accepted" vs "ignored." Is a merged PR with `review_status = 'fixed'` an acceptance? Is a closed PR with no fixes an ignored suggestion?
   - Recommendation: Define acceptance rate as `(reviews where review_status IN ('fixed', 'approved') AND fixes_applied > 0) / total_reviews`. This captures both direct acceptance and fix-after-review scenarios.

2. **Health alert notification channel**
   - What we know: Phase spec says "at minimum, displayed in-app; optionally via configured channel."
   - What's unclear: What "configured channel" means -- webhook URL, email, Slack?
   - Recommendation: Start with in-app alerts using the existing SSE streaming infrastructure. Add an optional webhook URL field in health monitoring config that receives a POST with alert payload. This is generic enough to support Slack (via incoming webhook), email (via webhook-to-email bridge), or any HTTP endpoint.

3. **Smart scheduling -- data source for activity patterns**
   - What we know: ANA-06 says "analyze repo activity patterns (commit frequency, PR volume by hour/day)."
   - What's unclear: Whether this means analyzing GitHub API data (which requires API calls and rate limits) or analyzing existing execution history timestamps.
   - Recommendation: Analyze existing `execution_logs.started_at` timestamps and `pr_reviews.created_at` for activity patterns. This avoids external API dependencies and uses data already available. The suggestions would be "based on when your bots are triggered, optimal times are X."

4. **Max monthly run count enforcement**
   - What we know: ANA-07 requires "max monthly runs per bot."
   - What's unclear: Whether this is a new field on the trigger/bot or an extension of the existing `budget_limits` table.
   - Recommendation: Extend the existing `budget_limits` table with `max_monthly_runs INTEGER` and `max_execution_seconds INTEGER` columns. The `BudgetService.check_budget()` method already queries this table -- extend it to count monthly executions and check against the limit.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `backend/app/db/budgets.py` -- Token usage CRUD, budget limits, aggregation queries
- Existing codebase: `backend/app/services/budget_service.py` -- Cost estimation, budget checks, token extraction
- Existing codebase: `backend/app/services/monitoring_service.py` -- Rate limit monitoring, threshold detection, APScheduler integration
- Existing codebase: `backend/app/services/process_manager.py` -- Graceful cancellation with SIGTERM/SIGKILL
- Existing codebase: `backend/app/db/schema.py` -- All table definitions including execution_logs, token_usage, budget_limits, pr_reviews
- Existing codebase: `frontend/src/components/monitoring/` -- 14 Chart.js monitoring components
- Existing codebase: `frontend/src/components/security/FindingsChart.vue` -- Chart.js dark-theme pattern
- [Chart.js Time Cartesian Axis](https://www.chartjs.org/docs/latest/axes/cartesian/time.html) -- Official time-scale documentation
- [SQLite Window Functions](https://sqlite.org/windowfunctions.html) -- Official SQLite window function documentation
- [SQLite Built-in Aggregate Functions](https://sqlite.org/lang_aggfunc.html) -- Official aggregate function reference

### Secondary (MEDIUM confidence)
- [chartjs-adapter-date-fns GitHub](https://github.com/chartjs/chartjs-adapter-date-fns) -- Adapter configuration and usage
- [Google SRE Workbook: Monitoring](https://sre.google/workbook/monitoring/) -- Alert design and threshold patterns
- [Google SRE: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) -- Multi-window alerting approach
- [SRE Monitoring Best Practices](https://l3an.dev/blog/sre-monitoring-best-practices/) -- Alert fatigue prevention
- [Handling Time Series Data in SQLite](https://moldstud.com/articles/p-handling-time-series-data-in-sqlite-best-practices) -- Indexing and query optimization patterns
- [CodeRabbit: Measuring AI Development Impact](https://www.coderabbit.ai/blog/measuring-what-matters-in-the-age-of-ai-assisted-development) -- PR acceptance rate as a quality signal

### Tertiary (LOW confidence)
- [LeadDev: The Rise and Fall of Acceptance Rate](https://leaddev.com/reporting/the-rise-and-looming-fall-of-acceptance-rate) -- Cautions about acceptance rate as a standalone metric; recommend pairing with qualitative signals
- [Better Stack: Cron Job Monitoring Tools](https://betterstack.com/community/comparisons/cronjob-monitoring-tools/) -- Overview of scheduling monitoring tools

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use; no new dependencies required
- Architecture: HIGH -- follows established codebase patterns; extends existing services and components
- Recommendations: HIGH -- based on direct codebase analysis of existing working patterns
- Pitfalls: MEDIUM -- common issues identified from codebase review and web research; some are theoretical until validated under load
- Experiment design: MEDIUM -- baseline performance numbers are estimates; actual values depend on real data volume

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable domain, no fast-moving dependencies)
