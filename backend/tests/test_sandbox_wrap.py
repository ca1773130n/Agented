"""L1 unit tests for the OS-sandbox prefix builder (24-01).

Pure string/argv composition + degrade-path assertions — no real bwrap/seatbelt
is exercised here (that is the L3 escape test in test_sandbox_escape.py). Platform
and availability are monkeypatched so BOTH the Linux (bwrap) and macOS (SBPL) paths
are asserted regardless of the host running the suite.
"""

import os

from app.services import sandbox_wrap


def _reset(monkeypatch):
    """Clear the module-level probe cache + one-shot degrade-warning flag."""
    monkeypatch.setattr(sandbox_wrap, "_PROBE_CACHE", {})
    monkeypatch.setattr(sandbox_wrap, "_DEGRADE_WARNED", False)


def test_bwrap_prefix_composition(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "linux")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)

    cmd = ["claude", "-p", "hi"]
    prefix, sandboxed = sandbox_wrap.build_sandbox_prefix(
        cmd, "/ws", net=True, proxy_url="http://127.0.0.1:9000"
    )

    assert sandboxed is True
    assert prefix[0] == "bwrap"
    s = " ".join(prefix)
    assert "--bind /ws /ws" in s
    assert "--chdir /ws" in s
    assert "--ro-bind /usr /usr" in s
    assert "--proc /proc" in s
    assert "--dev /dev" in s
    assert "--tmpfs /tmp" in s
    assert "--unshare-all" in prefix
    # BLOCKER 2 (24-fix): private, empty netns — NO host network. The child cannot
    # bypass the L7 egress proxy (raw socket / DNS / hard-coded IP) because it has no
    # route off-box. ``--share-net`` (the bypass) must be gone.
    assert "--unshare-net" in prefix
    assert "--share-net" not in prefix
    assert "--die-with-parent" in prefix
    assert "--setenv HTTPS_PROXY http://127.0.0.1:9000" in s
    assert "--setenv HTTP_PROXY http://127.0.0.1:9000" in s
    # ends with `-- <cmd...>`
    dd = prefix.index("--")
    assert prefix[dd + 1 :] == cmd


def test_bwrap_no_proxy_omits_setenv(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "linux")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)
    prefix, sandboxed = sandbox_wrap.build_sandbox_prefix(["echo", "x"], "/ws", net=True)
    assert sandboxed is True
    assert "HTTPS_PROXY" not in " ".join(prefix)


def test_sbpl_profile_composition(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "darwin")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)

    cmd = ["claude", "-p", "hi"]
    prefix, sandboxed = sandbox_wrap.build_sandbox_prefix(
        cmd, "/ws", net=True, proxy_url="http://127.0.0.1:9000"
    )

    assert sandboxed is True
    assert prefix[0] == "sandbox-exec"
    assert prefix[1] == "-p"
    profile = prefix[2]
    assert prefix[3:] == cmd
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "(deny file-write*)" in profile
    assert '(allow file-write* (subpath "/ws"))' in profile
    assert "(deny network*)" in profile
    assert '(allow network* (remote ip "localhost:9000"))' in profile


def test_sbpl_reads_are_scoped_not_global(monkeypatch):
    """BLOCKER 1 (24-fix): the SBPL no longer grants an unconditional global read of
    the whole filesystem. It keeps broad read for system libs (dyld/exec) but DENIES
    reading file CONTENTS under the home dir, fully denies the credential dirs, and
    re-allows only the workspace + interpreter/tool install roots."""
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "darwin")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: "/Users/tester" if p == "~" else p)

    prefix, sandboxed = sandbox_wrap.build_sandbox_prefix(["claude", "-p", "hi"], "/ws", net=False)
    assert sandboxed is True
    profile = prefix[2]

    # Reading the CONTENTS of files under the home dir is denied...
    assert '(deny file-read-data (subpath "/Users/tester"))' in profile
    # ...and the high-value credential dirs are fully denied (metadata too).
    assert '(deny file-read* (subpath "/Users/tester/.ssh"))' in profile
    assert '(deny file-read* (subpath "/Users/tester/.aws"))' in profile
    assert '(deny file-read* (subpath "/Users/tester/.config"))' in profile
    assert '(deny file-read* (literal "/Users/tester/.netrc"))' in profile
    # The workspace contents ARE re-allowed (so the child can actually work).
    assert '(allow file-read-data (subpath "/ws"))' in profile
    # The bare, unconditional global read grant is gone.
    assert "(allow file-read*)\n(deny file-write*)" not in profile


def test_sbpl_network_allow_only_with_proxy(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "darwin")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)
    # net=False, no proxy → fully offline: no remote allow, no broad allow.
    prefix, _ = sandbox_wrap.build_sandbox_prefix(["echo", "x"], "/ws", net=False)
    profile = prefix[2]
    assert "(allow network*" not in profile
    assert "(deny network*)" in profile


def test_degrade_when_unavailable(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap.shutil, "which", lambda _tool: None)
    warnings: list = []
    monkeypatch.setattr(sandbox_wrap.logger, "warning", lambda *a, **k: warnings.append(a))

    cmd = ["echo", "x"]
    out, sandboxed = sandbox_wrap.build_sandbox_prefix(cmd, "/ws")

    assert out == cmd
    assert sandboxed is False
    assert len(warnings) == 1  # exactly one degrade warning


def test_probe_failure_degrades(monkeypatch):
    _reset(monkeypatch)
    # which() succeeds but the runtime probe fails (e.g. unprivileged userns off).
    monkeypatch.setattr(sandbox_wrap.shutil, "which", lambda _tool: "/usr/bin/" + _tool)
    monkeypatch.setattr(sandbox_wrap, "_probe", lambda _tool: False)
    warnings: list = []
    monkeypatch.setattr(sandbox_wrap.logger, "warning", lambda *a, **k: warnings.append(a))

    out, sandboxed = sandbox_wrap.build_sandbox_prefix(["echo", "x"], "/ws")

    assert sandboxed is False
    assert out == ["echo", "x"]
    assert len(warnings) == 1


def test_sandbox_enabled_reads_env(monkeypatch):
    monkeypatch.delenv(sandbox_wrap._SANDBOX_ENABLED_ENV, raising=False)
    assert sandbox_wrap.sandbox_enabled() is False
    monkeypatch.setenv(sandbox_wrap._SANDBOX_ENABLED_ENV, "1")
    assert sandbox_wrap.sandbox_enabled() is True


def test_wrap_harness_command_passthrough_when_disabled(monkeypatch):
    monkeypatch.delenv(sandbox_wrap._SANDBOX_ENABLED_ENV, raising=False)
    out, sandboxed = sandbox_wrap.wrap_harness_command(["echo", "x"], "/ws")
    assert out == ["echo", "x"]
    assert sandboxed is False


def test_wrap_harness_command_no_workspace_passthrough(monkeypatch):
    monkeypatch.setenv(sandbox_wrap._SANDBOX_ENABLED_ENV, "1")
    out, sandboxed = sandbox_wrap.wrap_harness_command(["echo", "x"], None)
    assert out == ["echo", "x"]
    assert sandboxed is False


# --------------------------------------------------------------------------- #
# BLOCKER 1 (24-fix): the credential denies must be the FINAL word, and
# _interpreter_read_paths must never re-allow $HOME / a credential dir.
# --------------------------------------------------------------------------- #
def test_interpreter_read_paths_never_emits_home(monkeypatch, tmp_path):
    """A home-rooted tool ($HOME/bin/claude) derives the parent $HOME — but that must
    be FILTERED, else re-allowing $HOME re-opens ~/.ssh for read (defense-in-depth
    beside the SBPL reorder)."""
    home = str(tmp_path)
    monkeypatch.setattr(os.path, "expanduser", lambda p: home if p == "~" else p)
    paths = sandbox_wrap._interpreter_read_paths([os.path.join(home, "bin", "claude")])
    assert home not in paths, "must not re-allow $HOME"
    assert os.path.dirname(home) not in paths, "must not re-allow an ancestor of $HOME"
    # The tool's own bin dir (neither $HOME nor a cred dir) IS still allowed.
    assert os.path.join(home, "bin") in paths


def test_interpreter_read_paths_filters_credential_dirs(monkeypatch, tmp_path):
    """A tool nested under a credential dir must not re-allow that credential dir."""
    home = str(tmp_path)
    monkeypatch.setattr(os.path, "expanduser", lambda p: home if p == "~" else p)
    tool = os.path.join(home, ".config", "foo", "bin", "tool")
    paths = sandbox_wrap._interpreter_read_paths([tool])
    cfg_root = os.path.join(home, ".config")
    for p in paths:
        assert not p.startswith(cfg_root), f"{p} re-opens a credential dir"


def test_sbpl_credential_denies_are_the_final_word(monkeypatch):
    """The credential denies are emitted AFTER the workspace/interpreter re-allows, so
    SBPL last-match-wins keeps ~/.ssh denied even under a home-rooted read allow."""
    _reset(monkeypatch)
    monkeypatch.setattr(os.path, "expanduser", lambda p: "/Users/tester" if p == "~" else p)
    # Force a home-rooted read allow (an interpreter resolved under $HOME).
    profile = sandbox_wrap._build_sbpl_profile(
        "/ws", net=False, proxy_url=None, read_paths=["/Users/tester"]
    )
    lines = profile.splitlines()
    allow_idxs = [
        i for i, ln in enumerate(lines) if ln.startswith("(allow file-read-data (subpath")
    ]
    ssh_deny_idx = next(
        i for i, ln in enumerate(lines) if ln == '(deny file-read* (subpath "/Users/tester/.ssh"))'
    )
    # An explicit file-read-DATA deny is REQUIRED — a file-read* deny alone does not
    # override a preceding file-read-data allow (empirical seatbelt quirk).
    ssh_data_deny_idx = next(
        i
        for i, ln in enumerate(lines)
        if ln == '(deny file-read-data (subpath "/Users/tester/.ssh"))'
    )
    assert allow_idxs, "expected read re-allows in the profile"
    assert ssh_deny_idx > max(allow_idxs), "credential deny must WIN over any read allow"
    assert ssh_data_deny_idx > max(allow_idxs), "credential DATA deny must WIN over any read allow"
    # The home-rooted allow really is present (the exact defeat scenario we guard).
    assert '(allow file-read-data (subpath "/Users/tester"))' in profile


def test_sbpl_config_dirs_readable_and_writable(monkeypatch):
    """MAJOR 1 (24-fix): harness config dirs are re-allowed for READ and WRITE so a
    sandboxed claude/codex/gemini can reach CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_HOME."""
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "darwin")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: "/Users/tester" if p == "~" else p)
    cfg = "/Users/tester/.claude"
    prefix, _ = sandbox_wrap.build_sandbox_prefix(
        ["claude", "-p", "hi"], "/ws", net=False, config_dirs=[cfg]
    )
    profile = prefix[2]
    assert f'(allow file-read-data (subpath "{cfg}"))' in profile
    assert f'(allow file-write* (subpath "{cfg}"))' in profile


def test_bwrap_binds_config_dirs(monkeypatch, tmp_path):
    """MAJOR 1 (24-fix): bwrap binds existing harness config dirs read-write; a missing
    config dir is skipped (existence-guarded) so bwrap never fails."""
    _reset(monkeypatch)
    monkeypatch.setattr(sandbox_wrap, "_platform", lambda: "linux")
    monkeypatch.setattr(sandbox_wrap, "sandbox_available", lambda: True)
    cfg = tmp_path / "dot-claude"
    cfg.mkdir()
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    prefix, _ = sandbox_wrap.build_sandbox_prefix(["claude"], ws, net=False, config_dirs=[str(cfg)])
    assert f"--bind {cfg} {cfg}" in " ".join(prefix)
    # A non-existent config dir is skipped (guarded).
    missing = str(tmp_path / "nope")
    prefix2, _ = sandbox_wrap.build_sandbox_prefix(["claude"], ws, net=False, config_dirs=[missing])
    assert missing not in " ".join(prefix2)
