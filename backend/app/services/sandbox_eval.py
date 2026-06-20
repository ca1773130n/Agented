"""Isolated, env-scrubbed runner for loop quality-gate check commands.

Reward-hacking mitigation (research F9): run the grader against a throwaway
SNAPSHOT of the workspace with a minimal env, so the live agent session can't
race/tamper with the running eval or leak secrets into it. Oversized
workspaces fall back to an in-place run (logged) to bound copy cost.

Both the isolated and the in-place runners go through ``_popen_run``, which:
- scrubs the environment to a small allowlist (no inherited secrets),
- starts the check in its OWN process group and SIGKILLs the whole group on
  timeout (so a check that spawns children can't orphan grandchildren).
The snapshot additionally neutralizes symlinks that escape the snapshot root,
so a pre-planted symlink can't read outside the isolation boundary.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_IGNORE_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".worktrees",
    "dist",
    ".mypy_cache",
}
_IGNORE = shutil.ignore_patterns(*_IGNORE_NAMES)
_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "SHELL")
_MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024  # 512 MB guard


@dataclass
class IsolatedResult:
    returncode: int
    stdout: str
    stderr: str
    sandboxed: bool


def _scrubbed_env() -> dict:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/local/bin")
    return env


def _dir_size(root: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_NAMES]
        for f in filenames:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
            if total > _MAX_SNAPSHOT_BYTES:
                return total
    return total


def _neutralize_escaping_symlinks(root: Path) -> None:
    """Remove any symlink under ``root`` whose resolved target escapes ``root``.

    ``copytree(symlinks=True)`` preserves symlinks AS links (no content
    duplication, no crash on dangling links), but an absolute/``..`` link would
    still point at a file OUTSIDE the snapshot — letting the grader read beyond
    the isolation boundary. Drop those; intra-snapshot links are left intact.
    """
    root_real = os.path.realpath(root)
    prefix = root_real + os.sep
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in list(dirnames) + filenames:
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                continue
            target = os.path.realpath(p)
            if target != root_real and not target.startswith(prefix):
                try:
                    os.unlink(p)
                except OSError:
                    logger.debug("sandbox_eval: could not remove escaping symlink %s", p)


def _popen_run(check_cmd: str, run_cwd: str, timeout: int) -> tuple[int, str, str]:
    """Run ``check_cmd`` (shell) in its own process group with a scrubbed env.

    On timeout, SIGKILL the whole group so children/grandchildren don't orphan.
    Returns ``(returncode, stdout, stderr)`` — returncode 124 on timeout,
    127 if the command couldn't be launched.
    """
    try:
        proc = subprocess.Popen(
            check_cmd,
            shell=True,
            cwd=run_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_scrubbed_env(),
            start_new_session=True,  # own process group → killable as a unit
        )
    except (OSError, ValueError) as exc:
        return 127, "", f"check failed to run: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = "", ""
        return 124, out or "", (err or "") + f"\ntimed out after {timeout}s"


def run_check_inplace(check_cmd: str, cwd: str, *, timeout: int) -> IsolatedResult:
    """Run the check in the given cwd (no snapshot) but still env-scrubbed +
    process-group-killed. Used for the ``sandbox=inherit`` escape hatch so even
    the non-isolated path doesn't leak the full parent env into the grader."""
    rc, out, err = _popen_run(check_cmd, cwd, timeout)
    return IsolatedResult(rc, out, err, sandboxed=False)


def run_isolated_check(check_cmd: str, workspace_cwd: str, *, timeout: int) -> IsolatedResult:
    src = Path(workspace_cwd)
    sandboxed = True
    run_cwd = workspace_cwd
    tmp_root: Optional[str] = None
    try:
        if not src.is_dir() or _dir_size(src) > _MAX_SNAPSHOT_BYTES:
            sandboxed = False
            logger.warning("sandbox_eval: workspace missing or too large — running in-place")
            # A missing dir is not a valid cwd; fall back to a safe one.
            if not src.is_dir():
                run_cwd = str(src.parent) if src.parent.is_dir() else os.getcwd()
        else:
            tmp_root = tempfile.mkdtemp(prefix="agented-eval-")
            dst = Path(tmp_root) / "ws"
            shutil.copytree(src, dst, ignore=_IGNORE, symlinks=True)
            _neutralize_escaping_symlinks(dst)
            run_cwd = str(dst)
        rc, out, err = _popen_run(check_cmd, run_cwd, timeout)
        return IsolatedResult(rc, out, err, sandboxed)
    finally:
        if tmp_root:
            shutil.rmtree(tmp_root, ignore_errors=True)
