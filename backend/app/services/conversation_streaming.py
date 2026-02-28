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
import subprocess
import threading
from pathlib import Path
from typing import Generator, List, Optional

import yaml

logger = logging.getLogger(__name__)

SUBPROCESS_TIMEOUT = 120

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
) -> Generator[str, None, None]:
    """Stream an LLM response token by token.

    Priority order (adjusted when account_email is set):
    1. Explicit api_base/api_key args (proxy mode)
    2. CLIProxyAPI (managed or auto-detected) — required when account_email is set
    3. ANTHROPIC_API_KEY env var (direct API, no account routing, Claude only)
    4. Claude CLI subprocess fallback (Claude only)

    When ``account_email`` is specified, CLIProxyAPI is tried before direct API
    because account routing only works through the proxy's X-Account-Email header.

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
        logger.info(
            "Streaming via CLIProxyAPI at %s (backend=%s, account=%s, msg_count=%d, roles=%s)",
            proxy_base,
            effective_backend,
            account_email,
            len(messages),
            [m.get("role") for m in messages],
        )
        yield from _stream_via_proxy(messages, resolved_model, proxy_base, proxy_key, account_email)
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

                # Detect "unknown provider" and guide the user to register the backend
                if "unknown provider" in error_detail.lower():
                    _LOGIN_FLAGS = {
                        "codex": "--codex-login",
                        "gemini": "--login",
                        "kimi": "--kimi-login",
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

            for line in response.iter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue

    except httpx.TimeoutException:
        logger.error("Proxy request timed out at %s", api_base)
        yield "\n\n[Proxy request timed out]"
    except httpx.ConnectError:
        logger.error("Could not connect to proxy at %s", api_base)
        yield f"\n\n[Could not connect to proxy at {api_base}]"
    except Exception as exc:
        logger.error("Proxy streaming error: %s", exc)
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
        logger.error("LiteLLM streaming error: %s", exc)
        yield f"\n\n[Streaming error: {exc}]"


def _stream_via_cli(
    messages: List[dict],
    model: str,
) -> Generator[str, None, None]:
    """Stream via Claude CLI with --output-format stream-json --verbose.

    Last-resort fallback when no API base or key is configured.
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

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        timed_out = False

        def _on_timeout():
            nonlocal timed_out
            timed_out = True
            try:
                proc.kill()
            except OSError:
                pass

        timer = threading.Timer(SUBPROCESS_TIMEOUT, _on_timeout)
        timer.start()

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

            text = _extract_text_from_event(event)
            if text:
                yield text

        proc.wait()
        timer.cancel()

        if timed_out:
            yield "\n\n[Request timed out]"
            return

        if proc.returncode != 0:
            stderr_output = ""
            try:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                logger.debug("Stderr read: %s", e)
            logger.error("Claude CLI error (rc=%d): %s", proc.returncode, stderr_output)
            # Show the actual error — not a useless apology
            detail = stderr_output[:200] if stderr_output else f"exit code {proc.returncode}"
            yield f"\n\n[Claude CLI error: {detail}]"

    except FileNotFoundError:
        logger.error("Claude CLI not found")
        yield "[Error: Claude CLI not found. Please install Claude Code CLI.]"
    except Exception as exc:
        logger.error("CLI streaming error: %s", exc)
        yield f"[Error: {exc}]"


def _stream_via_opencode_cli(
    messages: List[dict],
    model: str,
) -> Generator[str, None, None]:
    """Stream via OpenCode CLI for native opencode/* models.

    OpenCode native models (e.g. opencode/big-pickle) are only accessible
    through the ``opencode`` CLI, not through CLIProxyAPI.
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

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        timed_out = False

        def _on_timeout():
            nonlocal timed_out
            timed_out = True
            try:
                proc.kill()
            except OSError:
                pass

        timer = threading.Timer(SUBPROCESS_TIMEOUT, _on_timeout)
        timer.start()

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
                        # OpenCode JSON output may have "output" or "result" key
                        text = data.get("output") or data.get("result") or data.get("content", "")
                        if text:
                            yield text
                            continue
                    except json.JSONDecodeError:
                        pass
                # Plain text output — yield directly
                yield line

        proc.wait()
        timer.cancel()

        if timed_out:
            yield "\n\n[Request timed out]"
            return

        if proc.returncode != 0:
            stderr_output = ""
            try:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                logger.debug("Stderr read: %s", e)
            logger.error("OpenCode CLI error (rc=%d): %s", proc.returncode, stderr_output)
            detail = stderr_output[:200] if stderr_output else f"exit code {proc.returncode}"
            yield f"\n\n[OpenCode CLI error: {detail}]"

    except FileNotFoundError:
        logger.error("OpenCode CLI not found")
        yield "[Error: OpenCode CLI not found. Please install OpenCode.]"
    except Exception as exc:
        logger.error("OpenCode CLI streaming error: %s", exc)
        yield f"[Error: {exc}]"


def _extract_text_from_event(event: dict) -> Optional[str]:
    """Extract text from a Claude CLI stream-json NDJSON event."""
    event_type = event.get("type", "")

    if event_type == "stream_event":
        inner = event.get("event", {})
        if inner.get("type") == "content_block_delta":
            delta = inner.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")

    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return delta.get("text", "")

    return None
