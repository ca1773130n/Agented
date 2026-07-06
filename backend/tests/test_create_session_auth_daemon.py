"""Auth-daemon fix: autonomous claude sessions must keep CLAUDE_CONFIG_DIR
pointed at the REAL, daemon-backed account dir (so the OAuth token can be
refreshed) and deliver the PreToolUse permission hook via ``--settings``,
NOT via the /tmp overlay (which has no auth daemon → "Not logged in").

Interactive sessions keep the /tmp overlay unchanged.

We stop create_session just before the spawn by patching
``apply_sandbox_and_enforce`` in the module namespace to capture the resolved
cmd + config_dirs and raise a sentinel, so no real process is forked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import project_session_manager as psm
from app.services import sandbox_wrap as sbw
from app.services.claude_config_overlay import _hook_script_path


class _StopSpawn(Exception):
    """Sentinel raised from the sandbox seam to abort before pty.fork/Popen."""


@pytest.fixture
def capture(monkeypatch, tmp_path):
    """Patch the account lookup + sandbox seam. Returns a dict populated with
    the resolved ``cmd`` and ``config_dirs`` at the moment of (aborted) spawn.
    """
    real_dir = tmp_path / "real-claude-cfg"
    real_dir.mkdir()
    (real_dir / "settings.json").write_text("{}")

    monkeypatch.setattr(
        psm,
        "get_accounts_for_backend_type",
        lambda _kind: [{"config_path": str(real_dir)}],
    )
    monkeypatch.setattr(psm, "_resolve_admin_api_key", lambda: "admin-key-xyz")

    captured: dict = {"real_dir": str(real_dir)}

    def _fake_enforce(cmd, cwd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["config_dirs"] = list(kwargs.get("config_dirs") or [])
        raise _StopSpawn()

    # create_session imports this locally: ``from .sandbox_wrap import
    # apply_sandbox_and_enforce`` — patch it at the source module.
    monkeypatch.setattr(sbw, "apply_sandbox_and_enforce", _fake_enforce)
    return captured


def _run(execution_type="grd_research", execution_mode="autonomous", **kw):
    with pytest.raises(_StopSpawn):
        psm.ProjectSessionManager.create_session(
            project_id="proj-abc123",
            cmd=["claude", "-p", "hi", "--output-format", "stream-json"],
            cwd=str(Path.cwd()),
            execution_type=execution_type,
            execution_mode=execution_mode,
            stream_json=True,
            yolo_mode=kw.pop("yolo_mode", False),
            **kw,
        )


def _settings_arg(cmd):
    assert "--settings" in cmd, cmd
    return json.loads(cmd[cmd.index("--settings") + 1])


def test_autonomous_grd_keeps_real_config_dir(capture, monkeypatch):
    """The temp overlay must NOT be built; CLAUDE_CONFIG_DIR stays the real dir."""
    called = {"overlay": False}
    import app.services.claude_config_overlay as cco

    monkeypatch.setattr(
        cco,
        "prepare_session_overlay",
        lambda *a, **k: called.__setitem__("overlay", True) or "/tmp/should-not-be-used",
    )

    _run()

    assert called["overlay"] is False, "prepare_session_overlay called for autonomous session"
    # config_dirs is derived from CLAUDE_CONFIG_DIR — it must be the real dir,
    # never a /tmp/agented-claude-overlay path.
    assert capture["real_dir"] in capture["config_dirs"]
    assert not any("agented-claude-overlay" in d for d in capture["config_dirs"])


def test_autonomous_grd_injects_settings_hook(capture):
    _run()
    payload = _settings_arg(capture["cmd"])
    pre = payload["hooks"]["PreToolUse"]
    assert any(
        h.get("command") == str(_hook_script_path()) for e in pre for h in (e.get("hooks") or [])
    )
    # --settings inserted right after cmd[0].
    assert capture["cmd"][1] == "--settings"


def test_autonomous_settings_arg_idempotent(capture):
    """If cmd already carries --settings we do NOT insert a second one."""
    with pytest.raises(_StopSpawn):
        psm.ProjectSessionManager.create_session(
            project_id="proj-abc123",
            cmd=["claude", "--settings", '{"hooks": {}}', "-p", "hi"],
            cwd=str(Path.cwd()),
            execution_type="grd_research",
            execution_mode="autonomous",
            stream_json=True,
        )
    assert capture["cmd"].count("--settings") == 1


def test_interactive_without_forge_uses_daemon_path(capture, monkeypatch):
    """Interactive sessions WITHOUT a forge bundle (the common case, e.g. the
    conversation-fork) now take the daemon-backed real-dir + --settings path —
    NOT the daemon-less /tmp overlay — so they authenticate (auth-daemon fix)."""
    import app.services.claude_config_overlay as cco

    seen = {}

    def _fake_overlay(session_id, user_config_dir):
        seen["called"] = True
        return f"/tmp/agented-claude-overlay-{session_id}"

    monkeypatch.setattr(cco, "prepare_session_overlay", _fake_overlay)

    _run(execution_mode="interactive")

    assert seen.get("called") is None, "overlay must NOT be built for interactive-without-forge"
    assert "--settings" in capture["cmd"]
    assert not any("agented-claude-overlay" in d for d in capture["config_dirs"])


def test_interactive_with_forge_uses_overlay(capture, monkeypatch):
    """Interactive + a forge bundle still builds the disposable /tmp overlay (the
    only reason for it), delivering the hook via the overlay, not --settings."""
    import app.services.claude_config_overlay as cco

    seen = {}

    def _fake_overlay(session_id, user_config_dir):
        seen["called"] = True
        return f"/tmp/agented-claude-overlay-{session_id}"

    monkeypatch.setattr(cco, "prepare_session_overlay", _fake_overlay)
    monkeypatch.setattr(cco, "apply_forge_bundle", lambda *a, **k: None)

    _run(execution_mode="interactive", forge_bundle={"overlay_files": {}})

    assert seen.get("called") is True
    assert "--settings" not in capture["cmd"]
    assert any("agented-claude-overlay" in d for d in capture["config_dirs"])


def test_grd_chat_and_team_autonomous_paths(capture):
    for etype in ("grd_chat", "team_spawn"):
        capture.pop("cmd", None)
        _run(execution_type=etype)
        assert "--settings" in capture["cmd"]
        assert capture["real_dir"] in capture["config_dirs"]
        assert not any("agented-claude-overlay" in d for d in capture["config_dirs"])


def test_yolo_skips_both_overlay_and_settings(capture, monkeypatch):
    """yolo_mode retains the real dir but adds neither overlay nor --settings."""
    import app.services.claude_config_overlay as cco

    monkeypatch.setattr(
        cco,
        "prepare_session_overlay",
        lambda *a, **k: pytest.fail("overlay must not be built in yolo mode"),
    )
    _run(yolo_mode=True)
    assert "--settings" not in capture["cmd"]
    assert capture["real_dir"] in capture["config_dirs"]


def test_autonomous_missing_dir_skips_settings_but_keeps_auth(capture, monkeypatch):
    """If build_hook_settings_arg returns None (no hook), we still spawn
    against the real dir — auth intact, hook absent."""
    import app.services.claude_config_overlay as cco

    monkeypatch.setattr(cco, "build_hook_settings_arg", lambda _d: None)
    _run()
    assert "--settings" not in capture["cmd"]
    assert capture["real_dir"] in capture["config_dirs"]
