"""Service for generating command configurations using Claude CLI."""

import re

from ..database import get_all_commands
from .base_generation_service import BaseGenerationService


class CommandGenerationService(BaseGenerationService):

    @classmethod
    def _gather_context(cls) -> dict:
        return {"commands": get_all_commands()}

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        commands = context.get("commands", [])
        sections = [
            "You are a slash command configuration generator for an AI agent platform called Agented.",
            "Commands are slash commands that users can invoke. They have a name (prefixed with /), a description, content (the prompt/instructions), and optional arguments.",
        ]

        if commands:
            cmd_lines = [
                f"  - name: {c.get('name')}, description: {c.get('description', 'N/A')}"
                for c in commands
            ]
            sections.append("Existing commands:\n" + "\n".join(cmd_lines))

        sections.append(
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "name": "command-name",\n'
            '  "description": "What this command does",\n'
            '  "content": "The command prompt/instructions content",\n'
            '  "arguments": "[{\\"name\\": \\"arg1\\", \\"type\\": \\"string\\", \\"description\\": \\"...\\"}, ...]"\n'
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
                messages.append(f"Command: {m.group(1)}")
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
        if not config.get("name"):
            warnings.append("Missing command name")
        return config, warnings
