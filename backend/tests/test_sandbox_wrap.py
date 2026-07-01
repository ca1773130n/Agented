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
