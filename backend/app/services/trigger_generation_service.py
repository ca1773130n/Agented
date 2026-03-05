"""Service for generating trigger configurations using Claude CLI."""

import re
import logging

from ..db.triggers import VALID_BACKENDS, VALID_TRIGGER_SOURCES, get_all_triggers
from .base_generation_service import BaseGenerationService

logger = logging.getLogger(__name__)


class TriggerGenerationService(BaseGenerationService):
    """Generate trigger configurations from natural language descriptions."""

    # Placeholder variables available by trigger source
    PLACEHOLDERS_BY_SOURCE = {
        "github": {
            "{pr_url}": "Full URL to the pull request",
            "{pr_title}": "PR title text",
            "{pr_author}": "PR author username",
            "{pr_number}": "PR number",
            "{repo_url}": "Repository clone URL",
            "{repo_full_name}": "Repository full name (owner/repo)",
        },
        "webhook": {
            "{message}": "The message text from the webhook payload",
            "{paths}": "Newline-separated list of configured project paths",
        },
        "scheduled": {
            "{paths}": "Newline-separated list of configured project paths",
        },
        "manual": {
            "{message}": "The message text provided by the user",
            "{paths}": "Newline-separated list of configured project paths",
        },
    }

    @classmethod
    def _gather_context(cls) -> dict:
        """Gather existing triggers, valid backends, and sources for context."""
        triggers = get_all_triggers()
        existing = [
            {"name": t.get("name"), "trigger_source": t.get("trigger_source")} for t in triggers
        ]
        return {
            "existing_triggers": existing,
            "backends": list(VALID_BACKENDS),
            "trigger_sources": list(VALID_TRIGGER_SOURCES),
            "placeholders": cls.PLACEHOLDERS_BY_SOURCE,
        }

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        """Build the Claude prompt for trigger configuration generation."""
        existing = context.get("existing_triggers", [])
        backends = context.get("backends", [])
        trigger_sources = context.get("trigger_sources", [])
        placeholders = context.get("placeholders", {})

        sections = [
            "You are a trigger configuration generator for an AI bot automation platform called Agented.",
            (
                "Triggers define automated bot behaviors -- they specify when a bot runs "
                "(trigger source), what AI backend to use, and what prompt to execute. "
                "Generate a complete trigger configuration based on the user's description."
            ),
        ]

        # Available backends
        sections.append(f"Available AI backends: {', '.join(backends)}")

        # Available trigger sources
        sections.append(f"Available trigger sources: {', '.join(trigger_sources)}")

        # Placeholder variables
        placeholder_lines = []
        for source, vars_dict in placeholders.items():
            var_list = ", ".join(f"{k} ({v})" for k, v in vars_dict.items())
            placeholder_lines.append(f"  - {source}: {var_list}")
        sections.append(
            "Available placeholder variables for prompt_template (by trigger source):\n"
            + "\n".join(placeholder_lines)
        )

        # Existing triggers for context
        if existing:
            trigger_lines = [f"  - {t.get('name')} ({t.get('trigger_source')})" for t in existing]
            sections.append(
                "Existing triggers (avoid name conflicts):\n" + "\n".join(trigger_lines)
            )

        # JSON schema
        sections.append(
            "Respond with ONLY a valid JSON object (no markdown fences, no extra text) "
            "matching this schema:\n"
            "{\n"
            '  "name": "Human-readable trigger name",\n'
            '  "prompt_template": "Detailed prompt with appropriate {placeholder} variables",\n'
            '  "backend_type": "claude|opencode|gemini|codex",\n'
            '  "trigger_source": "webhook|github|scheduled|manual",\n'
            '  "model": null,\n'
            '  "schedule_type": "daily|weekly|monthly (only if trigger_source is scheduled, else omit)",\n'
            '  "schedule_value": "time or day value (only if scheduled, else omit)",\n'
            '  "paths": []\n'
            "}\n\n"
            "Guidelines:\n"
            "- Generate a detailed, effective prompt_template (at least 3-5 sentences)\n"
            "- Use appropriate placeholder variables for the chosen trigger_source\n"
            "- Choose the most appropriate trigger_source based on the description\n"
            "- Default to 'claude' backend unless the description suggests otherwise\n"
            "- Set model to null unless a specific model is requested"
        )

        sections.append(f"User's description: {description}")
        return "\n\n".join(sections)

    @classmethod
    def _extract_progress(cls, text: str, reported: set) -> list[str]:
        """Extract progress messages from growing JSON text."""
        messages = []

        if "name" not in reported:
            m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("name")
                messages.append(f"Trigger: {m.group(1)}")

        if "trigger_source" not in reported:
            m = re.search(r'"trigger_source"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("trigger_source")
                messages.append(f"Source: {m.group(1)}")

        if "backend_type" not in reported:
            m = re.search(r'"backend_type"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("backend_type")
                messages.append(f"Backend: {m.group(1)}")

        if "prompt_template" not in reported:
            m = re.search(r'"prompt_template"\s*:\s*"([^"]{20,})"', text)
            if m:
                reported.add("prompt_template")
                prompt_preview = m.group(1)[:100]
                if len(m.group(1)) > 100:
                    prompt_preview += "..."
                messages.append(f"Prompt: {prompt_preview}")

        return messages

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        """Validate the generated trigger configuration.

        Returns (config, warnings) -- adds warnings for missing optional fields
        but does NOT reject for them.
        """
        warnings = []

        # Check required fields
        required = ["name", "prompt_template", "backend_type", "trigger_source"]
        for field in required:
            if not config.get(field):
                warnings.append(f"Missing required field: {field}")

        # Validate backend_type
        backend = config.get("backend_type", "")
        if backend and backend not in VALID_BACKENDS:
            warnings.append(f"Invalid backend_type '{backend}'. Valid: {', '.join(VALID_BACKENDS)}")
            config["backend_type"] = "claude"  # Default to claude

        # Validate trigger_source
        source = config.get("trigger_source", "")
        if source and source not in VALID_TRIGGER_SOURCES:
            warnings.append(
                f"Invalid trigger_source '{source}'. Valid: {', '.join(VALID_TRIGGER_SOURCES)}"
            )
            config["trigger_source"] = "webhook"  # Default to webhook

        # Check schedule fields if scheduled trigger
        if config.get("trigger_source") == "scheduled":
            if not config.get("schedule_type"):
                warnings.append("Scheduled trigger missing schedule_type (daily/weekly/monthly)")
            if not config.get("schedule_value"):
                warnings.append("Scheduled trigger missing schedule_value")

        # Warn about missing optional fields
        if not config.get("model"):
            config["model"] = None  # Ensure it's explicitly null

        return config, warnings
