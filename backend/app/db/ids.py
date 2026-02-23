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


# --- Generic helper ---


def _generate_short_id(length: int = 6) -> str:
    """Generate a random short ID for internal use."""
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


# --- Public ID generators ---


def generate_trigger_id() -> str:
    """Generate a unique trigger ID like 'trig-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(TRIGGER_ID_LENGTH))
    return f"{TRIGGER_ID_PREFIX}{random_part}"


def generate_agent_id() -> str:
    """Generate a unique agent ID like 'agent-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(AGENT_ID_LENGTH))
    return f"{AGENT_ID_PREFIX}{random_part}"


def generate_conversation_id() -> str:
    """Generate a unique conversation ID like 'conv-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(CONVERSATION_ID_LENGTH))
    return f"{CONVERSATION_ID_PREFIX}{random_part}"


def generate_team_id() -> str:
    """Generate a unique team ID like 'team-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(TEAM_ID_LENGTH))
    return f"{TEAM_ID_PREFIX}{random_part}"


def generate_product_id() -> str:
    """Generate a unique product ID like 'prod-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PRODUCT_ID_LENGTH))
    return f"{PRODUCT_ID_PREFIX}{random_part}"


def generate_project_id() -> str:
    """Generate a unique project ID like 'proj-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PROJECT_ID_LENGTH))
    return f"{PROJECT_ID_PREFIX}{random_part}"


def generate_plugin_id() -> str:
    """Generate a unique plugin ID like 'plug-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PLUGIN_ID_LENGTH))
    return f"{PLUGIN_ID_PREFIX}{random_part}"


def generate_execution_id(trigger_id: str) -> str:
    """Generate a unique execution ID like 'exec-trig-abc123-20260127T143022'."""
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    random_part = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
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
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(SUPER_AGENT_ID_LENGTH))
    return f"{SUPER_AGENT_ID_PREFIX}{random_part}"


def generate_session_id() -> str:
    """Generate a unique session ID like 'sess-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(SESSION_ID_LENGTH))
    return f"{SESSION_ID_PREFIX}{random_part}"


def generate_message_id() -> str:
    """Generate a unique message ID like 'msg-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(MESSAGE_ID_LENGTH))
    return f"{MESSAGE_ID_PREFIX}{random_part}"


def generate_workflow_id() -> str:
    """Generate a unique workflow ID like 'wf-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(WORKFLOW_ID_LENGTH))
    return f"{WORKFLOW_ID_PREFIX}{random_part}"


def generate_workflow_execution_id() -> str:
    """Generate a unique workflow execution ID like 'wfx-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(WORKFLOW_EXECUTION_ID_LENGTH))
    return f"{WORKFLOW_EXECUTION_ID_PREFIX}{random_part}"


def generate_sketch_id() -> str:
    """Generate a unique sketch ID like 'sketch-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(SKETCH_ID_LENGTH))
    return f"{SKETCH_ID_PREFIX}{random_part}"


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
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(MILESTONE_ID_LENGTH))
    return f"{MILESTONE_ID_PREFIX}{random_part}"


def generate_phase_id() -> str:
    """Generate a unique phase ID like 'phase-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PHASE_ID_LENGTH))
    return f"{PHASE_ID_PREFIX}{random_part}"


def generate_plan_id() -> str:
    """Generate a unique plan ID like 'plan-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PLAN_ID_LENGTH))
    return f"{PLAN_ID_PREFIX}{random_part}"


def generate_project_session_id() -> str:
    """Generate a unique project session ID like 'psess-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PROJECT_SESSION_ID_LENGTH))
    return f"{PROJECT_SESSION_ID_PREFIX}{random_part}"


def generate_rotation_event_id() -> str:
    """Generate a unique rotation event ID like 'rot-abc12345'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(ROTATION_EVENT_ID_LENGTH))
    return f"{ROTATION_EVENT_ID_PREFIX}{random_part}"


def generate_product_decision_id() -> str:
    """Generate a unique product decision ID like 'pdec-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PRODUCT_DECISION_ID_LENGTH))
    return f"{PRODUCT_DECISION_ID_PREFIX}{random_part}"


def generate_product_milestone_id() -> str:
    """Generate a unique product milestone ID like 'pms-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(PRODUCT_MILESTONE_ID_LENGTH))
    return f"{PRODUCT_MILESTONE_ID_PREFIX}{random_part}"


def generate_mcp_server_id() -> str:
    """Generate a unique MCP server ID like 'mcp-abc123'."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(MCP_SERVER_ID_LENGTH))
    return f"{MCP_SERVER_ID_PREFIX}{random_part}"


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
