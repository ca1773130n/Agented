"""Hybrid auto-skill gate (Phase 22, REQ-24).

The integration point that ties the signal store (22-01), the detector signals
(22-03), the safety scanner / dedup / provenance guards (22-04), per-project
autonomy policy, and the proven evolver skill-create path together.

Two layers:

- ``evaluate_signal(...) -> GateDecision`` — a PURE function. AUTO iff
  ``occurrence_count >= 3`` within the last 30 days AND
  ``verified_success_count >= 1`` AND the content scanned clean AND dedup is OK
  AND provenance is OK AND the per-project policy is enabled. Anything weaker —
  too few occurrences, unverified, a stale window, a scan failure, a diverged
  provenance hash, or a disabled policy — routes to PROPOSE (operator queue,
  confidence 0.65). A scan failure or diverged provenance DOWNGRADES the AUTO
  candidate to PROPOSE; it never silently REJECTs the whole signal.

- ``convert_signal(signal, *, ...)`` — the effectful driver. On AUTO it emits a
  ``discovered_procedure`` takeaway at confidence 0.9 and creates (or, on a
  dedup hit, patches) the skill via the evolver ``_create_dispatch['skill']`` /
  ``_update_dispatch['skill']`` — the PROVEN path (test_forge_skill_dispatch.py).
  ``create_and_bind_and_materialize`` is deliberately NOT used: "skill" is
  absent from its ``_CREATE_FNS`` (verified at plan time). After create it
  records ``origin_hash`` and marks the signal ``skill_created``. PROPOSE
  produces an operator-queue entry (no skill-create); REJECT is a no-op.

Per-project policy: read ``project_autonomy_config`` for the signal's project
first; fall back to the ``AGENTED_TAKEAWAY_AUTOAPPLY`` env flag only when no
project row exists (REQ-24 "promote env flag to per-project policy").
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

Route = Literal["auto", "propose", "reject"]

# Phase-22 design constants.
_AUTO_OCCURRENCE_MIN = 3
_AUTO_WINDOW_DAYS = 30
_CONF_AUTO = 0.9
_CONF_PROPOSE = 0.65
_EXTRACTOR_VERSION = "repeated_request_gate/1"


@dataclass(frozen=True)
class GateDecision:
    """Routing decision for a repeated-request signal.

    ``route`` is the chosen lane; ``confidence`` is 0.9 for AUTO and 0.65 for
    PROPOSE; ``patch`` is True when a near-duplicate binding exists (the AUTO
    path then patches via ``_update_dispatch`` rather than creating); ``reasons``
    explains a downgrade for the operator queue / audit trail.
    """

    route: Route
    confidence: float
    patch: bool = False
    reasons: tuple[str, ...] = ()


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate_signal(
    *,
    occurrence_count: int,
    verified_success_count: int,
    scan_safe: bool,
    dedup_existing: Optional[dict],
    provenance_ok: bool,
    policy_enabled: bool,
    first_seen_at: str | datetime,
    now: str | datetime | None = None,
) -> GateDecision:
    """Pure routing function. See module docstring for the AUTO conjunction.

    No DB, no IO — every input is passed in. ``patch`` is set whenever
    ``dedup_existing`` is not None, regardless of route, so a PROPOSE on a
    near-duplicate still carries the patch hint for the operator.
    """
    patch = dedup_existing is not None

    now_dt = _parse_ts(now) if now is not None else datetime.now(timezone.utc)
    first_dt = _parse_ts(first_seen_at)
    within_window = (now_dt - first_dt) <= timedelta(days=_AUTO_WINDOW_DAYS)

    reasons: list[str] = []
    if occurrence_count < _AUTO_OCCURRENCE_MIN:
        reasons.append(f"occurrence_count {occurrence_count} < {_AUTO_OCCURRENCE_MIN}")
    if not within_window:
        reasons.append(f"first_seen_at outside {_AUTO_WINDOW_DAYS}-day window")
    if verified_success_count < 1:
        reasons.append("no verified success")
    if not scan_safe:
        reasons.append("scan failed")
    if not provenance_ok:
        reasons.append("provenance diverged")
    if not policy_enabled:
        reasons.append("per-project auto-apply policy disabled")

    if reasons:
        return GateDecision(
            route="propose", confidence=_CONF_PROPOSE, patch=patch, reasons=tuple(reasons)
        )
    return GateDecision(route="auto", confidence=_CONF_AUTO, patch=patch)


# --- effectful driver --------------------------------------------------------


def _auto_apply_policy(project_id: str | None) -> bool:
    """Per-project auto-apply policy with env fallback.

    Read ``project_autonomy_config`` for ``project_id``. If a row exists, honor
    its ``enabled`` flag (and, if ``policy_json`` scopes a ``kinds`` allow-list,
    require ``discovered_procedure`` to be in it). If NO row exists, fall back to
    the ``AGENTED_TAKEAWAY_AUTOAPPLY`` env flag.
    """
    from app.db.connection import get_connection

    row = None
    if project_id is not None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT enabled, policy_json FROM project_autonomy_config WHERE project_id = ?",
                (project_id,),
            ).fetchone()

    if row is None:
        return os.environ.get("AGENTED_TAKEAWAY_AUTOAPPLY", "0") == "1"

    if not bool(row["enabled"]):
        return False

    # Optional kind-scoping via policy_json {"kinds": [...]}.
    try:
        policy = json.loads(row["policy_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        policy = {}
    kinds = policy.get("kinds")
    if isinstance(kinds, list) and kinds:
        return "discovered_procedure" in kinds
    return True


def convert_signal(
    signal: Any,
    *,
    skill_name: str,
    skill_description: str,
    skill_content: str,
    scan_safe: bool,
    dedup_existing: Optional[dict],
    provenance_ok: bool,
    now: str | datetime | None = None,
) -> dict:
    """Drive a signal through the gate and apply the AUTO path.

    Returns a result dict ``{"route", "confidence", "patch", "takeaway_id",
    "asset_id", "reasons"}``. On AUTO: insert a ``discovered_procedure``
    takeaway at confidence 0.9, create (or patch) the skill via the evolver
    dispatch, record the origin hash, and mark the signal ``skill_created``.
    On PROPOSE: an operator-queue entry (no skill-create). On REJECT: no-op.
    """
    from app.db import harness_takeaways
    from app.db.forge_origin import record_origin
    from app.db.repeated_request_signals import mark_skill_created
    from app.services import harness_evolver as ev
    from app.utils.plugin_format import content_hash

    project_id = getattr(signal, "project_id", None)
    decision = evaluate_signal(
        occurrence_count=getattr(signal, "occurrence_count", 0),
        verified_success_count=getattr(signal, "verified_success_count", 0),
        scan_safe=scan_safe,
        dedup_existing=dedup_existing,
        provenance_ok=provenance_ok,
        policy_enabled=_auto_apply_policy(project_id),
        first_seen_at=getattr(signal, "first_seen_at"),
        now=now,
    )

    result: dict = {
        "route": decision.route,
        "confidence": decision.confidence,
        "patch": decision.patch,
        "reasons": list(decision.reasons),
        "takeaway_id": None,
        "asset_id": None,
    }

    if decision.route != "auto":
        # PROPOSE / REJECT: queue for the operator, never create a skill.
        return result

    example_sessions = getattr(signal, "example_session_ids", []) or []
    source_session_id = example_sessions[-1] if example_sessions else None

    takeaway_ids = harness_takeaways.insert_many(
        [
            {
                "session_kind": getattr(signal, "session_kind", "project"),
                "session_id": source_session_id or "repeated-request-gate",
                "project_id": project_id,
                "kind": "discovered_procedure",
                "content": skill_description,
                "confidence": _CONF_AUTO,
                "evidence": {
                    "request_hash": getattr(signal, "request_hash", None),
                    "occurrence_count": getattr(signal, "occurrence_count", 0),
                    "verified_success_count": getattr(signal, "verified_success_count", 0),
                },
                "suggested_target": "skill",
                "suggested_payload": {"name": skill_name},
                "extractor_version": _EXTRACTOR_VERSION,
            }
        ]
    )
    result["takeaway_id"] = takeaway_ids[0] if takeaway_ids else None

    payload = {"description": skill_description, "content": skill_content}
    if decision.patch and dedup_existing is not None:
        asset_id = dedup_existing.get("id")
        ev._update_dispatch["skill"](asset_id=asset_id, payload=payload)
    else:
        asset_id = ev._create_dispatch["skill"](
            name=skill_name, payload=payload, project_id=project_id
        )
    result["asset_id"] = asset_id

    if asset_id is not None:
        record_origin(
            str(asset_id),
            "skill",
            origin_hash=content_hash(skill_content),
            source_session_id=source_session_id,
        )
    mark_skill_created(getattr(signal, "request_hash"))

    return result
