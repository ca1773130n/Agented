"""AnswerEvalService — baseline-vs-pipeline evaluation with LLM-as-blind-judge.

Implements:
- build_question_set(project_id, n) — deterministic, project-scoped
- run_eval(project_id, *, n, judge_backend, llm_call, pipeline_llm_call, run_id) -> int

All LLM calls are injected via seams (llm_call / pipeline_llm_call) so tests
can stub them without spawning subprocesses. The default wraps stream_llm_response
exactly like AnswerPipelineService._default_llm_call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _stable_bucket(seed: int, question: str) -> int:
    """Process-stable 2-way bucket for a question (Python's hash() is salted).

    Used to split a question pool into disjoint train/eval halves
    deterministically across runs and processes.
    """
    digest = hashlib.sha256(f"{seed}|{question}".encode()).hexdigest()
    return int(digest, 16) % 2


def _partition_pool(pool: list[str], *, n: int, partition: str, seed: int) -> list[str]:
    """Return up to n questions from the requested half of a seed-split universe.

    The universe is the real question pool plus any generic fallbacks not
    already in it (so thin corpora still split). ``train`` is bucket 0,
    ``eval`` is bucket 1 — complementary, so the two halves are disjoint by
    construction.
    """
    universe = list(pool) + [g for g in _GENERIC_QUESTIONS if g not in pool]
    want = 0 if partition == "train" else 1
    half = [q for q in universe if _stable_bucket(seed, q) == want]
    return half[:n]


LLMCall = Callable[[list[dict]], str]  # messages -> collected text

# ---------------------------------------------------------------------------
# Forgiving judge-response parser (mirror goal_judge_service._parse_judge_json)
# ---------------------------------------------------------------------------

_OBJ_BLOB_RE = re.compile(r"\{[\s\S]*\}")


def _parse_judge_response(text: str) -> dict:
    """Parse {groundedness, sufficiency, quality, reason} from LLM text.

    Each axis is 0..1. Falls back to zeros + reason='error' on any failure.
    """
    try:
        # Try direct parse first
        data = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        # Try extracting first {...} blob
        m = _OBJ_BLOB_RE.search(text)
        if m:
            try:
                data = json.loads(m.group(0))
            except (json.JSONDecodeError, ValueError):
                data = {}
        else:
            data = {}

    def _clamp(v) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    return {
        "groundedness": _clamp(data.get("groundedness", 0.0)),
        "sufficiency": _clamp(data.get("sufficiency", 0.0)),
        "quality": _clamp(data.get("quality", 0.0)),
        "reason": str(data.get("reason", data.get("reasoning", ""))),
    }


# ---------------------------------------------------------------------------
# Question-set builder
# ---------------------------------------------------------------------------

# Generic fallback questions when corpus is sparse
_GENERIC_QUESTIONS = [
    "What is the overall architecture of this project?",
    "What are the main components and how do they interact?",
    "What is the deployment process for this project?",
    "How are errors and failures handled?",
    "What monitoring and observability is in place?",
    "How are database migrations managed?",
    "What are the main configuration options?",
    "How is authentication and authorization implemented?",
]


def _project_execution_ids(project_id: str) -> set[str]:
    """Return the set of execution_ids belonging to a project (mirrors answer_pipeline_service)."""
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT e.execution_id
                   FROM execution_logs e
                   JOIN project_paths p ON p.trigger_id = e.trigger_id
                   WHERE p.project_id = ?""",
                (project_id,),
            ).fetchall()
        return {r["execution_id"] for r in rows}
    except Exception:
        logger.debug("_project_execution_ids failed for %s", project_id, exc_info=True)
        return set()


class AnswerEvalService:
    """Baseline-vs-pipeline answer quality evaluator."""

    @staticmethod
    def build_question_set(
        project_id: str,
        n: int = 8,
        *,
        partition: Optional[str] = None,
        seed: int = 0,
    ) -> list[str]:
        """Build a deterministic, project-scoped question set of at most n items.

        Sources (in priority order):
        1. harness_kg_signals questions (already project-keyed)
        2. Execution prompt first lines (project-scoped via _project_execution_ids JOIN)
        3. Session takeaway content-derived questions
        4. Generic fallback questions (padded to reach n)

        The final list is sorted + sliced to guarantee determinism.

        ``partition`` (SkillOpt held-out split): when ``"train"`` or ``"eval"``,
        the deduped pool (plus generics) is split into two disjoint halves by a
        process-stable hash keyed on ``seed``, and up to n items of the
        requested half are returned. ``None`` (default) keeps the historical
        top-n behavior unchanged.
        """
        questions: list[str] = []

        # --- Source 1: kg signals ---
        try:
            from app.db.harness_kg_signals import list_signals

            signals = list_signals(project_id, limit=n * 3)
            for sig in signals:
                q = sig.get("question", "").strip()
                if q and q not in questions:
                    questions.append(q)
        except Exception:
            logger.debug("build_question_set: kg_signals failed for %s", project_id, exc_info=True)

        # --- Source 2: execution prompts (project-scoped) ---
        try:
            from app.db.execution_logs import get_execution_logs_filtered

            allowed_ids = _project_execution_ids(project_id)
            if allowed_ids:
                # get_execution_logs_filtered is global — we filter by allowed_ids
                logs = get_execution_logs_filtered(limit=n * 5)
                seen_prompts: set[str] = set()
                for log in logs:
                    eid = log.get("execution_id", "")
                    if eid not in allowed_ids:
                        continue
                    prompt = (log.get("prompt") or "").strip()
                    if not prompt:
                        continue
                    # Use the first line as a question stub
                    first_line = prompt.split("\n")[0].strip()
                    if not first_line or first_line in seen_prompts:
                        continue
                    seen_prompts.add(first_line)
                    # Convert to question form if not already
                    if not first_line.endswith("?"):
                        first_line = first_line + "?"
                    if first_line not in questions:
                        questions.append(first_line)
        except Exception:
            logger.debug(
                "build_question_set: execution_logs failed for %s", project_id, exc_info=True
            )

        # --- Source 3: takeaway content ---
        try:
            from app.db.harness_takeaways import list_for_project

            takeaways = list_for_project(project_id, limit=n * 2)
            for tw in takeaways:
                content = (tw.get("content") or tw.get("takeaway") or "").strip()
                if not content:
                    continue
                # Use first sentence as a question
                first_sentence = content.split(".")[0].strip()
                if first_sentence and len(first_sentence) > 10:
                    q = first_sentence if first_sentence.endswith("?") else first_sentence + "?"
                    if q not in questions:
                        questions.append(q)
        except Exception:
            logger.debug("build_question_set: takeaways failed for %s", project_id, exc_info=True)

        # Deduped, deterministic pool (pre-slice) — shared by both code paths.
        pool = sorted(set(questions))

        if partition in ("train", "eval"):
            return _partition_pool(pool, n=n, partition=partition, seed=seed)

        # Default (unchanged): top-n, padded with generics if short.
        result = pool[:n]
        if len(result) < n:
            for gq in _GENERIC_QUESTIONS:
                if gq not in result:
                    result.append(gq)
                if len(result) >= n:
                    break

        return result[:n]

    @staticmethod
    def run_eval(
        project_id: str,
        *,
        n: int = 8,
        judge_backend: str = "claude",
        llm_call: Optional[LLMCall] = None,
        pipeline_llm_call: Optional[LLMCall] = None,
        run_id: Optional[int] = None,
    ) -> int:
        """Run the baseline-vs-pipeline evaluation.

        Parameters
        ----------
        project_id:          Project to evaluate.
        n:                   Number of questions to evaluate.
        judge_backend:       LLM backend name for the judge prompt.
        llm_call:            Test seam for baseline LLM + judge calls. When None,
                             uses _default_llm_call built from judge_backend.
        pipeline_llm_call:   Test seam for pipeline answer generation. When None,
                             also uses _default_llm_call.
        run_id:              Pre-allocated run id (from the async route). When None,
                             creates a new run — ONE owner per run, no orphans.

        Returns
        -------
        run_id (int)
        """
        from app.db.answer_eval import create_run

        # --- Build LLM call defaults ---
        if llm_call is None:
            llm_call = _build_default_llm_call(judge_backend)
        if pipeline_llm_call is None:
            pipeline_llm_call = _build_default_llm_call(judge_backend)

        # --- ONE owner per run ---
        if run_id is None:
            run_id = create_run(project_id, judge_backend=judge_backend)

        try:
            return AnswerEvalService._run_eval_body(
                project_id,
                run_id=run_id,
                n=n,
                llm_call=llm_call,
                pipeline_llm_call=pipeline_llm_call,
                judge_backend=judge_backend,
            )
        except Exception:
            # A fatal error before finalize must not leave the run 'running'
            # forever (codex PR review P2) — mark terminal and re-raise.
            try:
                from app.db.answer_eval import fail_run

                fail_run(run_id)
            except Exception:
                logger.warning("could not mark run %d failed", run_id, exc_info=True)
            raise

    @staticmethod
    def _run_eval_body(
        project_id: str,
        *,
        run_id: int,
        n: int,
        llm_call,
        pipeline_llm_call,
        judge_backend: str,
    ) -> int:
        from app.db.answer_eval import finalize_run, record_result
        from app.services.answer_pipeline_service import gather_context

        questions = AnswerEvalService.build_question_set(project_id, n=n)

        baseline_scores: list[dict] = []
        pipeline_scores: list[dict] = []

        for question in questions:
            # ---- Arm A: baseline (plain LLM, no RAG context) ----
            try:
                baseline_answer = llm_call(
                    [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": question},
                    ]
                )
            except Exception:
                logger.debug("baseline llm_call failed for question %r", question, exc_info=True)
                baseline_answer = None

            # ---- Arm B: pipeline (RAG context injected, unless the gate suppresses) ----
            pipeline_injected = False
            try:
                rag = gather_context(
                    project_id,
                    question,
                    llm_call=pipeline_llm_call,
                    deadline_seconds=90,
                )
                pipeline_injected = bool(rag.get("injected"))
                if pipeline_injected:
                    pipeline_messages: list[dict] = [
                        {"role": "system", "content": "You are a helpful assistant."},
                        rag["context_message"],
                        {"role": "user", "content": question},
                    ]
                    pipeline_answer = pipeline_llm_call(pipeline_messages)
                    pipeline_sources = [
                        f"{c.source}:{c.provenance_key}" for c in rag.get("chunks", [])
                    ]
                else:
                    # The injection gate suppressed retrieval, so the pipeline's
                    # actual production behavior on this question IS a plain
                    # baseline turn. Model that faithfully — reuse the baseline
                    # answer so a suppressed question contributes a true 0 delta
                    # rather than arm-sampling noise (two independent samples of
                    # the same prompt would otherwise diverge under a noisy
                    # judge and masquerade as a pipeline effect).
                    pipeline_answer = baseline_answer
                    pipeline_sources = []
            except Exception:
                logger.debug("pipeline arm failed for question %r", question, exc_info=True)
                pipeline_answer = None
                pipeline_sources = []

            # ---- Judge: blind evaluation (prompt NEVER names the arm) ----
            baseline_eval = _judge_and_record(
                run_id, question, "baseline", baseline_answer, [], llm_call
            )
            baseline_scores.append(baseline_eval)

            if (
                not pipeline_injected
                and pipeline_answer is not None
                and pipeline_answer == baseline_answer
            ):
                # Suppressed → identical to baseline by construction; reuse the
                # baseline judgment (exact 0 delta, one fewer judge call).
                record_result(
                    run_id,
                    question=question,
                    arm="pipeline",
                    answer_text=pipeline_answer,
                    scores=baseline_eval,
                    judge_reason=baseline_eval.get("reason"),
                    tokens=None,
                    cost_usd=None,
                )
                pipeline_scores.append(baseline_eval)
            else:
                pipeline_scores.append(
                    _judge_and_record(
                        run_id, question, "pipeline", pipeline_answer, pipeline_sources, llm_call
                    )
                )

        # ---- Finalize: compute per-arm means + deltas ----
        def _mean(scores: list[dict], key: str) -> Optional[float]:
            vals = [s[key] for s in scores if key in s]
            return sum(vals) / len(vals) if vals else None

        b_g = _mean(baseline_scores, "groundedness")
        b_s = _mean(baseline_scores, "sufficiency")
        b_q = _mean(baseline_scores, "quality")
        p_g = _mean(pipeline_scores, "groundedness")
        p_s = _mean(pipeline_scores, "sufficiency")
        p_q = _mean(pipeline_scores, "quality")

        def _delta(p, b):
            if p is not None and b is not None:
                return p - b
            return None

        aggregates = {
            "baseline_groundedness": b_g,
            "baseline_sufficiency": b_s,
            "baseline_quality": b_q,
            "pipeline_groundedness": p_g,
            "pipeline_sufficiency": p_s,
            "pipeline_quality": p_q,
            "delta_groundedness": _delta(p_g, b_g),
            "delta_sufficiency": _delta(p_s, b_s),
            "delta_quality": _delta(p_q, b_q),
        }
        finalize_run(run_id, aggregates=aggregates, question_count=len(questions))

        return run_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _judge_and_record(run_id, question, arm, answer, sources, llm_call) -> dict:
    """Blind-judge one arm's answer and persist the result row. Returns the
    scores dict (zeros + reason='error' on any failure, still recorded)."""
    from app.db.answer_eval import record_result

    try:
        if answer is None:
            raise ValueError("no answer generated")
        judge_prompt = _build_judge_prompt(question, answer, sources)
        judge_text = llm_call([{"role": "user", "content": judge_prompt}])
        scores = _parse_judge_response(judge_text)
        record_result(
            run_id,
            question=question,
            arm=arm,
            answer_text=answer,
            scores=scores,
            judge_reason=scores.get("reason"),
            tokens=None,
            cost_usd=None,
        )
        return scores
    except Exception:
        logger.debug("judge failed for arm=%s question=%r", arm, question, exc_info=True)
        zero_scores = {"groundedness": 0.0, "sufficiency": 0.0, "quality": 0.0}
        record_result(
            run_id,
            question=question,
            arm=arm,
            answer_text=answer,
            scores=zero_scores,
            judge_reason="error",
            tokens=None,
            cost_usd=None,
        )
        return zero_scores


def _build_default_llm_call(backend: str = "claude") -> LLMCall:
    """Build the default LLM call wrapping stream_llm_response."""

    def _call(messages: list[dict]) -> str:
        from app.services.conversation_streaming import stream_llm_response

        chunks = []
        for token in stream_llm_response(messages, model=None, backend=backend):
            if isinstance(token, str):
                chunks.append(token)
        return "".join(chunks)

    return _call


def _build_judge_prompt(question: str, answer: str, sources: list[str]) -> str:
    """Build a BLIND judge prompt — never names the arm.

    The judge sees only: the question, the answer, and available sources.
    Returns JSON {groundedness, sufficiency, quality, reason} each 0..1.
    """
    sources_section = ""
    if sources:
        sources_section = "\n\nAvailable source references:\n" + "\n".join(
            f"- {s}" for s in sources[:20]
        )

    return f"""You are an impartial quality evaluator. Rate the following answer to a question.

Question: {question}

Answer: {answer}{sources_section}

Evaluate the answer on three axes (each 0.0 to 1.0):
- groundedness: Is the answer factually grounded and not hallucinated?
- sufficiency: Does the answer fully address the question?
- quality: Is the answer clear, well-structured, and useful?

Respond with ONLY a JSON object (no other text):
{{"groundedness": <0-1>, "sufficiency": <0-1>, "quality": <0-1>, "reason": "<brief explanation>"}}"""
