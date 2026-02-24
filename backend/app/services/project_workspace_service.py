"""Service for resolving project working directories."""

import logging
import os
import subprocess
import threading
from datetime import datetime, timezone

from ..database import (
    get_project,
    get_projects_with_github_repo,
    get_setting,
    update_project_clone_status,
)

logger = logging.getLogger(__name__)


class ProjectWorkspaceService:
    """Resolves the working directory for a project's team execution."""

    @staticmethod
    def _normalize_github_repo(raw: str) -> str:
        """Extract 'owner/repo' from various GitHub URL formats.

        Accepts: 'owner/repo', 'https://github.com/owner/repo',
        'https://github.acme.com/owner/repo.git', 'github.com/owner/repo', etc.
        Returns the bare 'owner/repo' slug.
        """
        repo = raw.strip().rstrip("/")
        # Strip .git suffix
        if repo.endswith(".git"):
            repo = repo[:-4]
        # Strip full URL prefixes (any host)
        import re

        url_match = re.match(r"https?://[^/]+/(.+)", repo)
        if url_match:
            repo = url_match.group(1)
        elif "/" in repo and "." in repo.split("/")[0]:
            # Handle bare host prefix like 'github.acme.com/owner/repo'
            repo = "/".join(repo.split("/")[1:])
        return repo

    @staticmethod
    def _extract_github_host(raw: str) -> str:
        """Extract the GitHub host from a URL.

        Returns the host (e.g. 'github.com' or 'github.acme.com').
        Defaults to 'github.com' if no host can be extracted.
        """
        import re

        raw = raw.strip()
        match = re.match(r"https?://([^/]+)", raw)
        if match:
            return match.group(1)
        # Handle bare host prefix like 'github.acme.com/owner/repo'
        if "/" in raw and "." in raw.split("/")[0]:
            return raw.split("/")[0]
        return "github.com"

    @staticmethod
    def _get_clone_dir(project: dict) -> str | None:
        """Build the clone directory path for a project with a github_repo."""
        workspace_root = get_setting("workspace_root")
        if not workspace_root or not os.path.isdir(workspace_root):
            return None
        project_name = project.get("name", project["id"])
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
        return os.path.join(workspace_root, "projects", safe_name)

    @staticmethod
    def resolve_working_directory(project_id: str) -> str:
        """Resolve the working directory for a project.

        Priority:
        1. project.local_path (if set and directory exists)
        2. project.github_repo (clone to workspace_root/projects/{name}/)

        Raises ValueError if no working directory can be resolved.
        """
        project = get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # 1. Try local_path first
        local_path = project.get("local_path")
        if local_path and os.path.isdir(local_path):
            logger.info(f"Using local_path for project {project_id}: {local_path}")
            return local_path

        if local_path and not os.path.isdir(local_path):
            raise ValueError(f"Project local_path does not exist: {local_path}")

        # 2. Try github_repo with workspace_root
        github_repo = project.get("github_repo")
        if github_repo:
            workspace_root = get_setting("workspace_root")
            if not workspace_root:
                raise ValueError(
                    "workspace_root setting is not configured. "
                    "Set it in Settings > General to enable GitHub-based project execution."
                )

            if not os.path.isdir(workspace_root):
                raise ValueError(f"workspace_root directory does not exist: {workspace_root}")

            clone_dir = ProjectWorkspaceService._get_clone_dir(project)

            if os.path.isdir(clone_dir):
                logger.info(f"Using existing clone for project {project_id}: {clone_dir}")
                return clone_dir

            # Clone the repo
            github_host = project.get("github_host", "github.com")
            repo_url = f"https://{github_host}/{ProjectWorkspaceService._normalize_github_repo(github_repo)}.git"
            os.makedirs(os.path.dirname(clone_dir), exist_ok=True)
            logger.info(f"Cloning {repo_url} to {clone_dir}")
            result = subprocess.run(
                ["git", "clone", repo_url, clone_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise ValueError(f"Failed to clone {repo_url}: {result.stderr.strip()}")

            return clone_dir

        raise ValueError(
            f"Project {project_id} has no local_path or github_repo configured. "
            "Set one in project settings to enable team execution."
        )

    @staticmethod
    def clone_async(project_id: str) -> None:
        """Clone a project's GitHub repo in a background thread."""

        def _do_clone():
            try:
                update_project_clone_status(project_id, "cloning")
                project = get_project(project_id)
                if not project or not project.get("github_repo"):
                    update_project_clone_status(
                        project_id, "error", clone_error="No github_repo configured"
                    )
                    return

                workspace_root = get_setting("workspace_root")
                if not workspace_root:
                    update_project_clone_status(
                        project_id,
                        "error",
                        clone_error="workspace_root setting is not configured",
                    )
                    return

                os.makedirs(workspace_root, exist_ok=True)
                clone_dir = ProjectWorkspaceService._get_clone_dir(project)
                if not clone_dir:
                    update_project_clone_status(
                        project_id, "error", clone_error="Could not determine clone directory"
                    )
                    return

                if os.path.isdir(clone_dir):
                    # Already cloned
                    now = datetime.now(timezone.utc).isoformat()
                    update_project_clone_status(project_id, "cloned", last_synced_at=now)
                    return

                github_host = project.get("github_host", "github.com")
                repo_url = f"https://{github_host}/{ProjectWorkspaceService._normalize_github_repo(project['github_repo'])}.git"
                os.makedirs(os.path.dirname(clone_dir), exist_ok=True)
                logger.info(f"[clone_async] Cloning {repo_url} to {clone_dir}")
                result = subprocess.run(
                    ["git", "clone", repo_url, clone_dir],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    update_project_clone_status(
                        project_id, "error", clone_error=result.stderr.strip()
                    )
                    return

                now = datetime.now(timezone.utc).isoformat()
                update_project_clone_status(project_id, "cloned", last_synced_at=now)
                logger.info(f"[clone_async] Clone complete for project {project_id}")
            except Exception as e:
                logger.exception(f"[clone_async] Failed for project {project_id}")
                update_project_clone_status(project_id, "error", clone_error=str(e))

        thread = threading.Thread(target=_do_clone, daemon=True)
        thread.start()

    @staticmethod
    def sync_repo(project_id: str) -> dict:
        """Run git pull on an already-cloned project repo."""
        project = get_project(project_id)
        if not project:
            return {"status": "error", "error": "Project not found"}

        if project.get("clone_status") != "cloned":
            return {
                "status": "error",
                "error": f"Project clone_status is '{project.get('clone_status')}', not 'cloned'",
            }

        clone_dir = ProjectWorkspaceService._get_clone_dir(project)
        if not clone_dir or not os.path.isdir(clone_dir):
            # Fall back to local_path
            local_path = project.get("local_path")
            if local_path and os.path.isdir(local_path):
                clone_dir = local_path
            else:
                return {"status": "error", "error": "Clone directory not found"}

        try:
            result = subprocess.run(
                ["git", "pull", "--ff-only"],
                cwd=clone_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                update_project_clone_status(project_id, "cloned", clone_error=error_msg)
                return {"status": "error", "error": error_msg}

            now = datetime.now(timezone.utc).isoformat()
            update_project_clone_status(project_id, "cloned", last_synced_at=now)
            return {"status": "ok", "output": result.stdout.strip()}
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "git pull timed out after 120s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def sync_all_repos() -> dict:
        """Sync all cloned project repos. Called by the scheduler."""
        projects = get_projects_with_github_repo("cloned")
        synced = 0
        failed = 0
        errors = []

        for project in projects:
            result = ProjectWorkspaceService.sync_repo(project["id"])
            if result["status"] == "ok":
                synced += 1
            else:
                failed += 1
                errors.append(
                    {"project_id": project["id"], "error": result.get("error", "unknown")}
                )

        logger.info(f"[sync_all_repos] synced={synced}, failed={failed}")
        return {"synced": synced, "failed": failed, "errors": errors}
