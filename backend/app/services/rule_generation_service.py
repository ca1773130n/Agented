"""Service for generating rule configurations using Claude CLI."""

import re

from ..database import get_all_rules
from .base_generation_service import BaseGenerationService

VALID_RULE_TYPES = ["pre_check", "post_check", "validation"]


class RuleGenerationService(BaseGenerationService):

    @classmethod
    def _gather_context(cls) -> dict:
        return {"rules": get_all_rules()}

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        rules = context.get("rules", [])
        sections = [
            "You are a rule configuration generator for an AI agent platform called Agented.",
            f"Valid rule types: {', '.join(VALID_RULE_TYPES)}",
            "Rules define conditions and actions. A 'condition' is the check/trigger, and 'action' is what happens when the condition is met.",
        ]

        if rules:
            rule_lines = [
                f"  - name: {r.get('name')}, type: {r.get('rule_type')}, description: {r.get('description', 'N/A')}"
                for r in rules
            ]
            sections.append("Existing rules:\n" + "\n".join(rule_lines))

        sections.append(
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "name": "rule-name",\n'
            '  "rule_type": "pre_check|post_check|validation",\n'
            '  "description": "What this rule does",\n'
            '  "condition": "The condition to check",\n'
            '  "action": "The action to take when condition is met"\n'
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
                messages.append(f"Rule: {m.group(1)}")
        if "rule_type" not in reported:
            m = re.search(r'"rule_type"\s*:\s*"([^"]+)"', text)
            if m:
                reported.add("rule_type")
                messages.append(f"Type: {m.group(1)}")
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
        rule_type = config.get("rule_type")
        if rule_type and rule_type not in VALID_RULE_TYPES:
            warnings.append(
                f"Invalid rule type '{rule_type}'. Valid: {', '.join(VALID_RULE_TYPES)}"
            )
        if not config.get("name"):
            warnings.append("Missing rule name")
        return config, warnings
