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

from app.services import egress_proxy, sandbox_wrap
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


def test_sbpl_home_rooted_read_allow_does_not_expose_ssh_live(tmp_path, monkeypatch):
    """BLOCKER 1 (24-fix), LIVE seatbelt: even when a read re-allow covers $HOME
    (the exact case a tool resolved under $HOME would produce), reading
    ``~/.ssh/id_rsa`` is STILL blocked — the credential denies are the FINAL word in
    the reordered profile. This proves the reorder at runtime, not just in the argv.

    macOS-only (SBPL). On Linux bwrap the host FS simply isn't bound, so there is no
    analogous last-match ordering to prove — that path is covered argv-only."""
    if sys.platform != "darwin":
        pytest.skip("macOS seatbelt (SBPL) last-match ordering only")

    # macOS canonicalizes paths (/var → /private/var) before matching SBPL subpaths,
    # so every path baked into the profile MUST be realpath'd or the rules silently
    # miss the kernel's canonical path (mirrors the other live tests' os.path.realpath).
    base = os.path.realpath(str(tmp_path))
    fake_home = os.path.join(base, "home")
    ssh = os.path.join(fake_home, ".ssh")
    os.makedirs(ssh)
    secret = os.path.join(ssh, "id_rsa")
    with open(secret, "w") as fh:
        fh.write("TOP-SECRET-KEY-MATERIAL")
    ws = os.path.join(base, "ws")
    os.makedirs(ws)
    # ``_build_sbpl_profile`` reads $HOME via expanduser("~"); point it at the fake home.
    monkeypatch.setenv("HOME", fake_home)

    # Force a home-rooted read allow (read_paths=[$HOME]) — the defeat scenario.
    profile = sandbox_wrap._build_sbpl_profile(
        ws, net=False, proxy_url=None, read_paths=[fake_home]
    )
    r = subprocess.run(
        ["sandbox-exec", "-p", profile, "/bin/cat", secret],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode != 0, "home-rooted read allow must NOT re-expose ~/.ssh/id_rsa"
    assert "TOP-SECRET" not in r.stdout


def test_config_dir_home_or_root_dropped_ssh_blocked_live(tmp_path, monkeypatch):
    """ITEM 4 (24-fix), LIVE seatbelt: a config dir of $HOME or / is REJECTED (never
    added to the SBPL allows), so a hostile/misconfigured CLAUDE_CONFIG_DIR can't
    re-open the whole home — reading ~/.ssh/id_rsa stays blocked. A proper config
    SUBDIR (~/.claude) IS added and readable while ~/.ssh remains blocked.

    macOS-only (SBPL live read-scoping). Uses a FAKE $HOME so no real secret is touched."""
    if sys.platform != "darwin":
        pytest.skip("macOS seatbelt (SBPL) live read-scoping only")

    base = os.path.realpath(str(tmp_path))
    fake_home = os.path.join(base, "home")
    ssh = os.path.join(fake_home, ".ssh")
    os.makedirs(ssh)
    ssh_secret = os.path.join(ssh, "id_rsa")
    with open(ssh_secret, "w") as fh:
        fh.write("TOP-SECRET-KEY")
    claude_cfg = os.path.join(fake_home, ".claude")  # a legit config SUBDIR
    os.makedirs(claude_cfg)
    cfg_file = os.path.join(claude_cfg, "settings.json")
    with open(cfg_file, "w") as fh:
        fh.write("CONFIG-OK")
    ws = os.path.join(base, "ws")
    os.makedirs(ws)
    monkeypatch.setenv("HOME", fake_home)

    # (a) config_dir == $HOME → dropped: NOT added to the allows, ~/.ssh still blocked.
    pfx_home, _ = build_sandbox_prefix(
        ["/bin/cat", ssh_secret], ws, net=False, config_dirs=[fake_home]
    )
    profile_home = pfx_home[2]
    assert f'(allow file-read-data (subpath "{fake_home}"))' not in profile_home, (
        "config_dir == $HOME must be dropped, not granted a broad home read"
    )
    assert f'(allow file-write* (subpath "{fake_home}"))' not in profile_home
    r_home = subprocess.run(pfx_home, capture_output=True, text=True, timeout=30)
    assert r_home.returncode != 0 and "TOP-SECRET" not in r_home.stdout, (
        "config_dir == $HOME must not re-expose ~/.ssh"
    )

    # (b) config_dir == "/" → dropped (never grants root).
    pfx_root, _ = build_sandbox_prefix(["/bin/cat", ssh_secret], ws, net=False, config_dirs=["/"])
    profile_root = pfx_root[2]
    assert '(allow file-read-data (subpath "/"))' not in profile_root
    assert '(allow file-write* (subpath "/"))' not in profile_root

    # (c) config_dir == a proper subdir (~/.claude) → added + readable, ~/.ssh blocked.
    real_cfg = os.path.realpath(claude_cfg)
    pfx_cfg, _ = build_sandbox_prefix(
        ["/bin/cat", cfg_file], ws, net=False, config_dirs=[claude_cfg]
    )
    assert f'(allow file-read-data (subpath "{real_cfg}"))' in pfx_cfg[2]
    r_cfg = subprocess.run(pfx_cfg, capture_output=True, text=True, timeout=30)
    assert r_cfg.returncode == 0 and "CONFIG-OK" in r_cfg.stdout, r_cfg.stderr
    pfx_ssh, _ = build_sandbox_prefix(
        ["/bin/cat", ssh_secret], ws, net=False, config_dirs=[claude_cfg]
    )
    r_ssh = subprocess.run(pfx_ssh, capture_output=True, text=True, timeout=30)
    assert r_ssh.returncode != 0 and "TOP-SECRET" not in r_ssh.stdout, (
        "~/.ssh must stay blocked even with a valid config dir granted"
    )


def test_secret_blocked_when_home_is_symlinked_live(tmp_path, monkeypatch):
    """ITEM 1 (24-fix), LIVE seatbelt: when $HOME itself is a SYMLINK, ``expanduser``
    returns the non-canonical link path — a credential deny keyed on THAT raw path would
    miss the kernel's canonical path, leaving ~/.ssh readable. realpath-canonicalizing
    $HOME (and emitting BOTH forms) blocks the secret via the canonical AND the aliased
    path. macOS-only (SBPL canonical-path matching)."""
    if sys.platform != "darwin":
        pytest.skip("macOS seatbelt canonical-path matching only")

    base = os.path.realpath(str(tmp_path))
    real_home = os.path.join(base, "realhome")
    ssh = os.path.join(real_home, ".ssh")
    os.makedirs(ssh)
    secret = os.path.join(ssh, "id_rsa")
    with open(secret, "w") as fh:
        fh.write("TOP-SECRET-VIA-ALIASED-HOME")
    ws = os.path.join(base, "ws")
    os.makedirs(ws)
    home_link = os.path.join(base, "homelink")  # $HOME is a symlink → real_home
    os.symlink(real_home, home_link)
    monkeypatch.setenv("HOME", home_link)

    # Reach the secret via BOTH the canonical path and the symlinked-home path.
    for path in (secret, os.path.join(home_link, ".ssh", "id_rsa")):
        prefix, sandboxed = build_sandbox_prefix(["/bin/cat", path], ws, net=False)
        assert sandboxed is True, "sandbox_available() was True but the wrap degraded"
        r = subprocess.run(prefix, capture_output=True, text=True, timeout=30)
        assert r.returncode != 0, f"reading {path} must be blocked under an aliased $HOME"
        assert "TOP-SECRET" not in r.stdout


def test_secret_via_symlink_into_ssh_blocked_live(tmp_path, monkeypatch):
    """ITEM 1 (24-fix), LIVE seatbelt: a secret reached via a SYMLINK (outside home)
    that points into ~/.ssh is still blocked — seatbelt canonicalizes the accessed
    path and the realpath'd credential deny matches it. macOS-only."""
    if sys.platform != "darwin":
        pytest.skip("macOS seatbelt canonical-path matching only")

    base = os.path.realpath(str(tmp_path))
    fake_home = os.path.join(base, "home")
    ssh = os.path.join(fake_home, ".ssh")
    os.makedirs(ssh)
    secret = os.path.join(ssh, "id_rsa")
    with open(secret, "w") as fh:
        fh.write("TOP-SECRET-KEY-MATERIAL")
    ws = os.path.join(base, "ws")
    os.makedirs(ws)
    link = os.path.join(base, "link_to_ssh")  # OUTSIDE home, points into ~/.ssh
    os.symlink(ssh, link)
    monkeypatch.setenv("HOME", fake_home)

    linked_secret = os.path.join(link, "id_rsa")  # resolves to ~/.ssh/id_rsa
    prefix, sandboxed = build_sandbox_prefix(["/bin/cat", linked_secret], ws, net=False)
    assert sandboxed is True
    r = subprocess.run(prefix, capture_output=True, text=True, timeout=30)
    assert r.returncode != 0, "reading ~/.ssh/id_rsa via a symlink must be blocked"
    assert "TOP-SECRET" not in r.stdout


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
