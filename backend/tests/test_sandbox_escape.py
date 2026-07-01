"""L3 escape-attempt boundary proof (24-05, crit 5) — skip-if-unavailable.

On a host WITH a usable OS sandbox (macOS seatbelt / Linux bwrap) these run a REAL
wrapped command that (a) tries to write OUTSIDE the workspace and (b) tries to
CONNECT to a NON-allowlisted host through the deny-by-default egress proxy, and
assert BOTH are blocked (and the connect is logged as a deny). On a host without
any usable sandbox they SKIP cleanly (``sandbox_available()`` is False) rather than
failing — the CI reality from 24-RESEARCH §Test Design.

CEILING (Pitfall 3): v1 egress is env+proxy BEST-EFFORT. These prove the configured
boundary holds for a COOPERATING client — not that a hostile process cannot bypass
env vars / dial a raw IP. Airtight no-bypass needs netns + nftables (deferred).
"""

import os
import subprocess
import sys
import time

import pytest

from app.services import egress_proxy
from app.services.egress_proxy import ThreadedEgressProxy
from app.services.sandbox_wrap import build_sandbox_prefix, sandbox_available

pytestmark = pytest.mark.skipif(
    not sandbox_available(), reason="no usable OS sandbox (bwrap/seatbelt) on this host"
)

_OUTSIDE_PROBES = ("/etc/agented_escape_probe", "/escape_probe")


def test_escape_write_outside_workspace_blocked(tmp_path):
    ws = os.path.realpath(str(tmp_path))
    inside = os.path.join(ws, "inside_probe")
    # One command: a write INSIDE the workspace (must succeed) + writes OUTSIDE it
    # (must be contained). The "|| true" keeps the shell rc clean regardless.
    script = (
        f"echo inside > {inside}; "
        "echo escaped > /etc/agented_escape_probe 2>/dev/null || "
        "echo escaped > /escape_probe 2>/dev/null; true"
    )
    prefix, sandboxed = build_sandbox_prefix(["/bin/sh", "-c", script], ws, net=False)
    assert sandboxed is True, "sandbox_available() was True but the wrap degraded"

    try:
        subprocess.run(prefix, capture_output=True, text=True, timeout=30)
        # The write OUTSIDE the workspace was contained — neither path exists.
        for p in _OUTSIDE_PROBES:
            assert not os.path.exists(p), f"escape write landed at {p}"
        # The write INSIDE the workspace SUCCEEDED — proving it's a boundary, not a
        # blanket write block.
        assert os.path.exists(inside), "in-workspace write should be allowed"
    finally:
        for p in _OUTSIDE_PROBES:
            try:
                os.path.exists(p) and os.remove(p)
            except OSError:
                pass


def test_escape_read_secret_outside_workspace_blocked(tmp_path):
    """BLOCKER 1 (24-fix): a wrapped child can read WITHIN the workspace and run a
    real interpreter, but reading a secret under the home dir is BLOCKED — the SBPL
    no longer grants global ``file-read*``. Linux bwrap already can't see the host FS
    outside its binds; this asserts the macOS seatbelt read-scoping empirically."""
    ws = os.path.realpath(str(tmp_path))
    inside = os.path.join(ws, "inside.txt")
    with open(inside, "w") as fh:
        fh.write("workspace-data")

    # A secret UNDER the home dir (where ~/.ssh / ~/.aws / credentials live). We use
    # a uniquely-named probe file so we never touch real user secrets; cleaned up.
    home = os.path.expanduser("~")
    secret = os.path.join(home, ".agented_sandbox_read_probe")
    with open(secret, "w") as fh:
        fh.write("TOP-SECRET")
    try:
        # Reading the in-workspace file SUCCEEDS (proves it's a boundary, not a block).
        pfx_in, sandboxed = build_sandbox_prefix(["/bin/cat", inside], ws, net=False)
        assert sandboxed is True, "sandbox_available() was True but the wrap degraded"
        r_in = subprocess.run(pfx_in, capture_output=True, text=True, timeout=30)
        assert r_in.returncode == 0 and "workspace-data" in r_in.stdout, r_in.stderr

        # Running a real interpreter still works (system libs remain readable).
        pfx_py, _ = build_sandbox_prefix(
            [sys.executable, "-c", "import json,ssl,hashlib;print('pyok')"], ws, net=False
        )
        r_py = subprocess.run(pfx_py, capture_output=True, text=True, timeout=30)
        assert r_py.returncode == 0 and "pyok" in r_py.stdout, r_py.stderr

        # Reading the home-dir secret is DENIED — cat cannot read the contents.
        pfx_secret, _ = build_sandbox_prefix(["/bin/cat", secret], ws, net=False)
        r_secret = subprocess.run(pfx_secret, capture_output=True, text=True, timeout=30)
        assert r_secret.returncode != 0, "reading a home-dir secret must be blocked"
        assert "TOP-SECRET" not in r_secret.stdout
    finally:
        try:
            os.remove(secret)
        except OSError:
            pass


def test_escape_connect_non_allowlisted_blocked(tmp_path, monkeypatch):
    ws = os.path.realpath(str(tmp_path))
    captured: list = []
    monkeypatch.setattr(egress_proxy.logger, "warning", lambda *a, **k: captured.append(a))

    # Allowlist contains a benign host (loopback) but NOT the target.
    proxy = ThreadedEgressProxy(allowlist={"127.0.0.1"}, session_id="escape").start()
    try:
        script = (
            'import urllib.request; urllib.request.urlopen("http://blocked.invalid/", timeout=5)'
        )
        prefix, sandboxed = build_sandbox_prefix(
            [sys.executable, "-c", script], ws, net=True, proxy_url=proxy.url
        )
        assert sandboxed is True
        # The macOS SBPL wrap does not inject proxy env (bwrap does via --setenv), so
        # point the client at the proxy explicitly — the sandbox still confines the
        # child to reaching ONLY the proxy on loopback.
        env = dict(os.environ)
        env.update(
            {
                "http_proxy": proxy.url,
                "https_proxy": proxy.url,
                "HTTP_PROXY": proxy.url,
                "HTTPS_PROXY": proxy.url,
            }
        )
        result = subprocess.run(prefix, env=env, capture_output=True, text=True, timeout=30)
        # The connection to the NON-allowlisted host is refused (403 surfaces as a
        # non-zero exit from urllib).
        assert result.returncode != 0, result.stderr
        # And the proxy logged the deny for the blocked host.
        time.sleep(0.2)
        assert any("blocked.invalid" in str(x) for a in captured for x in a), (
            "expected an egress deny log for the non-allowlisted host"
        )
    finally:
        proxy.stop()
