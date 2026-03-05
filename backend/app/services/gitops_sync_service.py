"""GitOps sync engine for watching git repositories and applying config changes.

Clones/pulls a configured git repository, compares YAML config files against
DB state, and applies changes via ConfigExportService.import_trigger(upsert=True).
Conflicts are detected via content hashing; Git wins by default (standard GitOps).
"""

import glob
import hashlib
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from app.db.gitops import (
    add_sync_log,
    get_gitops_repo,
    list_gitops_repos,
    update_sync_state,
)
from app.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)

# Local cache directory for cloned repos (relative to backend/)
_CACHE_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".gitops-cache")


class GitOpsSyncService:
    """Git-based config sync engine with conflict detection."""

    _scheduler_jobs: dict = {}

    @classmethod
    def sync_repo(cls, repo_id: str, dry_run: bool = False) -> dict:
        """Sync a single GitOps repository.

        Clones or pulls the repo, detects YAML config changes, and applies
        them via import_trigger(upsert=True).

        Args:
            repo_id: The gitops repo ID to sync.
            dry_run: If True, return what would change without applying.

        Returns:
            Summary dict with commit_sha, files_changed, files_applied,
            files_conflicted, changes list, and status.

        Raises:
            ValueError: If repo not found or git operations fail.
        """
        repo = get_gitops_repo(repo_id)
        if not repo:
            raise ValueError(f"GitOps repo not found: {repo_id}")

        if not repo.get("enabled"):
            return {
                "commit_sha": None,
                "files_changed": 0,
                "files_applied": 0,
                "files_conflicted": 0,
                "changes": [],
                "status": "disabled",
            }

        local_path = cls._get_local_path(repo_id)
        try:
            # Clone or pull
            current_sha = cls._ensure_repo(
                local_path, repo["repo_url"], repo["branch"]
            )
        except subprocess.CalledProcessError as e:
            error_msg = f"Git operation failed: {e.stderr or e.stdout or str(e)}"
            logger.error("GitOps sync failed for %s: %s", repo_id, error_msg)
            add_sync_log(
                repo_id=repo_id,
                commit_sha=None,
                status="failed",
                details=json.dumps({"error": error_msg}),
            )
            AuditLogService.log(
                action="gitops.sync",
                entity_type="gitops_repo",
                entity_id=repo_id,
                outcome="failed",
                details={"error": error_msg},
            )
            return {
                "commit_sha": None,
                "files_changed": 0,
                "files_applied": 0,
                "files_conflicted": 0,
                "changes": [],
                "status": "failed",
                "error": error_msg,
            }

        # Check if anything changed
        last_sha = repo.get("last_commit_sha")
        if current_sha == last_sha and not dry_run:
            add_sync_log(
                repo_id=repo_id,
                commit_sha=current_sha,
                status="skipped",
                details=json.dumps({"reason": "no_changes"}),
            )
            return {
                "commit_sha": current_sha,
                "files_changed": 0,
                "files_applied": 0,
                "files_conflicted": 0,
                "changes": [],
                "status": "skipped",
            }

        # Find YAML config files
        config_dir = os.path.join(local_path, repo["config_path"])
        yaml_files = sorted(
            glob.glob(os.path.join(config_dir, "*.yaml"))
            + glob.glob(os.path.join(config_dir, "*.yml"))
        )

        changes = []
        files_changed = 0
        files_applied = 0
        files_conflicted = 0

        for yaml_path in yaml_files:
            try:
                change = cls._process_config_file(
                    yaml_path, repo_id, last_sha, dry_run
                )
                if change:
                    changes.append(change)
                    files_changed += 1
                    if change.get("applied"):
                        files_applied += 1
                    if change.get("conflict"):
                        files_conflicted += 1
            except Exception as e:
                logger.error(
                    "Error processing %s: %s", os.path.basename(yaml_path), e
                )
                changes.append({
                    "file": os.path.basename(yaml_path),
                    "error": str(e),
                    "applied": False,
                })

        # Update sync state
        status = "dry_run" if dry_run else "success"
        now = datetime.now(timezone.utc).isoformat()

        if not dry_run:
            update_sync_state(repo_id, current_sha, now)

        add_sync_log(
            repo_id=repo_id,
            commit_sha=current_sha,
            files_changed=files_changed,
            files_applied=files_applied,
            files_conflicted=files_conflicted,
            status=status,
            details=json.dumps({"changes": changes}),
        )

        AuditLogService.log(
            action="gitops.sync",
            entity_type="gitops_repo",
            entity_id=repo_id,
            outcome=status,
            details={
                "commit_sha": current_sha,
                "files_changed": files_changed,
                "files_applied": files_applied,
                "files_conflicted": files_conflicted,
                "dry_run": dry_run,
            },
        )

        return {
            "commit_sha": current_sha,
            "files_changed": files_changed,
            "files_applied": files_applied,
            "files_conflicted": files_conflicted,
            "changes": changes,
            "status": status,
        }

    @classmethod
    def _process_config_file(
        cls,
        yaml_path: str,
        repo_id: str,
        last_sha: Optional[str],
        dry_run: bool,
    ) -> Optional[dict]:
        """Process a single YAML config file.

        Returns change info dict if config differs from DB, None if unchanged.
        """
        # Deferred import to avoid circular imports at module load
        from app.services.config_export_service import (
            export_trigger,
            import_trigger,
        )
        from app.db import get_trigger_by_name

        filename = os.path.basename(yaml_path)

        with open(yaml_path, "r") as f:
            raw_content = f.read()

        config = yaml.safe_load(raw_content)
        if not config or not isinstance(config, dict):
            return None

        if config.get("kind") != "trigger":
            return None

        name = config.get("metadata", {}).get("name")
        if not name:
            return None

        # Hash the git config
        git_hash = hashlib.sha256(raw_content.encode()).hexdigest()

        # Check existing trigger in DB
        existing = get_trigger_by_name(name)
        if existing:
            # Export current DB state and hash it
            db_config_str = export_trigger(existing["id"], format="yaml")
            db_hash = hashlib.sha256(
                (db_config_str or "").encode()
            ).hexdigest()

            if git_hash == db_hash:
                # No changes
                return None

            # Detect conflict: if both sides changed since last sync
            conflict = last_sha is not None and db_config_str is not None
            if conflict:
                logger.warning(
                    "GitOps conflict for '%s': both DB and Git changed. "
                    "Applying Git version (Git wins).",
                    name,
                )
        else:
            db_hash = None
            conflict = False

        change_info = {
            "file": filename,
            "name": name,
            "action": "update" if existing else "create",
            "conflict": conflict,
            "git_hash": git_hash[:12],
            "db_hash": (db_hash or "")[:12] if db_hash else None,
        }

        if dry_run:
            change_info["applied"] = False
            change_info["dry_run"] = True
            return change_info

        # Apply the change -- Git wins
        trigger_id, status = import_trigger(
            config_str=raw_content, format="yaml", upsert=True
        )

        change_info["applied"] = True
        change_info["trigger_id"] = trigger_id
        change_info["import_status"] = status

        AuditLogService.log(
            action="gitops.apply",
            entity_type="trigger",
            entity_id=trigger_id,
            outcome=status,
            details={
                "repo_id": repo_id,
                "file": filename,
                "conflict": conflict,
            },
        )

        return change_info

    @classmethod
    def start_polling(cls):
        """Start polling all enabled GitOps repos via APScheduler.

        Registers a job for each enabled repo with the configured interval.
        """
        try:
            from flask import current_app
            scheduler = current_app.extensions.get("scheduler")
        except RuntimeError:
            logger.debug("No Flask app context; skipping GitOps polling setup")
            return

        if not scheduler:
            logger.warning("APScheduler not available; GitOps polling disabled")
            return

        repos = list_gitops_repos()
        for repo in repos:
            if not repo.get("enabled"):
                continue
            cls._register_poll_job(scheduler, repo)

    @classmethod
    def stop_polling(cls):
        """Remove all GitOps scheduler jobs."""
        try:
            from flask import current_app
            scheduler = current_app.extensions.get("scheduler")
        except RuntimeError:
            return

        if not scheduler:
            return

        for job_id in list(cls._scheduler_jobs.keys()):
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        cls._scheduler_jobs.clear()

    @classmethod
    def _register_poll_job(cls, scheduler, repo: dict):
        """Register an APScheduler job for a single repo."""
        job_id = f"gitops_sync_{repo['id']}"
        interval = repo.get("poll_interval_seconds", 60)

        try:
            scheduler.add_job(
                func=cls._poll_sync,
                trigger="interval",
                seconds=interval,
                id=job_id,
                args=[repo["id"]],
                replace_existing=True,
            )
            cls._scheduler_jobs[job_id] = repo["id"]
            logger.info(
                "GitOps polling started for %s (every %ds)",
                repo["name"],
                interval,
            )
        except Exception as e:
            logger.error("Failed to register GitOps poll job: %s", e)

    @classmethod
    def _poll_sync(cls, repo_id: str):
        """Polling callback -- sync a repo (catches all exceptions)."""
        try:
            cls.sync_repo(repo_id)
        except Exception as e:
            logger.error("GitOps poll sync failed for %s: %s", repo_id, e)

    @classmethod
    def init(cls):
        """Initialize GitOps polling on server start."""
        cls.start_polling()

    @classmethod
    def _get_local_path(cls, repo_id: str) -> str:
        """Get the local cache path for a repo clone."""
        return os.path.join(_CACHE_BASE, repo_id)

    @classmethod
    def _ensure_repo(cls, local_path: str, repo_url: str, branch: str) -> str:
        """Clone or pull a git repo and return the current HEAD SHA.

        Args:
            local_path: Local directory for the clone.
            repo_url: Remote repo URL.
            branch: Branch to checkout.

        Returns:
            Current HEAD commit SHA.

        Raises:
            subprocess.CalledProcessError: If git commands fail.
        """
        if os.path.isdir(os.path.join(local_path, ".git")):
            # Pull latest changes
            subprocess.run(
                ["git", "-C", local_path, "fetch", "origin", branch],
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            subprocess.run(
                ["git", "-C", local_path, "reset", "--hard", f"origin/{branch}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        else:
            # Fresh clone
            os.makedirs(local_path, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--branch", branch, "--single-branch",
                 repo_url, local_path],
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )

        # Get current HEAD SHA
        result = subprocess.run(
            ["git", "-C", local_path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
