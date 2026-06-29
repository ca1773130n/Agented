"""Composition + degrade-path tests for the OS-level sandbox-prefix builder.

All assertions are pure string/argv checks — no real bwrap/sandbox-exec is
invoked, so the suite runs deterministically in CI on any platform.
"""

from __future__ import annotations

import app.services.sandbox_wrap as sw


# ---------------------------------------------------------------------------
# Task 1: bwrap prefix composition
# ---------------------------------------------------------------------------


def test_bwrap_prefix_contains_required_tokens():
    prefix = sw._build_bwrap_prefix(
        ["claude", "-p"], workspace="/ws", proxy_addr="127.0.0.1:9119"
    )
    joined = " ".join(prefix)
    assert prefix[0] == "bwrap"
    assert "--bind /ws /ws" in joined
    assert "--unshare-all" in joined
    assert "--share-net" in joined
    assert "--die-with-parent" in joined
    assert "--chdir /ws" in joined
    assert "--setenv HTTPS_PROXY http://127.0.0.1:9119" in joined
    assert "--setenv HTTP_PROXY http://127.0.0.1:9119" in joined
    # original command preserved at the tail, after a -- terminator
    assert prefix[-2:] == ["claude", "-p"]
    assert "--" in prefix
    assert prefix.index("--") < prefix.index("claude")


def test_bwrap_prefix_no_proxy_omits_proxy_setenv():
    prefix = sw._build_bwrap_prefix(["claude"], workspace="/ws", proxy_addr=None)
    joined = " ".join(prefix)
    assert "HTTPS_PROXY" not in joined
    assert "HTTP_PROXY" not in joined
    # FS isolation still present
    assert "--bind /ws /ws" in joined
    assert "--unshare-all" in joined


# ---------------------------------------------------------------------------
# Task 1: SBPL profile + prefix composition
# ---------------------------------------------------------------------------


def test_sbpl_profile_contains_required_tokens():
    profile = sw._build_sbpl_profile(workspace="/ws", proxy_addr="127.0.0.1:9119")
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert '(allow file-write* (subpath "/ws"))' in profile
    # local proxy host allowed when a proxy is given
    assert "127.0.0.1" in profile
    assert "allow network" in profile


def test_sbpl_profile_no_proxy_is_fs_only():
    profile = sw._build_sbpl_profile(workspace="/ws", proxy_addr=None)
    assert "(deny network*)" in profile
    assert '(allow file-write* (subpath "/ws"))' in profile
    # no proxy => no network allow carve-out
    assert "allow network" not in profile


def test_sbpl_prefix_wraps_command():
    prefix = sw._build_sbpl_prefix(
        ["claude", "-p"], workspace="/ws", proxy_addr="127.0.0.1:9119"
    )
    assert prefix[0] == "sandbox-exec"
    assert prefix[1] == "-p"
    assert "(deny default)" in prefix[2]
    assert prefix[3:] == ["claude", "-p"]


# ---------------------------------------------------------------------------
# Task 2: public build_sandbox_prefix + detection/degrade
# ---------------------------------------------------------------------------


def test_build_prefix_degrades_when_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(sw, "sandbox_available", lambda: False)
    import logging

    with caplog.at_level(logging.WARNING):
        prefix, sandboxed = sw.build_sandbox_prefix(
            ["claude", "-p"], workspace="/ws"
        )
    assert sandboxed is False
    assert prefix == ["claude", "-p"]
    assert any("sandbox" in r.message.lower() for r in caplog.records)


def test_build_prefix_uses_bwrap_on_linux(monkeypatch):
    monkeypatch.setattr(sw.sys, "platform", "linux")
    monkeypatch.setattr(sw, "sandbox_available", lambda: True)
    prefix, sandboxed = sw.build_sandbox_prefix(
        ["claude", "-p"], workspace="/ws", proxy_addr="127.0.0.1:9119"
    )
    assert sandboxed is True
    assert prefix[0] == "bwrap"
    assert prefix[-2:] == ["claude", "-p"]


def test_build_prefix_uses_sandbox_exec_on_macos(monkeypatch):
    monkeypatch.setattr(sw.sys, "platform", "darwin")
    monkeypatch.setattr(sw, "sandbox_available", lambda: True)
    prefix, sandboxed = sw.build_sandbox_prefix(["claude"], workspace="/ws")
    assert sandboxed is True
    assert prefix[0] == "sandbox-exec"
    assert prefix[-1] == "claude"


def test_sandbox_available_returns_false_on_probe_failure(monkeypatch):
    # which() finds the binary but the probe run raises => degrade, never raise.
    sw._PROBE_CACHE.clear()
    monkeypatch.setattr(sw.shutil, "which", lambda _name: "/usr/bin/bwrap")

    def _boom(*_a, **_k):
        raise OSError("userns disabled")

    monkeypatch.setattr(sw.subprocess, "run", _boom)
    monkeypatch.setattr(sw.sys, "platform", "linux")
    assert sw.sandbox_available() is False
