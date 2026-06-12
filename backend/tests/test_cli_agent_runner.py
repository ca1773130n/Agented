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
            (
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "hello"}]},
                    }
                )
                + "\n"
            ).encode(),
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


def test_claude_result_event_does_not_double_yield_text(captured):
    """claude stream-json emits an ``assistant`` event then a ``result`` event
    carrying the SAME text. Extracting both used to print every reply twice,
    concatenated into one bubble. Only the assistant text should be yielded."""
    reply = "Hey. What do you need?"
    captured["proc"] = _FakeProc(
        [
            (
                json.dumps(
                    {"type": "assistant", "message": {"content": [{"type": "text", "text": reply}]}}
                )
                + "\n"
            ).encode(),
            (
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "result": reply,
                    }
                )
                + "\n"
            ).encode(),
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
    assert "".join(chunks) == reply  # exactly once, not doubled


def test_claude_streams_token_deltas_and_skips_duplicate_assistant(captured):
    """With --include-partial-messages claude streams content_block_delta
    tokens, then repeats the whole text in a final `assistant` event. We must
    stream the tokens and drop the duplicate — net text appears exactly once."""
    tokens = ["Hello", " from", " streaming"]
    lines = []
    for tok in tokens:
        lines.append(
            (
                json.dumps(
                    {
                        "type": "stream_event",
                        "event": {
                            "type": "content_block_delta",
                            "delta": {"type": "text_delta", "text": tok},
                        },
                    }
                )
                + "\n"
            ).encode()
        )
    # Final full assistant message (the duplicate) + result (also duplicate).
    full = "".join(tokens)
    lines.append(
        (
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": full}]}}
            )
            + "\n"
        ).encode()
    )
    lines.append((json.dumps({"type": "result", "result": full}) + "\n").encode())

    captured["proc"] = _FakeProc(lines)
    chunks = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp",
            yolo=True,
        )
    )
    # Streamed token-by-token (3 chunks), and the full text appears once.
    assert chunks == tokens
    assert "".join(chunks) == full
    assert "--include-partial-messages" in captured["cmd"]


def test_claude_assistant_event_emits_thinking_and_tool_use(captured):
    """A final assistant event with thinking + tool_use + text blocks surfaces
    a ThinkingEvent + ToolUseEvent alongside the text (folded in the UI)."""
    from app.services.conversation_streaming import ThinkingEvent, ToolUseEvent

    captured["proc"] = _FakeProc(
        [
            (
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "thinking", "thinking": "Let me plan the epics."},
                                {
                                    "type": "tool_use",
                                    "name": "tesserae_ask",
                                    "id": "tu1",
                                    "input": {"question": "prior art?"},
                                },
                                {"type": "text", "text": "Here's the plan."},
                            ]
                        },
                    }
                )
                + "\n"
            ).encode(),
            (json.dumps({"type": "result", "result": "Here's the plan."}) + "\n").encode(),
        ]
    )
    out = list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "plan it"}],
            backend="claude",
            cwd="/tmp",
            yolo=True,
        )
    )
    thinking = [x for x in out if isinstance(x, ThinkingEvent)]
    tools = [x for x in out if isinstance(x, ToolUseEvent)]
    text = "".join(x for x in out if isinstance(x, str))
    assert thinking and "plan the epics" in thinking[0].text
    assert tools and tools[0].name == "tesserae_ask"
    assert text == "Here's the plan."  # not doubled by the result event


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


def test_gemini_yolo_passes_yolo_flag(captured):
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
    # Gemini CLI uses ``--yolo`` (long form); ``-y`` doesn't exist there.
    assert "--yolo" in cmd


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
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("off", False),
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
    monkeypatch.setattr("app.services.conversation_streaming._find_cliproxy", lambda: None)
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
    monkeypatch.setattr("app.services.conversation_streaming._find_cliproxy", lambda: None)
    assert runner.should_route_via_cli_agent("claude", None) is True
    assert runner.should_route_via_cli_agent("codex", None) is True
    assert runner.should_route_via_cli_agent("gemini", None) is True


# ---------------------------------------------------------------------------
# Per-account config-dir env injection. Multi-account ai-accounts setups
# put each account at a distinct path (~/.claude-personal1, etc.); the
# CLI must read the right vault or it reports "Not logged in" with no
# TTY available to recover.
# ---------------------------------------------------------------------------


def test_config_dir_sets_claude_config_dir_env(monkeypatch, captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp",
            yolo=True,
            config_dir="~/.claude-personal1",
        )
    )
    env = captured["kwargs"]["env"]
    assert env is not None
    assert env["CLAUDE_CONFIG_DIR"].endswith(".claude-personal1")
    # Other env vars stay inherited so PATH etc. work.
    assert "PATH" in env


def test_config_dir_sets_codex_home_env(captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="codex",
            cwd="/tmp",
            yolo=True,
            config_dir="/Users/x/.codex-pro",
        )
    )
    env = captured["kwargs"]["env"]
    assert env["CODEX_HOME"] == "/Users/x/.codex-pro"


def test_config_dir_sets_gemini_home_env(captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="gemini",
            cwd="/tmp",
            yolo=True,
            config_dir="~/.gemini-personal1",
        )
    )
    env = captured["kwargs"]["env"]
    assert env["GEMINI_HOME"].endswith(".gemini-personal1")


def test_no_config_dir_inherits_env_unchanged(captured):
    captured["proc"] = _FakeProc([])
    list(
        runner.stream_via_cli_agent(
            [{"role": "user", "content": "hi"}],
            backend="claude",
            cwd="/tmp",
            yolo=True,
            config_dir=None,
        )
    )
    # ``env=None`` lets Popen inherit os.environ unchanged, which is
    # cheaper than copying the dict and avoids surprising downstream
    # tools that read other env vars.
    assert captured["kwargs"]["env"] is None


def test_resolve_account_config_dir_picks_default(isolated_db):
    """No account_id → first row matching backend type, prefer is_default."""
    from app.db.backends import create_backend_account

    create_backend_account(
        backend_id="backend-claude",
        account_name="alt",
        email=None,
        config_path="~/.claude-alt",
        api_key_env=None,
        is_default=0,
        plan=None,
        usage_data=None,
    )
    create_backend_account(
        backend_id="backend-claude",
        account_name="primary",
        email=None,
        config_path="~/.claude-primary",
        api_key_env=None,
        is_default=1,
        plan=None,
        usage_data=None,
    )

    result = runner.resolve_account_config_dir(None, "claude")
    assert result is not None
    assert result.endswith(".claude-primary")


def test_resolve_account_config_dir_uses_local_int_id(isolated_db):
    """Numeric account_id → exact local PK lookup."""
    from app.db.backends import create_backend_account

    create_backend_account(
        backend_id="backend-codex",
        account_name="primary",
        email=None,
        config_path="~/.codex-primary",
        api_key_env=None,
        is_default=1,
        plan=None,
        usage_data=None,
    )
    aid = create_backend_account(
        backend_id="backend-codex",
        account_name="alt",
        email=None,
        config_path="~/.codex-alt",
        api_key_env=None,
        is_default=0,
        plan=None,
        usage_data=None,
    )

    result = runner.resolve_account_config_dir(str(aid), "codex")
    assert result is not None
    assert result.endswith(".codex-alt")


def test_resolve_account_config_dir_returns_none_when_no_accounts(isolated_db):
    """No matching accounts → None (caller lets the CLI hit its default)."""
    assert runner.resolve_account_config_dir(None, "claude") is None
    assert runner.resolve_account_config_dir("999", "claude") is None


def test_resolve_account_config_dir_unknown_backend(isolated_db):
    assert runner.resolve_account_config_dir(None, "future-llm") is None
    assert runner.resolve_account_config_dir(None, "") is None
    assert runner.resolve_account_config_dir(None, None) is None


def test_routing_proxy_probe_failure_does_not_crash(monkeypatch):
    """If `_find_cliproxy` raises, the helper falls through cleanly.

    Without this guard, an httpx import error or transient probe failure
    could break the chat flow entirely; the helper logs and returns
    False so the caller picks the legacy path.
    """
    monkeypatch.setattr(runner, "is_yolo_mode_enabled", lambda: False)

    def _boom():
        raise RuntimeError("probe failed")

    monkeypatch.setattr("app.services.conversation_streaming._find_cliproxy", _boom)
    assert runner.should_route_via_cli_agent("claude", None) is False


# ---------------------------------------------------------------------------
# resolve_execution_driver() — precedence matrix + degrade/read-failure safety
# (Phase 19-01, REQ-10). Always inject the degrade callables so a "grd"
# outcome needs no real binary/workspace.
# ---------------------------------------------------------------------------

# GRD reports available + workspace resolves cleanly → "grd" survives.
_GRD_OK = {"grd_tools_available": True, "gd_available": True}
_grd_available_ok = lambda: _GRD_OK  # noqa: E731
_resolve_ws_ok = lambda project_id: "/tmp/clone"  # noqa: E731


def _conn():
    """Open the live (isolated_db) SQLite connection for seeding driver columns."""
    from app.db.connection import get_connection

    return get_connection()


def _resolve(**kw):
    """Call resolve_execution_driver with the available/workspace callables
    defaulted to the happy path unless a test overrides them."""
    kw.setdefault("_grd_available", _grd_available_ok)
    kw.setdefault("_resolve_workspace", _resolve_ws_ok)
    return runner.resolve_execution_driver(**kw)


def test_resolve_global_default_is_grd():
    """No source set + GRD available → global default 'grd'."""
    assert _resolve(backend="claude") == "grd"


def test_resolve_non_cli_backend_is_cliproxy():
    """A backend outside {claude,codex,gemini} can never run grd/cli_agent."""
    assert _resolve(backend="openai") == "cliproxy"
    # Even an explicit turn override cannot promote a non-CLI backend.
    assert _resolve(backend="openai", turn_driver="grd") == "cliproxy"


def test_resolve_turn_driver_overrides_everything(isolated_db):
    """An explicit turn_driver wins over every lower precedence source."""
    from app.db.projects import create_project, update_project

    pid = create_project(name="p-turn")
    update_project(pid, status="active")
    # Seed a project default that would otherwise win.
    with _conn() as conn:
        conn.execute("UPDATE projects SET default_driver='cli_agent' WHERE id=?", (pid,))
        conn.commit()
    assert _resolve(backend="claude", turn_driver="cliproxy", project_id=pid) == "cliproxy"


def test_resolve_use_cli_agent_legacy_mapping():
    """Legacy boolean maps when turn_driver is None."""
    assert _resolve(backend="claude", use_cli_agent=True) == "cli_agent"
    assert _resolve(backend="claude", use_cli_agent=False) == "cliproxy"


def test_resolve_super_agent_wins_over_instance_and_project(isolated_db):
    """SuperAgent config_json.driver beats instance + project defaults."""
    from app.db.projects import create_project
    from app.db.project_sa_instances import create_project_sa_instance
    from app.db.super_agents import create_super_agent

    pid = create_project(name="p-sa")
    with _conn() as conn:
        conn.execute("UPDATE projects SET default_driver='grd' WHERE id=?", (pid,))
        conn.commit()
    sa_id = create_super_agent(name="sa", config_json=json.dumps({"driver": "cliproxy"}))
    iid = create_project_sa_instance(pid, sa_id, driver="cli_agent")
    assert (
        _resolve(
            backend="claude",
            super_agent_id=sa_id,
            instance_id=iid,
            project_id=pid,
        )
        == "cliproxy"
    )


def test_resolve_instance_wins_over_project(isolated_db):
    """Instance driver beats the project default."""
    from app.db.projects import create_project
    from app.db.project_sa_instances import create_project_sa_instance
    from app.db.super_agents import create_super_agent

    pid = create_project(name="p-inst")
    with _conn() as conn:
        conn.execute("UPDATE projects SET default_driver='grd' WHERE id=?", (pid,))
        conn.commit()
    sa_id = create_super_agent(name="sa2")
    iid = create_project_sa_instance(pid, sa_id, driver="cli_agent")
    assert _resolve(backend="claude", instance_id=iid, project_id=pid) == "cli_agent"


def test_resolve_project_default_wins_over_global(isolated_db):
    """projects.default_driver beats the global 'grd' default."""
    from app.db.projects import create_project

    pid = create_project(name="p-proj")
    with _conn() as conn:
        conn.execute("UPDATE projects SET default_driver='cli_agent' WHERE id=?", (pid,))
        conn.commit()
    assert _resolve(backend="claude", project_id=pid) == "cli_agent"


def test_resolve_no_source_is_grd(isolated_db):
    """Project with NULL default_driver + no other source → 'grd'."""
    from app.db.projects import create_project

    pid = create_project(name="p-null")
    assert _resolve(backend="claude", project_id=pid) == "grd"


def test_resolve_degrade_when_grd_unavailable():
    """grd → cli_agent when the GRD binary reports unavailable."""
    assert (
        runner.resolve_execution_driver(
            backend="claude",
            _grd_available=lambda: {"grd_tools_available": False, "gd_available": False},
            _resolve_workspace=_resolve_ws_ok,
        )
        == "cli_agent"
    )


def test_resolve_degrade_when_workspace_unresolvable():
    """grd → cli_agent when the workspace resolver raises ValueError."""

    def _no_clone(project_id):
        raise ValueError("no clone path")

    assert (
        runner.resolve_execution_driver(
            backend="claude",
            project_id="proj-x",
            _grd_available=_grd_available_ok,
            _resolve_workspace=_no_clone,
        )
        == "cli_agent"
    )


def test_resolve_read_failure_degrades_does_not_raise(monkeypatch):
    """A DB read failure during precedence resolution degrades to the legacy
    choice (cli_agent for a CLI backend) instead of raising."""

    def _boom(project_id):
        raise RuntimeError("db exploded")

    monkeypatch.setattr("app.db.projects.get_project_default_driver", _boom)
    # project read raises → falls through to global 'grd', which is available,
    # so the resolver returns 'grd' (the read failure is swallowed, not raised).
    out = _resolve(backend="claude", project_id="proj-x")
    assert out in {"grd", "cli_agent"}  # never raised


def test_resolve_total_failure_returns_legacy_choice(monkeypatch):
    """If even the degrade check explodes, the outer guard returns the legacy
    choice rather than propagating."""

    def _boom():
        raise RuntimeError("boom")

    out = runner.resolve_execution_driver(
        backend="claude",
        _grd_available=_boom,
        _resolve_workspace=_resolve_ws_ok,
    )
    assert out == "cli_agent"
