"""Git worktree lifecycle management for GRD plan execution isolation."""

import logging
import os
import subprocess
import threading
from typing import Dict, List

logger = logging.getLogger(__name__)


class WorktreeService:
    """Manages git worktrees for isolated plan execution.

    Uses classmethod singleton pattern (no instantiation needed).
    Per-project locks prevent race conditions on concurrent limit enforcement
    and .gitignore writes.
    """

    _locks: Dict[str, threading.Lock] = {}
    _global_lock = threading.Lock()
    DEFAULT_LIMIT = 5  # Max concurrent worktrees per project

    @classmethod
    def _get_project_lock(cls, project_path: str) -> threading.Lock:
        """Return or create a per-project lock (thread-safe via global lock)."""
        with cls._global_lock:
            if project_path not in cls._locks:
                cls._locks[project_path] = threading.Lock()
            return cls._locks[project_path]

    @classmethod
    def create_worktree(
        cls,
        project_path: str,
        worktree_name: str,
        branch_name: str,
        limit: int = 5,
    ) -> str:
        """Create a git worktree for isolated execution.

        Args:
            project_path: Absolute path to the main git repository.
            worktree_name: Name for the worktree directory under .worktrees/.
            branch_name: Git branch name to create or reuse.
            limit: Maximum concurrent worktrees allowed per project.

        Returns:
            Absolute path to the created worktree directory.

        Raises:
            RuntimeError: If concurrent limit reached or git commands fail.
        """
        lock = cls._get_project_lock(project_path)
        with lock:
            # Check concurrent worktree limit
            existing = cls.list_worktrees(project_path)
            if len(existing) >= limit:
                raise RuntimeError(
                    f"Concurrent worktree limit reached ({limit}). "
                    "Complete or remove existing worktrees."
                )

            # Ensure .worktrees/ is in .gitignore
            cls._ensure_gitignore(project_path)

            # Fetch latest from remote
            logger.info("Fetching latest from remote for %s", project_path)
            result = subprocess.run(
                ["git", "fetch", "--quiet"],
                cwd=project_path,
                text=True,
                capture_output=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning("git fetch failed (non-fatal): %s", result.stderr.strip())

            # Compute worktree path
            worktree_path = os.path.join(project_path, ".worktrees", worktree_name)

            # Reuse existing worktree if path already exists
            if os.path.isdir(worktree_path):
                logger.info("Reusing existing worktree at %s", worktree_path)
                return worktree_path

            # Create the worktree with a new branch from origin/main
            logger.info("Creating worktree: %s on branch %s", worktree_path, branch_name)
            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, worktree_path, "origin/main"],
                cwd=project_path,
                text=True,
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Branch may already exist -- try without -b
                if "already exists" in result.stderr:
                    logger.info("Branch %s already exists, reusing without -b", branch_name)
                    result = subprocess.run(
                        ["git", "worktree", "add", worktree_path, branch_name],
                        cwd=project_path,
                        text=True,
                        capture_output=True,
                        timeout=30,
                    )
                    if result.returncode != 0:
                        raise RuntimeError(
                            f"Failed to create worktree (reuse branch): {result.stderr.strip()}"
                        )
                else:
                    raise RuntimeError(f"Failed to create worktree: {result.stderr.strip()}")

            logger.info("Created worktree at %s", worktree_path)
            return worktree_path

    @classmethod
    def remove_worktree(cls, project_path: str, worktree_path: str) -> bool:
        """Remove a git worktree and prune stale entries.

        Args:
            project_path: Absolute path to the main git repository.
            worktree_path: Absolute path to the worktree to remove.

        Returns:
            True on success, False on failure.
        """
        logger.info("Removing worktree: %s", worktree_path)
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=project_path,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Failed to remove worktree %s: %s", worktree_path, result.stderr.strip())
            return False

        # Prune stale worktree entries
        cls.prune_worktrees(project_path)
        logger.info("Removed worktree: %s", worktree_path)
        return True

    @classmethod
    def list_worktrees(cls, project_path: str) -> List[dict]:
        """List all non-main worktrees for a project.

        Args:
            project_path: Absolute path to the main git repository.

        Returns:
            List of dicts with keys: path, head, branch.
            The main worktree (first entry) is filtered out.
        """
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=project_path,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("git worktree list failed: %s", result.stderr.strip())
            return []

        worktrees = []
        current: dict = {}
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line[len("worktree ") :], "head": "", "branch": ""}
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD ") :]
            elif line.startswith("branch "):
                raw_branch = line[len("branch ") :]
                # Strip refs/heads/ prefix for readability
                if raw_branch.startswith("refs/heads/"):
                    raw_branch = raw_branch[len("refs/heads/") :]
                current["branch"] = raw_branch
            elif line == "" and current:
                worktrees.append(current)
                current = {}
        if current:
            worktrees.append(current)

        # Filter out the main worktree (first entry is always the repo itself)
        if worktrees:
            worktrees = worktrees[1:]

        return worktrees

    @classmethod
    def prune_worktrees(cls, project_path: str) -> bool:
        """Prune stale worktree entries.

        Args:
            project_path: Absolute path to the main git repository.

        Returns:
            True on success.
        """
        result = subprocess.run(
            ["git", "worktree", "prune"],
            cwd=project_path,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("git worktree prune failed: %s", result.stderr.strip())
            return False
        return True

    @classmethod
    def _ensure_gitignore(cls, project_path: str):
        """Ensure .worktrees/ is listed in .gitignore.

        Creates .gitignore if it does not exist. Caller must hold the
        per-project lock.
        """
        gitignore_path = os.path.join(project_path, ".gitignore")
        existing_content = ""
        if os.path.isfile(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                existing_content = f.read()

        # Check if already listed
        for line in existing_content.splitlines():
            stripped = line.strip()
            if stripped in (".worktrees/", ".worktrees"):
                return  # Already present

        # Append entry
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write("\n# GRD worktrees\n.worktrees/\n")
        logger.info("Added .worktrees/ to %s", gitignore_path)

    @classmethod
    def get_worktree_for_plan(
        cls,
        project_path: str,
        phase_number: int,
        plan_number: int,
        phase_slug: str,
    ) -> str:
        """Convenience method to create/get a worktree for a specific plan.

        Args:
            project_path: Absolute path to the main git repository.
            phase_number: Phase number (e.g. 48).
            plan_number: Plan number (e.g. 1).
            phase_slug: Slug for the phase (e.g. "git-worktrees-session-manager").

        Returns:
            Absolute path to the worktree directory.
        """
        worktree_name = f"phase-{phase_number:02d}-plan-{plan_number:02d}"
        branch_name = f"grd/phase-{phase_number:02d}-{phase_slug}"
        return cls.create_worktree(
            project_path=project_path,
            worktree_name=worktree_name,
            branch_name=branch_name,
        )
