"""Shared filters applied to message lists before they leave the
backend for CLIProxyAPI.

The proxy's OpenAI translation rejects empty text content blocks
with "text content blocks must be non-empty". Six callers built
their own ``if content and content.strip()`` filter against this
class of error; this module centralizes it so a new caller can't
silently introduce a regression of the same shape.
"""

from __future__ import annotations

from typing import Any, Iterable


def drop_empty_content_messages(
    messages: Iterable[Any],
) -> list[dict[str, str]]:
    """Yield ``{"role", "content"}`` dicts for every message whose
    ``content`` is a non-empty, non-whitespace string. Accepts
    either dicts (``{"role": ..., "content": ...}``) or objects
    with ``.role`` / ``.content`` attributes, so both
    ``conv["messages"]`` (in-memory ConversationMessage lists)
    and ``conversation_log`` (DB-persisted dict lists) flow
    through the same path.

    ``None`` content, empty strings, and whitespace-only strings
    are all dropped. Non-string content (e.g. a list of
    multimodal blocks) is rejected as well — current SuperAgent
    + plugin/skill/agent/base/grd flows all assign string content;
    a list-shaped content reaching this filter would more likely
    indicate a serializer bug than a legitimate value.
    """
    out: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append({"role": role, "content": content})
    return out
