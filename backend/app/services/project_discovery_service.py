"""ProjectDiscoveryService — scan a folder for git repos, dedup against
existing projects, and bulk-import them (optionally running harness-setup).

The backend runs on the operator's own machine, so scanning a server-side
folder path is the operator inspecting their own filesystem. Scans are bounded
(depth + result caps) and best-effort (unreadable dirs are skipped + counted).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from typing import Optional

from app.database import create_project as db_create_project
from app.database import get_all_projects

logger = logging.getLogger(__name__)

_IGNORE_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", ".git",
    "__pycache__", ".cache", ".tox", ".next", "target",
}
_MAX_DEPTH_CAP = 8
_MAX_REPOS = 500


def _is_repo(path: str) -> bool:
    """A directory is a repo when it has a ``.git`` entry (dir or file)."""
    return os.path.exists(os.path.join(path, ".git"))


def _git_remote_url(path: str) -> Optional[str]:
    """Best-effort ``git remote get-url origin``; None for local-only repos."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        logger.debug("git remote read failed for %s", path, exc_info=True)
    return None


def _scan_fs(root: str, nested: bool, max_depth: int) -> tuple[list[dict], int]:
    """Return ``(repos, unreadable_count)``.

    Each repo dict: ``{name, local_path, remote_url}``. ``nested=False`` lists
    direct child repos; ``nested=True`` walks (depth-capped, ignore-pruned) and
    stops descending once a repo is found (no submodule double-import).
    """
    repos: list[dict] = []
    unreadable = 0

    def _add(path: str) -> None:
        repos.append({
            "name": os.path.basename(path.rstrip("/")),
            "local_path": path,
            "remote_url": _git_remote_url(path),
        })

    if not nested:
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError as e:
            raise ValueError(f"cannot read folder: {e}")
        for entry in entries:
            if len(repos) >= _MAX_REPOS:
                break
            try:
                if entry.is_dir(follow_symlinks=False) and _is_repo(entry.path):
                    _add(entry.path)
            except OSError:
                unreadable += 1
        return repos, unreadable

    depth_cap = min(max_depth, _MAX_DEPTH_CAP)
    base_depth = root.rstrip("/").count(os.sep)
    for dirpath, dirnames, _files in os.walk(root):
        if len(repos) >= _MAX_REPOS:
            break
        depth = dirpath.rstrip("/").count(os.sep) - base_depth
        if depth >= depth_cap:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        if dirpath != root and _is_repo(dirpath):
            _add(dirpath)
            dirnames[:] = []  # don't descend into a found repo
    return repos, unreadable
