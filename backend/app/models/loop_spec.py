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


class LoopBody(msgspec.Struct, frozen=True):
    kind: BodyKind
    goal: str
    check_cmd: Optional[str] = None
    judge_backend_kind: str = "claude"
    judge_model_override: Optional[str] = None
    metric_spec: Optional[dict] = None


class LoopExit(msgspec.Struct, frozen=True):
    # Quality-gate / convergence first; HARD budgets last (always enforced).
    convergence: bool = True                  # Ouroboros verdict-convergence
    stagnation_no_progress_for: int = 0       # 0 = off
    max_iterations: int = 20
    max_wall_seconds: int = 1800
    max_cost_usd: float = 0.0                  # 0 = off
    max_tokens: int = 0                        # 0 = off (tokens_in+out accumulated)


class LoopState(msgspec.Struct, frozen=True):
    context_policy: ContextPolicy = "carry"
    checkpoint: bool = True


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
            exit_ = LoopExit(
                convergence=False,
                stagnation_no_progress_for=int(c.get("no_progress_threshold") or 3),
                max_iterations=int(c.get("max_iterations") or 50),
                max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
                max_cost_usd=_as_float(c.get("max_cost_usd")),
                max_tokens=int(c.get("max_tokens") or 0),
            )
            state = LoopState(context_policy=c.get("context_policy") or "reset")
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
        exit_ = LoopExit(
            convergence=bool(c.get("ouroboros", True)),
            stagnation_no_progress_for=int(c.get("stagnation_no_progress_for") or 0),
            max_iterations=int(c.get("max_iterations") or 20),
            max_wall_seconds=int(c.get("max_wall_seconds") or 1800),
            max_cost_usd=_as_float(c.get("max_cost_usd")),
            max_tokens=int(c.get("max_tokens") or 0),
        )
        state = LoopState(context_policy=c.get("context_policy") or "carry")
        return LoopSpec(body=body, exit=exit_, state=state, meta_execution_type="goal_loop")


def _as_float(v) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
