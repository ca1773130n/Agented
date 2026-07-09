"""Tests for ``GoalJudgeService``.

Covers: deterministic check exit-0 / non-zero / timeout, LLM
judge response parsing (well-formed / malformed / fenced),
per-backend default model resolution, and the cost-telemetry
fields making it through to the verdict.
"""

from __future__ import annotations

import httpx

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
        1.0,
    )


def test_parse_judge_json_fenced():
    payload = """thinking aloud
```json
{"met": false, "reason": "tests still fail"}
```
trailing"""
    assert _parse_judge_json(payload) == (False, "tests still fail", 1.0)


def test_parse_judge_json_with_preamble():
    payload = 'After review: {"met": true, "reason": "ok"} — full stop.'
    assert _parse_judge_json(payload) == (True, "ok", 1.0)


def test_parse_judge_json_missing_met_key():
    assert _parse_judge_json('{"reason": "no verdict field"}') is None


def test_parse_judge_json_garbage():
    assert _parse_judge_json("just prose, no JSON anywhere") is None
    assert _parse_judge_json("") is None
    assert _parse_judge_json(None) is None  # type: ignore[arg-type]


def test_parse_judge_json_empty_reason_defaults():
    met, reason, confidence = _parse_judge_json('{"met": false, "reason": ""}')
    assert met is False
    assert reason == "(no reason given)"
    assert confidence == 1.0


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
    monkeypatch.setattr(goal_judge_service.httpx, "post", lambda *a, **kw: response)


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
        "choices": [{"message": {"content": '{"met": false, "reason": "tests fail"}'}}],
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
                "choices": [{"message": {"content": '{"met": true, "reason": "ok"}'}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)
    # Force discovery to None so this test deterministically exercises the
    # per-backend DEFAULT fallback (a live catalog would otherwise make
    # cheap_model_for win — and the DEFAULT branch is what this asserts).
    monkeypatch.setattr(
        "app.services.model_discovery_service.ModelDiscoveryService.cheap_model_for",
        classmethod(lambda cls, backend: None),
    )

    for kind, expected_model in DEFAULT_JUDGE_MODEL.items():
        captured.clear()
        GoalJudgeService.judge("g", "t", backend_kind=kind)
        assert captured["model"] == expected_model
        assert captured["backend_kind"] == kind


def test_llm_judge_prefers_discovered_cheap_model(monkeypatch):
    """When the live catalog yields a cheap model it WINS over the pinned DEFAULT
    (the anti-staleness path)."""
    captured: dict = {}

    def capture_post(url, *, json, headers, timeout):
        captured["model"] = json["model"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"met": true, "reason": "ok"}'}}],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)
    monkeypatch.setattr(
        "app.services.model_discovery_service.ModelDiscoveryService.cheap_model_for",
        classmethod(lambda cls, backend: "discovered-cheap"),
    )

    GoalJudgeService.judge("g", "t", backend_kind="claude")
    assert captured["model"] == "discovered-cheap"


def test_llm_judge_model_override_wins(monkeypatch):
    captured: dict = {}

    def capture_post(url, *, json, headers, timeout):
        captured["model"] = json["model"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"met": true, "reason": "ok"}'}}],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)

    GoalJudgeService.judge("g", "t", backend_kind="claude", model_override="claude-opus-4-7")
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


# -----------------------------------------------------------------
# Composable graders — deterministic check AND rubric
# -----------------------------------------------------------------

from app.models.loop_spec import QualityGate  # noqa: E402


def _rubric_gate(rubric="output must be well-formed"):
    return QualityGate(kind="test_pass", rubric=rubric)


def test_check_and_rubric_compose_both_met(monkeypatch):
    # check passes (exit 0) AND rubric passes -> composite met.
    body = {
        "choices": [{"message": {"content": '{"met": true, "reason": "rubric ok"}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    _install_mock_proxy(monkeypatch, httpx.Response(200, json=body))
    v = GoalJudgeService.judge("g", "t", check_cmd="true", quality_gate=_rubric_gate())
    assert v.met is True
    assert v.source == "composite"
    assert "check:" in v.reason and "rubric:" in v.reason


def test_check_passes_rubric_fails_is_not_met(monkeypatch):
    # check passes but the rubric fails -> composite NOT met (the whole point:
    # "tests pass AND rubric satisfied", not "tests pass so we're done").
    body = {
        "choices": [{"message": {"content": '{"met": false, "reason": "sloppy"}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    _install_mock_proxy(monkeypatch, httpx.Response(200, json=body))
    v = GoalJudgeService.judge("g", "t", check_cmd="true", quality_gate=_rubric_gate())
    assert v.met is False
    assert v.source == "composite"
    assert "sloppy" in v.reason


def test_check_fails_skips_rubric(monkeypatch):
    # A failing artifact-truth check short-circuits: the LLM rubric is NOT called
    # (no point paying for it, and the check trace drives the next turn).
    def explode(*a, **kw):
        raise AssertionError("LLM must not be called when the check already failed")

    monkeypatch.setattr(goal_judge_service.httpx, "post", explode)
    v = GoalJudgeService.judge("g", "t", check_cmd="false", quality_gate=_rubric_gate())
    assert v.met is False
    assert v.source == "deterministic"
    assert "exited 1" in v.reason


# -----------------------------------------------------------------
# Artifact-grounded LLM judge (reward-hacking guard)
# -----------------------------------------------------------------


def _capture_payload(monkeypatch):
    captured: dict = {}

    def capture_post(url, *, json, headers, timeout):
        captured["system"] = json["messages"][0]["content"]
        captured["user"] = json["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"met": false, "reason": "x"}'}}],
                "usage": {},
            },
        )

    monkeypatch.setattr(
        goal_judge_service.CLIProxyManager,
        "get_url_and_key",
        classmethod(lambda cls: ("http://127.0.0.1:8317/v1", "k")),
    )
    monkeypatch.setattr(goal_judge_service.httpx, "post", capture_post)
    return captured


def test_llm_judge_includes_artifact_diff(monkeypatch):
    captured = _capture_payload(monkeypatch)
    GoalJudgeService.judge(
        "add a function foo",
        "I added foo, all good.",
        backend_kind="claude",
        artifact_diff="diff --git a/foo.py b/foo.py\n+def foo(): pass",
    )
    assert "def foo(): pass" in captured["user"]
    # System prompt switches to the artifact-grounded variant.
    assert "REAL changes" in captured["system"]


def test_empty_artifact_diff_is_flagged_to_judge(monkeypatch):
    # The reward-hacking case: agent claims success, changed nothing. The judge is
    # explicitly told the tree is clean so it can rule not-met.
    captured = _capture_payload(monkeypatch)
    GoalJudgeService.judge(
        "add a function foo",
        "Done! foo is implemented and tests pass.",
        backend_kind="claude",
        artifact_diff="",
    )
    assert "no changes detected" in captured["user"]
    assert "REAL changes" in captured["system"]


def test_ouroboros_uses_diff_aware_system_prompt(monkeypatch):
    # Codex #6: the Ouroboros judge must switch to the diff-aware system prompt
    # (empty/no-relevant diff -> not confirmed) when a diff is supplied.
    captured = _capture_payload(monkeypatch)
    GoalJudgeService.judge(
        "prove the cache helps",
        "**Hypothesis:** cache helps\n**Predicted outcome:** faster",
        backend_kind="claude",
        hypothesis="cache helps",
        predicted_outcome="faster",
        artifact_diff="diff --git a/c.py b/c.py\n+cache = {}",
    )
    assert "REAL changes" in captured["system"]
    assert "cache = {}" in captured["user"]


# -----------------------------------------------------------------
# Hardened artifact-diff builder (Codex review of Loop 2)
# -----------------------------------------------------------------

import os  # noqa: E402
import subprocess as _sp  # noqa: E402

from app.services.goal_judge_service import _redact_secrets, build_artifact_diff  # noqa: E402


def _git_repo(path):
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        _sp.run(["git", *args], cwd=path, check=True)


def _commit(path, msg="c"):
    _sp.run(["git", "add", "-A"], cwd=path, check=True)
    _sp.run(["git", "commit", "-qm", msg], cwd=path, check=True)


def test_build_diff_none_when_not_a_git_repo(tmp_path):
    # Codex #2: a git failure must NOT be reported as a clean tree.
    assert build_artifact_diff(str(tmp_path)) is None


def test_build_diff_none_when_cwd_missing():
    assert build_artifact_diff(None) is None


def test_build_diff_empty_only_when_genuinely_clean(tmp_path):
    _git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("seed")
    _commit(tmp_path)
    assert build_artifact_diff(str(tmp_path)) == ""


def test_build_diff_includes_untracked_content_not_just_name(tmp_path):
    # Codex #3: a suggestive filename alone must not stand in for real content.
    _git_repo(tmp_path)
    (tmp_path / "seed").write_text("x")
    _commit(tmp_path)
    (tmp_path / "feature.py").write_text("def real_impl():\n    return 42\n")
    out = build_artifact_diff(str(tmp_path))
    assert "feature.py" in out
    assert "def real_impl():" in out


def test_build_diff_redacts_secret_values(tmp_path):
    # Codex #5: an edited tracked secret must not be forwarded to the judge model.
    _git_repo(tmp_path)
    (tmp_path / ".env").write_text("PLACEHOLDER=1\n")
    _commit(tmp_path)
    (tmp_path / ".env").write_text("API_KEY=sk-abcdefghij1234567890abcdefgh\n")
    out = build_artifact_diff(str(tmp_path))
    assert "sk-abcdefghij1234567890abcdefgh" not in out
    assert "redacted" in out


def test_build_diff_truncates_with_marker_and_stat_header(tmp_path):
    # Codex #4: an over-cap diff carries a truncation marker + the full --stat scope.
    _git_repo(tmp_path)
    (tmp_path / "big.py").write_text("orig\n")
    _commit(tmp_path)  # tracked, so a huge rewrite shows in `git diff --stat`
    (tmp_path / "big.py").write_text("\n".join(f"line_{i} = {i}" for i in range(5000)))
    out = build_artifact_diff(str(tmp_path), max_chars=2000)
    assert "diff truncated" in out
    assert "git diff --stat" in out


def test_redact_secrets_unit():
    assert "«redacted»" in _redact_secrets("+API_TOKEN=supersecretvalue123")
    assert "supersecretvalue123" not in _redact_secrets("+API_TOKEN=supersecretvalue123")
    assert "ghp_" not in _redact_secrets("token ghp_ABCDEFGHIJ1234567890abcd here")


def test_judge_artifact_diff_skipped_for_check_only(tmp_path):
    # Codex #1: a check-only loop must NOT compute the diff (the judge never reads
    # it), but check+rubric or no-check MUST.
    from app.models.loop_spec import QualityGate
    from app.services.goal_loop_runner import _judge_artifact_diff

    _git_repo(tmp_path)
    (tmp_path / "seed").write_text("x")
    _commit(tmp_path)
    (tmp_path / "seed").write_text("changed")  # a real diff exists
    cwd = str(tmp_path)
    assert _judge_artifact_diff(cwd, QualityGate(kind="test_pass"), "pytest", None) is None
    assert _judge_artifact_diff(cwd, QualityGate(kind="test_pass", rubric="r"), "pytest", None)
    assert _judge_artifact_diff(cwd, QualityGate(kind="llm_judge", rubric="r"), None, None)


# -----------------------------------------------------------------
# Codex round-2 hardening: symlink safety, redaction gaps, base-ref failure
# -----------------------------------------------------------------


def test_build_diff_does_not_follow_symlink_out_of_worktree(tmp_path):
    # Codex B1 (blocker): an untracked symlink pointing outside the repo must NOT
    # have its target content read into the judge prompt.
    outside = tmp_path.parent / f"{tmp_path.name}_secret.txt"
    outside.write_text("TOPSECRET_LEAKED_VALUE")
    _git_repo(tmp_path)
    (tmp_path / "seed").write_text("x")
    _commit(tmp_path)
    os.symlink(outside, tmp_path / "leak.txt")  # untracked symlink out of the repo
    out = build_artifact_diff(str(tmp_path))
    assert "TOPSECRET_LEAKED_VALUE" not in out
    assert "leak.txt" in out  # name shown, content omitted


def test_build_diff_none_when_base_ref_invalid(tmp_path):
    # Codex B3: a failed `git diff <base>` is UNAVAILABLE, not a clean tree.
    _git_repo(tmp_path)
    (tmp_path / "seed").write_text("x")
    _commit(tmp_path)
    assert build_artifact_diff(str(tmp_path), "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef") is None


def test_build_diff_redacts_sensitive_untracked_file(tmp_path):
    # Codex B2: an untracked .env with a non-KEY=VALUE secret is redacted wholesale.
    _git_repo(tmp_path)
    (tmp_path / "seed").write_text("x")
    _commit(tmp_path)
    (tmp_path / ".env").write_text("WEIRD_FORMAT super-secret-line-no-equals")
    out = build_artifact_diff(str(tmp_path))
    assert "super-secret-line-no-equals" not in out
    assert ".env" in out


def test_redact_pem_and_quoted_secrets():
    # Codex B2: PEM/OpenSSH private-key blocks and quoted JSON secrets.
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk=\n-----END OPENSSH PRIVATE KEY-----"
    red = _redact_secrets(pem)
    assert "b3BlbnNzaC1rZXk=" not in red
    assert "«redacted-private-key»" in red
    quoted = '+  "client_secret": "plain-generic-token-value"'
    assert "plain-generic-token-value" not in _redact_secrets(quoted)
