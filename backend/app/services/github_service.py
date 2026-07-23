"""GitHub repository operations service."""

import datetime
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Optional, Tuple

from app.config import CLONE_TIMEOUT as _CLONE_TIMEOUT
from app.config import GIT_OP_TIMEOUT as _GIT_OP_TIMEOUT

logger = logging.getLogger(__name__)

DEFAULT_GITHUB_HOST = "github.com"


class GitHubService:
    """Service for GitHub repository clone, branch, commit, push, and PR operations."""

    CLONE_TIMEOUT = _CLONE_TIMEOUT
    GIT_OP_TIMEOUT = _GIT_OP_TIMEOUT

    @staticmethod
    def parse_repo_url_with_host(url: str) -> Tuple[str, str, str]:
        """Extract (owner, repo_name, host) from a GitHub URL.

        Accepts GitHub.com and GitHub Enterprise URLs, https or ssh:
          https://github.com/owner/repo
          https://github.example.com/owner/repo.git
          git@github.example.com:owner/repo.git
        """
        url = url.strip()
        # scp-style / ssh:// remotes collapse to the https form so the host
        # survives (GHE repo pages default to the SSH clone URL).
        url = re.sub(r"^git@([^:/]+):", r"https://\1/", url)
        url = re.sub(r"^ssh://(?:[^@/]+@)?", "https://", url)
        pattern = r"https?://([^/]+)/([^/]+)/([^/.]+?)(?:\.git)?/?$"
        match = re.match(pattern, url)
        if not match:
            raise ValueError(f"Invalid GitHub repo URL: {url}")
        host = match.group(1).lower()
        if host == "www.github.com":
            host = DEFAULT_GITHUB_HOST
        return match.group(2), match.group(3), host

    @staticmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """Extract (owner, repo_name) from a GitHub URL. See parse_repo_url_with_host."""
        owner, repo, _host = GitHubService.parse_repo_url_with_host(url)
        return owner, repo

    @staticmethod
    def _gh_env(host: Optional[str]) -> Optional[dict]:
        """Subprocess env for gh CLI calls: pin GH_HOST for GitHub Enterprise
        hosts and inject the host's vault-stored token (if any) under the env
        var gh reads for that host class.

        Returns None (inherit the parent env) for github.com with no stored
        token, so the default path is byte-for-byte unchanged.
        """
        from .github_credentials_service import GithubCredentialsService, gh_env_token_var

        additions = {}
        if host and host != DEFAULT_GITHUB_HOST:
            additions["GH_HOST"] = host
        token = GithubCredentialsService.stored_token_for_host(
            host or DEFAULT_GITHUB_HOST, accessor="github_service"
        )
        if token:
            additions[gh_env_token_var(host or DEFAULT_GITHUB_HOST)] = token
        return {**os.environ, **additions} if additions else None

    @staticmethod
    def _origin_host(repo_path: str) -> Optional[str]:
        """Host of the clone's origin remote (https or ssh form), or None."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=GitHubService.GIT_OP_TIMEOUT,
            )
            if result.returncode != 0:
                return None
            url = result.stdout.strip()
            match = re.match(r"(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?([^:/\s]+)", url)
            if not match:
                return None
            host = match.group(1).lower()
            return DEFAULT_GITHUB_HOST if host == "www.github.com" else host
        except Exception:
            return None

    @staticmethod
    def api_base_for_host(host: str) -> str:
        """REST API base URL for a GitHub host.

        github.com -> https://api.github.com; GHE Cloud data-residency
        (*.ghe.com) -> https://api.HOST; GHE Server -> https://HOST/api/v3.
        """
        if host == DEFAULT_GITHUB_HOST:
            return "https://api.github.com"
        if host.endswith(".ghe.com"):
            return f"https://api.{host}"
        return f"https://{host}/api/v3"

    @staticmethod
    def validate_repo_url(url: str) -> bool:
        """Check if a GitHub repo URL is well-formed and likely valid.

        First validates the URL format, then tries gh CLI.  If gh fails
        (auth issues, network, etc.), falls back to an unauthenticated
        HTTP check for public repos.  Returns True on any ambiguous result
        so project creation isn't blocked — the async clone will surface
        real errors later.
        """
        try:
            owner, repo, host = GitHubService.parse_repo_url_with_host(url)
        except ValueError:
            return False

        # SECURITY: never probe a non-github.com host from the backend process.
        # The host comes from the user's pasted URL, so an active check here
        # would be a blind SSRF into internal networks AND would hand gh's
        # GH_ENTERPRISE_TOKEN to an arbitrary host. Format validity is enough —
        # the async clone surfaces real errors, same as the lenient policy below.
        if host != DEFAULT_GITHUB_HOST:
            return True

        # Try gh CLI first (works for private repos if authed)
        try:
            result = subprocess.run(
                ["gh", "repo", "view", f"{owner}/{repo}", "--json", "name"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass  # Intentionally silenced: file may not exist, which is acceptable

        # Fallback: unauthenticated GitHub API check (public repos)
        try:
            import httpx

            resp = httpx.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                timeout=10,
                # Don't follow redirects off the GitHub API — only a direct 200
                # from api.github.com confirms the repo (05 L1).
                follow_redirects=False,
            )
            if resp.status_code == 200:
                return True
            # 404 = repo doesn't exist or is private and we can't verify
            # For private repos where gh auth is broken, allow creation
            # and let the clone step handle the error.
            if resp.status_code == 404:
                return True  # Might be private; let clone discover the issue
        except Exception:
            pass  # Intentionally silenced: failure is non-critical

        # If everything failed (network down, etc.), still allow creation
        return True

    @staticmethod
    def clone_repo(repo_url: str, target_dir: str = None) -> str:
        """Clone a GitHub repo with --recursive to a temp directory.

        Returns the path to the cloned directory.
        Raises RuntimeError on failure.
        """
        # Validate URL format before passing to subprocess
        owner, repo_name, host = GitHubService.parse_repo_url_with_host(repo_url)

        if target_dir is None:
            prefix = f"agented_clone_{owner}_{repo_name}_"
            target_dir = tempfile.mkdtemp(prefix=prefix)

        try:
            # Rebuild a canonical URL from the parsed parts (never the raw input)
            # so the host survives — a bare owner/repo slug would make gh resolve
            # a GitHub Enterprise repo against github.com.
            clone_url = f"https://{host}/{owner}/{repo_name}.git"
            result = subprocess.run(
                ["gh", "repo", "clone", clone_url, target_dir, "--", "--recursive"],
                capture_output=True,
                text=True,
                timeout=GitHubService.CLONE_TIMEOUT,
                env=GitHubService._gh_env(host),
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
            logger.error("Failed to clean up clone directory %s: %s", clone_path, e, exc_info=True)
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
        # Configure gh as git credential helper for this repo. For a GitHub
        # Enterprise origin the hostname must be explicit — bare setup-git
        # only covers hosts gh treats as default (github.com).
        host = GitHubService._origin_host(repo_path)
        auth_cmd = ["gh", "auth", "setup-git"]
        if host and host != DEFAULT_GITHUB_HOST:
            auth_cmd += ["--hostname", host]
        auth_result = subprocess.run(
            auth_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GitHubService.GIT_OP_TIMEOUT,
            env=GitHubService._gh_env(host),
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
            # gh's credential helper (configured above) resolves tokens from
            # the env, so the push must carry the host's stored token too.
            env=GitHubService._gh_env(host),
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
            # Pin gh to the origin's host so a GHE clone's PR isn't opened
            # against github.com (None ⇒ inherit env, unchanged for github.com).
            env=GitHubService._gh_env(GitHubService._origin_host(repo_path)),
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
            env=GitHubService._gh_env(GitHubService._origin_host(repo_path)),
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
