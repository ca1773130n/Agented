"""CLI agent runner — command construction + YOLO setting coverage.

The runner spawns real subprocesses, so these tests stub out
``subprocess.Popen`` with a fake whose ``stdout.readline`` plays back a
canned line stream. We assert two things per backend:

* The argv we build matches what the CLI expects in YOLO and non-YOLO
  modes (this is the contract that lets agents use tools).
* The streamed text is what we yield back to the caller (Claude parses
  NDJSON events; codex/gemini pass through line-by-line).
"""

from __future__ import annotations

import io
import json
from typing import List, Optional

import pytest

from app.services import cli_agent_runner_service as runner


class _FakeStdout(io.BytesIO):
    """``readline()`` that returns ``b''`` once exhausted (mimics Popen)."""

    def __init__(self, lines: List[bytes]) -> None:
        super().__init__(b"".join(lines))


class _FakeProc:
    def __init__(self, stdout_lines: List[bytes], rc: int = 0, stderr: bytes = b""):
        self.stdout = _FakeStdout(stdout_lines)
        self.stderr = io.BytesIO(stderr)
        self.returncode: Optional[int] = None
        self._rc_after_wait = rc
        self.killed = False

    def wait(self) -> int:
        self.returncode = self._rc_after_wait
        return self.returncode

    def kill(self) -> None:
        self.killed = True


@pytest.fixture
def captured(monkeypatch):
    """Captures the argv passed to Popen so we can assert flag composition."""
    captured: dict = {}

    def _fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return captured["proc"]

    monkeypatch.setattr(runner.subprocess, "Popen", _fake_popen)
    return captured


def test_claude_yolo_passes_skip_permissions(captured):
    captured["proc"] = _FakeProc(
        [
            (json.dumps({"type": "assistant", "message": {
                "content": [{"type": "text", "text": "hello"}]
            }}) + "\n").encode(),
        ]
    )
    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp/work",
            yolo=True,
        )
    )
    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--dangerously-skip-permissions" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert captured["kwargs"]["cwd"] == "/tmp/work"
    assert "hello" in "".join(chunks)


def test_claude_non_yolo_omits_skip_permissions(captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp/work",
            yolo=False,
        )
    )
    assert "--dangerously-skip-permissions" not in captured["cmd"]


def test_codex_yolo_uses_dangerous_bypass(captured):
    captured["proc"] = _FakeProc([b"line1\n", b"line2\n"])
    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "fix the bug"}],
            backend="codex",
            cwd="/tmp/proj",
            yolo=True,
        )
    )
    cmd = captured["cmd"]
    assert cmd[:2] == ["codex", "exec"]
    assert "--cd" in cmd and "/tmp/proj" in cmd
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    # Codex passes through line-by-line (no NDJSON parsing).
    joined = "".join(chunks)
    assert "line1" in joined and "line2" in joined


def test_codex_non_yolo_uses_workspace_write_sandbox(captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "x"}],
            backend="codex",
            cwd="/tmp/proj",
            yolo=False,
        )
    )
    cmd = captured["cmd"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
    assert "--sandbox" in cmd and "workspace-write" in cmd
    assert "--ask-for-approval" in cmd and "never" in cmd


def test_gemini_yolo_passes_y_flag(captured):
    captured["proc"] = _FakeProc([b"out\n"])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "x"}],
            backend="gemini",
            cwd="/tmp/proj",
            yolo=True,
        )
    )
    cmd = captured["cmd"]
    assert cmd[0] == "gemini"
    assert "-y" in cmd


def test_unsupported_backend_yields_error(captured):
    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "x"}],
            backend="future-llm",
            cwd=None,
            yolo=True,
        )
    )
    assert any("does not support" in c for c in chunks)


def test_empty_prompt_short_circuits():
    chunks = list(
        runner.stream_via_cli_agent(
            [],
            backend="claude",
            cwd="/tmp",
            yolo=True,
        )
    )
    assert any("empty prompt" in c.lower() for c in chunks)


def test_cli_not_found_yields_clean_error(monkeypatch):
    def _raise_fnf(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(runner.subprocess, "Popen", _raise_fnf)

    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp",
            yolo=True,
        )
    )
    assert any("Claude CLI not found" in c for c in chunks)


def test_nonzero_exit_surfaces_stderr(captured):
    captured["proc"] = _FakeProc(
        stdout_lines=[b"work in progress\n"],
        rc=2,
        stderr=b"boom: missing arg",
    )
    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "x"}],
            backend="codex",
            cwd="/tmp",
            yolo=True,
        )
    )
    joined = "".join(chunks)
    assert "boom: missing arg" in joined


def test_yolo_mode_defaults_on_when_unset(isolated_db):
    assert runner.is_yolo_mode_enabled() is True


def test_yolo_mode_persists_disabled(isolated_db):
    runner.set_yolo_mode(False)
    assert runner.is_yolo_mode_enabled() is False
    runner.set_yolo_mode(True)
    assert runner.is_yolo_mode_enabled() is True


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("1", True), ("yes", True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ],
)
def test_yolo_mode_truthy_parsing(monkeypatch, raw, expected):
    monkeypatch.setattr(runner, "get_setting", lambda _k: raw, raising=False)

    # Need to also stub the import inside is_yolo_mode_enabled (it imports
    # lazily), so monkey the underlying db helper too.
    from app.db import settings as settings_module

    monkeypatch.setattr(settings_module, "get_setting", lambda _k: raw)
    assert runner.is_yolo_mode_enabled() is expected


# ---------------------------------------------------------------------------
# should_route_via_cli_agent — routing matrix shared across the three
# streaming sites (streaming_helper, base_conversation_service, grd_routes).
# ---------------------------------------------------------------------------


def test_routing_unsupported_backend_never_uses_cli(monkeypatch):
    """OpenCode and exotic backends never go through the CLI runner.

    Even if the global YOLO is on or CLIProxy is unavailable, an
    `opencode` request must keep using its own dedicated path —
    `stream_via_cli_agent` doesn't know how to drive opencode.
    """
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: True)
    assert runner.should_route_via_cli_agent("opencode", None) is False
    assert runner.should_route_via_cli_agent("opencode", True) is False
    assert runner.should_route_via_cli_agent(None, True) is False
    assert runner.should_route_via_cli_agent("", True) is False


def test_routing_explicit_true_wins(monkeypatch):
    """Caller `use_cli_agent=True` overrides everything."""
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)
    # Even when CLIProxy is reachable and YOLO is off:
    monkeypatch.setattr(
        "app.services.conversation_streaming._find_cliproxy",
        lambda: ("http://localhost:1234", "key"),
    )
    assert runner.should_route_via_cli_agent("claude", True) is True


def test_routing_explicit_false_wins_even_without_cliproxy(monkeypatch):
    """Caller `use_cli_agent=False` is honored even if CLIProxy is gone.

    If the operator explicitly opts into CLIProxy, we don't second-guess
    them — the missing-proxy fallback only kicks in when the caller
    deferred. They get whatever error CLIProxy yields.
    """
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.conversation_streaming._find_cliproxy", lambda: None
    )
    assert runner.should_route_via_cli_agent("claude", False) is False


def test_routing_defer_uses_cli_when_yolo_on(monkeypatch):
    """Caller defers (None) + YOLO global on → CLI runner."""
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: True)
    assert runner.should_route_via_cli_agent("claude", None) is True
    assert runner.should_route_via_cli_agent("codex", None) is True
    assert runner.should_route_via_cli_agent("gemini", None) is True


def test_routing_defer_uses_cliproxy_when_yolo_off_and_proxy_up(monkeypatch):
    """Caller defers, YOLO off, CLIProxy reachable → CLIProxy path."""
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.conversation_streaming._find_cliproxy",
        lambda: ("http://localhost:1234", "key"),
    )
    assert runner.should_route_via_cli_agent("claude", None) is False


def test_routing_defer_falls_over_to_cli_when_proxy_missing(monkeypatch):
    """Caller defers, YOLO off, CLIProxy unreachable → CLI runner.

    This is the core fallback that prevents a missing proxy from
    silently dropping the SSE: the legacy CLIProxy path can't satisfy
    the request, so the only way to actually answer is the CLI runner.
    """
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)
    monkeypatch.setattr(
        "app.services.conversation_streaming._find_cliproxy", lambda: None
    )
    assert runner.should_route_via_cli_agent("claude", None) is True
    assert runner.should_route_via_cli_agent("codex", None) is True
    assert runner.should_route_via_cli_agent("gemini", None) is True


def test_routing_proxy_probe_failure_does_not_crash(monkeypatch):
    """If `_find_cliproxy` raises, the helper falls through cleanly.

    Without this guard, an httpx import error or transient probe failure
    could break the chat flow entirely; the helper logs and returns
    False so the caller picks the legacy path.
    """
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)

    def _boom():
        raise RuntimeError("probe failed")

    monkeypatch.setattr(
        "app.services.conversation_streaming._find_cliproxy", _boom
    )
    assert runner.should_route_via_cli_agent("claude", None) is False
