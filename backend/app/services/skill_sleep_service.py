"""Skill-Sleep: SkillOpt's validation gate ported onto Agented.

SkillOpt (arXiv:2605.23904) treats a skill document as the *trainable text-space
state of a frozen agent* and accepts an edit only when it strictly improves a
held-out validation score. Agented trains nothing and has no labeled dataset, so
this is the honest port of that ONE load-bearing invariant — the
strict-improvement, self-grading-forbidden GATE — onto Agented's own infra:

  * the "frozen agent" is the opaque claude/codex subprocess;
  * the trainable text is ``.claude/skills/<name>/SKILL.md``;
  * the validation score is the **blind LLM judge** already used by
    ``AnswerEvalService`` (the prompt never names which arm it scores);
  * the "held-out split" is a seed-partitioned, run-disjoint question set
    (``build_question_set(partition="eval")``) — an honest *proxy*, not a
    frozen labeled VAL set (see docs/research/skillopt-integration.md §7).

Discipline carried over from SkillOpt / Agented's existing gate:
  * **strict improvement** — accept iff the candidate's composite score is
    strictly greater than the current body's;
  * **fail CLOSED** — any judge/infra error rejects (never auto-accepts);
  * **abstain on a thin corpus** — when ``corpus_health`` is below
    ``AGENTED_RAG_MIN_CORPUS`` the proxy is meaningless, so reject without
    judging.

The judge/answer LLM calls are injected seams (``answer_call`` / ``judge_call``)
so tests run with zero subprocesses, exactly like ``AnswerEvalService``.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

LLMCall = Callable[[list[dict]], str]

# Axes the blind judge scores; the composite is their mean.
_AXES = ("groundedness", "sufficiency", "quality")


def _skill_context_message(body: str) -> dict:
    """System message that puts a skill body in the agent's context.

    This is the *only* difference between arm A and arm B — so the judge's
    score difference is attributable to the skill edit.
    """
    return {
        "role": "system",
        "content": (
            "You have access to the following project skill. Use it to answer "
            "the user's question.\n\n" + (body or "")
        ),
    }


def _composite(scores: dict) -> float:
    return sum(scores.get(a, 0.0) for a in _AXES) / len(_AXES)


class SkillSleepGate:
    """Validation gate that decides whether a candidate skill body is adopted."""

    @staticmethod
    def evaluate_candidate(
        project_id: str,
        *,
        skill_name: str,
        current_body: str,
        candidate_body: str,
        skill_id: Optional[int] = None,
        answer_call: Optional[LLMCall] = None,
        judge_call: Optional[LLMCall] = None,
        n: int = 6,
        seed: int = 0,
        judge_backend: str = "claude",
        min_corpus: Optional[int] = None,
    ) -> dict:
        """Blind-judge current vs candidate skill body; accept only on strict gain.

        Returns a verdict dict:
            {status, accepted, current_score, candidate_score, delta,
             question_count, reason, run_id}
        ``status`` ∈ accepted | rejected | abstained | failed.
        """
        from app.db import skill_sleep
        from app.services.answer_eval_service import (
            AnswerEvalService,
            _build_default_llm_call,
            _build_judge_prompt,
            _parse_judge_response,
        )
        from app.services.answer_pipeline_service import corpus_health

        run_id = skill_sleep.create_run(
            project_id,
            skill_name,
            skill_id=skill_id,
            partition_seed=seed,
            judge_backend=judge_backend,
        )

        def _verdict(status: str, *, cur=None, cand=None, qc=0, reason=None) -> dict:
            skill_sleep.finalize_run(
                run_id,
                status=status,
                current_score=cur,
                candidate_score=cand,
                question_count=qc,
                candidate_body=candidate_body if status == "accepted" else None,
                reason=reason,
            )
            return {
                "run_id": run_id,
                "status": status,
                "accepted": status == "accepted",
                "current_score": cur,
                "candidate_score": cand,
                "delta": (cand - cur) if (cur is not None and cand is not None) else None,
                "question_count": qc,
                "reason": reason,
            }

        # --- Abstain on a thin corpus: the held-out proxy is meaningless. ---
        try:
            health = corpus_health(project_id, min_items=min_corpus)
        except Exception:
            logger.warning("skill-sleep: corpus_health failed for %s", project_id, exc_info=True)
            return _verdict("failed", reason="corpus_health error (fail-closed)")
        if not health.get("healthy"):
            return _verdict(
                "abstained",
                reason=f"thin corpus ({health.get('total')} < {health.get('min_items')} items)",
            )

        # --- Held-out eval partition (disjoint from the train half by seed). ---
        questions = AnswerEvalService.build_question_set(
            project_id, n=n, partition="eval", seed=seed
        )
        if not questions:
            return _verdict("abstained", reason="no held-out questions available")

        answer_call = answer_call or _build_default_llm_call(judge_backend)
        judge_call = judge_call or _build_default_llm_call(judge_backend)

        # --- Score each arm; fail CLOSED on any error. ---
        try:
            cur_scores: list[float] = []
            cand_scores: list[float] = []
            for q in questions:
                cur_ans = answer_call(
                    [_skill_context_message(current_body), {"role": "user", "content": q}]
                )
                cand_ans = answer_call(
                    [_skill_context_message(candidate_body), {"role": "user", "content": q}]
                )
                # Blind: the judge prompt names neither arm (reused verbatim).
                cur_scores.append(
                    _composite(
                        _parse_judge_response(
                            judge_call(
                                [{"role": "user", "content": _build_judge_prompt(q, cur_ans, [])}]
                            )
                        )
                    )
                )
                cand_scores.append(
                    _composite(
                        _parse_judge_response(
                            judge_call(
                                [{"role": "user", "content": _build_judge_prompt(q, cand_ans, [])}]
                            )
                        )
                    )
                )
        except Exception:
            logger.warning(
                "skill-sleep: scoring failed for %s/%s", project_id, skill_name, exc_info=True
            )
            return _verdict("failed", reason="judge/answer error (fail-closed)")

        if not cur_scores or not cand_scores:
            return _verdict("rejected", reason="no scores produced")

        cur_mean = sum(cur_scores) / len(cur_scores)
        cand_mean = sum(cand_scores) / len(cand_scores)
        qc = len(questions)

        # Strict improvement (SkillOpt's cand > current on the held-out score).
        if cand_mean > cur_mean:
            return _verdict(
                "accepted",
                cur=cur_mean,
                cand=cand_mean,
                qc=qc,
                reason="candidate strictly improved held-out score",
            )
        return _verdict(
            "rejected",
            cur=cur_mean,
            cand=cand_mean,
            qc=qc,
            reason="candidate did not strictly improve held-out score",
        )
