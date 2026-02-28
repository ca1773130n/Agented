"""Project chat service for AI-managed kanban board via natural language.

Bridges the super agent session system with plan CRUD operations.
The AI responds in natural language and embeds structured action markers
that this service parses and executes against the plan database.
"""

import json
import logging
import re
from typing import Optional

from ..database import (
    add_project_plan,
    delete_project_plan,
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_project_plan,
    update_project_plan,
)

logger = logging.getLogger(__name__)

# Regex to extract action markers from AI response text
_ACTION_PATTERN = re.compile(
    r"---PLAN_ACTION---\s*\n(.*?)\n\s*---END_PLAN_ACTION---",
    re.DOTALL,
)


def build_project_context(project_id: str, milestone_id: Optional[str] = None) -> str:
    """Assemble current project state into a system prompt section.

    Includes all phases and plans with their IDs and statuses so the AI
    can reference them when creating action markers.
    """
    milestones = get_milestones_by_project(project_id)
    if not milestones:
        return "No milestones found for this project."

    target_milestones = milestones
    if milestone_id:
        target_milestones = [m for m in milestones if m["id"] == milestone_id]

    lines = ["## Current Project State\n"]
    for ms in target_milestones:
        lines.append(f"### Milestone: {ms.get('title', ms['id'])} ({ms.get('version', '?')})")
        phases = get_phases_by_milestone(ms["id"])
        if not phases:
            lines.append("  (no phases)")
            continue
        for phase in phases:
            lines.append(
                f"\n**Phase {phase['phase_number']}: {phase['name']}** "
                f"(id: `{phase['id']}`, status: {phase.get('status', '?')})"
            )
            plans = get_plans_by_phase(phase["id"])
            if not plans:
                lines.append("  - (no plans)")
            else:
                for plan in plans:
                    lines.append(f"  - [{plan['status']}] **{plan['title']}** (id: `{plan['id']}`)")
        lines.append("")

    return "\n".join(lines)


def parse_plan_actions(response_text: str) -> list[dict]:
    """Detect ---PLAN_ACTION--- markers in AI response text.

    Returns a list of parsed action dicts, skipping any that fail JSON parsing.
    """
    actions = []
    for match in _ACTION_PATTERN.finditer(response_text):
        raw = match.group(1).strip()
        try:
            action = json.loads(raw)
            if isinstance(action, dict) and "action" in action:
                actions.append(action)
        except json.JSONDecodeError:
            logger.warning("Failed to parse plan action JSON: %s", raw[:200])
    return actions


def execute_plan_action(project_id: str, action: dict) -> Optional[dict]:
    """Execute a single plan action against the DB.

    Returns a result dict on success, None on failure.
    """
    action_type = action.get("action")

    if action_type == "create":
        phase_id = action.get("phase_id")
        title = action.get("title")
        if not phase_id or not title:
            logger.warning("create action missing phase_id or title: %s", action)
            return None

        existing = get_plans_by_phase(phase_id)
        plan_number = max((p["plan_number"] for p in existing), default=0) + 1

        plan_id = add_project_plan(
            phase_id=phase_id,
            plan_number=plan_number,
            title=title,
            description=action.get("description"),
            tasks_json=action.get("tasks_json"),
        )
        if not plan_id:
            return None

        status = action.get("status", "pending")
        if status != "pending":
            update_project_plan(plan_id, status=status)

        return {"action": "create", "plan_id": plan_id, "title": title}

    elif action_type == "update":
        plan_id = action.get("plan_id")
        if not plan_id:
            return None

        kwargs = {}
        for field in ("title", "description", "status", "tasks_json"):
            if field in action and action[field] is not None:
                kwargs[field] = action[field]

        if kwargs:
            update_project_plan(plan_id, **kwargs)

        return {"action": "update", "plan_id": plan_id, "fields": list(kwargs.keys())}

    elif action_type == "move":
        plan_id = action.get("plan_id")
        new_status = action.get("status")
        if not plan_id or not new_status:
            return None

        update_project_plan(plan_id, status=new_status)
        return {"action": "move", "plan_id": plan_id, "status": new_status}

    elif action_type == "delete":
        plan_id = action.get("plan_id")
        if not plan_id:
            return None

        plan = get_project_plan(plan_id)
        title = plan["title"] if plan else "unknown"
        if delete_project_plan(plan_id):
            return {"action": "delete", "plan_id": plan_id, "title": title}
        return None

    else:
        logger.warning("Unknown plan action type: %s", action_type)
        return None


def execute_plan_actions(project_id: str, response_text: str) -> list[dict]:
    """Parse and execute all plan actions found in AI response text.

    Returns list of successfully executed action results.
    """
    actions = parse_plan_actions(response_text)
    results = []
    for action in actions:
        result = execute_plan_action(project_id, action)
        if result:
            results.append(result)
    return results
