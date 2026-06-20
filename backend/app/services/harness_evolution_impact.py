"""Project-scoped A/B impact metrics for applied evolution rounds.

For an ``applied`` round on project P: compares the N executions immediately
preceding the round's start to the N executions immediately following its
finish, *all scoped to project P*. Surfaces success rate, failure-layer
distribution, mean incident count.

These are *observational*, not a controlled A/B — Agented executions run
on whatever triggers naturally fire — so the operator reads them as
directional evidence rather than statistical truth.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db import harness_annotations as annotations_repo
from app.db import harness_evolution as evolution_repo
from app.db import harness_snapshots as snapshots_repo

logger = logging.getLogger(__name__)


_FAILURE_OUTCOMES = frozenset({"failed", "timeout", "interrupted", "cancelled"})


def compute_impact(round_id: str, *, window_size: int = 20) -> dict[str, Any]:
    rnd = evolution_repo.get_round(round_id)
    if rnd is None:
        return {"available": False, "reason": "round not found"}
    if rnd["status"] != "applied":
        return {
            "available": False,
            "reason": f"round not applied (status={rnd['status']!r})",
        }

    project_id = rnd["project_id"]
    started_at = rnd["started_at"]
    finished_at = rnd["finished_at"] or started_at

    before = _gather_window(project_id, before_ts=started_at, limit=window_size)
    after = _gather_window(project_id, after_ts=finished_at, limit=window_size)

    summary_before = _summarize(before)
    summary_after = _summarize(after)

    return {
        "available": True,
        "round_id": round_id,
        "project_id": project_id,
        "window_size": window_size,
        "before": summary_before,
        "after": summary_after,
        "delta": _delta(summary_before, summary_after),
    }


def _gather_window(project_id, *, before_ts=None, after_ts=None, limit=20):
    snaps = snapshots_repo.list_for_project(
        project_id,
        before_ts=before_ts,
        after_ts=after_ts,
        limit=limit,
    )
    enriched = []
    for snap in snaps:
        session_kind = snap.get("session_kind") or "trigger_execution"
        session_id = snap["session_id"]
        enriched.append(
            {
                "session_kind": session_kind,
                "session_id": session_id,
                "annotation": annotations_repo.get_annotation(session_kind, session_id),
                "snapshot_at": snap["created_at"],
                "bundle_hash": snap.get("bundle_hash"),
            }
        )
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
        "mean_incident_count": (incident_total / incident_observed if incident_observed else None),
    }


def _delta(before, after):
    def _diff(a, b):
        if a is None or b is None:
            return None
        return b - a

    return {
        "success_rate": _diff(before["success_rate"], after["success_rate"]),
        "mean_incident_count": _diff(
            before["mean_incident_count"],
            after["mean_incident_count"],
        ),
        "failure_layers": {
            k: after["failure_layers"][k] - before["failure_layers"][k]
            for k in ("h2", "h3", "h4", "general")
        },
    }
