"""Tests for ``drop_empty_content_messages`` — the shared filter
the six conversation-streaming sites use to keep empty text
content blocks from reaching CLIProxyAPI.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.conversation_filters import drop_empty_content_messages


@dataclass
class _Msg:
    role: str
    content: object


def test_filters_empty_whitespace_and_none():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "   \n\t  "},
        {"role": "assistant", "content": "world"},
        {"role": "tool", "content": None},
        {"role": "user", "content": "ok"},
    ]
    assert [m["content"] for m in drop_empty_content_messages(msgs)] == [
        "hello",
        "world",
        "ok",
    ]


def test_accepts_objects_with_role_and_content_attributes():
    msgs = [_Msg("user", "a"), _Msg("assistant", "  "), _Msg("user", "b")]
    out = drop_empty_content_messages(msgs)
    assert out == [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "b"},
    ]


def test_rejects_non_string_content():
    # A multimodal list shape is rejected — current SuperAgent /
    # plugin / skill / agent / base / grd flows all assign string
    # content; a list here is more likely a serializer bug than a
    # legitimate value.
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "user", "content": "real string"},
    ]
    assert drop_empty_content_messages(msgs) == [{"role": "user", "content": "real string"}]


def test_default_role_is_user_when_missing():
    msgs = [{"content": "no role here"}]
    assert drop_empty_content_messages(msgs) == [{"role": "user", "content": "no role here"}]


def test_empty_input_returns_empty_list():
    assert drop_empty_content_messages([]) == []
    assert drop_empty_content_messages(iter([])) == []
