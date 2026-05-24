"""A/B impact metrics for an applied Life-Harness evolution round.

For an applied round, compares the N executions immediately preceding the
round's start to the N executions immediately following its finish on the
same bot. Surfaces:

    - success rate before / after
    - failure-layer distribution (h2/h3/h4/general) before / after
    - mean incident count before / after

These are *observational*, not a controlled A/B — Agented executions run
on whatever triggers naturally fire — so the operator reads them as
"directional evidence" rather than statistical truth.

Reference: arXiv 2605.22166 §5.2 Evolution Dynamics.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.db import harness_annotations as annotations_repo
from app.db import harness_evolution as evolution_repo
from app.db import harness_snapshots as snapshots_repo

logger = logging.getLogger(__name__)


_FAILURE_OUTCOMES = frozenset({"failed", "timeout", "interrupted", "cancelled"})


def compute_impact(round_id: str, *, window_size: int = 20) -> dict[str, Any]:
    """Build the impact comparison for an applied round.

    Returns a dict with ``available`` flag. When ``available=False``, an
    explanatory ``reason`` field tells the UI what to show. When
    ``available=True``, ``before`` / ``after`` carry the aggregates and
    ``delta`` carries pre→post differences."""
    rnd = evolution_repo.get_round(round_id)
    if rnd is None:
        return {"available": False, "reason": "round not found"}
    if rnd["status"] != "applied":
        return {
            "available": False,
            "reason": f"round not applied (status={rnd['status']!r})",
        }

    bot_id = rnd["bot_id"]
    started_at = rnd["started_at"]
    finished_at = rnd["finished_at"] or started_at

    before = _gather_window(bot_id, before_ts=started_at, limit=window_size)
    after = _gather_window(bot_id, after_ts=finished_at, limit=window_size)

    summary_before = _summarize(before)
    summary_after = _summarize(after)

    return {
        "available": True,
        "round_id": round_id,
        "bot_id": bot_id,
        "window_size": window_size,
        "before": summary_before,
        "after": summary_after,
        "delta": _delta(summary_before, summary_after),
    }


def _gather_window(
    bot_id: str,
    *,
    before_ts: Optional[str] = None,
    after_ts: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Pull up to ``limit`` snapshot rows for the bot before / after a
    timestamp, newest first, then enrich each with the matching
    execution annotation."""
    snapshots = snapshots_repo.list_for_bot(bot_id)
    if before_ts:
        snapshots = [s for s in snapshots if s["created_at"] < before_ts]
    if after_ts:
        snapshots = [s for s in snapshots if s["created_at"] > after_ts]
    snapshots = snapshots[:limit]

    enriched: list[dict[str, Any]] = []
    for snap in snapshots:
        exec_id = snap["execution_id"]
        annotation = annotations_repo.get_annotation(exec_id)
        enriched.append({
            "execution_id": exec_id,
            "annotation": annotation,
            "snapshot_at": snap["created_at"],
        })
    return enriched


def _summarize(window: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(window)
    if total == 0:
        return {
            "executions": 0,
            "success_rate": None,
            "failure_layers": {"h2": 0, "h3": 0, "h4": 0, "general": 0},
            "mean_incident_count": None,
        }

    successes = 0
    failure_layers = {"h2": 0, "h3": 0, "h4": 0, "general": 0}
    incident_total = 0
    incident_observed = 0
    for entry in window:
        ann = entry.get("annotation") or {}
        outcome = (ann.get("outcome") or "").lower()
        if outcome and outcome not in _FAILURE_OUTCOMES:
            successes += 1
        primary = ann.get("primary_layer")
        if primary in failure_layers:
            failure_layers[primary] += 1
        if ann.get("incident_count") is not None:
            incident_total += int(ann["incident_count"])
            incident_observed += 1

    return {
        "executions": total,
        "success_rate": successes / total,
        "failure_layers": failure_layers,
        "mean_incident_count": (
            incident_total / incident_observed if incident_observed else None
        ),
    }


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    def _diff(a, b):
        if a is None or b is None:
            return None
        return b - a

    return {
        "success_rate": _diff(before["success_rate"], after["success_rate"]),
        "mean_incident_count": _diff(
            before["mean_incident_count"], after["mean_incident_count"],
        ),
        "failure_layers": {
            layer: after["failure_layers"][layer] - before["failure_layers"][layer]
            for layer in ("h2", "h3", "h4", "general")
        },
    }
