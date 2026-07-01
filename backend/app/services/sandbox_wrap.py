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

SECURITY (24-fix, fail CLOSED):
  * Linux bwrap uses ``--unshare-net`` — a PRIVATE, empty network namespace with NO
    host network. A hostile child therefore cannot bypass the L7 egress proxy with a
    raw socket / its own DNS / a hard-coded IP: it simply has no route off-box. The
    netns↔proxy BRIDGE that would let the child reach the local egress proxy from
    inside the namespace (``pasta`` / ``slirp4netns`` / an ``nftables`` NAT to the
    proxy port) is NOT wired in this round, so when a policy REQUIRES egress the run
    is fail-closed (no network) rather than run wide-open with ``--share-net`` — see
    the follow-up in ``_build_bwrap_prefix``.
  * macOS seatbelt reads are SCOPED: the profile keeps broad read for system libs
    (so dyld/exec work) but DENIES reading file *contents* under the home dir and
    fully denies the credential dirs (``~/.ssh``/``~/.aws``/``~/.config``/…), then
    re-allows only the workspace + the interpreter/tool install roots. A wrapped
    child can no longer exfiltrate ``~/.ssh/id_rsa`` or ``~/.aws/credentials``.

We reuse ``sandbox_eval._ENV_ALLOWLIST`` rather than deriving a second env allowlist.
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

# macOS read-scoping (24-fix, BLOCKER 1). Credential DIRECTORIES fully denied
# (metadata + data), so not even their listing leaks. Credential FILES denied by
# literal. These live under the home dir; the profile also denies reading the
# *contents* of anything else under home, then re-allows workspace + interpreter.
_CRED_DIRS = (
    ".ssh",
    ".aws",
    ".config",
    ".gnupg",
    ".gcloud",
    ".azure",
    ".kube",
    ".docker",
    ".terraform.d",
    ".cloudflared",
)
_CRED_FILES = (
    ".netrc",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    ".databrickscfg",
)


def _is_home_or_cred(path: str) -> bool:
    """True iff ``path`` is ``$HOME`` itself, an ANCESTOR of ``$HOME`` (e.g.
    ``/Users``), or a credential dir / anything nested under one.

    BLOCKER 1 defense-in-depth: these paths must NEVER be re-allowed for read. A
    home-rooted tool like ``$HOME/bin/claude`` makes ``_interpreter_read_paths``
    derive the parent ``$HOME`` (and a bare ``$HOME/claude`` even derives ``/Users``);
    re-allowing either would re-open the whole home — and thus the credential dirs —
    for read. Filtering them here is the suspenders to the SBPL credential-deny
    reorder's belt. Never raises.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    if not home or home == "/":
        return False
    try:
        rp = os.path.realpath(path)
    except OSError:  # pragma: no cover - defensive
        return True
    # ``path`` is $HOME or an ancestor of $HOME (== home, or a strict prefix of it).
    if rp == home or home.startswith(rp.rstrip(os.sep) + os.sep):
        return True
    # ``path`` is a credential dir or nested under one.
    for name in _CRED_DIRS:
        cred = os.path.join(home, name)
        if rp == cred or rp.startswith(cred + os.sep):
            return True
    return False


def _interpreter_read_paths(cmd: list[str]) -> list[str]:
    """Install roots whose file *contents* the wrapped child must still read.

    Covers (a) THIS process's Python runtime (``sys.prefix``/``sys.base_prefix`` —
    the venv + its base, e.g. a uv-managed CPython nested under ``$HOME``) so a
    Python-based wrapped command keeps working, and (b) the resolved tool being
    launched (``cmd[0]`` and its parent, catching a harness binary under
    ``~/.local/bin`` / ``~/.nvm`` / …). These are RE-ALLOWED for read even though
    the profile otherwise denies reading file contents under the home dir — the
    interpreter is not a secret, and denying it would break exec of anything
    installed under home. Never raises.

    SECURITY (24-fix, BLOCKER 1): the derived paths are FILTERED so we never emit
    ``$HOME`` itself, an ancestor of ``$HOME``, or a credential dir. A tool at
    ``$HOME/bin/claude`` derives the parent ``$HOME`` — re-allowing that would
    re-open the entire home (incl. ``~/.ssh``) for read, defeating the credential
    denies. ``_is_home_or_cred`` drops those; the SBPL reorder is the second layer.
    """
    paths: set[str] = set()
    for p in (sys.prefix, sys.base_prefix, os.path.dirname(sys.executable)):
        if p:
            paths.add(p)
    exe = cmd[0] if cmd else None
    if exe:
        resolved = exe if os.path.isabs(exe) else (shutil.which(exe) or exe)
        try:
            real = os.path.realpath(resolved)
            d = os.path.dirname(real)
            if d:
                paths.add(d)
                parent = os.path.dirname(d)
                if parent:
                    paths.add(parent)  # bin/ → install root (sibling lib/)
        except OSError:  # pragma: no cover - defensive
            pass
    # Drop empty / root ("/" would re-allow everything) and any $HOME/cred path.
    return sorted(p for p in paths if p and p != "/" and not _is_home_or_cred(p))


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
    cmd: list[str],
    workspace: str,
    *,
    net: bool,
    proxy_url: str | None,
    config_dirs: list[str] | None = None,
) -> list[str]:
    """Compose a bubblewrap argv prefix (Linux). Lifted from 24-RESEARCH Rec 1.

    Binds ONLY the workspace read-write; everything else read-only.

    SECURITY (24-fix, fail CLOSED): uses ``--unshare-net`` — a PRIVATE, empty
    network namespace with NO host network. This closes the ``--share-net`` bypass:
    a hostile child sharing the host netns could open a raw socket, run its own
    DNS, or dial a hard-coded IP straight past the L7 egress proxy. With
    ``--unshare-net`` the child has no route off-box at all, so the ONLY possible
    network path is one deliberately bridged INTO the namespace.

    FOLLOW-UP (not wired this round): the netns↔proxy bridge that would let the
    child reach the local egress proxy from inside its private namespace —
    ``pasta`` / ``slirp4netns``, or an ``nftables`` NAT redirecting outbound to the
    proxy port. Until that lands, an egress-requiring run is fail-CLOSED (the child
    is simply offline) rather than running wide-open on the host network. The
    ``--setenv HTTPS_PROXY`` injection is kept so the bridge, once added, needs no
    further launch-site change.

    ``--die-with-parent`` reaps the child if the harness dies. Read-only binds are
    guarded by existence so a distro missing ``/lib64`` doesn't make bwrap fail.
    """
    argv: list[str] = ["bwrap"]
    for src in ("/usr", "/bin", "/lib", "/lib64", "/etc/resolv.conf", "/etc/ssl"):
        if os.path.exists(src):
            argv += ["--ro-bind", src, src]
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    argv += ["--bind", workspace, workspace, "--chdir", workspace]
    # Harness config dirs (CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_HOME) — bound
    # READ-WRITE so a sandboxed harness can read its auth/plugins AND persist state
    # into its config dir (MAJOR 1: previously bwrap bound only workspace/system, so
    # a sandboxed claude could not read CLAUDE_CONFIG_DIR). Guarded by existence so a
    # missing dir doesn't make bwrap fail.
    for cd in config_dirs or []:
        if cd and os.path.exists(cd):
            argv += ["--bind", cd, cd]
    # Isolate EVERY namespace INCLUDING the network: a private, empty netns with no
    # host network means a hostile child cannot bypass the egress proxy (no raw
    # sockets / DNS / hard-coded IP off-box). ``--unshare-all`` already unshares the
    # net namespace; ``--unshare-net`` is stated explicitly so the intent — and the
    # absence of ``--share-net`` — is unmistakable at the launch boundary.
    argv += ["--unshare-all", "--unshare-net", "--die-with-parent"]
    if proxy_url:
        argv += ["--setenv", "HTTPS_PROXY", proxy_url, "--setenv", "HTTP_PROXY", proxy_url]
    argv.append("--")
    argv += list(cmd)
    return argv


def _build_sbpl_profile(
    workspace: str,
    *,
    net: bool,
    proxy_url: str | None,
    read_paths: list[str] | None = None,
    config_dirs: list[str] | None = None,
) -> str:
    """Compose a macOS seatbelt (SBPL) profile string. Lifted from 24-RESEARCH Rec 2.

    ``(deny default)`` then narrow allows. Apple SBPL resolves by LAST-match, which
    this profile leans on for both read scoping and network:

    READ SCOPING (24-fix, BLOCKER 1 — no more global ``file-read*``, and the
    credential denies are the FINAL word):
      1. ``(allow file-read*)`` — broad read so dyld / system libs / path traversal
         work (a fully deny-default read profile SIGABRTs modern macOS binaries).
      2. ``(deny file-read-data (subpath <home>))`` — but the *contents* of files
         under the home dir are NOT readable (metadata/traversal still is, so exec
         of interpreters nested under home keeps working).
      3. ``(allow file-read-data (subpath <workspace>))`` + the interpreter/tool
         install roots + harness config dirs — re-allow reading exactly what the
         child legitimately needs.
      4. ``(deny file-read* (subpath <home>/.ssh))`` + ``(deny file-read-data
         (subpath <home>/.ssh))`` … — the credential dirs are denied both metadata
         (``file-read*``) AND data (``file-read-data``), emitted LAST among the read
         rules so they WIN over any broad or home-rooted re-allow above.

         EMPIRICAL SBPL QUIRK (verified live, BLOCKER 1): seatbelt does NOT let a
         ``(deny file-read*)`` override a *preceding* ``(allow file-read-data)`` for
         the data operation — only an explicit ``(deny file-read-data)`` does. So a
         ``file-read*``-only credential deny left ``~/.ssh/id_rsa`` READABLE whenever
         a home-rooted re-allow was present; the paired ``file-read-data`` deny is
         what actually closes it. (The previous ordering also appended these denies
         BEFORE the re-allows, compounding the leak.)
      Net effect: a wrapped child can read the workspace/config-dirs and run, but
      cannot exfiltrate ``~/.ssh/id_rsa`` / ``~/.aws/credentials`` / other secrets.

    WRITE: write only inside the workspace (+ TMPDIR + /dev + harness config dirs).
    NETWORK: ``(deny network*)`` then a MORE-SPECIFIC allow — the later ``(allow
    network* (remote ...))`` permits exactly the proxy while everything else stays
    denied (Pitfall 4 deny-wins quirk). ``net`` without a proxy allows network
    broadly (no egress filtering); ``net`` false + no proxy leaves it fully offline.
    """
    home = os.path.expanduser("~")
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-exec)",
        "(allow process-fork)",
        "(allow sysctl-read)",
        # Broad read so dyld / system libraries / path traversal work...
        "(allow file-read*)",
    ]
    if home and home != "/":
        # ...but NOT the CONTENTS of files under the home dir (secrets live here).
        lines.append(f'(deny file-read-data (subpath "{home}"))')
    # Re-allow reading contents of the workspace + interpreter/tool install roots +
    # harness config dirs (these may sit under home; last-match-wins lets the child
    # read exactly them). The credential denies below come AFTER, so they still win.
    for rp in [workspace, *(read_paths or []), *(config_dirs or [])]:
        if rp:
            lines.append(f'(allow file-read-data (subpath "{rp}"))')
    # CREDENTIAL DENIES — emitted LAST among the read rules so they are the FINAL
    # word (BLOCKER 1). Each credential path gets BOTH a ``file-read*`` deny (metadata)
    # and an explicit ``file-read-data`` deny (contents): a ``file-read*`` deny alone
    # does NOT override a preceding ``file-read-data`` re-allow in seatbelt, so the
    # paired data-deny is what actually keeps ``~/.ssh/id_rsa`` unreadable under a
    # broad or home-rooted re-allow.
    if home and home != "/":
        for name in _CRED_DIRS:
            lines.append(f'(deny file-read* (subpath "{home}/{name}"))')
            lines.append(f'(deny file-read-data (subpath "{home}/{name}"))')
        for name in _CRED_FILES:
            lines.append(f'(deny file-read* (literal "{home}/{name}"))')
            lines.append(f'(deny file-read-data (literal "{home}/{name}"))')
    lines += [
        "(deny file-write*)",
        f'(allow file-write* (subpath "{workspace}"))',
        '(allow file-write* (subpath "/private/var/folders"))',
        '(allow file-write* (subpath "/private/tmp"))',
        '(allow file-write* (subpath "/dev"))',
    ]
    # Harness config dirs are read+write — a harness persists state (sessions, todos,
    # projects/) into its config dir (MAJOR 1). None of ``_CRED_DIRS`` overlap the
    # default config dirs (~/.claude, ~/.codex, ~/.gemini), so this does not re-open
    # a credential dir.
    for cd in config_dirs or []:
        if cd:
            lines.append(f'(allow file-write* (subpath "{cd}"))')
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
    config_dirs: list[str] | None = None,
) -> tuple[list[str], bool]:
    """Return ``(argv_prefix_incl_cmd, sandboxed)`` for the current OS.

    Linux → a ``bwrap`` argv; macOS → ``["sandbox-exec", "-p", <SBPL>, *cmd]``. When
    no usable sandbox exists (or the platform is unsupported), degrades IN PLACE to
    ``(list(cmd), False)`` and logs ONE warning — it NEVER raises. ``net`` keeps the
    child able to reach the local egress proxy; ``proxy_url`` injects
    ``HTTPS_PROXY``/``HTTP_PROXY`` (bwrap) or the SBPL network allow so the sandbox's
    egress rule matches the proxy the child is pointed at. ``config_dirs`` (harness
    config dirs — CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_HOME) are bound/allowed
    read-write so a sandboxed harness can reach its auth/plugins (MAJOR 1).
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
        return (
            _build_bwrap_prefix(
                cmd, workspace, net=net, proxy_url=proxy_url, config_dirs=config_dirs
            ),
            True,
        )
    if platform == "darwin":
        profile = _build_sbpl_profile(
            workspace,
            net=net,
            proxy_url=proxy_url,
            read_paths=_interpreter_read_paths(cmd),
            config_dirs=config_dirs,
        )
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
    config_dirs: list[str] | None = None,
) -> tuple[list[str], bool]:
    """Live-launch entry point used by the harness Popen sites (Plan 03 sweep).

    Gates on :func:`sandbox_enabled` so normal operation is untouched until an
    operator sets ``AGENTED_SANDBOX``; when enabled it delegates to
    :func:`build_sandbox_prefix`. A missing workspace degrades to pass-through.
    ``config_dirs`` are the harness config dirs the sandbox must keep readable
    (CLAUDE_CONFIG_DIR / CODEX_HOME / GEMINI_HOME — MAJOR 1). Returns
    ``(argv, sandboxed)``.
    """
    if not workspace or not sandbox_enabled():
        return list(cmd), False
    return build_sandbox_prefix(
        cmd, workspace, net=net, proxy_url=proxy_url, config_dirs=config_dirs
    )


def apply_sandbox_and_enforce(
    cmd: list[str],
    workspace: str | None,
    *,
    session_id: str,
    backend: str,
    team_id: str | None = None,
    net: bool = True,
    proxy_url: str | None = None,
    interactive: bool = False,
    config_dirs: list[str] | None = None,
) -> tuple[list[str], bool]:
    """Shared Phase-24 launch seam: OS-sandbox-wrap ``cmd`` then run the Phase-23
    launch gate with the REAL ``sandboxed`` flag — BEFORE the caller's Popen/fork.

    SECURITY (24-fix, crit 4-7): every autonomous harness spawn that previously
    only *wrapped* (ignoring the ``sandboxed`` return, so an ``enforce_sandbox``
    policy could be silently bypassed) routes through this ONE helper. Because the
    wrap runs FIRST, the ``sandboxed`` flag handed to the gate is the true one, so a
    policy that mandates a sandbox DENIES an unsandboxable launch. A DENY raises
    ``PolicyDenied`` and the caller never reaches its spawn (fail CLOSED). Wrapping
    is a no-op pass-through unless ``AGENTED_SANDBOX`` is opted in, so normal
    operation is unchanged by default.

    ``interactive`` selects the gate: ``enforce_launch`` (blocks on a human-gate
    ASK) for operator-facing spawns; ``enforce_launch_noninteractive`` (ASK == deny,
    no operator prompt) for unattended check/generation/streaming spawns.

    Returns ``(wrapped_cmd, sandboxed)``. ``ExecutionService.run_trigger`` keeps its
    own equivalent inline seam (``_apply_sandbox_and_enforce``) because it also
    threads live cost/tool-call context into the gate.
    """
    from .policy_service import PolicyService

    wrapped, sandboxed = wrap_harness_command(
        cmd, workspace, net=net, proxy_url=proxy_url, config_dirs=config_dirs
    )
    gate = (
        PolicyService.enforce_launch if interactive else PolicyService.enforce_launch_noninteractive
    )
    gate(
        session_id=session_id,
        team_id=team_id,
        cmd=wrapped,
        backend=backend,
        sandboxed=sandboxed,
    )
    return wrapped, sandboxed
