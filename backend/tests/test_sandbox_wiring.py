"""Defense-in-depth sweep (24-03, crit 1 + repo bug-class-sweep rule).

Every harness ``subprocess.Popen`` call site must route its command through the
Phase-24 OS-sandbox wrapper (``wrap_harness_command`` / ``build_sandbox_prefix`` /
the execution_service ``_apply_sandbox_and_enforce`` seam). This AST/source sweep
asserts no BARE harness Popen remains — matching Pitfall 1 (missing a Popen site
leaves it unsandboxed).
"""

from pathlib import Path

_SERVICES = Path(__file__).resolve().parent.parent / "app" / "services"

# Harness-launch service modules that MUST sandbox-wrap their Popen commands.
_HARNESS_MODULES = [
    "execution_service.py",
    "conversation_streaming.py",
    "cli_agent_runner_service.py",
    "setup_execution_service.py",
    "base_generation_service.py",
    "replay_service.py",
    # 24-fix crit 7: the goal-loop/ralph/team/agent/sketch chokepoint (pty.fork +
    # subprocess.Popen) must sandbox-wrap AND enforce too.
    "project_session_manager.py",
]

# Tokens that prove a module routes its launch through the sandbox layer.
# ``apply_sandbox_and_enforce`` (the shared wrap+enforce seam) is a substring of
# ExecutionService's ``_apply_sandbox_and_enforce``, so it matches both.
_WRAP_TOKENS = (
    "wrap_harness_command",
    "build_sandbox_prefix",
    "apply_sandbox_and_enforce",
)

# Explicit allowlist marker for a Popen that is legitimately NOT a harness launch.
_NON_HARNESS_MARKER = "sandbox: non-harness"


def test_all_harness_popen_sites_wrapped():
    offenders = []
    for name in _HARNESS_MODULES:
        src = (_SERVICES / name).read_text()
        # Real call sites only ("subprocess.Popen(") — not type annotations.
        if "subprocess.Popen(" not in src:
            continue
        if any(tok in src for tok in _WRAP_TOKENS):
            continue
        if _NON_HARNESS_MARKER in src:
            continue
        offenders.append(name)

    assert not offenders, (
        "harness Popen sites not routed through the OS-sandbox wrapper "
        f"(add wrap_harness_command / build_sandbox_prefix): {offenders}"
    )


def test_execution_service_uses_enforce_seam():
    """The central chokepoint must set the REAL sandboxed flag on the launch gate."""
    src = (_SERVICES / "execution_service.py").read_text()
    assert "_apply_sandbox_and_enforce" in src
    # sandboxed must flow from the wrap result into enforce_launch, not be hardcoded.
    assert "sandboxed=sandboxed" in src
    assert "sandboxed=False,  # no sandbox runtime until Phase 24" not in src


def test_psm_wraps_after_config_dir_resolution():
    """MAJOR 1 (24-fix): create_session must resolve the harness config-dir env
    (CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_HOME) FIRST, then OS-sandbox-wrap, passing
    those dirs into the sandbox allow-list — so a sandboxed harness can read its config
    dir. Guard both the threading and the ordering (wrap AFTER the env is resolved)."""
    src = (_SERVICES / "project_session_manager.py").read_text()
    assert "config_dirs=_config_dirs" in src
    for key in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "GEMINI_HOME"):
        assert key in src, f"config-dir key {key} not collected"
    wrap_idx = src.index("config_dirs=_config_dirs")
    inject_idx = src.index('env["CLAUDE_CONFIG_DIR"] = expanded')
    assert wrap_idx > inject_idx, "sandbox wrap must run AFTER CLAUDE_CONFIG_DIR is resolved"
