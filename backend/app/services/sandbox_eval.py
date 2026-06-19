"""Isolated, env-scrubbed runner for loop quality-gate check commands.

Reward-hacking mitigation (research F9): run the grader against a throwaway
SNAPSHOT of the workspace with a minimal env, so the live agent session can't
race/tamper with the running eval or leak secrets into it. Oversized
workspaces fall back to an in-place run (logged) to bound copy cost.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_IGNORE = shutil.ignore_patterns(
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".worktrees", "dist", ".mypy_cache"
)
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
        dirnames[:] = [d for d in dirnames if d not in {
            ".git", "node_modules", ".venv", "venv", "__pycache__", ".worktrees", "dist", ".mypy_cache"}]
        for f in filenames:
            try:
                total += (Path(dirpath) / f).stat().st_size
            except OSError:
                pass
            if total > _MAX_SNAPSHOT_BYTES:
                return total
    return total


def run_isolated_check(check_cmd: str, workspace_cwd: str, *, timeout: int) -> IsolatedResult:
    src = Path(workspace_cwd)
    sandboxed = True
    run_cwd = workspace_cwd
    tmp_root: Optional[str] = None
    try:
        if not src.is_dir() or _dir_size(src) > _MAX_SNAPSHOT_BYTES:
            sandboxed = False
            logger.warning("sandbox_eval: workspace missing or too large — running in-place")
        else:
            tmp_root = tempfile.mkdtemp(prefix="agented-eval-")
            dst = Path(tmp_root) / "ws"
            shutil.copytree(src, dst, ignore=_IGNORE, symlinks=True)
            run_cwd = str(dst)
        try:
            proc = subprocess.run(
                check_cmd, shell=True, cwd=run_cwd, capture_output=True, text=True,
                timeout=timeout, env=_scrubbed_env(),
            )
            return IsolatedResult(proc.returncode, proc.stdout or "", proc.stderr or "", sandboxed)
        except subprocess.TimeoutExpired:
            return IsolatedResult(124, "", f"timed out after {timeout}s", sandboxed)
    finally:
        if tmp_root:
            shutil.rmtree(tmp_root, ignore_errors=True)
