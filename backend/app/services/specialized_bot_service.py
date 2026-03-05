"""Specialized bot helper service for PR comments and changelog utilities."""

import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class SpecializedBotService:
    """Utility service for specialized bot operations.

    Provides helper methods for PR comment posting via gh CLI and
    merged PR listing for changelog generation. All methods are
    classmethods and stateless.
    """

    GH_TIMEOUT = 30  # seconds

    @classmethod
    def post_pr_comment(cls, repo_full_name: str, pr_number: int, body: str) -> bool:
        """Post a comment on a GitHub PR using gh CLI.

        Args:
            repo_full_name: Repository in "owner/repo" format.
            pr_number: The pull request number.
            body: The comment body text (Markdown supported).

        Returns:
            True on success, False on failure.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "comment",
                    str(pr_number),
                    "--repo",
                    repo_full_name,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=cls.GH_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info(
                    "Posted PR comment on %s#%d (%d chars)",
                    repo_full_name,
                    pr_number,
                    len(body),
                )
                return True
            else:
                logger.error(
                    "Failed to post PR comment on %s#%d: %s",
                    repo_full_name,
                    pr_number,
                    result.stderr.strip(),
                )
                return False
        except subprocess.TimeoutExpired:
            logger.error(
                "Timeout posting PR comment on %s#%d (timeout=%ds)",
                repo_full_name,
                pr_number,
                cls.GH_TIMEOUT,
            )
            return False
        except FileNotFoundError:
            logger.error("gh CLI not found on PATH; cannot post PR comment", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                "Unexpected error posting PR comment on %s#%d: %s", repo_full_name, pr_number, e
            )
            return False

    @classmethod
    def list_merged_prs(
        cls, repo_full_name: str, base_branch: str = "main", limit: int = 100
    ) -> list:
        """List merged PRs for a repository using gh CLI.

        Args:
            repo_full_name: Repository in "owner/repo" format.
            base_branch: Base branch to filter by (default: "main").
            limit: Maximum number of PRs to return (default: 100).

        Returns:
            List of dicts with PR data (number, title, labels, mergedAt, author),
            or empty list on failure.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--state",
                    "merged",
                    "--repo",
                    repo_full_name,
                    "--base",
                    base_branch,
                    "--json",
                    "number,title,labels,mergedAt,author",
                    "--limit",
                    str(limit),
                ],
                capture_output=True,
                text=True,
                timeout=cls.GH_TIMEOUT,
            )
            if result.returncode != 0:
                logger.error(
                    "Failed to list merged PRs for %s: %s",
                    repo_full_name,
                    result.stderr.strip(),
                )
                return []

            prs = json.loads(result.stdout)
            logger.info(
                "Listed %d merged PRs for %s (base=%s)",
                len(prs),
                repo_full_name,
                base_branch,
            )
            return prs
        except subprocess.TimeoutExpired:
            logger.error(
                "Timeout listing merged PRs for %s (timeout=%ds)",
                repo_full_name,
                cls.GH_TIMEOUT,
            )
            return []
        except FileNotFoundError:
            logger.error("gh CLI not found on PATH; cannot list merged PRs", exc_info=True)
            return []
        except json.JSONDecodeError as e:
            logger.error("Failed to parse gh output for %s: %s", repo_full_name, e, exc_info=True)
            return []
        except Exception as e:
            logger.error(
                "Unexpected error listing merged PRs for %s: %s", repo_full_name, e, exc_info=True
            )
            return []

    @classmethod
    def check_gh_auth(cls) -> bool:
        """Check if gh CLI is authenticated.

        Returns:
            True if gh auth status returns exit code 0, False otherwise.
        """
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=cls.GH_TIMEOUT,
            )
            if result.returncode == 0:
                logger.info("gh CLI is authenticated")
                return True
            else:
                logger.warning("gh CLI is not authenticated: %s", result.stderr.strip())
                return False
        except FileNotFoundError:
            logger.error("gh CLI not found on PATH", exc_info=True)
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout checking gh auth status", exc_info=True)
            return False
        except Exception as e:
            logger.error("Unexpected error checking gh auth: %s", e, exc_info=True)
            return False

    @classmethod
    def check_osv_scanner(cls) -> bool:
        """Check if osv-scanner is available on PATH.

        Returns:
            True if osv-scanner is found, False otherwise.
        """
        found = shutil.which("osv-scanner") is not None
        if found:
            logger.info("osv-scanner found on PATH")
        else:
            logger.warning(
                "osv-scanner not found on PATH; "
                "vulnerability scanning will fall back to ecosystem-specific tools"
            )
        return found
