"""LoopSpec — the typed unifying schema for the v0.6.0 loop executor.

Promotes the previously-untyped goal-loop / ralph config dicts into one
struct. ``from_legacy_config`` adapts both legacy shapes so every existing
caller and route keeps passing plain dicts (the runner parses internally).
"""

from __future__ import annotations

from typing import Literal, Optional

import msgspec

BodyKind = Literal["agent_task", "eval_refine"]
ContextPolicy = Literal["carry", "reset"]
GateKind = Literal["test_pass", "metric", "llm_judge"]
GateMode = Literal["off", "every_n", "on_exit"]
SandboxMode = Literal["isolated", "inherit"]


class LoopBody(msgspec.Struct, frozen=True):
    kind: BodyKind
    goal: str
    check_cmd: Optional[str] = None
    judge_backend_kind: str = "claude"
    judge_model_override: Optional[str] = None
    metric_spec: Optional[dict] = None


class QualityGate(msgspec.Struct, frozen=True):
    kind: GateKind
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    comparator: str = ">="
    rubric: Optional[str] = None
    judge_version: Optional[str] = None
    min_confidence: float = 0.0


class LoopGate(msgspec.Struct, frozen=True):
    mode: GateMode = "off"
    n: int = 1


class LoopExit(msgspec.Struct, frozen=True):
    # Quality-gate / convergence first; HARD budgets last (always enforced).
    convergence: bool = True  # Ouroboros verdict-convergence
    stagnation_no_progress_for: int = 0  # 0 = off
    max_iterations: int = 20
    max_wall_seconds: int = 1800
    max_cost_usd: float = 0.0  # 0 = off
    max_tokens: int = 0  # 0 = off (tokens_in+out accumulated)
    quality_gate: Optional[QualityGate] = None


class LoopState(msgspec.Struct, frozen=True):
    context_policy: ContextPolicy = "carry"
    checkpoint: bool = True
    sandbox: SandboxMode = "isolated"
    human_gate: Optional[LoopGate] = None
    # Opt-in: discard a failed iteration's diff (git reset --hard + clean) before
    # the next one, so each iteration's work is provisional until the gate passes.
    # Default off — and skip it for Ralph, where carry-forward-on-fail is the point.
    iteration_rollback: bool = False


class LoopSpec(msgspec.Struct, frozen=True):
    body: LoopBody
    exit: LoopExit
    state: LoopState
    meta_execution_type: str = "goal_loop"

    @staticmethod
    def from_legacy_config(config: dict, *, execution_type: str = "goal_loop") -> "LoopSpec":
        c = config or {}
        if execution_type == "ralph":
            goal = (c.get("task_description") or c.get("goal") or "").strip()
            body = LoopBody(kind="agent_task", goal=goal, check_cmd=c.get("check_cmd"))
            quality_gate = _gate_from_legacy(c)
            exit_ = LoopExit(
                convergence=False,
                stagnation_no_progress_for=int(c.get("no_progress_threshold") or 3),
                max_iterations=int(c.get("max_iterations") or 50),
                max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
                max_cost_usd=_as_float(c.get("max_cost_usd")),
                max_tokens=int(c.get("max_tokens") or 0),
                quality_gate=quality_gate,
            )
            state = LoopState(
                context_policy=c.get("context_policy") or "reset",
                sandbox=c.get("sandbox") or "isolated",
                human_gate=_gate_cfg(c),
            )
            return LoopSpec(body=body, exit=exit_, state=state, meta_execution_type="ralph")

        # goal_loop (default)
        body = LoopBody(
            kind="eval_refine",
            goal=(c.get("goal") or "").strip(),
            check_cmd=c.get("check_cmd"),
            judge_backend_kind=c.get("judge_backend_kind", "claude"),
            judge_model_override=c.get("judge_model_override"),
            metric_spec=c.get("metric_spec"),
        )
        gate = _gate_from_legacy(c) or QualityGate(
            kind="llm_judge",
            rubric=(c.get("quality_gate") or {}).get("rubric"),
            judge_version=(c.get("quality_gate") or {}).get("judge_version"),
            min_confidence=float((c.get("quality_gate") or {}).get("min_confidence") or 0.0),
        )
        exit_ = LoopExit(
            convergence=bool(c.get("ouroboros", True)),
            stagnation_no_progress_for=int(c.get("stagnation_no_progress_for") or 0),
            max_iterations=int(c.get("max_iterations") or 20),
            max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
            max_cost_usd=_as_float(c.get("max_cost_usd")),
            max_tokens=int(c.get("max_tokens") or 0),
            quality_gate=gate,
        )
        state = LoopState(
            context_policy=c.get("context_policy") or "carry",
            sandbox=c.get("sandbox") or "isolated",
            human_gate=_gate_cfg(c),
            iteration_rollback=bool(c.get("iteration_rollback")),
        )
        return LoopSpec(body=body, exit=exit_, state=state, meta_execution_type="goal_loop")


def _gate_cfg(c: dict) -> Optional[LoopGate]:
    hg = c.get("human_gate")
    if isinstance(hg, dict) and hg.get("mode") and hg.get("mode") != "off":
        return LoopGate(mode=hg["mode"], n=int(hg.get("n") or 1))
    return None


def _gate_from_legacy(c: dict) -> Optional[QualityGate]:
    explicit = c.get("quality_gate")
    if isinstance(explicit, dict) and explicit.get("kind"):
        return QualityGate(
            kind=explicit["kind"],
            metric_name=explicit.get("metric_name"),
            threshold=explicit.get("threshold"),
            comparator=explicit.get("comparator", ">="),
            rubric=explicit.get("rubric"),
            judge_version=explicit.get("judge_version"),
            min_confidence=float(explicit.get("min_confidence") or 0.0),
        )
    if c.get("check_cmd"):
        # Preserve any configured rubric alongside the deterministic check so the
        # judge can compose them (tests pass AND rubric satisfied) instead of the
        # rubric being silently dropped whenever a check command exists.
        qg = c.get("quality_gate")
        rubric = qg.get("rubric") if isinstance(qg, dict) else None
        return QualityGate(
            kind="test_pass",
            rubric=rubric,
            judge_version=(qg.get("judge_version") if isinstance(qg, dict) else None),
            min_confidence=float(
                (qg.get("min_confidence") or 0.0) if isinstance(qg, dict) else 0.0
            ),
        )
    ms = c.get("metric_spec")
    if isinstance(ms, dict):
        return QualityGate(
            kind="metric",
            metric_name=ms.get("name"),
            threshold=ms.get("target") if ms.get("target") is not None else ms.get("threshold"),
        )
    return None


def _as_float(v) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
