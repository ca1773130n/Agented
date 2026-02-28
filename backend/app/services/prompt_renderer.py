"""Stateless prompt template rendering helper extracted from ExecutionService.

Handles placeholder substitution in trigger prompt templates and warns about
any unresolved placeholders that remain after rendering.  Pure functions --
no side effects, no I/O, no instance state.

Reference: Fowler "Refactoring" (2018) Extract Class pattern.
"""

import re


class PromptRenderer:
    """Stateless renderer for trigger prompt templates."""

    # All placeholder names that the rendering pipeline is expected to resolve.
    _KNOWN_PLACEHOLDERS = {
        "trigger_id",
        "bot_id",
        "paths",
        "message",
        "pr_url",
        "pr_number",
        "pr_title",
        "pr_author",
        "repo_url",
        "repo_full_name",
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
        if unknown:
            logger.warning(
                "Trigger '%s' has unresolved placeholders: %s",
                trigger_name,
                ", ".join(f"{{{p}}}" for p in unknown),
            )
