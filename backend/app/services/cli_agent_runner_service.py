"""CLI agent runner — invoke claude/codex/gemini CLIs as autonomous agents.

The legacy ``conversation_streaming.stream_llm_response`` path prefers
CLIProxyAPI for token streaming. That gives nice token-by-token chat,
but the CLIs running behind the proxy are stateless workers — they
cannot read files, run shell commands, or edit code in the user's
worktree. Sketches and agent-driven flows want the opposite: an agent
that opens a worktree, uses tools, and reports back when done.

This module spawns the CLIs directly via ``subprocess.Popen`` with
flags that grant tool privileges. When YOLO mode is on (the default),
each backend's "skip approvals" flag is added so the agent doesn't
hang waiting for permission prompts — the harness is already running
in a controlled context (Litestar + per-account credential isolation),
so an interactive approval prompt would only stall the run.

Backends covered:

* **Claude Code** — ``claude -p <prompt> --output-format stream-json
  --verbose --dangerously-skip-permissions`` (when YOLO). Streams rich
  events; we reuse the existing parser via dependency injection.
* **Codex CLI** — ``codex exec <prompt> --cd <cwd>
  --dangerously-bypass-approvals-and-sandbox`` (when YOLO) or
  ``--sandbox=workspace-write --ask-for-approval=never`` (non-YOLO,
  still avoids prompts but writes are scoped). Streams plaintext.
* **Gemini CLI** — ``gemini -p <prompt> -y`` (when YOLO; ``-y`` is
  Gemini's auto-accept flag). Streams plaintext.

The runner returns a generator of text chunks so callers can pipe
straight into ``ChatStateService.push_delta`` like the existing
``stream_llm_response``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Callable, Generator, List, Optional

logger = logging.getLogger(__name__)

# Subprocess timeout — agents can run for a while; align with the existing
# CLI fallback ceiling (15 minutes).
SUBPROCESS_TIMEOUT_SECONDS = 15 * 60


def _build_prompt(messages: List[dict]) -> str:
    """Flatten chat messages into a single prompt string for ``-p`` flags.

    Mirrors the legacy ``_stream_via_cli`` shape so the model sees
    "System: ...\\n\\nUser: ...\\n\\nAssistant: ..." just as before.
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content:
            continue
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


def _run_subprocess(
    cmd: List[str],
    *,
    cwd: Optional[str],
    line_handler: Callable[[str], Optional[str]],
    backend_label: str,
) -> Generator[str, None, None]:
    """Common subprocess streaming loop with timeout + stderr capture.

    ``line_handler`` receives each raw decoded stdout line and returns
    text to yield (or ``None`` to skip). Backends choose how to parse:
    Claude parses NDJSON events, codex/gemini just yield the line as-is.
    """
    logger.info(
        "CLI agent: spawning %s (cwd=%s) cmd=%s", backend_label, cwd, " ".join(cmd)
    )
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=cwd,
        )
    except FileNotFoundError:
        logger.error("CLI agent: %s CLI not found", backend_label)
        yield f"[Error: {backend_label} CLI not found. Install it and retry.]"
        return
    except OSError as exc:
        logger.error("CLI agent: spawn failed for %s: %s", backend_label, exc)
        yield f"[Error: failed to spawn {backend_label}: {exc}]"
        return

    timed_out = False

    def _on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        try:
            proc.kill()
        except OSError:
            pass

    timer = threading.Timer(SUBPROCESS_TIMEOUT_SECONDS, _on_timeout)
    timer.start()

    try:
        assert proc.stdout is not None  # bufsize=0 guarantees a stream
        while True:
            if timed_out:
                break
            raw = proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue
            chunk = line_handler(line)
            if chunk:
                yield chunk
        proc.wait()
    finally:
        timer.cancel()

    if timed_out:
        yield "\n\n[Request timed out]"
        return

    if proc.returncode and proc.returncode != 0:
        stderr_output = ""
        try:
            if proc.stderr is not None:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
        except Exception:
            logger.debug("stderr read failed", exc_info=True)
        logger.error(
            "CLI agent: %s exited rc=%d stderr=%s",
            backend_label,
            proc.returncode,
            stderr_output[:500],
        )
        detail = stderr_output[:200] if stderr_output else f"exit code {proc.returncode}"
        yield f"\n\n[{backend_label} CLI error: {detail}]"


def _claude_line_handler(line: str) -> Optional[str]:
    """Parse Claude's ``--output-format stream-json --verbose`` NDJSON."""
    from .conversation_streaming import _extract_text_from_event

    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return _extract_text_from_event(event)


def _passthrough_line_handler(line: str) -> Optional[str]:
    """Codex/Gemini emit human-readable progress; pass each line through."""
    return line + "\n"


def stream_via_cli_agent(
    messages: List[dict],
    *,
    backend: str,
    cwd: Optional[str],
    yolo: bool,
    model: Optional[str] = None,
) -> Generator[str, None, None]:
    """Spawn the requested CLI as an autonomous agent and stream its output.

    Args:
        messages: chat history to flatten into the agent's prompt.
        backend: ``claude``/``codex``/``gemini`` (case-insensitive). Other
            kinds are unsupported and yield an error chunk.
        cwd: project worktree to run the agent in. Required for tool
            access — without a cwd, Claude defaults to the home directory
            and tool use becomes meaningless.
        yolo: when ``True``, pass each backend's "skip approvals" flag.
        model: optional model override forwarded to ``-m``/``--model``.
    """
    backend_norm = (backend or "").lower()
    prompt = _build_prompt(messages)
    if not prompt:
        yield "[Error: empty prompt — nothing to send to the agent]"
        return

    if backend_norm == "claude":
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
        if yolo:
            cmd.append("--dangerously-skip-permissions")
        if model:
            cmd.extend(["--model", model])
        yield from _run_subprocess(
            cmd, cwd=cwd, line_handler=_claude_line_handler, backend_label="Claude"
        )
        return

    if backend_norm == "codex":
        cmd = ["codex", "exec", prompt]
        if cwd:
            cmd.extend(["--cd", cwd])
        if yolo:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            # Non-YOLO: still don't prompt the user (we have no TTY), but
            # restrict writes to the workspace via Codex's sandbox.
            cmd.extend(["--sandbox", "workspace-write", "--ask-for-approval", "never"])
        if model:
            cmd.extend(["-m", model])
        yield from _run_subprocess(
            cmd, cwd=cwd, line_handler=_passthrough_line_handler, backend_label="Codex"
        )
        return

    if backend_norm == "gemini":
        cmd = ["gemini", "-p", prompt]
        if yolo:
            cmd.append("-y")
        if model:
            cmd.extend(["-m", model])
        yield from _run_subprocess(
            cmd, cwd=cwd, line_handler=_passthrough_line_handler, backend_label="Gemini"
        )
        return

    yield f"[Error: CLI agent runner does not support backend '{backend}']"


def is_yolo_mode_enabled() -> bool:
    """Read the global ``agent_yolo_mode`` setting (default ``True``).

    Stored as ``"true"``/``"false"`` to match the existing settings
    convention. Any read failure is treated as YOLO-on so the agent
    doesn't silently fall back to interactive prompts that would hang.
    """
    try:
        from ..db.settings import get_setting
    except Exception:
        return True

    try:
        raw = get_setting("agent_yolo_mode")
    except Exception:
        logger.debug("YOLO mode read failed; defaulting to ON", exc_info=True)
        return True
    if raw is None:
        return True
    return str(raw).strip().lower() not in ("false", "0", "no", "off")


def set_yolo_mode(enabled: bool) -> None:
    """Persist the YOLO mode flag."""
    from ..db.settings import set_setting

    set_setting("agent_yolo_mode", "true" if enabled else "false")


_CLI_RUNNABLE_BACKENDS = ("claude", "codex", "gemini")


def should_route_via_cli_agent(
    backend: str | None,
    use_cli_agent: Optional[bool],
) -> bool:
    """Decide whether a chat turn should spawn the CLI agent runner.

    Three call sites — `streaming_helper.run_streaming_response`,
    `BaseConversationService._stream_and_accumulate`, and
    `grd_routes.project_chat` — all need the same routing decision.
    Centralizing it here keeps the rule one place:

    1. Backend not in {claude, codex, gemini} → never use the CLI
       runner (those CLIs aren't installed / don't apply).
    2. Caller passed ``use_cli_agent=True`` → CLI runner.
    3. Caller passed ``use_cli_agent=False`` → CLIProxy. The caller
       wants pure-token chat; honor that even if CLIProxy is missing
       (the caller will see an explicit error and can recover).
    4. Caller deferred (``None``) and global YOLO is on → CLI runner.
    5. Caller deferred (``None``), global YOLO is off, but CLIProxy
       is unreachable → CLI runner. The legacy CLIProxy path can't
       satisfy the request and the alternative is yielding
       ``[Error: CLIProxyAPI not running]`` into chat, which presents
       to the user as a silent SSE drop. Falling over to the CLI
       runner is the only way to actually answer.
    """
    backend_norm = (backend or "").lower()
    if backend_norm not in _CLI_RUNNABLE_BACKENDS:
        return False
    if use_cli_agent is True:
        return True
    if use_cli_agent is False:
        return False
    if is_yolo_mode_enabled():
        return True
    try:
        from .conversation_streaming import _find_cliproxy

        if _find_cliproxy() is None:
            logger.info(
                "CLIProxy unavailable; falling over to CLI agent runner for %s",
                backend_norm,
            )
            return True
    except Exception:
        logger.debug("CLIProxy availability probe failed", exc_info=True)
    return False
