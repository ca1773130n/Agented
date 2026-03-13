"""Stateless prompt template rendering helper extracted from ExecutionService.

Handles placeholder substitution in trigger prompt templates and warns about
any unresolved placeholders that remain after rendering.  Pure functions --
no side effects, no I/O, no instance state.

Reference: Fowler "Refactoring" (2018) Extract Class pattern.
"""

import logging
import re

from .prompt_snippet_service import SnippetService

logger = logging.getLogger(__name__)


class PromptRenderer:
    """Stateless renderer for trigger prompt templates."""

    # ── Known prompt-template placeholders ──────────────────────────────
    #
    # Every placeholder below can appear as ``{name}`` in a trigger's
    # ``prompt_template``.  The ``render()`` method resolves them using
    # values from the trigger context or event payload.
    #
    # Universal placeholders (available for all trigger sources):
    #   trigger_id  – The trigger's unique ID (e.g. "trg-abc123").
    #                 Source: passed directly to render().
    #   bot_id      – Legacy alias for trigger_id; kept for backward compat.
    #   paths       – Newline-separated list of project paths configured on
    #                 the trigger.  Source: computed by ExecutionService from
    #                 the trigger's ``paths`` field.
    #   message     – Free-text message supplied by the caller.  For webhook
    #                 triggers this is the payload body; for manual triggers
    #                 it's the user-provided text.
    #
    # GitHub PR placeholders (resolved only when event["type"] == "github_pr"):
    #   pr_url        – Full URL of the pull request (e.g. "https://github.com/…/pull/42").
    #   pr_number     – PR number as a string (e.g. "42").
    #   pr_title      – Title of the pull request.
    #   pr_author     – GitHub username of the PR author.
    #   repo_url      – Clone URL of the repository.
    #   repo_full_name – "owner/repo" identifier (e.g. "acme/widget").
    #   All sourced from the GitHub webhook event dict built by
    #   ``routes/github_webhook.py``.
    #
    # Adding a new placeholder:
    #   1. Add the name to ``_KNOWN_PLACEHOLDERS`` below.
    #   2. Perform the substitution in ``render()`` (use
    #      ``prompt.replace("{name}", value)``).
    #   3. If the value comes from a new event type, gate on
    #      ``event.get("type")`` like the GitHub PR block does.
    #   4. Add the placeholder to ``TriggerGenerationService.PLACEHOLDERS_BY_SOURCE``
    #      so the AI trigger generator knows about it.
    # ─────────────────────────────────────────────────────────────────────
    _KNOWN_PLACEHOLDERS = {
        "trigger_id",  # Universal – the trigger's unique ID
        "bot_id",  # Universal – legacy alias for trigger_id
        "paths",  # Universal – newline-separated project paths
        "message",  # Universal – incoming message / webhook body
        "pr_url",  # GitHub PR – full pull-request URL
        "pr_number",  # GitHub PR – pull-request number (string)
        "pr_title",  # GitHub PR – pull-request title
        "pr_author",  # GitHub PR – PR author's GitHub username
        "repo_url",  # GitHub PR – repository clone URL
        "repo_full_name",  # GitHub PR – "owner/repo" identifier
    }

    @staticmethod
    def render(
        trigger: dict,
        trigger_id: str,
        message_text: str,
        paths_str: str,
        event: dict = None,
    ) -> str:
        """Render a trigger's prompt template by substituting placeholders.

        Performs the following substitutions:
        1. ``{trigger_id}`` / ``{bot_id}`` -- the trigger ID (bot_id is legacy).
        2. ``{paths}`` -- comma-separated list of effective paths.
        3. ``{message}`` -- the incoming message text.
        4. GitHub PR placeholders when *event* is a ``github_pr`` type.
        5. Prepends ``skill_command`` if configured and not already present.

        Note: the security-audit threat-report logic (file I/O) is intentionally
        kept in ``ExecutionService.run_trigger`` because it has side effects.

        Args:
            trigger: Trigger dict (must contain ``prompt_template``; may contain
                ``skill_command``).
            trigger_id: The trigger/bot identifier.
            message_text: The incoming message text to substitute.
            paths_str: Pre-computed comma-separated paths string.
            event: Optional event context dict.  If ``event["type"]`` is
                ``"github_pr"``, PR-specific placeholders are resolved.

        Returns:
            The fully rendered prompt string.
        """
        prompt = trigger["prompt_template"]
        # Resolve {{snippet}} references before {placeholder} substitution
        prompt = SnippetService.resolve_snippets(prompt)
        prompt = prompt.replace("{trigger_id}", trigger_id)
        prompt = prompt.replace("{bot_id}", trigger_id)  # Legacy placeholder support
        prompt = prompt.replace("{paths}", paths_str)
        prompt = prompt.replace("{message}", message_text)

        # Add trigger context if available
        if event:
            # Handle GitHub PR placeholders
            if event.get("type") == "github_pr":
                prompt = prompt.replace("{pr_url}", event.get("pr_url", ""))
                prompt = prompt.replace("{pr_number}", str(event.get("pr_number", "")))
                prompt = prompt.replace("{pr_title}", event.get("pr_title", ""))
                prompt = prompt.replace("{pr_author}", event.get("pr_author", ""))
                prompt = prompt.replace("{repo_url}", event.get("repo_url", ""))
                prompt = prompt.replace("{repo_full_name}", event.get("repo_full_name", ""))

        # Prepend skill_command if configured and not already in prompt
        skill_command = trigger.get("skill_command", "")
        if skill_command and not prompt.lstrip().startswith(skill_command):
            prompt = f"{skill_command} {prompt}"

        return prompt

    @classmethod
    def warn_unresolved(cls, prompt: str, trigger_name: str, logger) -> None:
        """Log a warning for any unresolved ``{placeholder}`` tokens in the prompt.

        Only warns about placeholders that are **not** in ``_KNOWN_PLACEHOLDERS``,
        because known placeholders may legitimately be left empty (e.g. no PR
        context for a webhook trigger).

        Args:
            prompt: The rendered prompt to inspect.
            trigger_name: Human-readable trigger name for the log message.
            logger: A ``logging.Logger`` instance to emit the warning on.
        """
        unresolved = re.findall(r"\{(\w+)\}", prompt)
        unknown = [p for p in unresolved if p not in cls._KNOWN_PLACEHOLDERS]
        known_unresolved = [p for p in unresolved if p in cls._KNOWN_PLACEHOLDERS]
        if unknown:
            logger.warning(
                "Trigger '%s' has unknown unresolved placeholders: %s",
                trigger_name,
                ", ".join(f"{{{p}}}" for p in unknown),
            )
        if known_unresolved:
            logger.warning(
                "Trigger '%s' has known but unresolved placeholders (missing context?): %s",
                trigger_name,
                ", ".join(f"{{{p}}}" for p in known_unresolved),
            )
