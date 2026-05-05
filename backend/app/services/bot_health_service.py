"""v0.7.0: per-bot health rollup from execution_logs.

The "bots" the operator sees are stored in the `triggers` table —
the table was renamed in the v0.4 migration but the operator concept
stayed. This service exposes per-bot rollups (success rate, p50/p95/p99
latency, last failure, status pill) computed over a sliding window of
`execution_logs` rows.

The rollup is computed on-read (no materialised view) — at the
expected scale (tens of bots, ~10k executions/day) a single indexed
query per bot is well under 100ms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.database import get_connection

# Tunables — kept as module constants so behaviour change is grep-able.
DEGRADED_SUCCESS_THRESHOLD = 0.80
LATENCY_ANOMALY_RATIO = 5.0  # p95 / p50

StatusPill = Literal["healthy", "degraded", "down", "no_recent_runs"]


@dataclass(frozen=True)
class BotHealthRollup:
    bot_id: str
    bot_name: str
    success_count: int
    fail_count: int
    success_rate: float | None  # None if no runs in window
    p50_duration_ms: int | None
    p95_duration_ms: int | None
    p99_duration_ms: int | None
    last_run_at: str | None
    last_failure_at: str | None
    last_failure_message: str | None
    status_pill: StatusPill


def compute_rollups(window_days: int = 7) -> list[BotHealthRollup]:
    """Return one rollup per bot (trigger) for the requested window.

    Raises:
        ValueError: if `window_days` is outside the 1..90 range.
    """
    if not (1 <= window_days <= 90):
        raise ValueError(f"window_days must be 1..90, got {window_days}")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    with get_connection() as conn:
        bots = list(conn.execute("SELECT id, name FROM triggers ORDER BY name"))
        rollups = [_compute_one(conn, bot["id"], bot["name"], cutoff) for bot in bots]
    return rollups


def _compute_one(conn, bot_id: str, bot_name: str, cutoff_iso: str) -> BotHealthRollup:
    rows = list(
        conn.execute(
            """SELECT status, duration_ms, started_at, error_message
               FROM execution_logs
               WHERE trigger_id = ? AND started_at >= ?
               ORDER BY started_at DESC""",
            (bot_id, cutoff_iso),
        )
    )
    success = [r for r in rows if r["status"] == "success"]
    fail = [r for r in rows if r["status"] == "failed"]
    durations = sorted(r["duration_ms"] for r in rows if r["duration_ms"] is not None)
    p50 = _percentile(durations, 0.50)
    p95 = _percentile(durations, 0.95)
    p99 = _percentile(durations, 0.99)
    total = len(success) + len(fail)
    success_rate = (len(success) / total) if total else None
    last_run = rows[0]["started_at"] if rows else None
    last_failure = fail[0] if fail else None
    pill = _classify(len(success), len(fail), success_rate, p50, p95)
    return BotHealthRollup(
        bot_id=bot_id,
        bot_name=bot_name,
        success_count=len(success),
        fail_count=len(fail),
        success_rate=success_rate,
        p50_duration_ms=p50,
        p95_duration_ms=p95,
        p99_duration_ms=p99,
        last_run_at=last_run,
        last_failure_at=last_failure["started_at"] if last_failure else None,
        last_failure_message=last_failure["error_message"] if last_failure else None,
        status_pill=pill,
    )


def _percentile(sorted_values: list[int], p: float) -> int | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = p * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return int(sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo]))


def _classify(
    success: int,
    fail: int,
    rate: float | None,
    p50: int | None,
    p95: int | None,
) -> StatusPill:
    total = success + fail
    if total == 0:
        return "no_recent_runs"
    if success == 0 and fail > 0:
        return "down"
    if rate is not None and rate < DEGRADED_SUCCESS_THRESHOLD:
        return "degraded"
    if p50 and p95 and p50 > 0 and p95 / p50 >= LATENCY_ANOMALY_RATIO:
        return "degraded"
    return "healthy"
