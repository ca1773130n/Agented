"""PSM stream-json -> chat-SSE bridge loop (v0.8.0, REQ-11).

``bridge_psm_to_chat`` tails a GRD chat session's PSM stream-json
events and maps each onto the chat ``state_delta`` protocol that the
frontend already consumes, via ``ChatStateService.push_delta`` /
``push_status``.

CRITICAL — wire strings, not enum names. The frontend consumes the
raw wire strings ``content_delta`` / ``tool_use`` / ``finish`` /
``error`` (see 19-RESEARCH.md §3 + §10 risk 2). In particular tool
blocks map to the wire string ``tool_use``, NOT the ``ChatDeltaType``
enum member name ``tool_call``. Emitting the enum name here would
produce a silently-wrong stream the frontend ignores.

Mapping table:

    | PSM event              | push_delta / push_status                       |
    | ---------------------- | ---------------------------------------------- |
    | text / assistant token | ("content_delta", {"content": text})           |
    | tool_use block         | ("tool_use", tool_dict)                        |
    | result / end           | ("finish", {"finish_reason": ...})             |
    |                        |   + push_status(session_id, "complete")        |
    | error / abort          | ("error", {"error_message": ...})              |
    |                        |   + push_status(session_id, "error")           |

Event order is preserved 1:1 with the source iterator. The event
source is injectable (any iterable/generator of dicts) so tests feed
fake events without a real PSM, and so the production caller can pass
a tail of the PSM ring buffer / subscriber queue. Mirrors the
tail/teardown structure of ``goal_loop_runner.start_runner``.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _event_type(event: dict) -> str:
    """Classify a PSM stream-json event into one of our four buckets.

    Stream-json events vary in shape across CLI versions, so we sniff
    on the common keys rather than pinning one schema:
      * an explicit ``error``/``abort`` marker -> "error"
      * a terminal ``result``/``end`` marker  -> "finish"
      * a ``tool_use`` block                  -> "tool_use"
      * anything carrying text                 -> "content_delta"
    """
    etype = (event.get("type") or event.get("event") or "").lower()

    if etype in ("error", "abort") or event.get("error") or event.get("is_error"):
        return "error"
    if etype in ("result", "end", "finish", "done") or event.get("done"):
        return "finish"
    if etype in ("tool_use", "tool_call") or event.get("tool_use") or event.get("name"):
        return "tool_use"
    return "content_delta"


def _extract_text(event: dict) -> str:
    """Pull the assistant token/text out of a content event."""
    for key in ("content", "text", "delta", "token"):
        val = event.get(key)
        if isinstance(val, str):
            return val
    return ""


def _extract_tool(event: dict) -> dict:
    """Pull the tool-use payload out of a tool event.

    Prefer an explicit nested ``tool_use`` dict; otherwise pass the
    event's own tool-shaped fields through so the frontend gets the
    tool name + input.
    """
    tool = event.get("tool_use")
    if isinstance(tool, dict):
        return tool
    out: dict = {}
    for key in ("id", "name", "input", "arguments"):
        if key in event:
            out[key] = event[key]
    return out


def _extract_error(event: dict) -> str:
    """Pull a human-readable error message out of an error event."""
    for key in ("error_message", "error", "message"):
        val = event.get(key)
        if isinstance(val, str):
            return val
    return "GRD session error"


def _extract_finish_reason(event: dict) -> Optional[str]:
    """Pull the finish reason out of a terminal event."""
    for key in ("finish_reason", "reason", "result"):
        val = event.get(key)
        if isinstance(val, str):
            return val
    return "complete"


def bridge_psm_to_chat(
    session_id: str,
    psm_event_iter: Iterable[dict],
    chat_state_service,
) -> None:
    """Tail PSM stream-json events and bridge them to chat SSE deltas.

    Args:
        session_id: The chat session id to push deltas under.
        psm_event_iter: An iterable/generator of PSM stream-json event
            dicts (injectable so tests feed fakes without a real PSM).
        chat_state_service: ``ChatStateService`` (or a spy exposing
            ``push_delta`` / ``push_status``).

    Emits, in source order, one ``push_delta`` per event using the
    frontend wire strings, and a terminal ``push_status`` of
    ``complete`` (finish) or ``error`` (error/abort). Order is
    preserved 1:1 with the source.
    """
    terminated = False
    for event in psm_event_iter:
        kind = _event_type(event)

        if kind == "content_delta":
            chat_state_service.push_delta(
                session_id, "content_delta", {"content": _extract_text(event)}
            )
        elif kind == "tool_use":
            chat_state_service.push_delta(
                session_id, "tool_use", _extract_tool(event)
            )
        elif kind == "finish":
            chat_state_service.push_delta(
                session_id,
                "finish",
                {"finish_reason": _extract_finish_reason(event)},
            )
            chat_state_service.push_status(session_id, "complete")
            terminated = True
            break
        elif kind == "error":
            chat_state_service.push_delta(
                session_id, "error", {"error_message": _extract_error(event)}
            )
            chat_state_service.push_status(session_id, "error")
            terminated = True
            break

    # Teardown: if the source ran dry without a terminal marker, emit a
    # synthetic finish so the frontend's stream closes cleanly (mirrors
    # goal_loop_runner teardown — never leave the chat status hanging).
    if not terminated:
        chat_state_service.push_delta(
            session_id, "finish", {"finish_reason": "complete"}
        )
        chat_state_service.push_status(session_id, "complete")
