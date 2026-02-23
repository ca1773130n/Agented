"""Plugin format utilities for converting Agented entities to Claude Code plugin files.

All functions are pure -- they transform data structures without making DB calls.
"""

import hashlib
import json
import re
from typing import Optional

import yaml


def _slugify(name: str) -> str:
    """Convert a name to kebab-case for file names.

    Lowercase, replace spaces/underscores with hyphens, strip non-alphanumeric except hyphens,
    collapse multiple hyphens.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "unnamed"


def content_hash(content: str) -> str:
    """Generate SHA-256 hash of content for sync tracking."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def generate_agent_md(agent: dict) -> str:
    """Convert a Agented agent dict to Claude Code agent .md format.

    YAML frontmatter with name (kebab-case) and description.
    Body from system_prompt or role.
    Includes ## Goals section if agent has goals (JSON-parsed list).
    Includes ## Context section if agent has context.
    """
    name = _slugify(agent.get("name", "unnamed"))
    description = agent.get("description", "") or ""

    frontmatter = {"name": name, "description": description}
    body_parts = []

    # Main body from system_prompt or role
    system_prompt = agent.get("system_prompt") or ""
    role = agent.get("role") or ""
    main_body = system_prompt or role
    if main_body:
        body_parts.append(main_body)

    # Goals section
    goals_raw = agent.get("goals")
    if goals_raw:
        goals_list = _parse_json_or_string(goals_raw)
        if goals_list and isinstance(goals_list, list):
            goals_section = "## Goals\n\n"
            for goal in goals_list:
                goals_section += f"- {goal}\n"
            body_parts.append(goals_section)

    # Context section
    context = agent.get("context")
    if context:
        body_parts.append(f"## Context\n\n{context}")

    body = "\n\n".join(body_parts) if body_parts else ""
    return _render_frontmatter_md(frontmatter, body)


def generate_skill_md(skill: dict) -> str:
    """Convert a Agented skill dict to Claude Code SKILL.md format.

    YAML frontmatter with description. Body from content or description.
    """
    description = skill.get("description", "") or ""
    frontmatter = {"description": description}

    body = skill.get("content") or skill.get("description") or ""
    return _render_frontmatter_md(frontmatter, body)


def generate_command_md(command: dict) -> str:
    """Convert a Agented command dict to Claude Code command .md format.

    YAML frontmatter with description. If arguments exists (JSON string),
    parse and add as parameters in frontmatter. Body from content.
    """
    description = command.get("description", "") or ""
    frontmatter = {"description": description}

    # Parse arguments as parameters
    arguments_raw = command.get("arguments")
    if arguments_raw:
        parsed = _parse_json_or_string(arguments_raw)
        if parsed and isinstance(parsed, (list, dict)):
            frontmatter["parameters"] = parsed

    body = command.get("content") or ""
    return _render_frontmatter_md(frontmatter, body)


def generate_hooks_json(hooks: list, rules: list) -> tuple:
    """Convert Agented hooks and rules to Claude Code hooks.json format + scripts dict.

    Maps hooks by their event field.
    Maps rules: pre_check -> PreToolUse, post_check -> PostToolUse, validation -> PreToolUse.
    Returns (hooks_config_dict, scripts_dict) where scripts_dict maps filename -> script content.
    Uses ${CLAUDE_PLUGIN_ROOT}/scripts/ prefix for hook commands.
    """
    hooks_config = {"hooks": []}
    scripts = {}

    # Map hooks
    for hook in hooks:
        hook_name = _slugify(hook.get("name", "hook"))
        event = hook.get("event", "")
        content = hook.get("content") or ""

        # Determine script filename
        script_name = f"{hook_name}.sh"
        script_path = f"${{CLAUDE_PLUGIN_ROOT}}/scripts/{script_name}"

        hook_entry = {
            "event": event,
            "command": script_path,
        }
        if hook.get("description"):
            hook_entry["description"] = hook["description"]

        hooks_config["hooks"].append(hook_entry)
        scripts[script_name] = _wrap_script(content)

    # Map rules to hooks
    rule_type_map = {
        "pre_check": "PreToolUse",
        "post_check": "PostToolUse",
        "validation": "PreToolUse",
    }
    for rule in rules:
        rule_name = _slugify(rule.get("name", "rule"))
        rule_type = rule.get("rule_type", "validation")
        event = rule_type_map.get(rule_type, "PreToolUse")

        script_name = f"{rule_name}.sh"
        script_path = f"${{CLAUDE_PLUGIN_ROOT}}/scripts/{script_name}"

        hook_entry = {
            "event": event,
            "command": script_path,
        }
        if rule.get("description"):
            hook_entry["description"] = rule["description"]

        hooks_config["hooks"].append(hook_entry)
        scripts[script_name] = generate_rule_script(rule)

    return hooks_config, scripts


def generate_rule_script(rule: dict) -> str:
    """Generate a shell script from a Agented rule with condition/action as script body."""
    name = rule.get("name", "unnamed-rule")
    description = rule.get("description") or ""
    condition = rule.get("condition") or ""
    action = rule.get("action") or ""

    lines = ["#!/bin/bash", f"# Rule: {name}"]
    if description:
        lines.append(f"# {description}")
    lines.append("")

    if condition:
        lines.append("# Condition check")
        lines.append(condition)
        lines.append("")

    if action:
        lines.append("# Action")
        lines.append(action)

    return "\n".join(lines) + "\n"


def generate_plugin_manifest(
    team: dict,
    agents: list,
    skills: list,
    commands: list,
    hooks: list,
) -> dict:
    """Generate plugin.json manifest for a Claude Code plugin.

    Only includes component paths if those component lists are non-empty.
    """
    name = _slugify(team.get("name", "unnamed-plugin"))
    manifest = {
        "name": name,
        "version": "1.0.0",
        "description": team.get("description")
        or f"Plugin generated from team: {team.get('name', '')}",
        "author": "Agented",
        "keywords": ["agented-generated"],
    }

    components = {}
    if agents:
        components["agents"] = [f"agents/{_slugify(a.get('name', 'agent'))}.md" for a in agents]
    if skills:
        components["skills"] = [
            f"skills/{_slugify(s.get('skill_name', s.get('name', 'skill')))}/SKILL.md"
            for s in skills
        ]
    if commands:
        components["commands"] = [
            f"commands/{_slugify(c.get('name', 'command'))}.md" for c in commands
        ]
    if hooks:
        components["hooks"] = "hooks/hooks.json"

    if components:
        manifest["components"] = components

    return manifest


def generate_agented_manifest(
    team: dict,
    members: list,
    assignments: list,
    agents: list,
    skills: list,
    commands: list,
    hooks: list,
    rules: list,
) -> dict:
    """Generate agented.json with full team config including topology, trigger config, all entity data.

    This is the standalone Agented package format that can be imported back into a Agented instance.
    """
    manifest = {
        "agented_version": "1.0.0",
        "format": "agented-package",
        "team": {
            "name": team.get("name", ""),
            "description": team.get("description") or "",
            "topology": team.get("topology"),
            "topology_config": _parse_json_or_string(team.get("topology_config")),
            "trigger_source": team.get("trigger_source"),
            "trigger_config": _parse_json_or_string(team.get("trigger_config")),
        },
        "members": [
            {
                "name": m.get("name", ""),
                "role": m.get("role", "member"),
                "layer": m.get("layer", "backend"),
                "agent_id": m.get("agent_id"),
            }
            for m in members
        ],
        "assignments": [
            {
                "agent_id": a.get("agent_id", ""),
                "entity_type": a.get("entity_type", ""),
                "entity_id": str(a.get("entity_id", "")),
                "entity_name": a.get("entity_name"),
            }
            for a in assignments
        ],
        "entities": {},
    }

    if agents:
        manifest["entities"]["agents"] = [
            {
                "name": a.get("name", ""),
                "description": a.get("description") or "",
                "role": a.get("role") or "",
                "goals": _parse_json_or_string(a.get("goals")),
                "context": a.get("context") or "",
                "system_prompt": a.get("system_prompt") or "",
                "backend_type": a.get("backend_type", "claude"),
                "model": a.get("model"),
            }
            for a in agents
        ]

    if skills:
        manifest["entities"]["skills"] = [
            {
                "name": s.get("skill_name", s.get("name", "")),
                "description": s.get("description") or "",
                "content": s.get("content") or s.get("metadata") or "",
            }
            for s in skills
        ]

    if commands:
        manifest["entities"]["commands"] = [
            {
                "name": c.get("name", ""),
                "description": c.get("description") or "",
                "content": c.get("content") or "",
                "arguments": _parse_json_or_string(c.get("arguments")),
            }
            for c in commands
        ]

    if hooks:
        manifest["entities"]["hooks"] = [
            {
                "name": h.get("name", ""),
                "event": h.get("event", ""),
                "description": h.get("description") or "",
                "content": h.get("content") or "",
            }
            for h in hooks
        ]

    if rules:
        manifest["entities"]["rules"] = [
            {
                "name": r.get("name", ""),
                "rule_type": r.get("rule_type", "validation"),
                "description": r.get("description") or "",
                "condition": r.get("condition") or "",
                "action": r.get("action") or "",
            }
            for r in rules
        ]

    return manifest


def parse_yaml_frontmatter(content: str) -> tuple:
    """Parse a markdown file with YAML frontmatter delimited by ---.

    Returns (frontmatter_dict, body_string).
    Handles missing frontmatter gracefully (returns empty dict + full content).
    """
    if not content or not content.strip().startswith("---"):
        return {}, content or ""

    # Find the closing ---
    lines = content.split("\n")
    if len(lines) < 2:
        return {}, content

    # Skip the opening ---
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, content

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :]).strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return {}, content

    return frontmatter, body


# --- Internal helpers ---


def _render_frontmatter_md(frontmatter: dict, body: str) -> str:
    """Render a dict as YAML frontmatter + markdown body."""
    fm_text = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    parts = [f"---\n{fm_text}\n---"]
    if body:
        parts.append(body.strip())
    return "\n\n".join(parts) + "\n"


def _parse_json_or_string(value) -> Optional[any]:
    """Attempt to parse a JSON string; return parsed object or original value."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _wrap_script(content: str) -> str:
    """Wrap content as a bash script with shebang."""
    if content.startswith("#!/"):
        return content if content.endswith("\n") else content + "\n"
    return f"#!/bin/bash\n\n{content}\n"
