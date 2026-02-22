"""Service for generating team configurations from natural language using Claude CLI."""

import logging
import re
import subprocess

from ..database import (
    get_agent,
    get_all_agents,
    get_all_commands,
    get_all_hooks,
    get_all_rules,
    get_all_user_skills,
)
from ..models.team import VALID_TOPOLOGIES
from .base_generation_service import BaseGenerationService

logger = logging.getLogger(__name__)


class TeamGenerationService(BaseGenerationService):
    """Service for generating team configurations using Claude CLI."""

    SUBPROCESS_TIMEOUT = 120

    @classmethod
    def generate(cls, description: str) -> dict:
        """Sync generation (non-streaming). Kept for backward compatibility."""
        context = cls._gather_context()
        prompt = cls._build_prompt(description, context)

        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=cls.SUBPROCESS_TIMEOUT,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Claude CLI not found. Please install the Claude CLI to use team generation."
            )

        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error("Claude CLI error: %s, stderr: %s", result.returncode, stderr)

        stdout = result.stdout.strip() if result.stdout else ""
        if not stdout:
            raise RuntimeError("Claude CLI returned empty output. Please try again.")

        config = cls._parse_json(stdout)
        config, warnings = cls._validate(config)

        return {"config": config, "warnings": warnings}

    @classmethod
    def _gather_context(cls) -> dict:
        return {
            "agents": get_all_agents(),
            "skills": get_all_user_skills(),
            "commands": get_all_commands(),
            "hooks": get_all_hooks(),
            "rules": get_all_rules(),
        }

    @classmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        agents = context.get("agents", [])
        skills = context.get("skills", [])
        commands = context.get("commands", [])
        hooks = context.get("hooks", [])
        rules = context.get("rules", [])

        sections = []

        sections.append(
            "You are a team configuration generator for an AI agent platform called Hive."
        )
        sections.append(
            "Given the user's description, create a team configuration.\n\n"
            "IMPORTANT RULES:\n"
            "1. For agents: Use existing agent IDs from the 'Available agents' list when they match the needed role. "
            "Only use agent_id: null for genuinely new roles not covered by existing agents.\n"
            "2. For assignments: Use EXACT entity_id values from the 'Available skills/commands/hooks/rules' lists when possible. "
            "Only invent new skill names when no existing skill covers the needed capability.\n"
            "3. When inventing new skill names, make them SPECIFIC and ROLE-ORIENTED. "
            "Bad: 'performance-optimization', 'code-analysis', 'testing'. "
            "Good: 'vue-component-performance-profiler', 'python-static-code-analyzer', 'api-integration-test-runner'. "
            "Each name should clearly indicate: what domain/technology it targets, what action it performs, and for what purpose."
        )

        if agents:
            agent_lines = []
            for a in agents:
                agent_skills = a.get("skills", "")
                agent_lines.append(
                    f"  - id: {a['id']}, name: {a['name']}, role: {a.get('role', 'N/A')}, skills: {agent_skills}"
                )
            sections.append("Available agents:\n" + "\n".join(agent_lines))
        else:
            sections.append(
                "Available agents: None (you may suggest new agents with agent_id: null)"
            )

        if skills:
            skill_lines = [
                f"  - entity_id: {s.get('skill_name', s.get('name', 'unknown'))}, description: {s.get('description', 'N/A')}"
                for s in skills
            ]
            sections.append(
                "Available skills (use the exact entity_id value for assignments):\n"
                + "\n".join(skill_lines)
            )
        else:
            sections.append(
                "Available skills: None (you may suggest new skills with specific, role-oriented names)"
            )

        if commands:
            cmd_lines = [
                f"  - id: {c.get('id')}, name: {c.get('name', 'unknown')}, description: {c.get('description', 'N/A')}"
                for c in commands
            ]
            sections.append("Available commands:\n" + "\n".join(cmd_lines))

        if hooks:
            hook_lines = [
                f"  - id: {h.get('id')}, name: {h.get('name', 'unknown')}, event: {h.get('event', 'N/A')}"
                for h in hooks
            ]
            sections.append("Available hooks:\n" + "\n".join(hook_lines))

        if rules:
            rule_lines = [
                f"  - id: {r.get('id')}, name: {r.get('name', 'unknown')}, type: {r.get('rule_type', 'N/A')}"
                for r in rules
            ]
            sections.append("Available rules:\n" + "\n".join(rule_lines))

        sections.append(
            "Topology patterns:\n"
            "  - sequential: Pipeline execution, agents run in order\n"
            "  - parallel: Fan-out execution, agents run simultaneously\n"
            "  - coordinator: Hub-spoke, coordinator delegates to workers\n"
            "  - generator_critic: Iterative improvement between generator and critic"
        )

        sections.append(
            "Respond with ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "name": "Team Name",\n'
            '  "description": "Team description",\n'
            '  "topology": "sequential|parallel|coordinator|generator_critic",\n'
            '  "topology_config": { ... },\n'
            '  "color": "#hexcolor",\n'
            '  "agents": [\n'
            "    {\n"
            '      "agent_id": "agent-xxx or null if new",\n'
            '      "name": "Agent name",\n'
            '      "role": "Role description",\n'
            '      "assignments": [\n'
            '        {"entity_type": "skill", "entity_id": "exact-skill-name-from-available-list-or-new-specific-name", "entity_name": "Display Name"}\n'
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        sections.append(
            "If the user describes agents that don't exist, use agent_id: null and provide a suggested name and role."
        )

        sections.append(f"User's description: {description}")

        return "\n\n".join(sections)

    @classmethod
    def _extract_progress(cls, text: str, reported: set) -> list[str]:
        messages = []
        agents_pos = text.find('"agents"')

        if "team_name" not in reported:
            area = text[:agents_pos] if agents_pos > 0 else text
            m = re.search(r'"name"\s*:\s*"([^"]+)"', area)
            if m:
                reported.add("team_name")
                messages.append(f"Team: {m.group(1)}")

        if "description" not in reported:
            m = re.search(r'"description"\s*:\s*"([^"]{10,})"', text)
            if m:
                reported.add("description")
                desc = m.group(1)
                if len(desc) > 120:
                    desc = desc[:120] + "..."
                messages.append(desc)

        if "topology" not in reported:
            m = re.search(
                r'"topology"\s*:\s*"(sequential|parallel|coordinator|generator_critic)"', text
            )
            if m:
                reported.add("topology")
                messages.append(f"Topology: {m.group(1)}")

        if "color" not in reported:
            m = re.search(r'"color"\s*:\s*"(#[0-9a-fA-F]{3,8})"', text)
            if m:
                reported.add("color")
                messages.append(f"Color: {m.group(1)}")

        if agents_pos > 0:
            agents_text = text[agents_pos:]

            for m in re.finditer(r'"name"\s*:\s*"([^"]+)"', agents_text):
                key = f"agent_{m.group(1)}"
                if key not in reported:
                    reported.add(key)
                    messages.append(f"Agent: {m.group(1)}")

            for m in re.finditer(r'"role"\s*:\s*"([^"]+)"', agents_text):
                key = f"role_{m.start()}"
                if key not in reported:
                    reported.add(key)
                    role = m.group(1)
                    if len(role) > 100:
                        role = role[:100] + "..."
                    messages.append(f"  Role: {role}")

            for m in re.finditer(
                r'"entity_type"\s*:\s*"([^"]+)"\s*,\s*"entity_id"\s*:\s*"([^"]+)"'
                r'\s*,\s*"entity_name"\s*:\s*"([^"]+)"',
                agents_text,
            ):
                key = f"assign_{m.group(2)}"
                if key not in reported:
                    reported.add(key)
                    messages.append(f"  + {m.group(1).capitalize()}: {m.group(3)}")

        return messages

    @classmethod
    def _validate(cls, config: dict) -> tuple:
        warnings = []

        topology = config.get("topology")
        if topology and topology not in VALID_TOPOLOGIES:
            warnings.append(
                f"Invalid topology '{topology}'. Valid options: {', '.join(VALID_TOPOLOGIES)}"
            )

        for agent_cfg in config.get("agents", []):
            agent_id = agent_cfg.get("agent_id")

            if agent_id is not None:
                existing = get_agent(agent_id)
                if existing:
                    agent_cfg["valid"] = True
                else:
                    agent_cfg["valid"] = False
                    warnings.append(f"Agent '{agent_id}' not found in the system")
            else:
                agent_cfg["valid"] = True

            for assignment in agent_cfg.get("assignments", []):
                entity_type = assignment.get("entity_type")
                entity_id = assignment.get("entity_id")

                if entity_type and entity_id:
                    exists = cls._entity_exists(entity_type, entity_id)
                    assignment["valid"] = True
                    if not exists:
                        assignment["needs_creation"] = True
                        warnings.append(f"{entity_type.capitalize()} '{entity_id}' will be created")
                    else:
                        assignment["needs_creation"] = False
                else:
                    assignment["valid"] = False
                    assignment["needs_creation"] = False
                    warnings.append("Assignment missing entity_type or entity_id")

        return config, warnings

    @classmethod
    def _entity_exists(cls, entity_type: str, entity_id: str) -> bool:
        try:
            if entity_type == "skill":
                from ..database import get_all_user_skills

                skills = get_all_user_skills()
                return any(
                    str(s.get("id")) == str(entity_id) or s.get("skill_name") == entity_id
                    for s in skills
                )
            elif entity_type == "command":
                from ..database import get_all_commands

                commands = get_all_commands()
                return any(
                    str(c.get("id")) == str(entity_id) or c.get("name") == entity_id
                    for c in commands
                )
            elif entity_type == "hook":
                from ..database import get_all_hooks

                hooks = get_all_hooks()
                return any(
                    str(h.get("id")) == str(entity_id) or h.get("name") == entity_id for h in hooks
                )
            elif entity_type == "rule":
                from ..database import get_all_rules

                rules = get_all_rules()
                return any(
                    str(r.get("id")) == str(entity_id) or r.get("name") == entity_id for r in rules
                )
        except Exception:
            pass
        return False
