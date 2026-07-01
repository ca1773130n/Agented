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
import signal
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
    env: Optional[dict] = None,
    line_handler: Callable[[str], Optional[str]],
    backend_label: str,
) -> Generator[str, None, None]:
    """Common subprocess streaming loop with timeout + stderr capture.

    ``line_handler`` receives each raw decoded stdout line and returns
    text to yield (or ``None`` to skip). Backends choose how to parse:
    Claude parses NDJSON events, codex/gemini just yield the line as-is.

    ``env`` overrides selected variables (the per-account ``CLAUDE_CONFIG_DIR``
    / ``CODEX_HOME`` / ``GEMINI_HOME``). When ``None`` the subprocess
    inherits the harness's env unchanged.
    """
    logger.info("CLI agent: spawning %s (cwd=%s) cmd=%s", backend_label, cwd, " ".join(cmd))
    # Phase 24 (24-03 sweep): OS-sandbox wrap (no-op unless AGENTED_SANDBOX opted in).
    from .sandbox_wrap import wrap_harness_command

    cmd, _sandboxed = wrap_harness_command(cmd, cwd, net=True)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=cwd,
            env=env,
            # Own process group so tool grandchildren can be killed too — a bare
            # proc.kill() leaves them orphaned (H5).
            start_new_session=True,
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
        # Kill the whole process group, not just the direct child — otherwise
        # tool grandchildren survive the timeout (start_new_session gives the
        # child its own group). proc.kill() alone leaves them orphaned.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                proc.kill()
            except OSError:
                pass

    timer = threading.Timer(SUBPROCESS_TIMEOUT_SECONDS, _on_timeout)
    timer.start()

    from .account_rotation_service import RateLimitEvent

    completed = False
    rate_limited = False
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
            result = line_handler(line)
            if result is None:
                continue
            # A handler may return a single item or a list (e.g. one Claude
            # assistant event → tool_use + thinking + text). Normalize + emit.
            items = result if isinstance(result, list) else [result]
            for item in items:
                if isinstance(item, RateLimitEvent):
                    rate_limited = True
                yield item
        proc.wait()
        completed = True
    finally:
        timer.cancel()
        # If the consumer abandoned the generator (SSE client disconnect →
        # GeneratorExit) or we broke out early, the child + its tool
        # grandchildren would otherwise keep running for up to the timeout,
        # leaking the process group and both pipes (H5). Tear it all down.
        # Only tear down on the abandon/kill path. On normal completion the
        # post-loop block below still needs to read proc.stderr, so leave the
        # streams open (Popen closes them on GC).
        if not completed:
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        pass
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.warning("CLI agent: %s did not exit after SIGKILL", backend_label)
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass

    if timed_out:
        yield "\n\n[Request timed out]"
        return

    if proc.returncode and proc.returncode != 0:
        if rate_limited:
            # The non-zero exit is the provider's 429 (already surfaced as a
            # RateLimitEvent so the caller can rotate). Don't also emit the
            # cryptic "[Claude CLI error: exit code 1]" — that's the silent
            # failure that hid the real "weekly limit" reason.
            logger.info(
                "CLI agent: %s exited rc=%d due to rate limit (rotation signalled)",
                backend_label,
                proc.returncode,
            )
            return
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


def _make_claude_line_handler():
    """Build a stateful per-stream handler for Claude's ``stream-json`` NDJSON.

    With ``--include-partial-messages`` claude streams the reply as
    ``stream_event`` → ``content_block_delta`` token chunks, then repeats the
    whole thing in a final ``assistant`` event and again in ``result``. We
    stream the token deltas and DROP both duplicates, so the reply appears
    live and exactly once. Falls back to the full ``assistant`` text when no
    deltas streamed (older CLI without the flag).

    State (whether any token delta has streamed) lives in the closure, so a
    fresh handler must be created per stream — see ``stream_via_cli_agent``.
    """
    from .account_rotation_service import RateLimitEvent, detect_rate_limit_from_event
    from .conversation_streaming import (
        ThinkingEvent,
        _extract_text_from_event,
        _extract_thinking_from_event,
        _extract_tool_uses_from_event,
    )

    # ``streamed``/``thought`` track whether answer/thinking tokens have
    # already streamed this turn, so the final ``assistant`` event's full
    # copies are dropped instead of doubling the bubble.
    state = {"streamed": False, "thought": False}

    def handler(line: str):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        rl = detect_rate_limit_from_event(event)
        if rl is not None:
            return RateLimitEvent(rl)

        etype = event.get("type")
        # Terminal summary — always a duplicate of the assistant text.
        if etype == "result":
            return None

        items: list = []
        if etype == "assistant":
            # The final message carries COMPLETE tool_use blocks (full input)
            # — take them only here, not from the partial content_block_start
            # deltas, so a tool isn't surfaced twice with empty args.
            items.extend(_extract_tool_uses_from_event(event))
            if not state["thought"]:
                th = _extract_thinking_from_event(event)
                if th:
                    items.append(ThinkingEvent(th))
            if not state["streamed"]:
                txt = _extract_text_from_event(event)
                if txt:
                    items.append(txt)
            return items or None

        # stream_event / bare deltas — the live token stream.
        th = _extract_thinking_from_event(event)
        if th:
            state["thought"] = True
            items.append(ThinkingEvent(th))
        txt = _extract_text_from_event(event)
        if txt:
            state["streamed"] = True
            items.append(txt)
        return items or None

    return handler


def _passthrough_line_handler(line: str):
    """Codex/Gemini emit human-readable progress; pass each line through —
    but surface a :class:`RateLimitEvent` when a line reads as a rate limit
    so those backends rotate too."""
    from .account_rotation_service import RateLimitEvent, detect_rate_limit_from_text

    rl = detect_rate_limit_from_text(line)
    if rl is not None:
        return RateLimitEvent(rl)
    return line + "\n"


# Per-backend env var that points the CLI at a non-default config
# directory. Multi-account ai-accounts setups put each account at a
# distinct path (e.g. ``~/.claude-personal1``); without these the
# CLI loads the default location and reports "Not logged in".
_CONFIG_ENV_VAR = {
    "claude": "CLAUDE_CONFIG_DIR",
    "codex": "CODEX_HOME",
    "gemini": "GEMINI_HOME",
}


def _build_env(backend_norm: str, config_dir: Optional[str]) -> Optional[dict]:
    """Inherit os.environ + override the per-backend config var.

    Returns ``None`` (Popen inherits env unchanged) when no override is
    needed — keeps the spawn cheap and avoids surprising downstream
    tools that read other env vars.
    """
    if not config_dir:
        return None
    var = _CONFIG_ENV_VAR.get(backend_norm)
    if not var:
        return None
    expanded = os.path.expanduser(config_dir)
    env = dict(os.environ)
    env[var] = expanded
    logger.info(
        "CLI agent env: %s=%s for %s",
        var,
        expanded,
        backend_norm,
    )
    return env


def stream_via_cli_agent(
    messages: List[dict],
    *,
    backend: str,
    cwd: Optional[str],
    yolo: bool,
    model: Optional[str] = None,
    config_dir: Optional[str] = None,
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
        config_dir: per-account config directory (e.g.
            ``~/.claude-personal1``). When set, exported to the
            backend's expected env var (CLAUDE_CONFIG_DIR / CODEX_HOME /
            GEMINI_HOME) so the CLI reads the right credential vault
            instead of defaulting to ``~/.claude`` / ``~/.codex``.
    """
    backend_norm = (backend or "").lower()
    prompt = _build_prompt(messages)
    if not prompt:
        yield "[Error: empty prompt — nothing to send to the agent]"
        return

    env = _build_env(backend_norm, config_dir)

    if backend_norm == "claude":
        # --include-partial-messages makes claude emit token-by-token
        # content_block_delta events instead of one big assistant message at
        # the end, so the chat streams live instead of the user waiting
        # minutes for the whole reply. A fresh stateful handler per call
        # streams those deltas and drops the duplicate final assistant text.
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if yolo:
            cmd.append("--dangerously-skip-permissions")
        if model:
            cmd.extend(["--model", model])
        yield from _run_subprocess(
            cmd, cwd=cwd, env=env, line_handler=_make_claude_line_handler(), backend_label="Claude"
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
            cmd, cwd=cwd, env=env, line_handler=_passthrough_line_handler, backend_label="Codex"
        )
        return

    if backend_norm == "gemini":
        cmd = ["gemini", "-p", prompt]
        if yolo:
            cmd.append("--yolo")
        if model:
            cmd.extend(["-m", model])
        yield from _run_subprocess(
            cmd, cwd=cwd, env=env, line_handler=_passthrough_line_handler, backend_label="Gemini"
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


_BACKEND_KIND_TO_TYPE = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
}


def resolve_account_config_dir(account_id: Optional[str], backend_kind: str) -> Optional[str]:
    """Look up the config directory for a chat account.

    The frontend's account picker passes the sidecar's string id (e.g.
    ``bkd-8o3x4n9d...``); v0.7.16 mirrors sidecar accounts into the
    local ``backend_accounts`` table by display_name / config_path so
    the same row exists locally with an integer ``id`` and the right
    ``config_path``. We resolve preferentially by exact match heuristics:

    1. If ``account_id`` is a digit string, treat as local PK.
    2. If it looks like a sidecar id (``bkd-...``) or a display name,
       fall back to "first row whose ai_backends.type matches kind"
       preferring ``is_default=1`` — same pick-order the existing
       monitoring code uses.
    3. If ``account_id`` is None, pick the default for the backend kind.

    Returns the expanduser'd config path, or ``None`` if no account is
    available (caller should let the CLI hit its default).
    """
    backend_type = _BACKEND_KIND_TO_TYPE.get((backend_kind or "").lower())
    if not backend_type:
        return None
    try:
        from ..db.connection import get_connection
    except Exception:
        return None

    try:
        with get_connection() as conn:
            row = None
            if account_id and str(account_id).isdigit():
                cur = conn.execute(
                    """
                    SELECT ba.config_path FROM backend_accounts ba
                    JOIN ai_backends ab ON ba.backend_id = ab.id
                    WHERE ba.id = ? AND ab.type = ?
                    LIMIT 1
                    """,
                    (int(account_id), backend_type),
                )
                row = cur.fetchone()
            if row is None:
                # Default account for this backend kind.
                cur = conn.execute(
                    """
                    SELECT ba.config_path FROM backend_accounts ba
                    JOIN ai_backends ab ON ba.backend_id = ab.id
                    WHERE ab.type = ? AND ba.config_path IS NOT NULL
                    ORDER BY ba.is_default DESC, ba.id ASC
                    LIMIT 1
                    """,
                    (backend_type,),
                )
                row = cur.fetchone()
    except Exception as exc:
        logger.debug("Account config-dir lookup failed: %s", exc)
        return None

    if not row:
        return None
    config_path = row["config_path"] if hasattr(row, "keys") else row[0]
    if not config_path:
        return None
    return os.path.expanduser(config_path)


_DRIVERS = ("cliproxy", "cli_agent", "grd")


def _normalize_driver(value) -> Optional[str]:
    """Coerce a raw driver string to one of the literal set, else None."""
    if not value:
        return None
    v = str(value).strip().lower()
    return v if v in _DRIVERS else None


def resolve_execution_driver(
    *,
    backend: str | None,
    use_cli_agent: Optional[bool] = None,
    turn_driver: Optional[str] = None,
    super_agent_id: Optional[str] = None,
    project_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    _grd_available=None,
    _resolve_workspace=None,
) -> str:
    """Resolve the execution driver for a chat turn (Phase 19, REQ-10).

    A pure, precedence-driven, default-GRD, degrade-safe resolver returning
    one of ``"cliproxy" | "cli_agent" | "grd"`` for EVERY input. It replaces
    the 2-way ``should_route_via_cli_agent`` boolean (callers migrate in
    19-04; this function is purely additive).

    Precedence — first non-None source wins (19-RESEARCH.md §1 table):

      1. Turn override: explicit ``turn_driver``; else legacy ``use_cli_agent``
         (True → ``cli_agent``, False → ``cliproxy``).
      2. SuperAgent: ``config_json.driver`` for ``super_agent_id``.
      3. Instance: ``project_sa_instances.driver`` for ``instance_id``.
      4. Project default: ``projects.default_driver`` for ``project_id``.
      5. Global default: ``"grd"``.

    Backend guard: a backend outside the CLI-runnable set ({claude, codex,
    gemini}) cannot run grd/cli_agent, so it always resolves to ``cliproxy``
    — the same constraint ``should_route_via_cli_agent`` enforces.

    Degrade (grd → cli_agent): when the resolved driver is ``"grd"``, both the
    GRD binary and a resolvable project workspace must be present. If the
    injected ``_grd_available()`` reports unavailable, OR ``_resolve_workspace``
    raises ``ValueError`` (no clone path), degrade to ``cli_agent`` (never
    crash). Both checks are injectable so the degrade path is unit-testable
    with no real binary/workspace.

    Defensive: ANY unexpected exception degrades toward the legacy choice
    (``cli_agent`` if the backend is CLI-runnable, else ``cliproxy``) — a read
    failure during precedence resolution must never crash the turn.
    """
    backend_norm = (backend or "").lower()
    cli_runnable = backend_norm in _CLI_RUNNABLE_BACKENDS
    legacy_choice = "cli_agent" if cli_runnable else "cliproxy"

    try:
        # Non-CLI backends can only ever use CLIProxy.
        if not cli_runnable:
            return "cliproxy"

        resolved: Optional[str] = None

        # 1. Turn override.
        resolved = _normalize_driver(turn_driver)
        if resolved is None and use_cli_agent is not None:
            resolved = "cli_agent" if use_cli_agent else "cliproxy"

        # 2. SuperAgent config_json.driver.
        if resolved is None and super_agent_id:
            try:
                from ..db.super_agents import get_super_agent

                sa = get_super_agent(super_agent_id)
                if sa:
                    cfg = json.loads(sa.get("config_json") or "{}")
                    resolved = _normalize_driver(cfg.get("driver"))
            except Exception:
                logger.debug("SuperAgent driver read failed", exc_info=True)

        # 3. Instance driver.
        if resolved is None and instance_id:
            try:
                from ..db.project_sa_instances import get_instance_driver

                resolved = _normalize_driver(get_instance_driver(instance_id))
            except Exception:
                logger.debug("Instance driver read failed", exc_info=True)

        # 4. Project default driver.
        if resolved is None and project_id:
            try:
                from ..db.projects import get_project_default_driver

                resolved = _normalize_driver(get_project_default_driver(project_id))
            except Exception:
                logger.debug("Project default driver read failed", exc_info=True)

        # 5. Global default.
        if resolved is None:
            resolved = "grd"

        # Degrade grd → cli_agent when GRD or the workspace is unavailable.
        if resolved == "grd":
            grd_available = _grd_available
            if grd_available is None:
                from .grd_cli_service import GrdCliService

                grd_available = GrdCliService.available
            resolve_workspace = _resolve_workspace
            if resolve_workspace is None:
                from .project_workspace_service import ProjectWorkspaceService

                resolve_workspace = ProjectWorkspaceService.resolve_working_directory

            report = grd_available()
            ok = (
                bool(report.get("grd_tools_available") or report.get("gd_available"))
                if isinstance(report, dict)
                else bool(report)
            )
            if ok:
                try:
                    resolve_workspace(project_id)
                except ValueError:
                    ok = False
            if not ok:
                logger.info(
                    "GRD driver unavailable, degrading to cli_agent for project=%s",
                    project_id,
                )
                return "cli_agent"

        return resolved
    except Exception:
        logger.debug("resolve_execution_driver fell through to legacy choice", exc_info=True)
        return legacy_choice


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
