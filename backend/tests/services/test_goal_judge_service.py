"""Tests for ``GoalJudgeService``.

Covers: deterministic check exit-0 / non-zero / timeout, LLM
judge response parsing (well-formed / malformed / fenced),
per-backend default model resolution, and the cost-telemetry
fields making it through to the verdict.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import goal_judge_service
from app.services.goal_judge_service import (
    DEFAULT_JUDGE_MODEL,
    GoalJudgeService,
    JudgeVerdict,
    _parse_judge_json,
)


# -----------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------


def test_parse_judge_json_bare_object():
    assert _parse_judge_json('{"met": true, "reason": "done"}') == (
        True,
        "done",
    )


def test_parse_judge_json_fenced():
    payload = """thinking aloud
```json
{"met": false, "reason": "tests still fail"}
```
trailing"""
    assert _parse_judge_json(payload) == (False, "tests still fail")


def test_parse_judge_json_with_preamble():
    payload = 'After review: {"met": true, "reason": "ok"} — full stop.'
    assert _parse_judge_json(payload) == (True, "ok")


def test_parse_judge_json_missing_met_key():
    assert _parse_judge_json('{"reason": "no verdict field"}') is None


def test_parse_judge_json_garbage():
    assert _parse_judge_json("just prose, no JSON anywhere") is None
    assert _parse_judge_json("") is None
    assert _parse_judge_json(None) is None  # type: ignore[arg-type]


def test_parse_judge_json_empty_reason_defaults():
    met, reason = _parse_judge_json('{"met": false, "reason": ""}')
    assert met is False
    assert reason == "(no reason given)"


def test_default_judge_model_covers_all_backends():
    # All four CLI backends Agented supports must have a per-kind
    # default. See feedback_llm_features_support_all_backends.
    assert set(DEFAULT_JUDGE_MODEL.keys()) == {
        "claude",
        "codex",
        "gemini",
        "opencode",
    }


# -----------------------------------------------------------------
# Deterministic check
# -----------------------------------------------------------------


def test_deterministic_exit_zero_is_met():
    v = GoalJudgeService.judge("any", "any", check_cmd="true")
    assert v.met is True
    assert v.source == "deterministic"
    assert "exited 0" in v.reason
    assert v.tokens_in == 0
    assert v.tokens_out == 0


def test_deterministic_exit_nonzero_is_not_met():
    v = GoalJudgeService.judge("any", "any", check_cmd="false")
    assert v.met is False
    assert v.source == "deterministic"
    assert "exited 1" in v.reason


def test_deterministic_captures_stdout(tmp_path):
    script = tmp_path / "say.sh"
    script.write_text("#!/bin/sh\necho 'check output here'\nexit 0\n")
    script.chmod(0o755)
    v = GoalJudgeService.judge("any", "any", check_cmd=str(script))
    assert v.met is True
    assert v.stdout is not None
    assert "check output here" in v.stdout


def test_deterministic_timeout_is_not_met(monkeypatch):
    # Use a 1ms timeout so even ``sleep 1`` blows the budget.
    monkeypatch.setattr(goal_judge_service, "_CHECK_TIMEOUT_SECONDS", 0.1)
    v = GoalJudgeService.judge("any", "any", check_cmd="sleep 5")
    assert v.met is False
    assert v.source == "deterministic"
    assert "timed out" in v.reason


def test_deterministic_bad_command_is_not_met():
    # Shell=True so a nonsense command runs through sh and fails
    # with a non-zero exit + stderr message.
    v = GoalJudgeService.judge("any", "any", check_cmd="this-binary-does-not-exist-12345")
    assert v.met is False
    assert v.source == "deterministic"


# -----------------------------------------------------------------
# LLM judge — mocked transport
# -----------------------------------------------------------------


def _install_mock_proxy(monkeypatch, response: httpx.Response):
    """Patch CLIProxyManager.get_url_and_key to return a fake
    healthy proxy URL, then patch httpx.post to return the given
    response without hitting the network.
    """
    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "not-needed")),
    )
    monkeypatch.setattr(
        goal_judge_service.httpx, "post", lambda *a, **kw: response
    )


def test_llm_judge_met_verdict(monkeypatch):
    body = {
        "choices": [
            {
                "message": {
                    "content": '{"met": true, "reason": "looks done"}',
                }
            }
        ],
        "usage": {"prompt_tokens": 42, "completion_tokens": 8},
    }
    _install_mock_proxy(monkeypatch, httpx.Response(200, json=body))
    v = GoalJudgeService.judge(
        "ship the feature",
        "I shipped it.",
        backend_kind="claude",
    )
    assert v.met is True
    assert v.source == "llm"
    assert v.reason == "looks done"
    assert v.tokens_in == 42
    assert v.tokens_out == 8


def test_llm_judge_not_met_verdict(monkeypatch):
    body = {
        "choices": [
            {"message": {"content": '{"met": false, "reason": "tests fail"}'}}
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10},
    }
    _install_mock_proxy(monkeypatch, httpx.Response(200, json=body))
    v = GoalJudgeService.judge("goal", "turn", backend_kind="codex")
    assert v.met is False
    assert v.reason == "tests fail"


def test_llm_judge_proxy_unreachable(monkeypatch):
    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: None),
    )
    v = GoalJudgeService.judge("g", "t")
    assert v.met is False
    assert "CLIProxyAPI not reachable" in v.reason


def test_llm_judge_unparseable_output_is_not_met(monkeypatch):
    body = {
        "choices": [{"message": {"content": "Sorry, no JSON for you."}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5},
    }
    _install_mock_proxy(monkeypatch, httpx.Response(200, json=body))
    v = GoalJudgeService.judge("g", "t")
    assert v.met is False
    assert v.source == "llm"
    assert "unparseable" in v.reason


def test_llm_judge_http_error(monkeypatch):
    _install_mock_proxy(monkeypatch, httpx.Response(500, content=b"oops"))
    v = GoalJudgeService.judge("g", "t")
    assert v.met is False
    assert "HTTP 500" in v.reason


def test_llm_judge_uses_per_backend_default_model(monkeypatch):
    captured: dict = {}

    def capture_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["model"] = json["model"]
        captured["backend_kind"] = json.get("metadata", {}).get("backend_kind")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"met": true, "reason": "ok"}'}}
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)

    for kind, expected_model in DEFAULT_JUDGE_MODEL.items():
        captured.clear()
        GoalJudgeService.judge("g", "t", backend_kind=kind)
        assert captured["model"] == expected_model
        assert captured["backend_kind"] == kind


def test_llm_judge_model_override_wins(monkeypatch):
    captured: dict = {}

    def capture_post(url, *, json, headers, timeout):
        captured["model"] = json["model"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"met": true, "reason": "ok"}'}}
                ],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)

    GoalJudgeService.judge(
        "g", "t", backend_kind="claude", model_override="claude-opus-4-7"
    )
    assert captured["model"] == "claude-opus-4-7"


def test_check_cmd_short_circuits_llm(monkeypatch):
    # When a check_cmd is supplied, the LLM judge MUST NOT be
    # called. Verify by failing loudly if httpx.post is reached.
    def explode(*a, **kw):
        raise AssertionError("LLM judge should not be called when check_cmd is set")

    monkeypatch.setattr(goal_judge_service.httpx, "post", explode)
    v = GoalJudgeService.judge("g", "t", check_cmd="true")
    assert v.met is True
    assert v.source == "deterministic"


def test_verdict_dataclass_defaults():
    v = JudgeVerdict(met=True, source="deterministic", reason="ok")
    assert v.stdout is None
    assert v.tokens_in == 0
    assert v.tokens_out == 0
    assert v.cost_usd == 0.0
