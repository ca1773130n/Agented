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
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".git",
    "__pycache__",
    ".cache",
    ".tox",
    ".next",
    "target",
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
        repos.append(
            {
                "name": os.path.basename(path.rstrip("/")),
                "local_path": path,
                "remote_url": _git_remote_url(path),
            }
        )

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


def _short_remote(url: Optional[str]) -> Optional[str]:
    """Normalize a git remote URL to ``host/owner/repo`` for display + dedup.

    ``git@github.com:org/repo.git`` and ``https://github.com/org/repo`` both
    collapse to ``github.com/org/repo``. Returns None for empty input.
    """
    if not url:
        return None
    s = url.strip()
    s = re.sub(r"^git@([^:]+):", r"\1/", s)  # scp-style ssh
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s, flags=re.IGNORECASE)  # scheme
    s = re.sub(r"^[^@/]+@", "", s)  # user@ (ssh://user@host)
    s = re.sub(r"\.git$", "", s, flags=re.IGNORECASE)
    s = s.rstrip("/").lower()
    return s or None


class ProjectDiscoveryService:
    """Scan / dedup / import entry points for the discovery feature."""

    @classmethod
    def scan(cls, root: str, *, nested: bool = False, max_depth: int = 3) -> dict:
        if not root or not isinstance(root, str):
            raise ValueError("root folder is required")
        abs_root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(abs_root):
            raise ValueError(f"not a directory: {root}")
        repos, unreadable = _scan_fs(abs_root, nested, max_depth)
        cls._mark_existing(repos)
        new_count = sum(1 for r in repos if not r["already_imported"])
        return {
            "repos": repos,
            "scanned": len(repos),
            "found": len(repos),
            "new_count": new_count,
            "unreadable": unreadable,
        }

    @classmethod
    def _mark_existing(cls, repos: list[dict]) -> None:
        existing = get_all_projects()
        path_to_id = {
            os.path.abspath(p["local_path"]): p["id"] for p in existing if p.get("local_path")
        }
        remote_to_id = {}
        for p in existing:
            sr = _short_remote(p.get("github_repo"))
            if sr:
                remote_to_id[sr] = p["id"]
        for r in repos:
            ap = os.path.abspath(r["local_path"])
            sr = _short_remote(r.get("remote_url"))
            existing_id = path_to_id.get(ap) or (remote_to_id.get(sr) if sr else None)
            r["already_imported"] = existing_id is not None
            r["existing_project_id"] = existing_id

    @classmethod
    def import_repos(
        cls,
        repos: list[dict],
        *,
        product_id: Optional[str] = None,
        owner_team_id: Optional[str] = None,
        run_harness_setup: bool = False,
        user_id: Optional[str] = None,
    ) -> dict:
        existing = get_all_projects()
        path_ids = {
            os.path.abspath(p["local_path"]): p["id"] for p in existing if p.get("local_path")
        }
        remote_ids = {}
        for p in existing:
            sr = _short_remote(p.get("github_repo"))
            if sr:
                remote_ids[sr] = p["id"]

        imported: list[dict] = []
        skipped: list[dict] = []
        for r in repos:
            name = (r.get("name") or "").strip()
            local_path = (r.get("local_path") or "").strip()
            if not name or not local_path:
                skipped.append(
                    {"name": name or "(unknown)", "reason": "missing name or local_path"}
                )
                continue
            ap = os.path.abspath(local_path)
            sr = _short_remote(r.get("github_repo") or r.get("remote_url"))
            if ap in path_ids or (sr and sr in remote_ids):
                skipped.append({"name": name, "reason": "already imported"})
                continue
            try:
                pid = db_create_project(
                    name=name,
                    github_repo=sr,
                    local_path=local_path,
                    owner_team_id=owner_team_id,
                    product_id=product_id,
                    user_id=user_id,
                )
            except Exception:
                logger.warning("import: create_project failed for %s", name, exc_info=True)
                pid = None
            if not pid:
                skipped.append({"name": name, "reason": "create failed"})
                continue
            imported.append({"project_id": pid, "name": name})
            path_ids[ap] = pid
            if sr:
                remote_ids[sr] = pid

        setup_started = False
        if run_harness_setup and owner_team_id and imported:
            for it in imported:
                cls._spawn_harness_setup(it["project_id"])
            setup_started = True
        return {"imported": imported, "skipped": skipped, "setup_started": setup_started}

    @classmethod
    def _spawn_harness_setup(cls, project_id: str) -> None:
        """Flip status to running + run the 6-step setup off-thread (mirrors
        grd_routes.trigger_harness_setup)."""
        try:
            from app.db.projects import set_harness_setup_status
            from app.services.team_harness_setup_service import TeamHarnessSetupService

            set_harness_setup_status(project_id, "running")
            threading.Thread(
                target=TeamHarnessSetupService.setup,
                args=(project_id,),
                daemon=True,
                name=f"harness-setup-{project_id}",
            ).start()
        except Exception:
            logger.warning("harness setup spawn failed for %s", project_id, exc_info=True)
