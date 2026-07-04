"""Tests for AGENTED_SERVER_NO_LLM_KEYS server-side LLM-key isolation (REQ-41).

The flag makes the backend refuse to read raw LLM *inference* keys (e.g.
ANTHROPIC_API_KEY) from its OWN process environment. Credentials must instead
flow in per-request (explicit ``api_key`` args sourced from the ai-accounts
sidecar). This isolates a shared / "poison" server-wide key from silently
backing every user's inference.

Three guard clauses route their env fallback through ``config.env_llm_key``:
  1. cliproxy_chat_service.CLIProxyChatService.stream_chat_direct
  2. conversation_streaming (direct ANTHROPIC_API_KEY fallback)
  3. orchestration_service.OrchestrationService._build_account_env

Default (flag unset) behavior is byte-for-byte unchanged.
"""

import os
import re
from pathlib import Path

import pytest

from app import config

POISON = "sk-ant-POISON-should-never-reach-inference"

BACKEND_ROOT = Path(config.PROJECT_ROOT) / "backend"
APP_DIR = BACKEND_ROOT / "app"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start each test from a known env: no flag, no poison key."""
    monkeypatch.delenv("AGENTED_SERVER_NO_LLM_KEYS", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


# --- flag helper semantics -------------------------------------------------


def test_server_no_llm_keys_flag_default_off():
    assert config.server_no_llm_keys() is False


@pytest.mark.parametrize("truthy", ["1", "true", "True", "yes", "on", " ON "])
def test_server_no_llm_keys_flag_truthy_values(monkeypatch, truthy):
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", truthy)
    assert config.server_no_llm_keys() is True


@pytest.mark.parametrize("falsy", ["", "0", "false", "no", "off"])
def test_server_no_llm_keys_flag_falsy_values(monkeypatch, falsy):
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", falsy)
    assert config.server_no_llm_keys() is False


# --- env_llm_key: flag ON suppresses the poison key ------------------------


def test_env_llm_key_flag_on_ignores_poison(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")
    assert config.env_llm_key("ANTHROPIC_API_KEY") == ""
    assert config.env_llm_key("ANTHROPIC_API_KEY", "fallback") == "fallback"


# --- env_llm_key: flag OFF is unchanged (regression) -----------------------


def test_env_llm_key_flag_off_reads_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    assert config.env_llm_key("ANTHROPIC_API_KEY") == POISON


def test_env_llm_key_flag_off_missing_returns_default(monkeypatch):
    assert config.env_llm_key("ANTHROPIC_API_KEY") == ""
    assert config.env_llm_key("ANTHROPIC_API_KEY", "x") == "x"


# --- guard site 1: cliproxy_chat_service.stream_chat_direct ----------------


def test_cliproxy_direct_flag_on_ignores_poison(monkeypatch):
    from app.models.chat_state import ChatDeltaType
    from app.services.cliproxy_chat_service import CLIProxyChatService

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    deltas = list(CLIProxyChatService.stream_chat_direct([{"role": "user", "content": "hi"}]))
    # With the poison key suppressed and no explicit api_key, the method must
    # short-circuit with a "no API key" error rather than call LiteLLM.
    assert len(deltas) == 1
    assert deltas[0].type == ChatDeltaType.ERROR


def test_cliproxy_direct_flag_off_would_use_env(monkeypatch):
    """Regression: flag off, the env key IS resolved (no early no-key error)."""
    import app.services.cliproxy_chat_service as mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)

    captured = {}

    def _fake_completion(**kwargs):
        captured["api_key"] = kwargs.get("api_key")
        return iter(())  # empty stream

    monkeypatch.setattr(mod.litellm, "completion", _fake_completion)
    list(mod.CLIProxyChatService.stream_chat_direct([{"role": "user", "content": "hi"}]))
    assert captured.get("api_key") == POISON


# --- guard site 3: orchestration _build_account_env ------------------------


def test_orchestration_build_account_env_flag_on_ignores_poison(monkeypatch):
    from app.services.orchestration_service import OrchestrationService

    monkeypatch.setenv("ANTHROPIC_API_KEY_2", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    env = OrchestrationService._build_account_env({"api_key_env": "ANTHROPIC_API_KEY_2"})
    assert "ANTHROPIC_API_KEY" not in env


def test_orchestration_build_account_env_flag_off_maps_key(monkeypatch):
    from app.services.orchestration_service import OrchestrationService

    monkeypatch.setenv("ANTHROPIC_API_KEY_2", POISON)

    env = OrchestrationService._build_account_env({"api_key_env": "ANTHROPIC_API_KEY_2"})
    assert env.get("ANTHROPIC_API_KEY") == POISON


# --- 4th leak: subprocess env passthrough (REQ-41) -------------------------


def test_subprocess_env_flag_off_returns_base_unchanged(monkeypatch):
    # flag off ⇒ None (child inherits os.environ, byte-for-byte unchanged)
    assert config.subprocess_env() is None
    base = {"X": "1"}
    assert config.subprocess_env(base) is base


def test_subprocess_env_flag_on_strips_inference_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")
    env = config.subprocess_env()
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env
    # non-inference server vars still present
    assert env.get("AGENTED_SERVER_NO_LLM_KEYS") == "1"


def test_build_subprocess_env_flag_on_strips_poison(monkeypatch):
    from app.services.execution_runner import build_subprocess_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")
    env = build_subprocess_env({"FOO": "bar"})
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env
    assert env["FOO"] == "bar"


def test_build_subprocess_env_flag_on_keeps_per_request_override(monkeypatch):
    """A sidecar-sourced key layered in via env_overrides survives scrubbing."""
    from app.services.execution_runner import build_subprocess_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")
    env = build_subprocess_env({"ANTHROPIC_API_KEY": "sk-per-request"})
    assert env["ANTHROPIC_API_KEY"] == "sk-per-request"


def test_build_subprocess_env_flag_off_passthrough(monkeypatch):
    """Regression: flag off ⇒ env behavior byte-for-byte unchanged."""
    from app.services.execution_runner import build_subprocess_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    assert build_subprocess_env(None) is None
    env = build_subprocess_env({"FOO": "bar"})
    assert env["ANTHROPIC_API_KEY"] == POISON


def test_stream_via_cli_flag_on_passes_scrubbed_env(monkeypatch):
    """The CLI-fallback Popen must not inherit a server-baked poison key."""
    import app.services.conversation_streaming as cs

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    captured = {}

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(cs.subprocess, "Popen", _fake_popen)
    list(cs._stream_via_cli([{"role": "user", "content": "hi"}], "claude-x"))
    assert captured["env"] is not None
    assert "ANTHROPIC_API_KEY" not in captured["env"]


def test_stream_via_cli_flag_off_inherits_env(monkeypatch):
    """Regression: flag off ⇒ env=None (inherit os.environ, unchanged)."""
    import app.services.conversation_streaming as cs

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)

    captured = {}

    def _fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(cs.subprocess, "Popen", _fake_popen)
    list(cs._stream_via_cli([{"role": "user", "content": "hi"}], "claude-x"))
    assert captured["env"] is None


# --- fork path: config.scrub_env_inplace (PTY child, no real fork) ---------


def test_scrub_env_inplace_flag_on_pops_poison(monkeypatch):
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")
    environ = {"ANTHROPIC_API_KEY": POISON, "CLAUDE_CONFIG_DIR": "/cfg", "PATH": "/bin"}
    config.scrub_env_inplace(environ)
    assert "ANTHROPIC_API_KEY" not in environ
    # Non-inference vars (incl. the harness config dir) are untouched.
    assert environ["CLAUDE_CONFIG_DIR"] == "/cfg"
    assert environ["PATH"] == "/bin"


def test_scrub_env_inplace_flag_off_is_noop(monkeypatch):
    """Regression: flag off ⇒ mapping left byte-for-byte unchanged."""
    environ = {"ANTHROPIC_API_KEY": POISON, "PATH": "/bin"}
    before = dict(environ)
    config.scrub_env_inplace(environ)
    assert environ == before


def test_fork_child_scrubs_real_os_environ(monkeypatch):
    """The PTY child scrubs its inherited os.environ before execvp (no fork).

    We can't fork inside the test, so exercise the exact statement the child
    runs against the real os.environ it would inherit. monkeypatch owns both
    vars, so the pop is restored at teardown.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    config.scrub_env_inplace(os.environ)
    assert "ANTHROPIC_API_KEY" not in os.environ
    # A harness override layered on AFTER the scrub still survives.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/cfg")
    assert os.environ["CLAUDE_CONFIG_DIR"] == "/cfg"


# --- pipe path: project_session_manager._build_pipe_env --------------------


def test_pipe_env_flag_on_strips_poison(monkeypatch):
    from app.services.project_session_manager import _build_pipe_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    env = _build_pipe_env({"CLAUDE_CONFIG_DIR": "/cfg"})
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env
    assert env["CLAUDE_CONFIG_DIR"] == "/cfg"


def test_pipe_env_flag_off_inherits_poison(monkeypatch):
    """Regression: flag off ⇒ merged env carries os.environ byte-for-byte."""
    from app.services.project_session_manager import _build_pipe_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)

    env = _build_pipe_env(None)
    assert env["ANTHROPIC_API_KEY"] == POISON


# --- runner path: cli_agent_runner_service._build_env ----------------------


def test_runner_build_env_flag_on_with_config_dir_strips_poison(monkeypatch):
    from app.services.cli_agent_runner_service import _build_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    env = _build_env("claude", "~/.claude-personal1")
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env
    # The per-backend config override still lands.
    assert env["CLAUDE_CONFIG_DIR"].endswith(".claude-personal1")


def test_runner_build_env_flag_on_no_config_dir_returns_scrubbed(monkeypatch):
    """No override needed, but flag on ⇒ scrubbed dict (not raw os.environ)."""
    from app.services.cli_agent_runner_service import _build_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    monkeypatch.setenv("AGENTED_SERVER_NO_LLM_KEYS", "1")

    env = _build_env("claude", None)
    assert env is not None
    assert "ANTHROPIC_API_KEY" not in env


def test_runner_build_env_flag_off_no_override_returns_none(monkeypatch):
    """Regression: flag off + no config dir ⇒ None (inherit os.environ)."""
    from app.services.cli_agent_runner_service import _build_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    assert _build_env("claude", None) is None


def test_runner_build_env_flag_off_with_config_dir_keeps_poison(monkeypatch):
    """Regression: flag off ⇒ override env still inherits the env key."""
    from app.services.cli_agent_runner_service import _build_env

    monkeypatch.setenv("ANTHROPIC_API_KEY", POISON)
    env = _build_env("claude", "~/.claude-personal1")
    assert env["ANTHROPIC_API_KEY"] == POISON


# --- grep-guard: no NEW unguarded raw LLM-key reads ------------------------

# Raw *_API_KEY names that are NOT LLM inference keys and are legitimately read
# from the server's own environment (sidecar/self auth + the E2B sandbox
# provider). Every OTHER literal *_API_KEY read — most importantly a
# re-introduced ANTHROPIC_API_KEY fallback — must route through
# config.env_llm_key and therefore must NOT appear as a raw os.environ read.
_NON_LLM_KEY_NAMES = {
    "AI_ACCOUNTS_API_KEY",  # sidecar auth token
    "AGENTED_API_KEY",  # server self auth token
    "E2B_API_KEY",  # cloud sandbox provider
}

# Group 1 = literal key name (quoted) or None when the read is the dynamic
# os.environ.get(api_key_env, ...) account-mapping read (always an offender).
_RAW_KEY_PATTERN = re.compile(
    r"os\.environ(?:\.get\(|\[)\s*"
    r"(?:[\"']([A-Za-z0-9_]*API_KEY)[\"']|(api_key_env))"
)


def test_grep_guard_no_new_unguarded_llm_key_reads():
    offenders = []
    for py in APP_DIR.rglob("*.py"):
        rel = py.relative_to(BACKEND_ROOT).as_posix()
        text = py.read_text(encoding="utf-8")
        for m in _RAW_KEY_PATTERN.finditer(text):
            key_name = m.group(1)
            # Dynamic api_key_env read, or any LLM key name not on the
            # non-LLM allowlist, is an unguarded inference-key read.
            if key_name is None or key_name not in _NON_LLM_KEY_NAMES:
                line = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{rel}:{line}:{key_name or 'api_key_env'}")
    assert offenders == [], (
        "Unguarded raw LLM-key env read(s) found; route them through "
        f"config.env_llm_key: {offenders}"
    )
