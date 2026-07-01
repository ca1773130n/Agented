"""Shared LLM streaming utility for all conversation services.

Provides real-time token-by-token streaming via LiteLLM.
Authentication modes (checked in order):

1. Explicit api_base (proxy mode)
2. CLIProxyAPI (managed or auto-detected) — supports account routing via X-Account-Email
3. ANTHROPIC_API_KEY env var (direct API, no account routing)
4. Claude CLI fallback — subprocess with --output-format stream-json --verbose

CLIProxyAPI is checked BEFORE the direct API key so that account selection
(multiple Claude Code credentials) works when the proxy is running.
"""

import gzip
import json
import logging
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

SUBPROCESS_TIMEOUT = 120


def _terminate_proc_group(proc: "subprocess.Popen") -> None:
    """Best-effort SIGTERM→SIGKILL of a Popen's process group, then reap.

    Used by the CLI streaming generators so a timeout or an abandoned generator
    (SSE client disconnect) doesn't leak the child + its tool grandchildren
    (03 H1). The Popen must have been created with start_new_session=True.
    """
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except OSError:
            return
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
            logger.warning("conversation_streaming: process did not exit after SIGKILL")


@dataclass
class ToolUseEvent:
    """Structured tool-use event surfaced by a streaming backend.

    Yielded alongside text by ``stream_llm_response`` when the agent's
    underlying CLI / proxy exposes function-call deltas:

      - Anthropic stream-json (Claude CLI fallback): ``type=assistant``
        message events with a ``tool_use`` content block.
      - OpenAI chat-completions delta (CLIProxyAPI primary path):
        ``delta.tool_calls[].function`` entries.

    Callers that only want text can ``isinstance(chunk, str)``-filter;
    the chat-streaming helper dispatches us as a ``tool_use`` delta
    via ChatStateService so the operator UI surfaces a citation badge.

    ``input`` is the parsed JSON arguments when available, or the raw
    string fragment for proxy responses that stream tool-call args as
    incomplete JSON chunks (operator UI shows whichever it gets).
    """

    name: str
    input: Any = field(default_factory=dict)
    id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "input": self.input, "id": self.id}


@dataclass
class ThinkingEvent:
    """The model's extended-thinking / reasoning text for a turn.

    Surfaced by the Claude CLI stream-json path (``thinking`` content blocks
    on the final ``assistant`` event, or ``thinking_delta`` tokens under
    ``--include-partial-messages``). The chat helper dispatches it as a
    ``thinking`` delta so the operator UI can show it folded, separate from
    the answer.
    """

    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text}


# Tuple type for the chunk stream — what every helper yields and what
# ``run_streaming_response`` dispatches on. New event types added by
# extending this Union (and the callers that handle them).
ChatChunk = Union[str, ToolUseEvent, ThinkingEvent]


def _extract_thinking_from_event(event: dict) -> Optional[str]:
    """Pull reasoning text out of a Claude stream-json event: ``thinking``
    content blocks on an ``assistant`` message, or a ``thinking_delta`` token
    under ``--include-partial-messages``. Returns ``None`` when absent."""
    etype = event.get("type", "")
    if etype == "assistant":
        message = event.get("message", {})
        parts = []
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "thinking":
                t = block.get("thinking") or block.get("text")
                if t:
                    parts.append(t)
        return "".join(parts) or None
    if etype == "stream_event":
        inner = event.get("event", {})
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta", {})
            if delta.get("type") == "thinking_delta":
                return delta.get("thinking", "") or None
    return None


class ProxyAccountError(Exception):
    """Raised when the proxy returns an error that can be resolved by switching accounts.

    Covers 429 rate limits, 401 auth errors (expired tokens), and 403 forbidden.
    """

    def __init__(self, detail: str, status_code: int, account_email: str | None = None):
        self.detail = detail
        self.status_code = status_code
        self.account_email = account_email
        super().__init__(detail)


# CLIProxyAPI config location
_CLIPROXY_CONFIG = Path.home() / ".cli-proxy-api" / "config.yaml"


def _detect_cliproxy() -> tuple[str, str] | None:
    """Auto-detect a running CLIProxyAPI instance from its config file.

    Returns (api_base, api_key) if the proxy is reachable, else None.
    """
    if not _CLIPROXY_CONFIG.exists():
        return None

    try:
        conf = yaml.safe_load(_CLIPROXY_CONFIG.read_text())
    except Exception as e:
        logger.debug("CLIProxy config parse: %s", e)
        return None

    port = conf.get("port", 8317)
    keys = conf.get("api-keys", [])
    api_key = keys[0] if keys else "not-needed"
    base_url = f"http://127.0.0.1:{port}/v1"

    # Quick health check
    try:
        import httpx

        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=2,
        )
        if resp.status_code == 200:
            logger.info("Auto-detected CLIProxyAPI on port %d", port)
            return base_url, api_key
    except Exception as e:
        logger.debug("CLIProxy health check: %s", e)

    return None


def _find_cliproxy() -> tuple[str, str] | None:
    """Find a running CLIProxyAPI instance (managed or auto-detected).

    Returns (api_base, api_key) or None.
    """
    # 1. Check CLIProxyManager for a running managed instance
    try:
        from .cliproxy_manager import CLIProxyManager

        managed = CLIProxyManager.get_url_and_key()
        if managed:
            return managed
    except Exception as e:
        logger.debug("CLIProxyManager lookup: %s", e)

    # 2. Auto-detect global CLIProxyAPI (~/.cli-proxy-api/config.yaml)
    return _detect_cliproxy()


def _get_default_model(backend_type: str) -> str:
    """Get the default model for a backend by querying ModelDiscoveryService.

    Returns the raw (unnormalized) model ID so it works with CLIProxyAPI
    routing (e.g. ``claude-opus-4-6``, ``gpt-5.3-codex``).
    """
    try:
        from .model_discovery_service import ModelDiscoveryService

        raw_id = ModelDiscoveryService.get_default_model_id(backend_type)
        if raw_id:
            logger.info("Default model for %s: %s", backend_type, raw_id)
            return raw_id
    except Exception as e:
        logger.debug("Model discovery failed for %s: %s", backend_type, e)

    # Last-resort fallbacks — must be real model IDs that route correctly
    _FALLBACKS = {
        "claude": "claude-sonnet-4-20250514",
        "codex": "gpt-5.3-codex",
        "gemini": "gemini-3-pro-preview",
        "opencode": "opencode/glm-4.7-free",
    }
    return _FALLBACKS.get(backend_type, backend_type)


def _resolve_display_model(display_name: str, backend_type: str) -> str:
    """Resolve a normalized display model name back to a raw model ID.

    The model dropdown shows normalized names (e.g. "Opus 4.6", "big-pickle")
    but CLIProxyAPI routes by raw model ID prefix. This function maps them back.

    If the name already looks like a raw model ID, it is returned unchanged.
    """
    import re

    # Already a raw model ID — contains provider prefix or version pattern
    if re.match(r"^(claude|gpt|gemini|codex)-", display_name, re.IGNORECASE):
        return display_name
    # Already has provider/model format (e.g. "opencode/big-pickle")
    if "/" in display_name:
        return display_name

    try:
        from .model_discovery_service import ModelDiscoveryService

        raw_models = ModelDiscoveryService._discover_raw(backend_type)
        if not raw_models:
            return display_name

        # Direct match in raw list
        if display_name in raw_models:
            return display_name

        # OpenCode: "big-pickle" → "opencode/big-pickle"
        if backend_type == "opencode":
            for raw in raw_models:
                if "/" in raw:
                    _, model_id = raw.split("/", 1)
                    if model_id == display_name:
                        return raw

        # Claude: "Opus 4.6" → "claude-opus-4-6-20250514"
        if backend_type == "claude":
            match = re.match(
                r"^(Opus|Sonnet|Haiku)\s+(\d+(?:\.\d+)*)$", display_name, re.IGNORECASE
            )
            if match:
                family = match.group(1).lower()
                version = match.group(2).replace(".", "-")
                prefix = f"claude-{family}-{version}"
                for raw in raw_models:
                    if raw.startswith(prefix):
                        return raw

    except Exception as e:
        logger.debug("Model resolution failed for %s/%s: %s", backend_type, display_name, e)

    return display_name


def stream_llm_response(
    messages: List[dict],
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    account_email: str | None = None,
    backend: str | None = None,
    cwd: str | None = None,
    chat_mode: str | None = None,
) -> Generator[str, None, None]:
    """Stream an LLM response token by token.

    Priority order (adjusted when account_email is set):
    1. Work mode with cwd — forces CLI subprocess with cwd
    2. Explicit api_base/api_key args (proxy mode)
    3. CLIProxyAPI (managed or auto-detected) — required when account_email is set
    4. ANTHROPIC_API_KEY env var (direct API, no account routing, Claude only)
    5. Claude CLI subprocess fallback (Claude only)

    When ``account_email`` is specified, CLIProxyAPI is tried before direct API
    because account routing only works through the proxy's X-Account-Email header.

    Args:
        cwd: Optional working directory for CLI subprocess (work mode).
        chat_mode: Optional chat mode ('management' or 'work').

    Yields:
        Text chunks as they arrive from the LLM.
    """
    effective_backend = backend or "claude"
    if model:
        resolved_model = _resolve_display_model(model, effective_backend)
    else:
        resolved_model = _get_default_model(effective_backend)
    resolved_base = api_base or os.environ.get("ANTHROPIC_API_BASE", "").strip()
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "").strip()

    # Work mode: project context is already in the system prompt via assemble_system_prompt.
    # Use the normal routing (CLIProxy for real-time streaming) rather than forcing CLI
    # subprocess, which only outputs the complete response (no token-by-token streaming).
    # The cwd parameter is logged for debugging but routing follows normal priority.
    if chat_mode == "work" and cwd:
        logger.info(
            "Work mode active (cwd=%s) — using normal streaming with project context in prompt",
            cwd,
        )

    # OpenCode backend ALWAYS uses the OpenCode CLI.
    # OpenCode models use provider/model format (e.g. zhipu/glm-5-free) which
    # CLIProxyAPI doesn't understand. The OpenCode CLI handles its own routing.
    if effective_backend == "opencode":
        logger.info(
            "Streaming via OpenCode CLI (backend=%s, model=%s)", effective_backend, resolved_model
        )
        yield from _stream_via_opencode_cli(messages, resolved_model)
        return

    # 1. Explicit api_base — proxy mode (supports account routing)
    if resolved_base:
        logger.info("Streaming via LiteLLM proxy at %s", resolved_base)
        yield from _stream_via_proxy(
            messages, resolved_model, resolved_base, resolved_key, account_email
        )
        return

    # 2. CLIProxyAPI (managed or auto-detected) — try BEFORE direct API key
    #    because account routing via X-Account-Email only works through the proxy.
    proxy_result = _find_cliproxy()
    if proxy_result:
        proxy_base, proxy_key = proxy_result
        yield from _stream_via_proxy_with_fallback(
            messages,
            resolved_model,
            proxy_base,
            proxy_key,
            account_email,
            effective_backend,
        )
        return

    # Codex/Gemini require CLIProxyAPI — no fallback
    if effective_backend not in ("claude",):
        logger.error("CLIProxyAPI not available for %s backend", effective_backend)
        yield f"\n\n[Error: CLIProxyAPI not running. {effective_backend} requires CLIProxyAPI.]"
        return

    # 3. Direct API key (no proxy — account_email cannot be used here, Claude only)
    if resolved_key:
        if account_email:
            logger.warning(
                "account_email=%s specified but no CLIProxyAPI available; "
                "falling back to direct API (account selection ignored)",
                account_email,
            )
        logger.info("Streaming via LiteLLM direct API")
        yield from _stream_via_litellm(messages, resolved_model, resolved_key)
        return

    # 4. CLI subprocess fallback (Claude only)
    logger.info("Streaming via Claude CLI subprocess")
    yield from _stream_via_cli(messages, resolved_model)


def _extract_proxy_error(raw: bytes, status_code: int) -> str:
    """Extract a human-readable error message from a proxy error response.

    The CLIProxyAPI proxy sometimes embeds gzip-compressed upstream error
    bodies inside its own JSON error response. When Go's json.Marshal
    serializes these binary bytes, it replaces invalid UTF-8 sequences with
    U+FFFD, making the original gzip content irrecoverable. This function
    detects that case and falls back to structured error fields or the HTTP
    status code.
    """
    # Case 1: Entire body is gzip-compressed
    if raw[:2] == b"\x1f\x8b":
        try:
            decompressed = gzip.decompress(raw)
            try:
                err = json.loads(decompressed)
                return err.get("error", {}).get("message", decompressed.decode("utf-8")[:200])
            except Exception as e:
                logger.debug("Gzip JSON parse: %s", e)
                return decompressed.decode("utf-8", errors="replace")[:200]
        except Exception as e:
            logger.debug("Gzip decompress: %s", e)
            return f"HTTP {status_code} (compressed error, unable to decode)"

    # Case 2: JSON response — parse with lossy decode if needed
    err = None
    for attempt_bytes in [True, False]:
        try:
            err = (
                json.loads(raw)
                if attempt_bytes
                else json.loads(raw.decode("utf-8", errors="replace"))
            )
            break
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            continue

    if isinstance(err, dict):
        error_obj = err.get("error", {}) if isinstance(err.get("error"), dict) else {}
        msg = error_obj.get("message", "")
        error_type = error_obj.get("type", "")

        # Check if the message is readable (not garbled binary).
        # U+FFFD and control chars (except \n\r\t) indicate binary data.
        if msg and _is_readable(msg):
            return msg

        # Message is garbled — use type/code or status code
        if error_type:
            return f"{error_type} (HTTP {status_code})"
        return f"HTTP {status_code}"

    # Case 3: Plain-text body
    body = raw.decode("utf-8", errors="replace")
    if body.strip() and _is_readable(body):
        return body[:200]

    return f"HTTP {status_code}"


def _is_readable(text: str) -> bool:
    """Return True if text looks like human-readable content, not garbled binary."""
    sample = text[:100]
    if not sample:
        return False
    bad = sum(1 for c in sample if c == "\ufffd" or (ord(c) < 32 and c not in "\n\r\t"))
    return bad / len(sample) < 0.1


def _select_streaming_account(
    backend_type: str,
    account_email: str | None,
    tried_ids: set[int] | None = None,
) -> Optional[dict]:
    """Select the best account for streaming, using the existing scheduler/rate-limit infra.

    Mirrors OrchestrationService._select_account logic:
    - If account_email specified, find that account and check eligibility
    - Otherwise, pick_best_account excluding already-tried IDs
    Returns account dict or None.
    """
    from ..db.backends import get_accounts_for_backend_type
    from .agent_scheduler_service import AgentSchedulerService
    from .rate_limit_service import RateLimitService

    tried = tried_ids or set()

    if account_email:
        accounts = get_accounts_for_backend_type(backend_type)
        account = next((a for a in accounts if a.get("email") == account_email), None)
        if not account or account["id"] in tried:
            return None
        eligibility = AgentSchedulerService.check_eligibility(account["id"])
        if not eligibility["eligible"]:
            return None
        if RateLimitService.is_rate_limited(account["id"]):
            return None
        return account

    # Auto-select: pick_best_account already filters rate-limited, but also skip tried
    accounts = get_accounts_for_backend_type(backend_type)
    for acct in accounts:
        if acct["id"] in tried:
            continue
        if RateLimitService.is_rate_limited(acct["id"]):
            continue
        eligibility = AgentSchedulerService.check_eligibility(acct["id"])
        if not eligibility["eligible"]:
            continue
        return acct
    return None


def _stream_via_proxy_with_fallback(
    messages: List[dict],
    model: str,
    proxy_base: str,
    proxy_key: str,
    account_email: str | None,
    backend_type: str,
) -> Generator[str, None, None]:
    """Stream via proxy with automatic account fallback on rate limit or auth error.

    Uses RateLimitService + AgentSchedulerService (same infra as OrchestrationService)
    to select accounts and mark rate-limited ones. On 429/401/403, marks the account
    and retries with the next eligible account.
    """
    from .rate_limit_service import RateLimitService

    tried_ids: set[int] = set()

    # Initial account selection
    account = _select_streaming_account(backend_type, account_email)
    current_email = account["email"] if account else account_email

    while True:
        if account:
            tried_ids.add(account["id"])

        logger.info(
            "Streaming via CLIProxyAPI at %s (backend=%s, account=%s)",
            proxy_base,
            backend_type,
            current_email,
        )

        try:
            yield from _stream_via_proxy(messages, model, proxy_base, proxy_key, current_email)
            return
        except ProxyAccountError as e:
            logger.warning(
                "Account %s failed (HTTP %d): %s — trying fallback",
                current_email,
                e.status_code,
                e.detail,
            )
            if account:
                # 429 = rate limit cooldown; 401/403 = longer cooldown (expired token)
                cooldown = 300 if e.status_code == 429 else 3600
                RateLimitService.mark_rate_limited(account["id"], cooldown)

            # Try next eligible account
            account = _select_streaming_account(backend_type, None, tried_ids)
            if account:
                current_email = account["email"]
                logger.info("Falling back to account %s", current_email)
                continue

            yield (
                f"\n\n[All {backend_type} accounts are unavailable "
                f"(rate-limited or auth expired). Please try again later.]"
            )
            return


def _stream_via_proxy(
    messages: List[dict],
    model: str,
    api_base: str,
    api_key: str,
    account_email: str | None = None,
) -> Generator[str, None, None]:
    """Stream via httpx through a CLIProxyAPI OpenAI-compatible proxy.

    Uses httpx directly (instead of litellm) for proxy calls to avoid
    gzip-encoded error responses that litellm/OpenAI SDK can't decode.
    """
    import httpx

    url = f"{api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key or 'not-needed'}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        # Do NOT set Accept-Encoding: identity — the proxy may send gzip
        # regardless, and httpx auto-decompresses when it negotiates encoding.
    }
    if account_email:
        headers["X-Account-Email"] = account_email

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }

    try:
        with httpx.stream("POST", url, json=payload, headers=headers, timeout=120) as response:
            if response.status_code != 200:
                raw = response.read()
                error_detail = _extract_proxy_error(raw, response.status_code)
                logger.error("Proxy error %d: %s", response.status_code, error_detail)
                # v0.7.89 — dump the request shape on the
                # "text content blocks must be non-empty" class
                # of errors so we can locate the empty-content
                # bug at its source. The v0.7.80 defense filter
                # excludes None/whitespace content, but a payload
                # with whitespace-only content nested inside an
                # array would still slip past. Logged once per
                # occurrence at WARNING so it shows up in deploy
                # logs without spamming production.
                if "content block" in error_detail.lower():
                    debug_messages = []
                    for i, m in enumerate(payload.get("messages") or []):
                        content = m.get("content")
                        debug_messages.append(
                            {
                                "idx": i,
                                "role": m.get("role"),
                                "content_type": type(content).__name__,
                                "content_len": (
                                    len(content) if isinstance(content, (str, list)) else None
                                ),
                                "content_repr": repr(content)[:240],
                            }
                        )
                    logger.warning(
                        "Empty-content-block proxy error — request shape: model=%s, messages=%s",
                        payload.get("model"),
                        debug_messages,
                    )

                # Account-level errors — raise so caller can try another account
                if response.status_code in (429, 401, 403) or "rate" in error_detail.lower():
                    raise ProxyAccountError(error_detail, response.status_code, account_email)

                # Detect "unknown provider" and guide the user to register the backend
                if "unknown provider" in error_detail.lower():
                    # User-facing "Run: cliproxyapi <flag>" guidance — keep aligned
                    # with ai-accounts' real flags. "gemini" = Antigravity, so it is
                    # ``-antigravity-login`` (NOT the retired ``--login``).
                    _LOGIN_FLAGS = {
                        "codex": "--codex-device-login",
                        "gemini": "-antigravity-login",
                        "kimi": "-kimi-login",
                        "qwen": "--qwen-login",
                    }
                    # Extract backend from model name prefix
                    hint_backend = None
                    for prefix, flag in [
                        ("gpt", "codex"),
                        ("codex", "codex"),
                        ("gemini", "gemini"),
                        ("opencode", "opencode"),
                    ]:
                        if model.lower().startswith(prefix):
                            hint_backend = flag
                            break
                    if hint_backend == "opencode":
                        yield (
                            "\n\n[Error: OpenCode native models cannot be routed through "
                            "CLIProxyAPI. This is an internal routing error — please report it.]"
                        )
                    elif hint_backend:
                        login_flag = _LOGIN_FLAGS.get(hint_backend, "")
                        yield (
                            f"\n\n[Error: {hint_backend.capitalize()} is not registered in CLIProxyAPI. "
                            f"Run: cliproxyapi {login_flag}]"
                        )
                    else:
                        yield f"\n\n[Proxy error: {error_detail}]"
                else:
                    yield f"\n\n[Proxy error: {error_detail}]"
                return

            # Accumulator for OpenAI tool_calls — the protocol streams
            # tool-call ``arguments`` as JSON fragments across multiple
            # deltas, so we buffer per-index and emit a ToolUseEvent
            # only once the call is complete (arguments parse as JSON).
            tool_buffers: dict[int, dict[str, Any]] = {}

            def _flush_tool(idx: int):
                buf = tool_buffers.get(idx)
                if not buf or not buf.get("name"):
                    return None
                raw_args = buf.get("arguments") or ""
                try:
                    parsed = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    parsed = raw_args  # surface fragment as-is
                return ToolUseEvent(
                    name=buf["name"],
                    input=parsed,
                    id=buf.get("id"),
                )

            for line in response.iter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        # Flush any pending tool calls (model finished
                        # streaming arguments without an explicit close).
                        for idx in list(tool_buffers.keys()):
                            evt = _flush_tool(idx)
                            if evt is not None:
                                yield evt
                        tool_buffers.clear()
                        break
                    try:
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content

                        # OpenAI / CLIProxyAPI tool-call deltas: each
                        # entry has an index, may carry function name +
                        # streaming arguments fragments.
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            buf = tool_buffers.setdefault(idx, {})
                            if tc.get("id"):
                                buf["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                buf["name"] = fn["name"]
                            if fn.get("arguments"):
                                buf["arguments"] = buf.get("arguments", "") + fn["arguments"]

                        # finish_reason=tool_calls or stop → flush
                        finish_reason = choices[0].get("finish_reason")
                        if finish_reason in ("tool_calls", "stop") and tool_buffers:
                            for idx in list(tool_buffers.keys()):
                                evt = _flush_tool(idx)
                                if evt is not None:
                                    yield evt
                            tool_buffers.clear()
                    except json.JSONDecodeError:
                        continue

    except httpx.TimeoutException:
        logger.error("Proxy request timed out at %s", api_base, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="proxy_error", message=f"Proxy request timed out at {api_base}")
        yield "\n\n[Proxy request timed out]"
    except httpx.ConnectError:
        logger.error("Could not connect to proxy at %s", api_base, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="proxy_error", message=f"Could not connect to proxy at {api_base}")
        yield f"\n\n[Could not connect to proxy at {api_base}]"
    except Exception as exc:
        logger.error("Proxy streaming error: %s", exc, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="proxy_error", message=str(exc))
        yield f"\n\n[Streaming error: {exc}]"


def _stream_via_litellm(
    messages: List[dict],
    model: str,
    api_key: str,
) -> Generator[str, None, None]:
    """Stream via LiteLLM directly with an Anthropic API key."""
    try:
        import litellm

        litellm.suppress_debug_info = True

        response = litellm.completion(
            model=model,
            messages=messages,
            stream=True,
            api_key=api_key,
        )

        for chunk in response:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue

            choice = choices[0]
            delta = getattr(choice, "delta", None)

            if delta and getattr(delta, "content", None):
                yield delta.content

    except Exception as exc:
        logger.error("LiteLLM streaming error: %s", exc, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="streaming_error", message=str(exc))
        yield f"\n\n[Streaming error: {exc}]"


def _stream_via_cli(
    messages: List[dict],
    model: str,
    cwd: str | None = None,
) -> Generator[str, None, None]:
    """Stream via Claude CLI with --output-format stream-json --verbose.

    Last-resort fallback when no API base or key is configured.

    Args:
        cwd: Optional working directory for the subprocess.
    """
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            prompt_parts.append(f"System: {content}")
        elif role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    prompt = "\n\n".join(prompt_parts)

    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]

    # Phase 24 (24-fix, crit 6): wrap AND enforce the launch gate with the REAL
    # sandboxed flag BEFORE Popen (a bare wrap ignored the flag). A require-sandbox
    # / deny policy refuses the spawn (fail closed). No-op unless AGENTED_SANDBOX.
    from .policy_service import PolicyDenied
    from .sandbox_wrap import apply_sandbox_and_enforce

    try:
        cmd, _sandboxed = apply_sandbox_and_enforce(
            cmd, cwd, session_id="", backend="claude", net=True
        )
    except PolicyDenied as exc:
        reason = (getattr(exc, "verdict", None) or {}).get("reason") or "policy denied"
        yield f"[Error: launch blocked by policy: {reason}]"
        return

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=cwd,
            # Own process group so a timeout/disconnect can kill tool
            # grandchildren too (03 H1).
            start_new_session=True,
        )

        timed_out = False

        def _on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            _terminate_proc_group(proc)

        timer = threading.Timer(SUBPROCESS_TIMEOUT, _on_timeout)
        timer.start()

        completed = False
        try:
            while True:
                if timed_out:
                    break

                raw_line = proc.stdout.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Tool-use blocks land alongside text in the same event;
                # yield them as typed ToolUseEvent so the chat streaming
                # helper can dispatch a separate ChatStateService delta.
                for tu in _extract_tool_uses_from_event(event):
                    yield tu

                text = _extract_text_from_event(event)
                if text:
                    yield text

            proc.wait()
            completed = True
        finally:
            # Always disarm the timer; on an abandoned generator (SSE client
            # disconnect → GeneratorExit) tear down the orphaned process group
            # and pipes instead of leaking them for the full timeout (03 H1).
            timer.cancel()
            if not completed:
                _terminate_proc_group(proc)
                for stream in (proc.stdout, proc.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except OSError:
                        pass

        if timed_out:
            yield "\n\n[Request timed out]"
            return

        if proc.returncode != 0:
            stderr_output = ""
            try:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                logger.debug("Stderr read: %s", e)
            logger.error(
                "Claude CLI error (rc=%d): %s", proc.returncode, stderr_output, exc_info=True
            )
            # Show the actual error — not a useless apology
            detail = stderr_output[:200] if stderr_output else f"exit code {proc.returncode}"
            yield f"\n\n[Claude CLI error: {detail}]"

    except FileNotFoundError:
        logger.error("Claude CLI not found", exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="cli_error", message="Claude CLI not found")
        yield "[Error: Claude CLI not found. Please install Claude Code CLI.]"
    except Exception as exc:
        logger.error("CLI streaming error: %s", exc, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="cli_error", message=str(exc))
        yield f"[Error: {exc}]"


def _stream_via_opencode_cli(
    messages: List[dict],
    model: str,
    cwd: str | None = None,
) -> Generator[str, None, None]:
    """Stream via OpenCode CLI for native opencode models.

    OpenCode native models are only accessible through the ``opencode`` CLI,
    not through CLIProxyAPI.

    Args:
        cwd: Optional working directory for the subprocess.
    """
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            prompt_parts.append(f"System: {content}")
        elif role == "user":
            prompt_parts.append(content)
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    prompt = "\n\n".join(prompt_parts)

    # opencode run takes message as positional arg, model in provider/model format
    cmd = ["opencode", "run", prompt, "--model", model]

    # Phase 24 (24-fix, crit 6): wrap AND enforce the launch gate with the REAL
    # sandboxed flag BEFORE Popen (a bare wrap ignored the flag). A require-sandbox
    # / deny policy refuses the spawn (fail closed). No-op unless AGENTED_SANDBOX.
    from .policy_service import PolicyDenied
    from .sandbox_wrap import apply_sandbox_and_enforce

    try:
        cmd, _sandboxed = apply_sandbox_and_enforce(
            cmd, cwd, session_id="", backend="opencode", net=True
        )
    except PolicyDenied as exc:
        reason = (getattr(exc, "verdict", None) or {}).get("reason") or "policy denied"
        yield f"[Error: launch blocked by policy: {reason}]"
        return

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            cwd=cwd,
            start_new_session=True,  # killable process group (03 H1)
        )

        timed_out = False

        def _on_timeout() -> None:
            nonlocal timed_out
            timed_out = True
            _terminate_proc_group(proc)

        timer = threading.Timer(SUBPROCESS_TIMEOUT, _on_timeout)
        timer.start()

        completed = False
        try:
            # Read stdout line-by-line. OpenCode outputs the response as text.
            while True:
                if timed_out:
                    break

                raw_line = proc.stdout.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace")
                if line:
                    # Try parsing as JSON (opencode --format json)
                    stripped = line.strip()
                    if stripped.startswith("{"):
                        try:
                            data = json.loads(stripped)
                            # OpenCode JSON output may have "output"/"result" key
                            text = (
                                data.get("output") or data.get("result") or data.get("content", "")
                            )
                            if text:
                                yield text
                                continue
                        except json.JSONDecodeError:
                            pass  # Intentionally silenced: malformed data handled gracefully
                    # Plain text output — yield directly
                    yield line

            proc.wait()
            completed = True
        finally:
            timer.cancel()
            if not completed:
                _terminate_proc_group(proc)
                for stream in (proc.stdout, proc.stderr):
                    try:
                        if stream is not None:
                            stream.close()
                    except OSError:
                        pass

        if timed_out:
            yield "\n\n[Request timed out]"
            return

        if proc.returncode != 0:
            stderr_output = ""
            try:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                logger.debug("Stderr read: %s", e)
            logger.error(
                "OpenCode CLI error (rc=%d): %s", proc.returncode, stderr_output, exc_info=True
            )
            detail = stderr_output[:200] if stderr_output else f"exit code {proc.returncode}"
            yield f"\n\n[OpenCode CLI error: {detail}]"

    except FileNotFoundError:
        logger.error("OpenCode CLI not found", exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="cli_error", message="OpenCode CLI not found")
        yield "[Error: OpenCode CLI not found. Please install OpenCode.]"
    except Exception as exc:
        logger.error("OpenCode CLI streaming error: %s", exc, exc_info=True)
        from app.services.error_capture import capture_error

        capture_error(category="cli_error", message=str(exc))
        yield f"[Error: {exc}]"


def _extract_text_from_event(event: dict) -> Optional[str]:
    """Extract text from a Claude CLI stream-json NDJSON event."""
    event_type = event.get("type", "")

    # stream_event wrapper (older CLI format)
    if event_type == "stream_event":
        inner = event.get("event", {})
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")

    # Direct content_block_delta
    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text", "")

    # "assistant" message event (current CLI format) — extract text from content blocks
    if event_type == "assistant":
        message = event.get("message", {})
        content_blocks = message.get("content", [])
        texts = []
        for block in content_blocks:
            if block.get("type") == "text" and block.get("text"):
                texts.append(block["text"])
        if texts:
            return "".join(texts)

    # "result" event (terminal turn summary) — DO NOT emit its text.
    # In ``--output-format stream-json --verbose`` the answer has already
    # been streamed via ``assistant`` / ``content_block_delta`` events; the
    # ``result`` field merely echoes that same complete text. Both streaming
    # loops accumulate every non-None yield, so returning it here appended
    # the whole reply a second time — the "response shown twice in one
    # bubble" bug. Treat ``result`` as terminal metadata only.
    if event_type == "result":
        return None

    return None


def _extract_tool_uses_from_event(event: dict) -> list[ToolUseEvent]:
    """Surface ``tool_use`` content blocks from Claude stream-json
    events. The CLI emits one assistant event per turn whose
    ``message.content`` may contain a mix of text + tool_use blocks
    (the latter when the agent calls one of its MCP tools).

    Returns the list in event order so the caller can yield each one
    in sequence; an empty list when no tool_use is present.
    """
    out: list[ToolUseEvent] = []
    event_type = event.get("type", "")

    candidates: list[dict] = []
    if event_type == "assistant":
        message = event.get("message", {})
        candidates = message.get("content") or []
    elif event_type == "stream_event":
        # content_block_start with type=tool_use carries the block
        inner = event.get("event", {})
        if inner.get("type") == "content_block_start":
            block = inner.get("content_block", {})
            if block.get("type") == "tool_use":
                candidates = [block]

    for block in candidates:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if not isinstance(name, str):
            continue
        out.append(
            ToolUseEvent(
                name=name,
                input=block.get("input") or {},
                id=block.get("id"),
            )
        )
    return out
