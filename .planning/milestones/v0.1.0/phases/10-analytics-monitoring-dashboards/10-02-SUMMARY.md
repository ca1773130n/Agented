---
phase: 10-analytics-monitoring-dashboards
plan: 02
subsystem: health-monitoring
tags: [health-monitor, alerts, reports, apscheduler, sqlite]
dependency_graph:
  requires: []
  provides: [health-alerts-api, weekly-report-api, health-monitor-service]
  affects: [app-startup, routes, schema]
tech_stack:
  added: []
  patterns: [apscheduler-periodic-job, deduplication-window, simple-loop-detection]
key_files:
  created:
    - backend/app/db/health_alerts.py
    - backend/app/models/health.py
    - backend/app/services/health_monitor_service.py
    - backend/app/services/report_service.py
    - backend/app/routes/health_monitor.py
    - backend/tests/test_health_monitor.py
  modified:
    - backend/app/db/schema.py
    - backend/app/db/migrations.py
    - backend/app/db/__init__.py
    - backend/app/routes/__init__.py
    - backend/app/__init__.py
decisions:
  - Health monitor uses simple Python loop for consecutive failure detection instead of window functions for speed
  - Missing fire detection only applies to scheduled triggers (not webhook/github) per 10-RESEARCH.md Pitfall 3
  - Alert deduplication via 30-min same-type+trigger_id window prevents alert spam
  - Report uses direct SQL queries against execution_logs and pr_reviews (no Jinja2/PDF)
metrics:
  duration: 10m
  completed: 2026-03-04
---

# Phase 10 Plan 02: Health Monitor and Weekly Report Summary

Health monitoring service with APScheduler-based periodic checks detecting consecutive failures, slow executions, and missing scheduled fires. Weekly team impact report generator computing PRs reviewed, issues found, estimated time saved, top bots, and bots needing attention.

## Completed Tasks

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Create health_alerts DB table, health monitor service, and report service | cb9f708 | Schema, migration v57, CRUD, HealthMonitorService, ReportService, Pydantic models |
| 2 | Create API routes, app startup wiring, and tests | 465b430 | 5 endpoints, blueprint registration, 7 passing tests |

## Key Implementation Details

### Health Monitor Service

- Runs as APScheduler interval job every 5 minutes
- **Consecutive failure detection**: Simple reverse-chronological loop over last 10 executions; alerts when >= 3 consecutive failures
- **Slow execution detection**: Compares latest execution to average of last 20; alerts when > 3x average (requires >= 5 historical executions)
- **Missing fire detection**: Only for trigger_source='scheduled'; alerts when last_run_at exceeds 2x expected interval (daily=48h, weekly=336h)
- Daily cleanup job removes alerts older than 7 days

### Report Service

- `generate_weekly_report()` queries last 7 days of execution_logs and pr_reviews
- Calculates: prs_reviewed, issues_found, estimated_time_saved (15min/PR + 30min/audit), top 5 bots, bots needing attention (>50% failure rate or active alerts)

### API Endpoints

- `GET /admin/health-monitor/alerts` -- List alerts with optional filters
- `GET /admin/health-monitor/status` -- Alert counts summary
- `POST /admin/health-monitor/alerts/<id>/acknowledge` -- Acknowledge alert
- `GET /admin/health-monitor/report` -- Weekly team impact report
- `POST /admin/health-monitor/check` -- Manual health check trigger

## Verification

- 7/7 tests pass in test_health_monitor.py
- 947/947 total backend tests pass (0 regressions)
- All imports resolve correctly

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

All created files exist and both commits verified in git log.
