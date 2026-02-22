"""Service for generating plugin configurations using Claude CLI."""

import re

from ..database import get_all_plugins
from .base_generation_service import BaseGenerationService


class PluginGenerationService(BaseGenerationService):

    @classmethod
    def _gather_context(cls) -> dict:
        return {"plugins": get_all_plugins()}

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        plugins = context.get("plugins", [])
        sections = [
            "You are a plugin configuration generator for an AI agent platform called Hive.",
            "Plugins bundle multiple components together. Component types include: skill, command, hook, rule.",
        ]

        if plugins:
            plugin_lines = [
                f"  - name: {p.get('name')}, description: {p.get('description', 'N/A')}, "
                f"components: {p.get('component_count', 0)}"
                for p in plugins
            ]
            sections.append("Existing plugins:\n" + "\n".join(plugin_lines))

        sections.append(
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "name": "plugin-name",\n'
            '  "description": "What this plugin does",\n'
            '  "version": "1.0.0",\n'
            '  "components": [\n'
            '    {"name": "component-name", "type": "skill|command|hook|rule", '
            '"content": "component content"}\n'
            "  ]\n"
            "}"
        )
        sections.append(f"User's description: {description}")
        return "\n\n".join(sections)

    @classmethod
    def _extract_progress(cls, text: str, reported: set) -> list[str]:
        messages = []
        components_pos = text.find('"components"')

        if "name" not in reported:
            area = text[:components_pos] if components_pos > 0 else text
            m = re.search(r'"name"\s*:\s*"([^"]+)"', area)
            if m:
                reported.add("name")
                messages.append(f"Plugin: {m.group(1)}")

        if "description" not in reported:
            m = re.search(r'"description"\s*:\s*"([^"]{10,})"', text)
            if m:
                reported.add("description")
                desc = m.group(1)
                if len(desc) > 120:
                    desc = desc[:120] + "..."
                messages.append(desc)

        if components_pos > 0:
            comp_text = text[components_pos:]
            for m in re.finditer(r'"name"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"([^"]+)"', comp_text):
                key = f"comp_{m.group(1)}"
                if key not in reported:
                    reported.add(key)
                    messages.append(f"  + {m.group(2).capitalize()}: {m.group(1)}")

        return messages

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        warnings = []
        if not config.get("name"):
            warnings.append("Missing plugin name")
        valid_types = {"skill", "command", "hook", "rule"}
        for comp in config.get("components", []):
            if comp.get("type") not in valid_types:
                warnings.append(
                    f"Component '{comp.get('name')}' has invalid type '{comp.get('type')}'"
                )
        return config, warnings
