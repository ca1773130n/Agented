"""Sketch execution service.

Bridges sketch routing to actual LLM execution on super agent sessions.
"""

import json
import logging
import re
from typing import Optional

from ..db.connection import get_connection
from ..db.sketches import get_sketch, update_sketch
from ..db.super_agents import get_super_agent
from .agent_message_bus_service import AgentMessageBusService
from .streaming_helper import run_streaming_response
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


def find_team_super_agent(team_id: str) -> Optional[str]:
    """Find the best super agent in a team. Prefers role='leader'.

    Returns super_agent_id or None if no super agent members exist.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT super_agent_id, role FROM team_members "
            "WHERE team_id = ? AND super_agent_id IS NOT NULL "
            "ORDER BY CASE WHEN role = 'leader' THEN 0 ELSE 1 END",
            (team_id,),
        ).fetchall()
    if not rows:
        return None
    return rows[0]["super_agent_id"]


def get_team_context(team_id: str) -> dict:
    """Query team_members table for all super agents in the team.

    Returns a dict with team_id and a list of member dicts.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT tm.super_agent_id, tm.name, tm.role, tm.layer, tm.description,
                   sa.name as agent_name
            FROM team_members tm
            JOIN super_agents sa ON tm.super_agent_id = sa.id
            WHERE tm.team_id = ? AND tm.super_agent_id IS NOT NULL
            """,
            (team_id,),
        ).fetchall()

    members = []
    for row in rows:
        members.append(
            {
                "super_agent_id": row["super_agent_id"],
                "name": row["name"],
                "role": row["role"],
                "layer": row["layer"],
                "description": row["description"],
            }
        )

    return {"team_id": team_id, "members": members}


def _build_team_context_preamble(team_context: dict) -> str:
    """Build the team context preamble string to prepend to sketch content."""
    lines = [
        "[TEAM CONTEXT]",
        "You are the team leader. Your team members are:",
    ]
    for member in team_context["members"]:
        name = member.get("name") or member.get("super_agent_id")
        role = member.get("role") or "member"
        layer = member.get("layer") or ""
        description = member.get("description") or ""
        lines.append(f"- {name} (role: {role}, layer: {layer}) — {description}")
    lines.append(
        "To delegate work to a team member, mention them with @Name and describe their task."
    )
    lines.append(
        "The system will automatically send your instructions via mailbox and start their session."
    )
    lines.append("[END TEAM CONTEXT]")
    return "\n".join(lines)


def execute_sketch(
    sketch_id: str, super_agent_id: str, content: str, team_id: Optional[str] = None
) -> str:
    """Execute a routed sketch on a super agent session.

    Sets status to 'in_progress' before launching the background thread
    to prevent race conditions. When team_id is provided, prepends team
    context and processes delegations after completion.

    When ``super_agent_id`` starts with ``psa-``, the instance's template SA
    is used for backend detection, its ``worktree_path`` is passed as cwd,
    and the template SA ID is used for session management.

    Returns session_id.
    """
    # 1. Set status before launching thread
    update_sketch(sketch_id, status="in_progress")

    # 2. Resolve backend — handle project SA instances (psa-) vs global SAs
    cwd: Optional[str] = None
    instance_id: Optional[str] = None
    project_id: Optional[str] = None
    if super_agent_id.startswith("psa-"):
        from ..db.project_sa_instances import get_project_sa_instance

        instance = get_project_sa_instance(super_agent_id)
        if instance:
            sa = get_super_agent(instance["template_sa_id"])
            backend = (sa.get("backend_type") if sa else None) or "claude"
            instance_id = super_agent_id
            project_id = instance.get("project_id")
            # Use template SA ID for session management
            effective_sa_id = instance["template_sa_id"]
        else:
            # Instance not found — fall back to treating as regular SA ID
            sa = get_super_agent(super_agent_id)
            backend = (sa.get("backend_type") if sa else None) or "claude"
            effective_sa_id = super_agent_id
    else:
        sa = get_super_agent(super_agent_id)
        backend = (sa.get("backend_type") if sa else None) or "claude"
        effective_sa_id = super_agent_id

    # 3. Create session — use session-per-worktree for project instances
    if project_id and instance_id:
        from .instance_service import InstanceService

        title = content[:100] if content else "Sketch task"
        result = InstanceService.create_session_worktree(
            project_id=project_id,
            super_agent_id=effective_sa_id,
            instance_id=instance_id,
            title=title,
        )
        if result:
            session_id = result["session_id"]
            cwd = result.get("worktree_path")
        else:
            session_id = SuperAgentSessionService.get_or_create_session(effective_sa_id)
            cwd = instance.get("worktree_path") if instance else None
    else:
        session_id = SuperAgentSessionService.get_or_create_session(effective_sa_id)

    # 4. Build content — prepend team context if team_id provided
    team_context = None
    if team_id:
        team_context = get_team_context(team_id)
        if team_context["members"]:
            preamble = _build_team_context_preamble(team_context)
            content = preamble + "\n\n" + content

        # Store team_id in routing_json
        sketch = get_sketch(sketch_id)
        existing_routing = {}
        if sketch and sketch.get("routing_json"):
            try:
                existing_routing = json.loads(sketch["routing_json"])
            except (json.JSONDecodeError, TypeError):
                existing_routing = {}
        existing_routing["team_id"] = team_id
        existing_routing["delegations"] = []
        update_sketch(sketch_id, routing_json=json.dumps(existing_routing))

    # 5. Persist user message to session
    SuperAgentSessionService.send_message(session_id, content)

    # 6. Launch streaming with sketch status callbacks
    captured_team_context = team_context
    captured_session_id = session_id

    def _on_complete():
        if captured_team_context and captured_team_context["members"]:
            # Read the leader's response from the session conversation log
            state = SuperAgentSessionService.get_session_state(captured_session_id)
            leader_response = ""
            if state and state.get("conversation_log"):
                last_msg = state["conversation_log"][-1]
                if last_msg.get("role") == "assistant":
                    leader_response = last_msg["content"]

            if leader_response:
                process_delegations(
                    sketch_id, super_agent_id, leader_response, captured_team_context
                )
                # process_delegations will handle status updates
                return

        # Solo superagent: scan response for @mentions and send mailbox messages
        state = SuperAgentSessionService.get_session_state(captured_session_id)
        if state and state.get("conversation_log"):
            last_msg = state["conversation_log"][-1]
            if last_msg.get("role") == "assistant" and last_msg.get("content"):
                _scan_mentions_and_notify(sketch_id, super_agent_id, last_msg["content"])

        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s completed successfully", sketch_id)

    def _on_error(error_msg):
        update_sketch(sketch_id, status="classified")
        logger.error("Sketch %s failed: %s", sketch_id, error_msg)
        from app.services.error_capture import capture_error

        capture_error(
            category="streaming_error",
            message=error_msg,
            context={"sketch_id": sketch_id, "super_agent_id": super_agent_id},
        )

    run_streaming_response(
        session_id=session_id,
        super_agent_id=effective_sa_id,
        backend=backend,
        on_complete=_on_complete,
        on_error=_on_error,
        cwd=cwd,
        chat_mode="work" if cwd else None,
        instance_id=instance_id,
    )

    return session_id


def _scan_mentions_and_notify(sketch_id: str, from_agent_id: str, response_text: str) -> None:
    """Scan a solo superagent's response for agent references and send mailbox messages.

    Scans for both @Name mentions and agent names appearing in task assignment
    contexts (e.g. table rows, bullet points with agent names bolded).
    Extracts the surrounding context as the task content for the mail.
    """
    from ..db.super_agents import get_all_super_agents

    all_agents = get_all_super_agents()
    agent_by_name: dict[str, dict] = {}
    for sa in all_agents:
        if sa["id"] == from_agent_id:
            continue
        name = sa.get("name") or ""
        if name and name.lower() != "system":
            agent_by_name[name.lower()] = sa

    if not agent_by_name:
        return

    sketch = get_sketch(sketch_id)
    sketch_title = (sketch.get("title") if sketch else None) or sketch_id

    # Collect tasks per agent (dedup by agent ID)
    agent_tasks: dict[str, list[str]] = {}

    # Strategy 1: @Name mentions with content
    at_pattern = re.compile(r"@(\w+)[\s\u2014\-:]+(.+?)(?=@\w+|$)", re.DOTALL)
    for name, content in at_pattern.findall(response_text):
        agent = agent_by_name.get(name.lower())
        if agent:
            agent_tasks.setdefault(agent["id"], []).append(content.strip())

    # Strategy 2: Table rows with agent names (e.g. "| Task | **Name** | P0 |")
    # Matches: | description | **AgentName** | priority |
    # Also: | description | AgentName | priority |
    table_pattern = re.compile(
        r"\|([^|]+)\|\s*\*{0,2}("
        + "|".join(re.escape(n) for n in agent_by_name)
        + r")\*{0,2}\s*\|([^|]*)\|",
        re.IGNORECASE,
    )
    for task_text, name, extra in table_pattern.findall(response_text):
        agent = agent_by_name.get(name.strip().lower())
        if agent:
            combined = f"{task_text.strip()} {extra.strip()}".strip()
            agent_tasks.setdefault(agent["id"], []).append(combined)

    # Strategy 3: Lines with bold agent names followed by task description
    # e.g. "- **Seraph**: Deep-dive into Mastra memory source code"
    bold_pattern = re.compile(
        r"[-*]\s*\*{2}("
        + "|".join(re.escape(n) for n in agent_by_name)
        + r")\*{2}\s*[:\u2014\-]+\s*(.+)",
        re.IGNORECASE,
    )
    for name, content in bold_pattern.findall(response_text):
        agent = agent_by_name.get(name.strip().lower())
        if agent:
            agent_tasks.setdefault(agent["id"], []).append(content.strip())

    if not agent_tasks:
        return

    sent = 0
    for agent_id, tasks in agent_tasks.items():
        # Deduplicate and combine tasks
        seen = set()
        unique_tasks = []
        for t in tasks:
            key = t[:100].lower()
            if key not in seen:
                seen.add(key)
                unique_tasks.append(t)

        content = "\n\n".join(f"- {t}" for t in unique_tasks)
        agent = next(sa for sa in all_agents if sa["id"] == agent_id)
        agent_name = agent.get("name") or agent_id

        try:
            AgentMessageBusService.send_message(
                from_agent_id=from_agent_id,
                to_agent_id=agent_id,
                message_type="request",
                priority="high",
                subject=f"Tasks from sketch: {sketch_title}",
                content=f"You have been assigned the following tasks:\n\n{content}",
            )
            sent += 1
            logger.info(
                "Sketch %s: sent %d task(s) to %s (%s)",
                sketch_id,
                len(unique_tasks),
                agent_name,
                agent_id,
            )

            # Auto-execute: send the task as a user message and launch streaming
            try:
                session_id = SuperAgentSessionService.get_or_create_session(agent_id)
                task_prompt = (
                    f"You have received the following task assignment from "
                    f"a sketch research by {from_agent_id}:\n\n{content}\n\n"
                    f"Please work on these tasks now."
                )
                SuperAgentSessionService.send_message(session_id, task_prompt)
                backend = agent.get("backend_type") or "claude"
                run_streaming_response(
                    session_id=session_id,
                    super_agent_id=agent_id,
                    backend=backend,
                )
                logger.info(
                    "Sketch %s: auto-launched session %s for %s",
                    sketch_id,
                    session_id,
                    agent_name,
                )
            except Exception as launch_exc:
                logger.error(
                    "Sketch %s: failed to auto-launch session for %s: %s",
                    sketch_id,
                    agent_id,
                    launch_exc,
                )
        except Exception as exc:
            logger.error(
                "Sketch %s: failed to send mail to %s: %s",
                sketch_id,
                agent_id,
                exc,
            )

    if sent:
        logger.info("Sketch %s: notified %d agents from solo agent response", sketch_id, sent)


def process_delegations(
    sketch_id: str, leader_agent_id: str, leader_response: str, team_context: dict
) -> None:
    """Parse @Name mentions from leader response and delegate tasks to team members.

    Sends mailbox messages and launches delegate sessions for each matched mention.
    """
    # Parse @Name mentions with task content
    pattern = re.compile(r"@(\w+)[\s\u2014\-:]+(.+?)(?=@\w+|$)", re.DOTALL)
    matches = pattern.findall(leader_response)

    if not matches:
        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s completed — no delegations found", sketch_id)
        return

    # Build name-to-member lookup (case-insensitive)
    member_by_name = {}
    for member in team_context["members"]:
        name = member.get("name") or ""
        if name:
            member_by_name[name.lower()] = member

    delegations = []
    matched_members = []

    for name, task_text in matches:
        task_text = task_text.strip()
        member = member_by_name.get(name.lower())
        if not member:
            logger.warning(
                "Sketch %s: @%s does not match any team member — skipping", sketch_id, name
            )
            continue
        delegations.append(
            {
                "super_agent_id": member["super_agent_id"],
                "name": name,
                "task": task_text,
                "status": "pending",
            }
        )
        matched_members.append((member, task_text))

    if not matched_members:
        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s completed — no valid delegation targets", sketch_id)
        return

    # Set sketch to collaborating and store delegation info
    sketch = get_sketch(sketch_id)
    existing_routing = {}
    if sketch and sketch.get("routing_json"):
        try:
            existing_routing = json.loads(sketch["routing_json"])
        except (json.JSONDecodeError, TypeError):
            existing_routing = {}
    existing_routing["delegations"] = delegations
    update_sketch(sketch_id, status="collaborating", routing_json=json.dumps(existing_routing))
    logger.info("Sketch %s — collaborating with %d delegates", sketch_id, len(matched_members))

    # Get sketch title for mailbox subject
    sketch_title = (sketch.get("title") if sketch else None) or sketch_id
    sketch_content = (sketch.get("content") if sketch else None) or ""

    for member, task_text in matched_members:
        member_sa_id = member["super_agent_id"]
        member_name = member.get("name") or member_sa_id

        # Send mailbox message to the delegate
        try:
            AgentMessageBusService.send_message(
                from_agent_id=leader_agent_id,
                to_agent_id=member_sa_id,
                message_type="request",
                priority="high",
                subject=f"Sketch delegation: {sketch_title}",
                content=task_text,
            )
        except Exception as exc:
            logger.error("Sketch %s: failed to send mailbox to %s: %s", sketch_id, member_name, exc)

        # Launch delegate execution
        execute_delegate(
            sketch_id=sketch_id,
            super_agent_id=member_sa_id,
            task_content=task_text,
            leader_agent_id=leader_agent_id,
            sketch_content=sketch_content,
            sketch_title=sketch_title,
        )


def execute_delegate(
    sketch_id: str,
    super_agent_id: str,
    task_content: str,
    leader_agent_id: str,
    sketch_content: str = "",
    sketch_title: str = "",
) -> None:
    """Execute a delegated task on a team member's session.

    Sends the task to the member, launches streaming, and on completion
    sends the response back to the leader via mailbox and updates routing_json.
    """
    try:
        session_id = SuperAgentSessionService.get_or_create_session(super_agent_id)
    except Exception as exc:
        logger.error(
            "Sketch %s: failed to create session for delegate %s: %s",
            sketch_id,
            super_agent_id,
            exc,
        )
        _mark_delegation_status(sketch_id, super_agent_id, "error")
        _check_all_delegations_complete(sketch_id)
        return

    # Build the delegate prompt
    prompt = (
        "[DELEGATION FROM TEAM LEADER]\n"
        "You have been assigned this task by your team leader.\n"
        f"Original sketch: {sketch_content}\n\n"
        "Your specific assignment:\n"
        f"{task_content}\n\n"
        "Complete your task and your response will be sent back to the team leader via mailbox.\n"
        "[END DELEGATION]"
    )

    try:
        SuperAgentSessionService.send_message(session_id, prompt)
    except Exception as exc:
        logger.error(
            "Sketch %s: failed to send message to delegate session %s: %s",
            sketch_id,
            session_id,
            exc,
        )
        _mark_delegation_status(sketch_id, super_agent_id, "error")
        _check_all_delegations_complete(sketch_id)
        return

    sa = get_super_agent(super_agent_id)
    backend = (sa.get("backend_type") if sa else None) or "claude"

    captured_session_id = session_id
    captured_super_agent_id = super_agent_id

    def _on_complete():
        # Read delegate's response
        state = SuperAgentSessionService.get_session_state(captured_session_id)
        delegate_response = ""
        if state and state.get("conversation_log"):
            last_msg = state["conversation_log"][-1]
            if last_msg.get("role") == "assistant":
                delegate_response = last_msg["content"]

        # Send response back to leader via mailbox
        if delegate_response:
            try:
                AgentMessageBusService.send_message(
                    from_agent_id=captured_super_agent_id,
                    to_agent_id=leader_agent_id,
                    message_type="message",
                    priority="normal",
                    subject=f"Delegation completed: {sketch_title}",
                    content=delegate_response,
                )
            except Exception as exc:
                logger.error(
                    "Sketch %s: failed to send completion message from %s to leader: %s",
                    sketch_id,
                    captured_super_agent_id,
                    exc,
                )

        _mark_delegation_status(sketch_id, captured_super_agent_id, "completed")
        _check_all_delegations_complete(sketch_id)

    def _on_error(error_msg):
        logger.error(
            "Sketch %s: delegate %s failed: %s", sketch_id, captured_super_agent_id, error_msg
        )
        _mark_delegation_status(sketch_id, captured_super_agent_id, "error")
        _check_all_delegations_complete(sketch_id)
        from app.services.error_capture import capture_error

        capture_error(
            category="streaming_error",
            message=error_msg,
            context={"sketch_id": sketch_id, "super_agent_id": captured_super_agent_id},
        )

    try:
        run_streaming_response(
            session_id=session_id,
            super_agent_id=super_agent_id,
            backend=backend,
            on_complete=_on_complete,
            on_error=_on_error,
        )
    except Exception as exc:
        logger.error(
            "Sketch %s: failed to start streaming for delegate %s: %s",
            sketch_id,
            super_agent_id,
            exc,
        )
        _mark_delegation_status(sketch_id, super_agent_id, "error")
        _check_all_delegations_complete(sketch_id)


def _mark_delegation_status(sketch_id: str, super_agent_id: str, status: str) -> None:
    """Update a single delegation's status in routing_json."""
    sketch = get_sketch(sketch_id)
    if not sketch:
        return
    try:
        routing = json.loads(sketch.get("routing_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        routing = {}

    delegations = routing.get("delegations", [])
    for delegation in delegations:
        if delegation.get("super_agent_id") == super_agent_id:
            delegation["status"] = status
            break

    routing["delegations"] = delegations
    update_sketch(sketch_id, routing_json=json.dumps(routing))


def _check_all_delegations_complete(sketch_id: str) -> None:
    """Check if all delegations are done; if so, mark sketch as completed."""
    sketch = get_sketch(sketch_id)
    if not sketch:
        return
    try:
        routing = json.loads(sketch.get("routing_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        routing = {}

    delegations = routing.get("delegations", [])
    if not delegations:
        return

    all_done = all(d.get("status") in ("completed", "error") for d in delegations)
    if all_done:
        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s — all delegations complete, marking completed", sketch_id)
