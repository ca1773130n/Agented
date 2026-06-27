"""Goal-loop judge service (v0.7.74).

Two judging modes, one entry point:

* **Deterministic** — operator-supplied shell command run in the
  project cwd. Exit 0 → met. Anything else → not met. Stdout
  captured for the audit log.
* **LLM judge** — when no command is supplied (or as a sanity
  layer on stale "not met" streaks), fire a tiny chat completion
  asking "given this goal and this assistant turn, is the goal
  met?" with a structured JSON response.

The LLM path supports ALL FOUR backends Agented manages:
``claude`` / ``codex`` / ``gemini`` / ``opencode``. Routing goes
through CLIProxyAPI's OpenAI-compatible endpoint which serves all
four kinds — caller picks via ``backend_kind`` and (optionally)
overrides the model name. See
``feedback_llm_features_support_all_backends`` for the project-
wide rule.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import httpx

from app.config import AUTORESEARCH_KERNEL_ENABLED

from .cliproxy_manager import CLIProxyManager

if TYPE_CHECKING:
    from app.models.loop_spec import QualityGate

# autoresearch_core is imported lazily inside the flag-guarded kernel branch
# (see judge()), so a default-OFF deployment has no hard import dependency on
# the editable sibling package — the module imports identically whether or not
# autoresearch-core is present.

logger = logging.getLogger(__name__)


# Per-backend default judge model. Each picks the cheapest /
# fastest small model that can answer a yes/no question — the
# judge call is fire-and-forget, not where to spend operator
# dollars. ``auto`` lets CLIProxyAPI route to whatever the
# proxy considers default for that backend's accounts.
DEFAULT_JUDGE_MODEL = {
    # FALLBACK only — the PRIMARY source is
    # ``ModelDiscoveryService.cheap_model_for(kind)`` (live CLIProxyAPI catalog),
    # so ids never go stale. Used only when discovery is unavailable. Exact
    # catalog ids verified live (the "claude-haiku-4-5" / "o4-mini" /
    # "gemini-2.5-flash" aliases 502 "unknown provider"). gemini creds separately 401.
    "claude": "claude-haiku-4-5-20251001",
    "codex": "gpt-5.4-mini",
    "gemini": "gemini-3.1-flash-lite-preview",
    "opencode": "auto",
}

# How long to wait for the deterministic check before giving up.
# Operators should keep check commands fast (a test command's first
# few seconds is enough signal); a stuck check shouldn't hang the
# loop indefinitely.
_CHECK_TIMEOUT_SECONDS = 30

# Hard cap on judge-prompt input size. Claude turns can be long; we
# truncate to keep the judge call cheap. The judge only needs the
# tail of the assistant's reply to assess progress — earlier text
# is in the conversation history (which the judge doesn't see, by
# design — it judges the latest turn against the goal, not the full
# transcript).
_MAX_TURN_TEXT_CHARS = 8 * 1024


# Judge prompt template. Asks for a strict JSON response so we can
# parse without going through the model's natural-language layer.
# Forgiveness is built into the parser, not the prompt.
_JUDGE_SYSTEM = (
    "You are a strict goal-judging assistant. Read the goal and the "
    "agent's latest turn. Decide if the goal is met. Reply ONLY with "
    'a JSON object: {"met": true|false, "reason": "...", '
    '"confidence": 0.0-1.0}. '
    'The "confidence" is your certainty in the verdict (0–1) and is '
    "optional — omit it if unsure and it defaults to fully confident. "
    "Be concise — the reason is one sentence."
)

_JUDGE_USER_TEMPLATE = "Goal: {goal}\n\nLatest agent turn:\n---\n{turn}\n---\n\nIs the goal met?"


# v0.7.86 — Ouroboros-mode judge prompt. Used when the iteration
# emitted a hypothesis + predicted outcome the judge can score
# against. Output adds a 4-state verdict alongside the legacy
# met/not-met so the runner doesn't have to change shape — the
# extra field is opt-in for callers that read it.
_OUROBOROS_JUDGE_SYSTEM = (
    "You are a strict goal-judging assistant operating under the "
    "Ouroboros pattern. Compare the agent's actual outcome against "
    "its stated hypothesis and predicted outcome. Reply ONLY with a "
    'JSON object: {"met": true|false, "verdict": '
    '"confirmed"|"partial"|"falsified"|"unknown", '
    '"reason": "..."}. '
    'Use "confirmed" when actual matches predicted; "partial" '
    'when some but not all predictions held; "falsified" when the '
    'hypothesis was tested and failed; "unknown" when the agent '
    "didn't produce enough evidence to score. Reason is one sentence."
)

_OUROBOROS_JUDGE_USER_TEMPLATE = (
    "Goal: {goal}\n\n"
    "Hypothesis: {hypothesis}\n"
    "Predicted outcome: {predicted_outcome}\n\n"
    "Latest agent turn:\n---\n{turn}\n---\n\n"
    "Score the hypothesis against the actual turn."
)


@dataclass
class JudgeVerdict:
    """Outcome of one judging round.

    ``source`` distinguishes deterministic check, LLM judge, and
    cap-driven termination so the iteration row in
    ``goal_loop_iterations`` faithfully records which path decided
    the iteration's fate.

    v0.7.86 — ``ouroboros_verdict`` is the 4-state verdict
    (``confirmed`` / ``partial`` / ``falsified`` / ``unknown``)
    populated when the judge runs in Ouroboros mode (a hypothesis +
    predicted outcome were supplied). ``None`` when the judge ran
    in the legacy binary mode so existing callers don't see the
    field unless they opted in.
    """

    met: bool
    source: str
    reason: str
    stdout: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    ouroboros_verdict: Optional[str] = None
    metric_spec: Optional[dict] = None
    confidence: float = 1.0
    judge_version: Optional[str] = None
    kernel_record: Optional[object] = (
        None  # transient autoresearch_core.VerdictRecord; not persisted
    )


class GoalJudgeService:
    """Stateless — call ``judge()`` per iteration."""

    @classmethod
    def judge(
        cls,
        goal: str,
        last_assistant_text: str,
        *,
        check_cmd: Optional[str] = None,
        cwd: Optional[str] = None,
        backend_kind: str = "claude",
        model_override: Optional[str] = None,
        hypothesis: Optional[str] = None,
        predicted_outcome: Optional[str] = None,
        metric_spec: Optional[dict] = None,
        quality_gate: Optional["QualityGate"] = None,
        sandbox: str = "isolated",
    ) -> JudgeVerdict:
        """v0.7.86 — when both ``hypothesis`` and ``predicted_outcome``
        are supplied, the LLM judge runs in Ouroboros mode and
        returns a 4-state ``ouroboros_verdict`` alongside the
        binary ``met``. Deterministic checks ignore Ouroboros
        inputs — the operator's shell command is the source of
        truth there.

        v0.7.88 — when ``AUTORESEARCH_KERNEL_ENABLED`` and ``metric_spec``
        are both set, the kernel is the authoritative judge: it parses
        ``__RESULT__`` from the agent turn and compares against target.
        This branch ALWAYS returns — it never falls through to check_cmd
        (shell=True) or the LLM judges.
        """
        if AUTORESEARCH_KERNEL_ENABLED and metric_spec is not None:
            # metric_spec is authoritative — this branch ALWAYS returns; it never
            # falls through to check_cmd (shell=True) or the LLM judges.
            # Lazy import so flag-off deployments don't require the package.
            try:
                from autoresearch_core import (
                    ExperimentResult,
                    MetricSpec,
                    measure,
                    parse_metrics_line,
                    validate_metric_spec,
                )
            except ImportError as exc:
                logger.error("autoresearch-core unavailable but kernel enabled: %s", exc)
                return JudgeVerdict(
                    met=False,
                    source="kernel",
                    reason=f"kernel unavailable: {exc}",
                    metric_spec=metric_spec,
                )
            try:
                spec = MetricSpec(**metric_spec)
                validate_metric_spec(spec)
            except (TypeError, ValueError) as exc:
                return JudgeVerdict(
                    met=False,
                    source="kernel",
                    reason=f"invalid metric_spec: {exc}",
                    metric_spec=metric_spec,
                )
            rec = measure(
                spec, ExperimentResult(metrics=parse_metrics_line(last_assistant_text), exit_code=0)
            )
            return JudgeVerdict(
                met=(rec.verdict == "supported"),
                source="kernel",
                reason=rec.detail,
                metric_spec=metric_spec,
                kernel_record=rec,
                stdout=json.dumps(
                    {
                        "verdict": rec.verdict,
                        "evidence_level": rec.evidence_level,
                        "strategy": rec.strategy,
                        "detail": rec.detail,
                    }
                ),
            )
        if check_cmd:
            return cls._run_deterministic(check_cmd, cwd, sandbox=sandbox)
        from app.services.model_discovery_service import ModelDiscoveryService

        model = (
            model_override
            or ModelDiscoveryService.cheap_model_for(backend_kind)
            or DEFAULT_JUDGE_MODEL.get(backend_kind, "auto")
        )
        if hypothesis and predicted_outcome:
            return cls._run_ouroboros_judge(
                goal, last_assistant_text, hypothesis, predicted_outcome, backend_kind, model
            )
        return cls._run_llm_judge(
            goal, last_assistant_text, backend_kind, model, quality_gate=quality_gate
        )

    # -----------------------------------------------------------------
    # Deterministic check
    # -----------------------------------------------------------------

    @staticmethod
    def _run_deterministic(
        check_cmd: str, cwd: Optional[str], *, sandbox: str = "isolated"
    ) -> JudgeVerdict:
        # Both paths run through the hardened sandbox_eval runner (scrubbed env +
        # process-group SIGKILL on timeout). ``isolated`` (default, F9) grades
        # against a throwaway snapshot; ``inherit`` (escape hatch) runs in the
        # agent's cwd but STILL scrubs the env so secrets don't leak into the
        # operator's check_cmd.
        from .sandbox_eval import run_check_inplace, run_isolated_check

        if sandbox == "isolated":
            r = run_isolated_check(check_cmd, cwd or ".", timeout=_CHECK_TIMEOUT_SECONDS)
        else:
            r = run_check_inplace(check_cmd, cwd or ".", timeout=_CHECK_TIMEOUT_SECONDS)
        returncode = r.returncode
        stdout = (r.stdout or "")[-4096:]  # tail-cap for storage
        # Fold stderr into the captured trace on failure so tracebacks / compiler
        # errors (which land on stderr, not stdout) survive into the self-debug
        # feedback loop — the next turn fixes THIS error instead of re-deriving it.
        err_tail = (r.stderr or "").strip()
        fail_trace = stdout
        if err_tail:
            fail_trace = (f"{stdout}\n[stderr]\n{err_tail}" if stdout else err_tail)[-4096:]
        if returncode == 124:
            return JudgeVerdict(
                met=False,
                source="deterministic",
                reason=f"check timed out after {_CHECK_TIMEOUT_SECONDS}s",
                stdout=fail_trace,
                confidence=0.0,
            )
        if returncode == 127:
            return JudgeVerdict(
                met=False,
                source="deterministic",
                reason=f"check failed to run: {(r.stderr or '').strip()[:200]}",
                stdout=fail_trace,
                confidence=0.0,
            )
        if returncode == 0:
            return JudgeVerdict(
                met=True,
                source="deterministic",
                reason="check command exited 0",
                stdout=stdout,
                confidence=1.0,
            )
        return JudgeVerdict(
            met=False,
            source="deterministic",
            reason=f"check exited {returncode}",
            stdout=fail_trace,
            confidence=0.0,
        )

    # -----------------------------------------------------------------
    # LLM judge
    # -----------------------------------------------------------------

    @classmethod
    def _run_llm_judge(
        cls,
        goal: str,
        last_assistant_text: str,
        backend_kind: str,
        model: str,
        *,
        quality_gate: Optional["QualityGate"] = None,
    ) -> JudgeVerdict:
        url_and_key = CLIProxyManager.get_url_and_key()
        if not url_and_key:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason="CLIProxyAPI not reachable; cannot judge",
            )
        base_url, _api_key = url_and_key
        turn_text = (last_assistant_text or "")[-_MAX_TURN_TEXT_CHARS:]
        user_content = _JUDGE_USER_TEMPLATE.format(
            goal=goal.strip(),
            turn=turn_text.strip(),
        )
        if quality_gate and quality_gate.rubric:
            user_content = f"{user_content}\n\nRubric:\n{quality_gate.rubric.strip()}"
        judge_version = quality_gate.judge_version if quality_gate else None
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "stream": False,
            # Hint to the upstream which backend kind to route to.
            # CLIProxyAPI honors this when present; otherwise it
            # falls back to model-name inference.
            "metadata": {"backend_kind": backend_kind},
        }
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": "Bearer not-needed",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except httpx.RequestError as exc:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge request failed: {exc}",
                judge_version=judge_version,
            )
        if resp.status_code != 200:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge HTTP {resp.status_code}",
                judge_version=judge_version,
            )
        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
        except (ValueError, KeyError, IndexError) as exc:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge response malformed: {exc}",
                judge_version=judge_version,
            )
        parsed = _parse_judge_json(content)
        if parsed is None:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason="judge output unparseable (treated as not_met)",
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                judge_version=judge_version,
            )
        met, reason, confidence = parsed
        return JudgeVerdict(
            met=met,
            source="llm",
            reason=reason,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            confidence=confidence,
            judge_version=judge_version,
        )

    # -----------------------------------------------------------------
    # v0.7.86 — Ouroboros LLM judge
    # -----------------------------------------------------------------

    @classmethod
    def _run_ouroboros_judge(
        cls,
        goal: str,
        last_assistant_text: str,
        hypothesis: str,
        predicted_outcome: str,
        backend_kind: str,
        model: str,
    ) -> JudgeVerdict:
        """Score the agent's turn against its own hypothesis +
        predicted outcome. Returns a verdict with the 4-state
        ``ouroboros_verdict`` populated; ``met`` is derived from
        the verdict (``confirmed`` → True, others → False).
        """
        url_and_key = CLIProxyManager.get_url_and_key()
        if not url_and_key:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason="CLIProxyAPI not reachable; cannot judge",
                ouroboros_verdict="unknown",
            )
        base_url, _api_key = url_and_key
        turn_text = (last_assistant_text or "")[-_MAX_TURN_TEXT_CHARS:]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _OUROBOROS_JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": _OUROBOROS_JUDGE_USER_TEMPLATE.format(
                        goal=goal.strip(),
                        hypothesis=hypothesis.strip(),
                        predicted_outcome=predicted_outcome.strip(),
                        turn=turn_text.strip(),
                    ),
                },
            ],
            "stream": False,
            "metadata": {"backend_kind": backend_kind},
        }
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": "Bearer not-needed",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except httpx.RequestError as exc:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge request failed: {exc}",
                ouroboros_verdict="unknown",
            )
        if resp.status_code != 200:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge HTTP {resp.status_code}",
                ouroboros_verdict="unknown",
            )
        try:
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage") or {}
        except (ValueError, KeyError, IndexError) as exc:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge response malformed: {exc}",
                ouroboros_verdict="unknown",
            )
        parsed = _parse_ouroboros_judge_json(content)
        if parsed is None:
            # Fall back to the binary parser so we still get a
            # ``met``/``reason`` from a non-Ouroboros-shaped reply.
            fallback = _parse_judge_json(content)
            if fallback is None:
                return JudgeVerdict(
                    met=False,
                    source="llm",
                    reason="judge output unparseable (treated as not_met)",
                    tokens_in=usage.get("prompt_tokens", 0),
                    tokens_out=usage.get("completion_tokens", 0),
                    ouroboros_verdict="unknown",
                )
            met_fb, reason_fb, confidence_fb = fallback
            return JudgeVerdict(
                met=met_fb,
                source="llm",
                reason=reason_fb,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                confidence=confidence_fb,
                ouroboros_verdict="confirmed" if met_fb else "unknown",
            )
        met, verdict, reason = parsed
        return JudgeVerdict(
            met=met,
            source="llm",
            reason=reason,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            ouroboros_verdict=verdict,
        )


_JSON_BLOB_RE = re.compile(r"\{[\s\S]*?\}")


def _parse_judge_json(content: str) -> Optional[tuple[bool, str, float]]:
    """Forgiving JSON parser for the judge output.

    The model occasionally wraps the JSON in ``` ```json ``` ``` fences
    or adds a prose preamble. Extract the first ``{...}`` blob and
    try to parse. Returns ``(met, reason, confidence)`` or ``None``
    when no valid blob is found.

    ``confidence`` is the judge's optional self-reported certainty
    (0–1). Backward-safe: when the judge omits it, we default to
    ``1.0`` so legacy "absent" replies still terminate as before.
    Out-of-range values are clamped to ``[0, 1]``.
    """
    if not isinstance(content, str):
        return None
    for match in _JSON_BLOB_RE.finditer(content):
        try:
            blob = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(blob, dict) or "met" not in blob:
            continue
        met = bool(blob.get("met"))
        reason = str(blob.get("reason") or "").strip() or "(no reason given)"
        try:
            confidence = float(blob.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))
        return met, reason, confidence
    return None


_VALID_OUROBOROS_VERDICTS = {"confirmed", "partial", "falsified", "unknown"}


def _parse_ouroboros_judge_json(content: str) -> Optional[tuple[bool, str, str]]:
    """v0.7.86 — parse an Ouroboros judge JSON envelope. Returns
    ``(met, verdict, reason)`` or ``None`` if no valid blob found.
    Unknown ``verdict`` values are coerced to ``unknown`` rather
    than rejected so a slightly-off model reply still produces a
    usable iteration record.
    """
    if not isinstance(content, str):
        return None
    for match in _JSON_BLOB_RE.finditer(content):
        try:
            blob = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(blob, dict):
            continue
        if "met" not in blob and "verdict" not in blob:
            continue
        verdict = str(blob.get("verdict") or "").strip().lower()
        if verdict not in _VALID_OUROBOROS_VERDICTS:
            verdict = "unknown"
        met_value = blob.get("met")
        if met_value is None:
            met = verdict == "confirmed"
        else:
            met = bool(met_value)
        reason = str(blob.get("reason") or "").strip() or "(no reason given)"
        return met, verdict, reason
    return None
