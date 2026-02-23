"""GitHub repository operations service."""

import datetime
import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple


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
            print(f"Cloned {repo_url} to {target_dir}")
            return target_dir
        except subprocess.TimeoutExpired:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"gh repo clone timed out for {repo_url}")
        except RuntimeError:
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
                print(f"Cleaned up clone: {clone_path}")
                return True
        except Exception as e:
            print(f"Failed to clean up clone {clone_path}: {e}")
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
            print(f"Failed to create branch {branch_name}: {result.stderr}")
            return False
        print(f"Created branch: {branch_name}")
        return True

    @staticmethod
    def commit_changes(repo_path: str, commit_message: str) -> bool:
        """Stage all changes and commit. Returns False if nothing to commit."""
        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )

        # Check if there are staged changes
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_path,
            capture_output=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if status.returncode == 0:
            print("No changes to commit")
            return False

        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            print(f"Failed to commit: {result.stderr}")
            return False
        print(f"Committed changes: {commit_message}")
        return True

    @staticmethod
    def push_branch(repo_path: str, branch_name: str) -> bool:
        """Push the branch to origin using gh auth for credentials."""
        # Configure gh as git credential helper for this repo
        subprocess.run(
            ["gh", "auth", "setup-git"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        result = subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
        )
        if result.returncode != 0:
            print(f"Failed to push: {result.stderr}")
            return False
        print(f"Pushed branch: {branch_name}")
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
            print(f"Failed to create PR: {result.stderr}")
            return None
        pr_url = result.stdout.strip()
        print(f"Created PR: {pr_url}")
        return pr_url

    @staticmethod
    def validate_github_url_format(url: str) -> bool:
        """Validate GitHub URL format without requiring gh CLI auth.

        Accepts https://github.com/owner/repo format.
        """
        pattern = r"^https?://github\.com/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/?$"
        return bool(re.match(pattern, url.strip()))

    @staticmethod
    def generate_branch_name() -> str:
        """Generate a timestamped branch name for security fixes."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"security-fix/{timestamp}"
