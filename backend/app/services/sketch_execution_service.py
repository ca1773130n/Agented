"""Sketch execution service.

Bridges sketch routing to actual LLM execution on super agent sessions.
"""

import logging
from typing import Optional

from ..db.connection import get_connection
from ..db.sketches import update_sketch
from ..db.super_agents import get_super_agent
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


def execute_sketch(sketch_id: str, super_agent_id: str, content: str) -> str:
    """Execute a routed sketch on a super agent session.

    Sets status to 'in_progress' before launching the background thread
    to prevent race conditions. Returns session_id.
    """
    # 1. Set status before launching thread
    update_sketch(sketch_id, status="in_progress")

    # 2. Resolve backend from super agent record (same pattern as _resolve_session)
    sa = get_super_agent(super_agent_id)
    backend = (sa.get("backend_type") if sa else None) or "claude"

    # 3. Get or create session
    session_id = SuperAgentSessionService.get_or_create_session(super_agent_id)

    # 4. Persist user message to session
    SuperAgentSessionService.send_message(session_id, content)

    # 5. Launch streaming with sketch status callbacks
    def _on_complete():
        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s completed successfully", sketch_id)

    def _on_error(error_msg):
        update_sketch(sketch_id, status="classified")
        logger.error("Sketch %s failed: %s", sketch_id, error_msg)

    run_streaming_response(
        session_id=session_id,
        super_agent_id=super_agent_id,
        backend=backend,
        on_complete=_on_complete,
        on_error=_on_error,
    )

    return session_id
