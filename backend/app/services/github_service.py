"""GitHub repository operations service."""

import datetime
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class GitHubService:
    """Service for GitHub repository clone, branch, commit, push, and PR operations."""

    CLONE_TIMEOUT = 300  # 5 minutes
    GIT_OP_TIMEOUT = 120  # 2 minutes

    @staticmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """Extract (owner, repo_name) from a GitHub URL.

        Accepts GitHub.com and GitHub Enterprise URLs:
          https://github.com/owner/repo
          https://github.example.com/owner/repo.git
        """
        pattern = r"https?://[^/]+/([^/]+)/([^/.]+?)(?:\.git)?/?$"
        match = re.match(pattern, url.strip())
        if not match:
            raise ValueError(f"Invalid GitHub repo URL: {url}")
        return match.group(1), match.group(2)

    @staticmethod
    def validate_repo_url(url: str) -> bool:
        """Check if a GitHub repo URL is accessible via gh CLI."""
        try:
            owner, repo = GitHubService.parse_repo_url(url)
        except ValueError:
            return False

        # Use owner/repo format instead of raw URL to prevent argument injection
        try:
            result = subprocess.run(
                ["gh", "repo", "view", f"{owner}/{repo}", "--json", "name"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    @staticmethod
    def clone_repo(repo_url: str, target_dir: str = None) -> str:
        """Clone a GitHub repo with --recursive to a temp directory.

        Returns the path to the cloned directory.
        Raises RuntimeError on failure.
        """
        # Validate URL format before passing to subprocess
        owner, repo_name = GitHubService.parse_repo_url(repo_url)

        if target_dir is None:
            prefix = f"agented_clone_{owner}_{repo_name}_"
            target_dir = tempfile.mkdtemp(prefix=prefix)

        try:
            # Use owner/repo format instead of raw URL
            result = subprocess.run(
                ["gh", "repo", "clone", f"{owner}/{repo_name}", target_dir, "--", "--recursive"],
                capture_output=True,
                text=True,
                timeout=GitHubService.CLONE_TIMEOUT,
            )
            if result.returncode != 0:
                raise RuntimeError(f"gh repo clone failed: {result.stderr.strip()}")
            logger.info("Cloned %s to %s", repo_url, target_dir)
            return target_dir
        except subprocess.TimeoutExpired:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"gh repo clone timed out for {repo_url}")
        except RuntimeError:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise
        except Exception as e:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"gh repo clone failed: {e}")

    @staticmethod
    def cleanup_clone(clone_path: str) -> bool:
        """Remove a cloned repository directory."""
        try:
            if clone_path and os.path.isdir(clone_path):
                shutil.rmtree(clone_path)
                logger.info("Cleaned up clone: %s", clone_path)
                return True
        except Exception as e:
            logger.error("Failed to clean up clone directory %s: %s", clone_path, e)
        return False

    @staticmethod
    def create_branch(repo_path: str, branch_name: str) -> bool:
        """Create and checkout a new git branch."""
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error("Failed to create branch %s: %s", branch_name, result.stderr)
            return False
        logger.info("Created branch: %s", branch_name)
        return True

    @staticmethod
    def commit_changes(repo_path: str, commit_message: str) -> bool:
        """Stage all changes and commit. Returns False if nothing to commit."""
        # Stage all changes
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if add_result.returncode != 0:
            logger.warning(
                "git add -A failed (exit=%d): %s", add_result.returncode, add_result.stderr
            )

        # Check if there are staged changes
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_path,
            capture_output=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if status.returncode == 0:
            logger.info("No changes to commit")
            return False

        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git commit failed: {result.stderr.strip()}")
        logger.info("Committed changes: %s", commit_message)
        return True

    @staticmethod
    def push_branch(repo_path: str, branch_name: str) -> bool:
        """Push the branch to origin using gh auth for credentials."""
        # Configure gh as git credential helper for this repo
        auth_result = subprocess.run(
            ["gh", "auth", "setup-git"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if auth_result.returncode != 0:
            logger.warning(
                "gh auth setup-git failed (exit=%d): %s", auth_result.returncode, auth_result.stderr
            )
        result = subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git push failed: {result.stderr.strip()}")
        logger.info("Pushed branch: %s", branch_name)
        return True

    @staticmethod
    def create_pull_request(
        repo_path: str, branch_name: str, title: str, body: str, base_branch: str = "main"
    ) -> Optional[str]:
        """Create a PR using gh CLI. Returns PR URL on success."""
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--base",
                base_branch,
                "--head",
                branch_name,
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error("Failed to create PR: %s", result.stderr)
            return None
        pr_url = result.stdout.strip()
        logger.info("Created PR: %s", pr_url)
        return pr_url

    @staticmethod
    def validate_github_url_format(url: str) -> bool:
        """Validate GitHub URL format without requiring gh CLI auth.

        Accepts https://github.com/owner/repo and GitHub Enterprise URLs
        like https://github.acme.com/owner/repo.
        """
        pattern = (
            r"^https?://[a-zA-Z0-9._-]+(?:\.[a-zA-Z0-9._-]+)+/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/?$"
        )
        return bool(re.match(pattern, url.strip()))

    @staticmethod
    def delete_remote_branch(repo_path: str, branch_name: str) -> bool:
        """Delete a remote branch to roll back a partially created PR. Returns True on success."""
        result = subprocess.run(
            ["git", "push", "origin", "--delete", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            logger.error("Failed to delete remote branch %s: %s", branch_name, result.stderr)
            return False
        logger.info("Deleted remote branch: %s", branch_name)
        return True

    @staticmethod
    def generate_branch_name() -> str:
        """Generate a timestamped branch name for security fixes."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"security-fix/{timestamp}"
