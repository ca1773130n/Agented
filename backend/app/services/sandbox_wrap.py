"""OS-level sandbox-command-prefix builder for harness launches (Phase 24).

`build_sandbox_prefix` returns an argv *prefix* plus a `sandboxed: bool`, meant
to be prepended at the SINGLE `subprocess.Popen` chokepoint that already prepends
`stdbuf` in ``execution_service.py`` — it is NOT a new launcher.

Platform primitives:
- Linux: ``bwrap`` (bubblewrap) — bind the workspace rw, ro-bind system dirs,
  ``--unshare-all --share-net --die-with-parent``; force egress through the local
  proxy via ``HTTPS_PROXY``/``HTTP_PROXY`` setenv when a proxy address is given.
- macOS: ``sandbox-exec -p <SBPL>`` — deny-default seatbelt profile that limits
  ``file-write*`` to the workspace + TMPDIR and ``(deny network*)`` except a
  carve-out for the local proxy host.

Where the primitive is missing OR present-but-unusable (e.g. unprivileged user
namespaces disabled — Pitfall 2), detection probe-runs the primitive and the
builder degrades to ``(cmd, False)`` with a logged warning. It never raises, so
the Phase-23 ``enforce_sandbox`` policy (wired in 24-03) decides launch-vs-refuse.

# ponytail: env-var egress (HTTPS_PROXY) is best-effort — a process can unset it.
# Airtight egress (netns + nftables redirect) is the deferred upgrade (RESEARCH
# Pitfall 3). The env-scrub allowlist convention is reused from ``sandbox_eval``
# rather than re-invented.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)

# System paths ro-bound into the bwrap sandbox (skipped if absent on the host).
_BWRAP_RO_PATHS = (
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/etc/ssl",
    "/etc/resolv.conf",
    "/etc/ca-certificates",
)

# Memoize the (expensive) probe-run per primitive so detection is computed once.
_PROBE_CACHE: dict[str, bool] = {}


# ---------------------------------------------------------------------------
# Pure builders (no I/O — trivially testable)
# ---------------------------------------------------------------------------


def _build_bwrap_prefix(cmd: list[str], *, workspace: str, proxy_addr: str | None) -> list[str]:
    """Build a bwrap argv prefix wrapping ``cmd`` (Linux). Pure: no filesystem
    probing of the host beyond ``os.path.exists`` for ro-bind targets."""
    prefix: list[str] = ["bwrap"]
    for path in _BWRAP_RO_PATHS:
        if os.path.exists(path):
            prefix += ["--ro-bind", path, path]
    prefix += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    prefix += ["--bind", workspace, workspace, "--chdir", workspace]
    prefix += ["--unshare-all", "--share-net", "--die-with-parent"]
    if proxy_addr:
        proxy_url = f"http://{proxy_addr}"
        prefix += ["--setenv", "HTTPS_PROXY", proxy_url]
        prefix += ["--setenv", "HTTP_PROXY", proxy_url]
    prefix += ["--"]
    prefix += list(cmd)
    return prefix


def _sbpl_quote(value: str) -> str:
    """Escape a path/host for embedding in an SBPL double-quoted string literal.

    SBPL strings are ``"``-delimited with backslash escaping. Without this, a
    value containing ``"`` could break out of the literal and inject policy
    directives — defeating the deny-default sandbox this module exists to build.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_sbpl_profile(*, workspace: str, proxy_addr: str | None) -> str:
    """Build a deny-default seatbelt (SBPL) profile string (macOS).

    deny-wins: ``(deny network*)`` is the floor; when a proxy is given we add a
    specific ``(allow network* ...)`` for the local proxy host only.

    Paths are ``realpath``-resolved so the filter matches the kernel's canonical
    view — on macOS ``TMPDIR`` lives under ``/var/folders`` (``/var`` →
    ``/private/var``), so an unresolved ``subpath`` rule would never match and
    every temp write would be denied.
    """
    ws = _sbpl_quote(os.path.realpath(workspace))
    tmp = _sbpl_quote(os.path.realpath(os.environ.get("TMPDIR") or tempfile.gettempdir()))
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        "(allow process-exec)",
        "(allow sysctl-read)",
        "(allow file-read*)",
        f'(allow file-write* (subpath "{ws}"))',
        f'(allow file-write* (subpath "{tmp}"))',
        "(deny network*)",
    ]
    if proxy_addr:
        host = _sbpl_quote(proxy_addr.rsplit(":", 1)[0])
        lines.append(f'(allow network* (remote ip "{host}:*"))')
    return "\n".join(lines) + "\n"


def _build_sbpl_prefix(cmd: list[str], *, workspace: str, proxy_addr: str | None) -> list[str]:
    """Build a ``sandbox-exec -p <profile> *cmd`` argv prefix (macOS)."""
    profile = _build_sbpl_profile(workspace=workspace, proxy_addr=proxy_addr)
    return ["sandbox-exec", "-p", profile, *cmd]


# ---------------------------------------------------------------------------
# Detection + probe (Pitfall 2: which() passes but the primitive is unusable)
# ---------------------------------------------------------------------------


def _probe(name: str, probe_argv: list[str]) -> bool:
    """Run a trivial sandbox invocation once and cache the result. Any failure
    (binary missing, userns disabled, non-zero exit, timeout) => False."""
    if name in _PROBE_CACHE:
        return _PROBE_CACHE[name]
    ok = False
    try:
        if shutil.which(name):
            res = subprocess.run(
                probe_argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            ok = res.returncode == 0
    except Exception:  # noqa: BLE001 — probe must never raise (degrade instead)
        ok = False
    _PROBE_CACHE[name] = ok
    return ok


def sandbox_available() -> bool:
    """True iff the platform sandbox primitive is present AND usable (probed)."""
    if sys.platform == "darwin":
        return _probe(
            "sandbox-exec",
            ["sandbox-exec", "-p", "(version 1)(allow default)", "true"],
        )
    if sys.platform.startswith("linux"):
        return _probe("bwrap", ["bwrap", "--ro-bind", "/", "/", "true"])
    return False


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def build_sandbox_prefix(
    cmd: list[str], *, workspace: str, proxy_addr: str | None = None
) -> tuple[list[str], bool]:
    """Return ``(prefixed_argv, sandboxed)``.

    Picks the platform builder when the sandbox is available; otherwise logs a
    warning naming the missing primitive and returns ``(cmd, False)`` so the
    caller (policy in 24-03) decides launch-vs-refuse. Never raises.
    """
    if not sandbox_available():
        primitive = "sandbox-exec" if sys.platform == "darwin" else "bwrap"
        logger.warning(
            "sandbox_wrap: %s unavailable/unusable on %s — launching UNSANDBOXED",
            primitive,
            sys.platform,
        )
        return list(cmd), False

    if sys.platform == "darwin":
        return _build_sbpl_prefix(cmd, workspace=workspace, proxy_addr=proxy_addr), True
    return _build_bwrap_prefix(cmd, workspace=workspace, proxy_addr=proxy_addr), True
