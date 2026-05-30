"""Phase D: confidence-gated autonomous apply (decision + poller)."""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import Optional  # noqa: F401 — used by harness_evolver import chain

from app.db import harness_evolution as evo_repo
from app.db import project_autonomy_config as autonomy_cfg
from app.models.autonomy_policy import AutonomyDecision, AutonomyPolicy, GateResult
from app.services.harness_evolver import apply_dry_run_round

logger = logging.getLogger(__name__)


def _utc_minus(**kw) -> str:
    return (_dt.datetime.utcnow() - _dt.timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%S")


def _kill_switch_on() -> bool:
    return os.environ.get("AGENTED_AUTONOMY", "1") == "0"


def autonomous_apply_eligible(
    round_row: dict,
    policy: AutonomyPolicy,
    *,
    recent_auto_applies: int,
    recent_within_cooldown: bool,
) -> AutonomyDecision:
    gates: list[GateResult] = []
    entries = ((round_row.get("output_patch") or {}).get("entries")) or []
    verdict = round_row.get("eval_verdict") or {}
    kinds = {e.get("kind") for e in entries}
    has_delete = any(e.get("op") == "delete" for e in entries)
    score = float(verdict.get("score", 0.0))

    gates.append(
        GateResult(
            name="kill_switch",
            passed=not _kill_switch_on(),
            detail="AGENTED_AUTONOMY=0" if _kill_switch_on() else "",
        )
    )
    gates.append(
        GateResult(
            name="enabled",
            passed=bool(policy.enabled),
            detail="" if policy.enabled else "autonomy disabled for project",
        )
    )
    eval_ok = bool(verdict) and bool(verdict.get("passed"))
    gates.append(
        GateResult(
            name="eval_present",
            passed=eval_ok,
            detail="" if eval_ok else "no passing eval verdict",
        )
    )
    conf_ok = score >= policy.confidence_threshold
    gates.append(
        GateResult(
            name="confidence",
            passed=conf_ok,
            detail="" if conf_ok else f"{score} < {policy.confidence_threshold}",
        )
    )
    blast_ok = len(entries) <= policy.max_ops_per_round
    gates.append(
        GateResult(
            name="blast_radius",
            passed=blast_ok,
            detail="" if blast_ok else f"{len(entries)} > {policy.max_ops_per_round}",
        )
    )
    bad_kinds = [k for k in kinds if k not in policy.allowed_kinds]
    gates.append(
        GateResult(
            name="allowed_kinds",
            passed=not bad_kinds,
            detail="" if not bad_kinds else f"disallowed: {bad_kinds}",
        )
    )
    del_block = policy.block_deletes and has_delete
    gates.append(
        GateResult(
            name="block_deletes",
            passed=not del_block,
            detail="patch contains a delete" if del_block else "",
        )
    )
    gates.append(
        GateResult(
            name="cooldown",
            passed=not recent_within_cooldown,
            detail="within cooldown window" if recent_within_cooldown else "",
        )
    )
    rate_ok = recent_auto_applies < policy.rate_limit_per_day
    gates.append(
        GateResult(
            name="rate_limit",
            passed=rate_ok,
            detail="" if rate_ok else f"{recent_auto_applies} >= {policy.rate_limit_per_day}",
        )
    )

    eligible = all(g.passed for g in gates)
    reason = (
        ""
        if eligible
        else "; ".join(f"{g.name}:{g.detail or 'fail'}" for g in gates if not g.passed)
    )
    return AutonomyDecision(eligible=eligible, gates=gates, reason=reason)


def process_project_autonomy(project_id: str) -> list[dict]:
    """Evaluate + auto-apply eligible awaiting_approval rounds for one project."""
    policy = autonomy_cfg.get_policy(project_id)
    if policy is None or not policy.enabled:
        return []
    results: list[dict] = []
    day_cut = _utc_minus(days=1)
    cooldown_cut = _utc_minus(seconds=policy.cooldown_seconds)
    for rnd in evo_repo.list_for_project(project_id, limit=50):
        if rnd.get("status") != "awaiting_approval":
            continue
        if rnd.get("auto_applied") == 1 or rnd.get("auto_apply_blocked_reason"):
            continue
        if not rnd.get("eval_verdict"):
            continue
        entries = ((rnd.get("output_patch") or {}).get("entries")) or []
        if not entries:  # skip 0-entry (no-op) rounds
            continue
        recent = evo_repo.count_recent_auto_applies(project_id, since=day_cut)
        within_cooldown = evo_repo.count_recent_auto_applies(project_id, since=cooldown_cut) > 0
        decision = autonomous_apply_eligible(
            rnd,
            policy,
            recent_auto_applies=recent,
            recent_within_cooldown=within_cooldown,
        )
        reason = {
            "eligible": decision.eligible,
            "gates": [g.model_dump() for g in decision.gates],
            "reason": decision.reason,
            "score": float((rnd.get("eval_verdict") or {}).get("score", 0.0)),
        }
        if decision.eligible:
            try:
                apply_dry_run_round(rnd["id"], auto_applied=True, auto_apply_reason=reason)
                results.append({"round_id": rnd["id"], "action": "auto_applied"})
            except Exception:  # noqa: BLE001
                logger.warning("autonomy: auto-apply failed for %s", rnd["id"], exc_info=True)
                evo_repo.mark_auto_apply_blocked(rnd["id"], {**reason, "error": "apply failed"})
                results.append({"round_id": rnd["id"], "action": "apply_error"})
        else:
            evo_repo.mark_auto_apply_blocked(rnd["id"], reason)
            results.append({"round_id": rnd["id"], "action": "blocked", "reason": decision.reason})
    return results
