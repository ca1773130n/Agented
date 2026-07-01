"""OS-level sandbox command-prefix builder (phase 24, 24-01).

`build_sandbox_prefix` returns an argv PREFIX (bubblewrap on Linux,
``sandbox-exec -p <SBPL>`` on macOS) plus a ``sandboxed: bool`` — so the existing
``subprocess.Popen`` at every harness site stays put and just gets a prefix,
exactly mirroring the ``stdbuf`` prepend already in ``execution_service``. This is
a prefix-builder, NOT a second launcher.

Detection (:func:`sandbox_available`) probes for a *usable* sandbox — ``which`` AND
a cached runtime probe that catches a kernel with ``unprivileged_userns_clone=0``
(``bwrap`` present but unusable). When no usable OS sandbox exists the builder
degrades IN PLACE to ``(cmd, sandboxed=False)`` + a single logged warning and NEVER
raises; the Phase-23 ``enforce_sandbox`` policy then decides launch-vs-refuse
(fail closed). This generalizes the ``sandbox_eval.py`` pattern (scrubbed-env
allowlist, ``IsolatedResult.sandboxed`` reporting) beyond deterministic eval checks.

ponytail: v1 egress is env+proxy BEST-EFFORT — bwrap keeps ``--share-net`` (host
netns) and only injects ``HTTPS_PROXY``/``HTTP_PROXY``, which a hostile child could
unset or bypass by connecting to a raw IP. The airtight upgrade is an unprivileged
network namespace (``--unshare-net`` with the proxy bound inside it) + ``nftables``
forcing all egress to the proxy port; deferred to a later wave (see 24-RESEARCH
Pitfall 3 + Open Q1). We reuse ``sandbox_eval._ENV_ALLOWLIST`` rather than deriving
a second env allowlist.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse

# Reuse the env-scrub allowlist convention from the deterministic-eval sandbox
# rather than re-deriving one (24-01 key_link).
from .sandbox_eval import _ENV_ALLOWLIST  # noqa: F401  (re-exported convention)

logger = logging.getLogger(__name__)

# Feature flag for LIVE wiring (Plan 03). ``build_sandbox_prefix`` itself wraps
# whenever a usable sandbox exists (so the composition/escape tests exercise the
# real builder), but the harness launch sites gate on this so normal operation is
# unaffected until an operator opts in (the prod image must ship bwrap first —
# 24-RESEARCH Open Q2, deferred to the deployment phase). When OFF, a policy that
# mandates ``enforce_sandbox`` still refuses every launch (sandboxed=False → deny),
# which is the intended fail-closed contract.
_SANDBOX_ENABLED_ENV = "AGENTED_SANDBOX"

# Per-tool cached runtime-probe result (probe once per process — Pitfall 2).
_PROBE_CACHE: dict[str, bool] = {}
# Ensures the degrade warning is logged once per process, not per launch.
_DEGRADE_WARNED = False


def _platform() -> str:
    """Return the current platform token (indirection so tests can monkeypatch)."""
    return sys.platform


def _tool_for_platform(platform: str) -> str | None:
    if platform.startswith("linux"):
        return "bwrap"
    if platform == "darwin":
        return "sandbox-exec"
    return None


def _probe(tool: str) -> bool:
    """Cached runtime probe: is ``tool`` not merely present but actually usable?

    Catches the classic ``bwrap`` failure mode where ``shutil.which`` succeeds but
    the kernel has unprivileged user namespaces disabled
    (``kernel.unprivileged_userns_clone=0`` → "setting up uid map: Permission
    denied"). Result is cached module-level so we probe at most once per process.
    """
    if tool in _PROBE_CACHE:
        return _PROBE_CACHE[tool]
    if tool == "bwrap":
        probe_cmd = ["bwrap", "--ro-bind", "/", "/", "true"]
    elif tool == "sandbox-exec":
        probe_cmd = ["sandbox-exec", "-p", "(version 1)(allow default)", "true"]
    else:  # pragma: no cover - defensive
        _PROBE_CACHE[tool] = False
        return False
    try:
        rc = subprocess.run(
            probe_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode
        ok = rc == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _PROBE_CACHE[tool] = ok
    return ok


def sandbox_available() -> bool:
    """True iff this host has a USABLE OS sandbox (``which`` AND a runtime probe).

    Per-OS: Linux → ``bwrap``; macOS → ``sandbox-exec``. Any other platform (or a
    present-but-unusable tool) → False. Never raises.
    """
    tool = _tool_for_platform(_platform())
    if tool is None:
        return False
    if shutil.which(tool) is None:
        return False
    return _probe(tool)


def sandbox_enabled() -> bool:
    """True iff live harness sandboxing is opted-in via ``AGENTED_SANDBOX``.

    Distinct from :func:`sandbox_available` (which reports host capability): this
    is the operator feature-flag the launch sites (Plan 03) gate on. Default OFF.
    """
    return os.environ.get(_SANDBOX_ENABLED_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _proxy_port(proxy_url: str) -> str | None:
    """Extract the port from ``http://127.0.0.1:9000`` → ``"9000"``."""
    try:
        port = urlparse(proxy_url).port
    except (ValueError, TypeError):
        return None
    return str(port) if port is not None else None


def _build_bwrap_prefix(
    cmd: list[str], workspace: str, *, net: bool, proxy_url: str | None
) -> list[str]:
    """Compose a bubblewrap argv prefix (Linux). Lifted from 24-RESEARCH Rec 1.

    Binds ONLY the workspace read-write; everything else read-only. Uses
    ``--unshare-all --share-net`` so the child is isolated (pid/ipc/uts/…) but can
    still reach the LOCAL egress proxy over loopback (full ``--unshare-net`` would
    cut it off — Rec 1 egress note). ``--die-with-parent`` reaps the child if the
    harness dies. Read-only binds are guarded by existence so a distro missing
    ``/lib64`` doesn't make bwrap fail.
    """
    argv: list[str] = ["bwrap"]
    for src in ("/usr", "/bin", "/lib", "/lib64", "/etc/resolv.conf", "/etc/ssl"):
        if os.path.exists(src):
            argv += ["--ro-bind", src, src]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    argv += ["--bind", workspace, workspace, "--chdir", workspace]
    # Isolate every namespace but keep the network shared so loopback → proxy works.
    argv += ["--unshare-all", "--share-net", "--die-with-parent"]
    if proxy_url:
        argv += ["--setenv", "HTTPS_PROXY", proxy_url, "--setenv", "HTTP_PROXY", proxy_url]
    argv.append("--")
    argv += list(cmd)
    return argv


def _build_sbpl_profile(workspace: str, *, net: bool, proxy_url: str | None) -> str:
    """Compose a macOS seatbelt (SBPL) profile string. Lifted from 24-RESEARCH Rec 2.

    ``(deny default)`` then narrow allows: read broadly, write only inside the
    workspace (+ TMPDIR + /dev), and — for network — ``(deny network*)`` followed by
    a MORE-SPECIFIC allow. Apple SBPL resolves by last-match, so the later specific
    ``(allow network* (remote ...))`` permits exactly the proxy while everything else
    stays denied (Pitfall 4 deny-wins quirk). ``net`` without a proxy allows network
    broadly (no egress filtering); ``net`` false + no proxy leaves the sandbox
    fully offline.
    """
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        "(allow file-read*)",
        "(deny file-write*)",
        f'(allow file-write* (subpath "{workspace}"))',
        '(allow file-write* (subpath "/private/var/folders"))',
        '(allow file-write* (subpath "/private/tmp"))',
        '(allow file-write* (subpath "/dev"))',
    ]
    # Network rules — empirically verified against macOS seatbelt (24-RESEARCH
    # Pitfall 4): a SPECIFIC ``(allow network* (remote ip "localhost:PORT"))`` after
    # ``(deny network*)`` IS honored (the proxy is reachable), but a BROAD
    # ``(allow network*)`` after ``(deny network*)`` is NOT (deny wins). So the
    # net-without-proxy case must emit the broad allow WITHOUT a preceding deny.
    port = _proxy_port(proxy_url) if proxy_url else None
    if port is not None:
        # Only the local egress proxy is reachable; everything else denied.
        lines.append("(deny network*)")
        lines.append(f'(allow network* (remote ip "localhost:{port}"))')
    elif net:
        # net requested, no proxy → full network (no egress filtering in this mode).
        lines.append("(allow network*)")
    else:
        # Fully offline.
        lines.append("(deny network*)")
    return "\n".join(lines)


def build_sandbox_prefix(
    cmd: list[str],
    workspace: str,
    *,
    net: bool = False,
    proxy_url: str | None = None,
) -> tuple[list[str], bool]:
    """Return ``(argv_prefix_incl_cmd, sandboxed)`` for the current OS.

    Linux → a ``bwrap`` argv; macOS → ``["sandbox-exec", "-p", <SBPL>, *cmd]``. When
    no usable sandbox exists (or the platform is unsupported), degrades IN PLACE to
    ``(list(cmd), False)`` and logs ONE warning — it NEVER raises. ``net`` keeps the
    child able to reach the local egress proxy; ``proxy_url`` injects
    ``HTTPS_PROXY``/``HTTP_PROXY`` (bwrap) or the SBPL network allow so the sandbox's
    egress rule matches the proxy the child is pointed at.
    """
    global _DEGRADE_WARNED
    platform = _platform()
    if not sandbox_available():
        if not _DEGRADE_WARNED:
            logger.warning(
                "No usable OS sandbox on %s (bwrap/sandbox-exec absent or unusable) — "
                "running UNSANDBOXED (sandboxed=False); an enforce_sandbox policy will "
                "refuse this launch (fail closed).",
                platform,
            )
            _DEGRADE_WARNED = True
        return list(cmd), False

    if platform.startswith("linux"):
        return _build_bwrap_prefix(cmd, workspace, net=net, proxy_url=proxy_url), True
    if platform == "darwin":
        profile = _build_sbpl_profile(workspace, net=net, proxy_url=proxy_url)
        return ["sandbox-exec", "-p", profile, *cmd], True

    # Unsupported platform with a (spuriously) available tool — degrade.
    if not _DEGRADE_WARNED:
        logger.warning("Unsupported sandbox platform %s — running UNSANDBOXED.", platform)
        _DEGRADE_WARNED = True
    return list(cmd), False


def wrap_harness_command(
    cmd: list[str],
    workspace: str | None,
    *,
    net: bool = True,
    proxy_url: str | None = None,
) -> tuple[list[str], bool]:
    """Live-launch entry point used by the harness Popen sites (Plan 03 sweep).

    Gates on :func:`sandbox_enabled` so normal operation is untouched until an
    operator sets ``AGENTED_SANDBOX``; when enabled it delegates to
    :func:`build_sandbox_prefix`. A missing workspace degrades to pass-through.
    Returns ``(argv, sandboxed)``.
    """
    if not workspace or not sandbox_enabled():
        return list(cmd), False
    return build_sandbox_prefix(cmd, workspace, net=net, proxy_url=proxy_url)
