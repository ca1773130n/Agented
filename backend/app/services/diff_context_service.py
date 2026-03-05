"""Diff-aware context service for extracting focused context from PR diffs.

Uses the unidiff library to parse unified diff output into structured patches,
then extracts only changed files with surrounding context lines. This reduces
token costs by 40-80% for PR reviews compared to full-file inclusion.

Research basis: LongLLMLingua (Jiang 2023) shows 4x token reduction with
quality improvement when focusing on relevant context.
"""

import logging
import subprocess
from typing import Optional

from unidiff import PatchSet

logger = logging.getLogger(__name__)


class DiffContextService:
    """Service for extracting diff-aware context from PR diffs."""

    CONTEXT_LINES = 10

    @classmethod
    def extract_pr_diff_context(cls, diff_text: str, context_lines: Optional[int] = None) -> str:
        """Extract focused context from a unified diff.

        Args:
            diff_text: Raw unified diff text (e.g., from `git diff`).
            context_lines: Number of context lines around changes (default 10).

        Returns:
            Formatted context string with only changed files and hunks.
            Empty string for empty diff input.
        """
        if not diff_text or not diff_text.strip():
            return ""

        try:
            patch_set = PatchSet(diff_text)
        except Exception as e:
            logger.warning("Failed to parse diff: %s", e)
            return f"[Failed to parse diff: {e}]"

        if not patch_set:
            return ""

        parts = []

        for patched_file in patch_set:
            # Skip binary files
            if patched_file.is_binary_file:
                parts.append(f"[Binary file: {patched_file.path} -- skipped]")
                continue

            # Handle renamed files
            if patched_file.source_file and patched_file.target_file:
                source = patched_file.source_file.lstrip("a/")
                target = patched_file.target_file.lstrip("b/")
                if source != target:
                    parts.append(f"## {target} (renamed from {source})")
                else:
                    parts.append(f"## {target}")
            else:
                parts.append(f"## {patched_file.path}")

            # Add summary line
            parts.append(f"+{patched_file.added} -{patched_file.removed} lines changed")
            parts.append("")

            # Include all hunks with context
            for hunk in patched_file:
                parts.append(
                    f"@@ -{hunk.source_start},{hunk.source_length} "
                    f"+{hunk.target_start},{hunk.target_length} @@"
                )
                for line in hunk:
                    if line.is_added:
                        parts.append(f"+{line.value.rstrip()}")
                    elif line.is_removed:
                        parts.append(f"-{line.value.rstrip()}")
                    else:
                        parts.append(f" {line.value.rstrip()}")
                parts.append("")

        return "\n".join(parts).strip()

    @classmethod
    def extract_from_repo(
        cls,
        repo_path: str,
        base_branch: str = "main",
        context_lines: Optional[int] = None,
    ) -> str:
        """Extract diff-aware context from a local git repository.

        Args:
            repo_path: Path to the git repository.
            base_branch: Branch to compare against (default "main").
            context_lines: Number of context lines around changes.

        Returns:
            Formatted context string from the repo diff.
        """
        effective_context = context_lines if context_lines is not None else cls.CONTEXT_LINES

        try:
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    f"{base_branch}...HEAD",
                    f"-U{effective_context}",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git diff failed in %s: %s", repo_path, result.stderr)
                return ""

            return cls.extract_pr_diff_context(result.stdout, context_lines)
        except subprocess.TimeoutExpired:
            logger.error("git diff timed out in %s", repo_path)
            return ""
        except Exception as e:
            logger.error("Failed to extract diff from repo %s: %s", repo_path, e)
            return ""

    @classmethod
    def estimate_token_reduction(cls, full_content: str, diff_context: str) -> dict:
        """Estimate token reduction from using diff-aware context.

        Uses 4 chars/token heuristic per 08-RESEARCH.md.

        Args:
            full_content: The full file content that would be included without diff context.
            diff_context: The focused diff context string.

        Returns:
            Dict with full_tokens, diff_tokens, reduction_percent.
        """
        chars_per_token = 4
        full_tokens = len(full_content) / chars_per_token
        diff_tokens = len(diff_context) / chars_per_token

        if full_tokens == 0:
            reduction_percent = 0.0
        else:
            reduction_percent = round(((full_tokens - diff_tokens) / full_tokens) * 100, 1)

        return {
            "full_tokens": int(full_tokens),
            "diff_tokens": int(diff_tokens),
            "reduction_percent": reduction_percent,
        }
