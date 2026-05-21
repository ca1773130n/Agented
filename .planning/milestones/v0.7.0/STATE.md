# v0.7.0 State

Status: COMPLETE — shipped 2026-05-06.

## Shipped

Per-bot success-rate / p50-p95-p99 / last-failure rollups computed
from execution_logs over a sliding window (1..90 days). Status pill
classifies healthy / degraded / down / no_recent_runs using
DEGRADED_SUCCESS_THRESHOLD=0.80 and LATENCY_ANOMALY_RATIO=5.0
(p95/p50). Bots are queried via the triggers table (renamed from
'bots' in v0.4) but the dataclass keeps bot_id/bot_name to preserve
the operator-facing concept. Shipped as 10 sequential commits implementing the full slice.

## Key files touched

- `backend/app/db/migrations.py`
- `frontend/src/services/api/index.ts`
- `backend/app/services/bot_health_service.py`
- `frontend/src/components/layout/AppSidebar.vue`
- `frontend/src/router/routes/misc.ts`
- `frontend/src/views/BotHealthPage.vue`

## Reference

- Commit: `140c5548`
- Commits in slice: 9
