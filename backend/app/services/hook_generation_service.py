"""Service for generating hook configurations using Claude CLI."""

import re

from ..database import get_all_hooks
from .base_generation_service import BaseGenerationService

VALID_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreCompact",
    "Notification",
]


class HookGenerationService(BaseGenerationService):

    @classmethod
    def _gather_context(cls) -> dict:
        return {"hooks": get_all_hooks()}

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        hooks = context.get("hooks", [])
        sections = [
            "You are a hook configuration generator for an AI agent platform called Hive.",
            f"Valid hook events: {', '.join(VALID_EVENTS)}",
        ]

        if hooks:
            hook_lines = [
                f"  - name: {h.get('name')}, event: {h.get('event')}, description: {h.get('description', 'N/A')}"
                for h in hooks
            ]
            sections.append("Existing hooks:\n" + "\n".join(hook_lines))

        sections.append(
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "name": "hook-name",\n'
            '  "event": "PreToolUse|PostToolUse|Stop|...",\n'
            '  "description": "What this hook does",\n'
            '  "content": "The hook content/script",\n'
            '  "enabled": true\n'
            "}"
        )
        sections.append(f"User's description: {description}")
        return "\n\n".join(sections)

    @classmethod
    def _extract_progress(cls, text: str, reported: set) -> list[str]:
        messages = []
        if "name" not in reported:
            m = re.search(r'"name"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("name")
                messages.append(f"Hook: {m.group(1)}")
        if "event" not in reported:
            m = re.search(r'"event"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("event")
                messages.append(f"Event: {m.group(1)}")
        if "description" not in reported:
            m = re.search(r'"description"\s*:\s*"([^"]{10,})"', text)
            if m:
                reported.add("description")
                desc = m.group(1)
                if len(desc) > 120:
                    desc = desc[:120] + "..."
                messages.append(desc)
        return messages

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        warnings = []
        event = config.get("event")
        if event and event not in VALID_EVENTS:
            warnings.append(f"Invalid event '{event}'. Valid: {', '.join(VALID_EVENTS)}")
        if not config.get("name"):
            warnings.append("Missing hook name")
        return config, warnings
