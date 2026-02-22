"""Chat streaming service through CLIProxyAPI.

Routes chat completion requests through a local CLIProxyAPI instance's
OpenAI-compatible endpoint via direct httpx streaming, yielding typed
``ChatDelta`` objects for content fragments, accumulated tool calls,
and finish signals.

Uses httpx directly (instead of litellm) for proxy calls to avoid
gzip-encoded error responses that litellm/OpenAI SDK can't decode.
LiteLLM is still used for the direct API path (``stream_chat_direct``).
"""

import json
import logging
import shutil
from typing import Generator

import httpx
import litellm

from ..models.chat_state import ChatDelta, ChatDeltaType
from .conversation_streaming import _extract_proxy_error

logger = logging.getLogger(__name__)


class CLIProxyChatService:
    """Stateless service for streaming chat completions through CLIProxyAPI."""

    @classmethod
    def stream_chat(
        cls,
        base_url: str,
        messages: list[dict],
        model: str = "auto",
        account_email: str | None = None,
    ) -> Generator[ChatDelta, None, None]:
        """Stream a chat completion and yield typed ``ChatDelta`` events.

        Args:
            base_url: CLIProxyAPI base URL (e.g. ``http://127.0.0.1:18301/v1``).
            messages: OpenAI-format message list.
            model: Model name routed through CLIProxyAPI (default ``"auto"``).
            account_email: Route to a specific CLIProxyAPI credential.

        Yields:
            ``ChatDelta`` objects — ``content_delta``, ``tool_call``, or
            ``finish``.

        Per Pitfall 5 from research: tool call argument chunks arrive as
        partial JSON fragments spread across multiple SSE chunks. We
        accumulate per ``tool_call.index`` until ``finish_reason`` signals
        completion, then yield a single ``tool_call`` delta with the
        complete arguments JSON.
        """
        # Accumulate tool_call argument fragments keyed by tc.index
        tool_call_buffers: dict[int, dict] = {}

        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": "Bearer not-needed",
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
                    yield ChatDelta(
                        type=ChatDeltaType.ERROR,
                        error_message=f"Proxy error: {error_detail}",
                    )
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
                        except json.JSONDecodeError:
                            continue

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason")

                        # --- Content fragment ---
                        content = delta.get("content")
                        if content:
                            yield ChatDelta(
                                type=ChatDeltaType.CONTENT_DELTA,
                                text=content,
                            )

                        # --- Tool call fragment ---
                        tool_calls = delta.get("tool_calls")
                        if tool_calls:
                            for tc in tool_calls:
                                idx = tc.get("index", 0)
                                if idx not in tool_call_buffers:
                                    tool_call_buffers[idx] = {
                                        "id": tc.get("id"),
                                        "function_name": None,
                                        "arguments": "",
                                    }
                                buf = tool_call_buffers[idx]
                                if tc.get("id"):
                                    buf["id"] = tc["id"]
                                func = tc.get("function", {})
                                if func.get("name"):
                                    buf["function_name"] = func["name"]
                                if func.get("arguments"):
                                    buf["arguments"] += func["arguments"]

                        # --- Finish ---
                        if finish_reason:
                            for _idx in sorted(tool_call_buffers):
                                buf = tool_call_buffers[_idx]
                                yield ChatDelta(
                                    type=ChatDeltaType.TOOL_CALL,
                                    tool_call_id=buf["id"],
                                    function_name=buf["function_name"],
                                    arguments_json=buf["arguments"] or None,
                                )
                            tool_call_buffers.clear()

                            yield ChatDelta(
                                type=ChatDeltaType.FINISH,
                                finish_reason=finish_reason,
                            )

        except httpx.TimeoutException:
            logger.error("Proxy request timed out at %s", base_url)
            yield ChatDelta(
                type=ChatDeltaType.ERROR,
                error_message="Proxy request timed out",
            )
        except httpx.ConnectError:
            logger.error("Could not connect to proxy at %s", base_url)
            yield ChatDelta(
                type=ChatDeltaType.ERROR,
                error_message=f"Could not connect to proxy at {base_url}",
            )
        except Exception as exc:
            logger.error("Unexpected error during chat streaming: %s", exc)
            yield ChatDelta(
                type=ChatDeltaType.ERROR,
                error_message=str(exc),
            )

    @classmethod
    def check_proxy_available(cls) -> bool:
        """Return ``True`` if the ``cliproxyapi`` binary is on PATH."""
        return shutil.which("cliproxyapi") is not None

    @classmethod
    def stream_chat_direct(
        cls,
        messages: list[dict],
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ) -> Generator[ChatDelta, None, None]:
        """Stream via LiteLLM directly without CLIProxyAPI.

        Uses the provided API key directly with LiteLLM, bypassing
        the CLIProxyAPI binary. Falls back to ANTHROPIC_API_KEY env var.
        """
        import os

        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            yield ChatDelta(
                type=ChatDeltaType.ERROR,
                error_message="No API key available for direct LiteLLM streaming",
            )
            return

        tool_call_buffers: dict[int, dict] = {}

        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                stream=True,
                api_key=resolved_key,
            )

            for chunk in response:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue

                choice = choices[0]
                delta = getattr(choice, "delta", None)
                finish_reason = getattr(choice, "finish_reason", None)

                if delta and getattr(delta, "content", None):
                    yield ChatDelta(
                        type=ChatDeltaType.CONTENT_DELTA,
                        text=delta.content,
                    )

                if delta and getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": getattr(tc, "id", None),
                                "function_name": None,
                                "arguments": "",
                            }
                        buf = tool_call_buffers[idx]
                        if getattr(tc, "id", None):
                            buf["id"] = tc.id
                        func = getattr(tc, "function", None)
                        if func:
                            if getattr(func, "name", None):
                                buf["function_name"] = func.name
                            if getattr(func, "arguments", None):
                                buf["arguments"] += func.arguments

                if finish_reason:
                    for _idx in sorted(tool_call_buffers):
                        buf = tool_call_buffers[_idx]
                        yield ChatDelta(
                            type=ChatDeltaType.TOOL_CALL,
                            tool_call_id=buf["id"],
                            function_name=buf["function_name"],
                            arguments_json=buf["arguments"] or None,
                        )
                    tool_call_buffers.clear()

                    yield ChatDelta(
                        type=ChatDeltaType.FINISH,
                        finish_reason=finish_reason,
                    )

        except litellm.exceptions.APIError as exc:
            logger.error("LiteLLM direct API error: %s", exc)
            yield ChatDelta(type=ChatDeltaType.ERROR, error_message=str(exc))
        except Exception as exc:
            logger.error("Unexpected error during direct chat streaming: %s", exc)
            yield ChatDelta(type=ChatDeltaType.ERROR, error_message=str(exc))
