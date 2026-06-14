"""Regression tests for SketchRoutingService LLM classification fallback.

Root cause of err-h1xhkn / err-0keieo / err-ctdi9m: the LLM proxy
(model ``openai/claude-sonnet-4-20250514`` via CLIProxy) can return an
empty or non-JSON body. The old code called ``json.loads("")`` which
raised ``JSONDecodeError: Expecting value: line 1 column 1 (char 0)``,
which the broad ``except Exception`` captured as a ``runtime_error`` on
every single call. An empty/prose reply is an *expected* outcome and must
fall back to keyword classification silently.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import litellm

from app.services.sketch_routing_service import SketchRoutingService


def _fake_response(content):
    """Build a minimal litellm-completion-shaped response."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _patch_completion(monkeypatch, content):
    monkeypatch.setattr(litellm, "completion", lambda **kw: _fake_response(content))


def _spy_capture(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr("app.services.error_capture.capture_error", spy)
    return spy


def test_empty_llm_body_falls_back_without_capturing_error(monkeypatch):
    """An empty proxy reply must NOT capture a runtime_error (the original bug)."""
    _patch_completion(monkeypatch, "")
    spy = _spy_capture(monkeypatch)

    result = SketchRoutingService._llm_classify("build a login api")

    assert result is None
    spy.assert_not_called()


def test_none_llm_body_falls_back_without_capturing_error(monkeypatch):
    """A None content (no message body at all) must also fall back silently."""
    _patch_completion(monkeypatch, None)
    spy = _spy_capture(monkeypatch)

    result = SketchRoutingService._llm_classify("build a login api")

    assert result is None
    spy.assert_not_called()


def test_prose_llm_body_falls_back_without_capturing_error(monkeypatch):
    """Non-JSON prose must fall back silently rather than crash json.loads."""
    _patch_completion(monkeypatch, "Sorry, I can't classify that.")
    spy = _spy_capture(monkeypatch)

    result = SketchRoutingService._llm_classify("build a login api")

    assert result is None
    spy.assert_not_called()


def test_fenced_json_is_extracted(monkeypatch):
    """A Markdown-fenced JSON object is parsed and returned."""
    body = (
        "```json\n"
        '{"phase": "execution", "domains": ["backend"], '
        '"complexity": "medium", "confidence": 0.9}\n'
        "```"
    )
    _patch_completion(monkeypatch, body)
    spy = _spy_capture(monkeypatch)

    result = SketchRoutingService._llm_classify("build a login api")

    assert result == {
        "phase": "execution",
        "domains": ["backend"],
        "complexity": "medium",
        "confidence": 0.9,
    }
    spy.assert_not_called()


def test_real_proxy_error_is_still_captured(monkeypatch):
    """A genuine completion failure must still be captured (not swallowed)."""

    def _boom(**kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(litellm, "completion", _boom)
    spy = _spy_capture(monkeypatch)

    result = SketchRoutingService._llm_classify("build a login api")

    assert result is None
    spy.assert_called_once()
    _, kwargs = spy.call_args
    assert kwargs["category"] == "runtime_error"
    assert "connection refused" in kwargs["message"]
