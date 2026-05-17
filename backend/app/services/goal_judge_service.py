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
import subprocess
from dataclasses import dataclass
from typing import Optional

import httpx

from .cliproxy_manager import CLIProxyManager

logger = logging.getLogger(__name__)


# Per-backend default judge model. Each picks the cheapest /
# fastest small model that can answer a yes/no question — the
# judge call is fire-and-forget, not where to spend operator
# dollars. ``auto`` lets CLIProxyAPI route to whatever the
# proxy considers default for that backend's accounts.
DEFAULT_JUDGE_MODEL = {
    "claude": "claude-haiku-4-5",
    "codex": "o4-mini",
    "gemini": "gemini-2.5-flash",
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
    "a JSON object: {\"met\": true|false, \"reason\": \"...\"}. "
    "Be concise — the reason is one sentence."
)

_JUDGE_USER_TEMPLATE = (
    "Goal: {goal}\n\n"
    "Latest agent turn:\n---\n{turn}\n---\n\n"
    "Is the goal met?"
)


@dataclass
class JudgeVerdict:
    """Outcome of one judging round.

    ``source`` distinguishes deterministic check, LLM judge, and
    cap-driven termination so the iteration row in
    ``goal_loop_iterations`` faithfully records which path decided
    the iteration's fate.
    """

    met: bool
    source: str
    reason: str
    stdout: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


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
    ) -> JudgeVerdict:
        if check_cmd:
            return cls._run_deterministic(check_cmd, cwd)
        model = model_override or DEFAULT_JUDGE_MODEL.get(backend_kind, "auto")
        return cls._run_llm_judge(goal, last_assistant_text, backend_kind, model)

    # -----------------------------------------------------------------
    # Deterministic check
    # -----------------------------------------------------------------

    @staticmethod
    def _run_deterministic(check_cmd: str, cwd: Optional[str]) -> JudgeVerdict:
        try:
            proc = subprocess.run(
                check_cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_CHECK_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return JudgeVerdict(
                met=False,
                source="deterministic",
                reason=f"check timed out after {_CHECK_TIMEOUT_SECONDS}s",
            )
        except (OSError, ValueError) as exc:
            return JudgeVerdict(
                met=False,
                source="deterministic",
                reason=f"check failed to run: {exc}",
            )
        stdout = (proc.stdout or "")[-4096:]  # tail-cap for storage
        if proc.returncode == 0:
            return JudgeVerdict(
                met=True,
                source="deterministic",
                reason="check command exited 0",
                stdout=stdout,
            )
        return JudgeVerdict(
            met=False,
            source="deterministic",
            reason=f"check exited {proc.returncode}",
            stdout=stdout,
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
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": _JUDGE_USER_TEMPLATE.format(
                        goal=goal.strip(),
                        turn=turn_text.strip(),
                    ),
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
            )
        if resp.status_code != 200:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason=f"judge HTTP {resp.status_code}",
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
            )
        parsed = _parse_judge_json(content)
        if parsed is None:
            return JudgeVerdict(
                met=False,
                source="llm",
                reason="judge output unparseable (treated as not_met)",
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
            )
        met, reason = parsed
        return JudgeVerdict(
            met=met,
            source="llm",
            reason=reason,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
        )


_JSON_BLOB_RE = re.compile(r"\{[\s\S]*?\}")


def _parse_judge_json(content: str) -> Optional[tuple[bool, str]]:
    """Forgiving JSON parser for the judge output.

    The model occasionally wraps the JSON in ``` ```json ``` ``` fences
    or adds a prose preamble. Extract the first ``{...}`` blob and
    try to parse. Returns ``(met, reason)`` or ``None`` when no
    valid blob is found.
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
        return met, reason
    return None
