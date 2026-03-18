"""ID generation utilities for Agented database entities."""

import secrets
import string

# --- ID prefix and length constants ---

TRIGGER_ID_PREFIX = "trig-"
TRIGGER_ID_LENGTH = 6  # Length of random part

AGENT_ID_PREFIX = "agent-"
AGENT_ID_LENGTH = 6  # Length of random part

CONVERSATION_ID_PREFIX = "conv-"
CONVERSATION_ID_LENGTH = 8  # Length of random part

TEAM_ID_PREFIX = "team-"
TEAM_ID_LENGTH = 6  # Length of random part

PRODUCT_ID_PREFIX = "prod-"
PRODUCT_ID_LENGTH = 6  # Length of random part

PROJECT_ID_PREFIX = "proj-"
PROJECT_ID_LENGTH = 6  # Length of random part

PLUGIN_ID_PREFIX = "plug-"
PLUGIN_ID_LENGTH = 6  # Length of random part

# New v0.3.0 entity IDs
SUPER_AGENT_ID_PREFIX = "super-"
SUPER_AGENT_ID_LENGTH = 6

SESSION_ID_PREFIX = "sess-"
SESSION_ID_LENGTH = 8

MESSAGE_ID_PREFIX = "msg-"
MESSAGE_ID_LENGTH = 8

WORKFLOW_ID_PREFIX = "wf-"
WORKFLOW_ID_LENGTH = 6

WORKFLOW_EXECUTION_ID_PREFIX = "wfx-"
WORKFLOW_EXECUTION_ID_LENGTH = 8

SKETCH_ID_PREFIX = "sketch-"
SKETCH_ID_LENGTH = 6

# New v0.4.0 entity IDs
MILESTONE_ID_PREFIX = "ms-"
MILESTONE_ID_LENGTH = 6

PHASE_ID_PREFIX = "phase-"
PHASE_ID_LENGTH = 6

PLAN_ID_PREFIX = "plan-"
PLAN_ID_LENGTH = 6

PROJECT_SESSION_ID_PREFIX = "psess-"
PROJECT_SESSION_ID_LENGTH = 8

ROTATION_EVENT_ID_PREFIX = "rot-"
ROTATION_EVENT_ID_LENGTH = 8

PRODUCT_DECISION_ID_PREFIX = "pdec-"
PRODUCT_DECISION_ID_LENGTH = 6

PRODUCT_MILESTONE_ID_PREFIX = "pms-"
PRODUCT_MILESTONE_ID_LENGTH = 6

MCP_SERVER_ID_PREFIX = "mcp-"
MCP_SERVER_ID_LENGTH = 6

ROLE_ID_PREFIX = "role-"
ROLE_ID_LENGTH = 6

SECRET_ID_PREFIX = "sec-"
SECRET_ID_LENGTH = 6

BOOKMARK_ID_PREFIX = "bm-"
BOOKMARK_ID_LENGTH = 6

INTEGRATION_ID_PREFIX = "intg-"
INTEGRATION_ID_LENGTH = 6

CAMPAIGN_ID_PREFIX = "camp-"
CAMPAIGN_ID_LENGTH = 6

TEMPLATE_ID_PREFIX = "tpl-"
TEMPLATE_ID_LENGTH = 6

SNIPPET_ID_PREFIX = "snip-"
SNIPPET_ID_LENGTH = 6

COMMENT_ID_PREFIX = "cmt-"
COMMENT_ID_LENGTH = 6

ERROR_ID_PREFIX = "err-"
ERROR_ID_LENGTH = 6

FIX_ATTEMPT_ID_PREFIX = "fix-"
FIX_ATTEMPT_ID_LENGTH = 6


# --- Central ID factory ---

_ID_CHARS = string.ascii_lowercase + string.digits


def generate_id(prefix: str, length: int = 6) -> str:
    """Generate a random ID with the given prefix and random suffix length.

    Uses ``secrets.choice()`` for cryptographically secure randomness.
    All entity-specific generators delegate to this function.

    Args:
        prefix: The ID prefix (e.g. ``"agent-"``).
        length: Number of random characters in the suffix.

    Returns:
        A string like ``"{prefix}{random_suffix}"``.
    """
    random_part = "".join(secrets.choice(_ID_CHARS) for _ in range(length))
    return f"{prefix}{random_part}"


# --- Generic helper (kept for backward compat) ---


def _generate_short_id(length: int = 6) -> str:
    """Generate a random short ID for internal use."""
    return generate_id("", length)


# --- Public ID generators ---


def generate_trigger_id() -> str:
    """Generate a unique trigger ID like 'trig-abc123'."""
    return generate_id(TRIGGER_ID_PREFIX, TRIGGER_ID_LENGTH)


def generate_agent_id() -> str:
    """Generate a unique agent ID like 'agent-abc123'."""
    return generate_id(AGENT_ID_PREFIX, AGENT_ID_LENGTH)


def generate_conversation_id() -> str:
    """Generate a unique conversation ID like 'conv-abc12345'."""
    return generate_id(CONVERSATION_ID_PREFIX, CONVERSATION_ID_LENGTH)


def generate_team_id() -> str:
    """Generate a unique team ID like 'team-abc123'."""
    return generate_id(TEAM_ID_PREFIX, TEAM_ID_LENGTH)


def generate_product_id() -> str:
    """Generate a unique product ID like 'prod-abc123'."""
    return generate_id(PRODUCT_ID_PREFIX, PRODUCT_ID_LENGTH)


def generate_project_id() -> str:
    """Generate a unique project ID like 'proj-abc123'."""
    return generate_id(PROJECT_ID_PREFIX, PROJECT_ID_LENGTH)


def generate_plugin_id() -> str:
    """Generate a unique plugin ID like 'plug-abc123'."""
    return generate_id(PLUGIN_ID_PREFIX, PLUGIN_ID_LENGTH)


def generate_execution_id(trigger_id: str) -> str:
    """Generate a unique execution ID like 'exec-trig-abc123-20260127T143022'."""
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    random_part = generate_id("", 4)
    return f"exec-{trigger_id}-{timestamp}-{random_part}"


# --- Collision-safe ID generators (require a database connection) ---


def _get_unique_trigger_id(conn) -> str:
    """Generate a trigger ID that doesn't exist in the database."""
    while True:
        trigger_id = generate_trigger_id()
        cursor = conn.execute("SELECT id FROM triggers WHERE id = ?", (trigger_id,))
        if cursor.fetchone() is None:
            return trigger_id


def _get_unique_agent_id(conn) -> str:
    """Generate an agent ID that doesn't exist in the database."""
    while True:
        agent_id = generate_agent_id()
        cursor = conn.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
        if cursor.fetchone() is None:
            return agent_id


def _get_unique_conversation_id(conn) -> str:
    """Generate a conversation ID that doesn't exist in the database."""
    while True:
        conv_id = generate_conversation_id()
        cursor = conn.execute("SELECT id FROM agent_conversations WHERE id = ?", (conv_id,))
        if cursor.fetchone() is None:
            return conv_id


def _get_unique_team_id(conn) -> str:
    """Generate a team ID that doesn't exist in the database."""
    while True:
        team_id = generate_team_id()
        cursor = conn.execute("SELECT id FROM teams WHERE id = ?", (team_id,))
        if cursor.fetchone() is None:
            return team_id


def _get_unique_product_id(conn) -> str:
    """Generate a product ID that doesn't exist in the database."""
    while True:
        product_id = generate_product_id()
        cursor = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,))
        if cursor.fetchone() is None:
            return product_id


def _get_unique_project_id(conn) -> str:
    """Generate a project ID that doesn't exist in the database."""
    while True:
        project_id = generate_project_id()
        cursor = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if cursor.fetchone() is None:
            return project_id


def _get_unique_plugin_id(conn) -> str:
    """Generate a plugin ID that doesn't exist in the database."""
    while True:
        plugin_id = generate_plugin_id()
        cursor = conn.execute("SELECT id FROM plugins WHERE id = ?", (plugin_id,))
        if cursor.fetchone() is None:
            return plugin_id


# --- v0.3.0 Public ID generators ---


def generate_super_agent_id() -> str:
    """Generate a unique super agent ID like 'super-abc123'."""
    return generate_id(SUPER_AGENT_ID_PREFIX, SUPER_AGENT_ID_LENGTH)


def generate_session_id() -> str:
    """Generate a unique session ID like 'sess-abc12345'."""
    return generate_id(SESSION_ID_PREFIX, SESSION_ID_LENGTH)


def generate_message_id() -> str:
    """Generate a unique message ID like 'msg-abc12345'."""
    return generate_id(MESSAGE_ID_PREFIX, MESSAGE_ID_LENGTH)


def generate_workflow_id() -> str:
    """Generate a unique workflow ID like 'wf-abc123'."""
    return generate_id(WORKFLOW_ID_PREFIX, WORKFLOW_ID_LENGTH)


def generate_workflow_execution_id() -> str:
    """Generate a unique workflow execution ID like 'wfx-abc12345'."""
    return generate_id(WORKFLOW_EXECUTION_ID_PREFIX, WORKFLOW_EXECUTION_ID_LENGTH)


def generate_sketch_id() -> str:
    """Generate a unique sketch ID like 'sketch-abc123'."""
    return generate_id(SKETCH_ID_PREFIX, SKETCH_ID_LENGTH)


# --- v0.3.0 Collision-safe ID generators ---


def _get_unique_super_agent_id(conn) -> str:
    """Generate a super agent ID that doesn't exist in the database."""
    while True:
        sa_id = generate_super_agent_id()
        cursor = conn.execute("SELECT id FROM super_agents WHERE id = ?", (sa_id,))
        if cursor.fetchone() is None:
            return sa_id


def _get_unique_session_id(conn) -> str:
    """Generate a session ID that doesn't exist in the database."""
    while True:
        sess_id = generate_session_id()
        cursor = conn.execute("SELECT id FROM super_agent_sessions WHERE id = ?", (sess_id,))
        if cursor.fetchone() is None:
            return sess_id


def _get_unique_message_id(conn) -> str:
    """Generate a message ID that doesn't exist in the database."""
    while True:
        msg_id = generate_message_id()
        cursor = conn.execute("SELECT id FROM agent_messages WHERE id = ?", (msg_id,))
        if cursor.fetchone() is None:
            return msg_id


def _get_unique_workflow_id(conn) -> str:
    """Generate a workflow ID that doesn't exist in the database."""
    while True:
        wf_id = generate_workflow_id()
        cursor = conn.execute("SELECT id FROM workflows WHERE id = ?", (wf_id,))
        if cursor.fetchone() is None:
            return wf_id


def _get_unique_workflow_execution_id(conn) -> str:
    """Generate a workflow execution ID that doesn't exist in the database."""
    while True:
        wfx_id = generate_workflow_execution_id()
        cursor = conn.execute("SELECT id FROM workflow_executions WHERE id = ?", (wfx_id,))
        if cursor.fetchone() is None:
            return wfx_id


def _get_unique_sketch_id(conn) -> str:
    """Generate a sketch ID that doesn't exist in the database."""
    while True:
        sketch_id = generate_sketch_id()
        cursor = conn.execute("SELECT id FROM sketches WHERE id = ?", (sketch_id,))
        if cursor.fetchone() is None:
            return sketch_id


# --- v0.4.0 Public ID generators ---


def generate_milestone_id() -> str:
    """Generate a unique milestone ID like 'ms-abc123'."""
    return generate_id(MILESTONE_ID_PREFIX, MILESTONE_ID_LENGTH)


def generate_phase_id() -> str:
    """Generate a unique phase ID like 'phase-abc123'."""
    return generate_id(PHASE_ID_PREFIX, PHASE_ID_LENGTH)


def generate_plan_id() -> str:
    """Generate a unique plan ID like 'plan-abc123'."""
    return generate_id(PLAN_ID_PREFIX, PLAN_ID_LENGTH)


def generate_project_session_id() -> str:
    """Generate a unique project session ID like 'psess-abc12345'."""
    return generate_id(PROJECT_SESSION_ID_PREFIX, PROJECT_SESSION_ID_LENGTH)


def generate_rotation_event_id() -> str:
    """Generate a unique rotation event ID like 'rot-abc12345'."""
    return generate_id(ROTATION_EVENT_ID_PREFIX, ROTATION_EVENT_ID_LENGTH)


def generate_product_decision_id() -> str:
    """Generate a unique product decision ID like 'pdec-abc123'."""
    return generate_id(PRODUCT_DECISION_ID_PREFIX, PRODUCT_DECISION_ID_LENGTH)


def generate_product_milestone_id() -> str:
    """Generate a unique product milestone ID like 'pms-abc123'."""
    return generate_id(PRODUCT_MILESTONE_ID_PREFIX, PRODUCT_MILESTONE_ID_LENGTH)


def generate_mcp_server_id() -> str:
    """Generate a unique MCP server ID like 'mcp-abc123'."""
    return generate_id(MCP_SERVER_ID_PREFIX, MCP_SERVER_ID_LENGTH)


def generate_role_id() -> str:
    """Generate a unique role ID like 'role-abc123'."""
    return generate_id(ROLE_ID_PREFIX, ROLE_ID_LENGTH)


def generate_bookmark_id() -> str:
    """Generate a unique bookmark ID like 'bm-abc123'."""
    return generate_id(BOOKMARK_ID_PREFIX, BOOKMARK_ID_LENGTH)


def generate_comment_id() -> str:
    """Generate a unique comment ID like 'cmt-abc123'."""
    return generate_id(COMMENT_ID_PREFIX, COMMENT_ID_LENGTH)


def generate_error_id() -> str:
    """Generate a unique error ID like 'err-abc123'."""
    return generate_id(ERROR_ID_PREFIX, ERROR_ID_LENGTH)


def generate_fix_attempt_id() -> str:
    """Generate a unique fix attempt ID like 'fix-abc123'."""
    return generate_id(FIX_ATTEMPT_ID_PREFIX, FIX_ATTEMPT_ID_LENGTH)


# --- v0.4.0 Collision-safe ID generators ---


def _get_unique_milestone_id(conn) -> str:
    """Generate a milestone ID that doesn't exist in the database."""
    while True:
        mid = generate_milestone_id()
        cursor = conn.execute("SELECT id FROM milestones WHERE id = ?", (mid,))
        if cursor.fetchone() is None:
            return mid


def _get_unique_phase_id(conn) -> str:
    """Generate a phase ID that doesn't exist in the database."""
    while True:
        pid = generate_phase_id()
        cursor = conn.execute("SELECT id FROM project_phases WHERE id = ?", (pid,))
        if cursor.fetchone() is None:
            return pid


def _get_unique_plan_id(conn) -> str:
    """Generate a plan ID that doesn't exist in the database."""
    while True:
        pid = generate_plan_id()
        cursor = conn.execute("SELECT id FROM project_plans WHERE id = ?", (pid,))
        if cursor.fetchone() is None:
            return pid


def _get_unique_project_session_id(conn) -> str:
    """Generate a project session ID that doesn't exist in the database."""
    while True:
        sid = generate_project_session_id()
        cursor = conn.execute("SELECT id FROM project_sessions WHERE id = ?", (sid,))
        if cursor.fetchone() is None:
            return sid


def _get_unique_rotation_event_id(conn) -> str:
    """Generate a rotation event ID that doesn't exist in the database."""
    while True:
        rid = generate_rotation_event_id()
        cursor = conn.execute("SELECT id FROM rotation_events WHERE id = ?", (rid,))
        if cursor.fetchone() is None:
            return rid


def _get_unique_product_decision_id(conn) -> str:
    """Generate a product decision ID that doesn't exist in the database."""
    while True:
        did = generate_product_decision_id()
        cursor = conn.execute("SELECT id FROM product_decisions WHERE id = ?", (did,))
        if cursor.fetchone() is None:
            return did


def _get_unique_product_milestone_id(conn) -> str:
    """Generate a product milestone ID that doesn't exist in the database."""
    while True:
        mid = generate_product_milestone_id()
        cursor = conn.execute("SELECT id FROM product_milestones WHERE id = ?", (mid,))
        if cursor.fetchone() is None:
            return mid


def _get_unique_mcp_server_id(conn) -> str:
    """Generate an MCP server ID that doesn't exist in the database."""
    while True:
        mid = generate_mcp_server_id()
        cursor = conn.execute("SELECT id FROM mcp_servers WHERE id = ?", (mid,))
        if cursor.fetchone() is None:
            return mid


def _get_unique_role_id(conn) -> str:
    """Generate a role ID that doesn't exist in the database."""
    while True:
        rid = generate_role_id()
        cursor = conn.execute("SELECT id FROM user_roles WHERE id = ?", (rid,))
        if cursor.fetchone() is None:
            return rid


def generate_secret_id() -> str:
    """Generate a unique secret ID like 'sec-abc123'."""
    return generate_id(SECRET_ID_PREFIX, SECRET_ID_LENGTH)


def _get_unique_secret_id(conn) -> str:
    """Generate a secret ID that doesn't exist in the database."""
    while True:
        sid = generate_secret_id()
        cursor = conn.execute("SELECT id FROM secrets WHERE id = ?", (sid,))
        if cursor.fetchone() is None:
            return sid


def _get_unique_bookmark_id(conn) -> str:
    """Generate a bookmark ID that doesn't exist in the database."""
    while True:
        bid = generate_bookmark_id()
        cursor = conn.execute("SELECT id FROM bookmarks WHERE id = ?", (bid,))
        if cursor.fetchone() is None:
            return bid


def generate_integration_id() -> str:
    """Generate a unique integration ID like 'intg-abc123'."""
    return generate_id(INTEGRATION_ID_PREFIX, INTEGRATION_ID_LENGTH)


def _get_unique_integration_id(conn) -> str:
    """Generate an integration ID that doesn't exist in the database."""
    while True:
        iid = generate_integration_id()
        cursor = conn.execute("SELECT id FROM integrations WHERE id = ?", (iid,))
        if cursor.fetchone() is None:
            return iid


def generate_campaign_id() -> str:
    """Generate a unique campaign ID like 'camp-abc123'."""
    return generate_id(CAMPAIGN_ID_PREFIX, CAMPAIGN_ID_LENGTH)


def _get_unique_campaign_id(conn) -> str:
    """Generate a campaign ID that doesn't exist in the database."""
    while True:
        cid = generate_campaign_id()
        cursor = conn.execute("SELECT id FROM campaigns WHERE id = ?", (cid,))
        if cursor.fetchone() is None:
            return cid


def generate_template_id() -> str:
    """Generate a unique template ID like 'tpl-abc123'."""
    return generate_id(TEMPLATE_ID_PREFIX, TEMPLATE_ID_LENGTH)


def _get_unique_template_id(conn) -> str:
    """Generate a template ID that doesn't exist in the database."""
    while True:
        tid = generate_template_id()
        cursor = conn.execute("SELECT id FROM bot_templates WHERE id = ?", (tid,))
        if cursor.fetchone() is None:
            return tid


def generate_snippet_id() -> str:
    """Generate a unique snippet ID like 'snip-abc123'."""
    return generate_id(SNIPPET_ID_PREFIX, SNIPPET_ID_LENGTH)


def _get_unique_snippet_id(conn) -> str:
    """Generate a snippet ID that doesn't exist in the database."""
    while True:
        sid = generate_snippet_id()
        cursor = conn.execute("SELECT id FROM prompt_snippets WHERE id = ?", (sid,))
        if cursor.fetchone() is None:
            return sid


def _get_unique_error_id(conn) -> str:
    """Generate an error ID that doesn't exist in the database."""
    while True:
        eid = generate_error_id()
        cursor = conn.execute("SELECT id FROM system_errors WHERE id = ?", (eid,))
        if cursor.fetchone() is None:
            return eid


def _get_unique_fix_attempt_id(conn) -> str:
    """Generate a fix attempt ID that doesn't exist in the database."""
    while True:
        fid = generate_fix_attempt_id()
        cursor = conn.execute("SELECT id FROM fix_attempts WHERE id = ?", (fid,))
        if cursor.fetchone() is None:
            return fid
