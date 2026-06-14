"""Reconstructed regression: `_llm_classify` falls back silently on an empty /
non-JSON / None LLM reply instead of crashing `json.loads` (or `.strip()` on a
None body).

Companion to test_sketch_routing_llm_fallback — both LLM-JSON parse paths now
route through ``utils.llm_json.extract_json_object``. (This test was lost with
the uncommitted edit and is reconstructed from the identical sketch-routing
pattern.)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services import turn_classifier_service as tc


def _resp(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _call(content):
    # _llm_classify does a LOCAL `import litellm`, so patch the real module's
    # completion (not a tc.litellm attr). _resolve_model is stubbed so the test
    # doesn't depend on model-resolution config.
    with (
        patch("litellm.completion", return_value=_resp(content)),
        patch.object(tc, "_resolve_model", return_value="m"),
    ):
        return tc._llm_classify("hi", backend_kind="claude", model_override="m")


def test_empty_reply_falls_back_to_none():
    assert _call("") is None


def test_none_body_does_not_crash():
    # The old code did `.content.strip()` → AttributeError on None.
    assert _call(None) is None


def test_prose_reply_falls_back_to_none():
    assert _call("Sure! I could not classify this.") is None


def test_fenced_json_is_parsed():
    out = _call('```json\n{"shape": "task", "intent": "build"}\n```')
    assert out == {"shape": "task", "intent": "build"}


def test_valid_json_object_is_parsed():
    out = _call('{"shape": "conversational", "intent": "chat"}')
    assert out == {"shape": "conversational", "intent": "chat"}


def test_missing_keys_falls_back_to_none():
    assert _call('{"shape": "task"}') is None
