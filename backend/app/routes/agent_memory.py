"""Agent memory API endpoints — threads, messages, working memory, recall."""

import json
from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.agent_memory import (
    count_messages,
    count_threads,
    create_thread,
    delete_thread,
    delete_working_memory,
    get_messages,
    get_thread,
    get_working_memory,
    list_threads,
    recall_messages,
    save_messages,
    update_thread,
    upsert_working_memory,
)
from ..db.agents import get_agent
from ..models.agent_memory import (
    AgentMemoryPath,
    CreateThreadBody,
    RecallQuery,
    SaveMessagesBody,
    ThreadPath,
    UpdateMemoryConfigBody,
    UpdateWorkingMemoryBody,
)

tag = Tag(
    name="agent-memory",
    description="Agent memory — threads, messages, working memory, recall",
)
agent_memory_bp = APIBlueprint(
    "agent_memory", __name__, url_prefix="/admin", abp_tags=[tag]
)


def _validate_agent(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        return None, error_response("NOT_FOUND", "Agent not found", HTTPStatus.NOT_FOUND)
    return agent, None


# --- Thread endpoints ---


@agent_memory_bp.get("/agents/<agent_id>/memory/threads")
def list_agent_threads(path: AgentMemoryPath):
    """List all memory threads for an agent."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    threads = list_threads(path.agent_id, "agent")
    total = count_threads(path.agent_id, "agent")
    return {"threads": threads, "total": total}, HTTPStatus.OK


@agent_memory_bp.post("/agents/<agent_id>/memory/threads")
def create_agent_thread(path: AgentMemoryPath, body: CreateThreadBody):
    """Create a new memory thread for an agent."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    thread = create_thread(
        resource_id=path.agent_id,
        resource_type="agent",
        title=body.title,
        metadata=body.metadata,
    )
    return thread, HTTPStatus.CREATED


@agent_memory_bp.get("/agents/<agent_id>/memory/threads/<thread_id>")
def get_agent_thread(path: ThreadPath):
    """Get a memory thread with message count."""
    thread = get_thread(path.thread_id)
    if not thread or thread.get("resource_id") != path.agent_id:
        return error_response("NOT_FOUND", "Thread not found", HTTPStatus.NOT_FOUND)
    thread["message_count"] = count_messages(path.thread_id)
    return thread, HTTPStatus.OK


@agent_memory_bp.delete("/agents/<agent_id>/memory/threads/<thread_id>")
def delete_agent_thread(path: ThreadPath):
    """Delete a memory thread and all its messages."""
    thread = get_thread(path.thread_id)
    if not thread or thread.get("resource_id") != path.agent_id:
        return error_response("NOT_FOUND", "Thread not found", HTTPStatus.NOT_FOUND)
    delete_thread(path.thread_id)
    return {"message": f"Thread {path.thread_id} deleted"}, HTTPStatus.OK


# --- Message endpoints ---


@agent_memory_bp.get("/agents/<agent_id>/memory/threads/<thread_id>/messages")
def list_thread_messages(path: ThreadPath):
    """List messages in a thread (newest first, paginated)."""
    thread = get_thread(path.thread_id)
    if not thread or thread.get("resource_id") != path.agent_id:
        return error_response("NOT_FOUND", "Thread not found", HTTPStatus.NOT_FOUND)
    messages = get_messages(path.thread_id, limit=100)
    total = count_messages(path.thread_id)
    return {"messages": messages, "total": total}, HTTPStatus.OK


@agent_memory_bp.post("/agents/<agent_id>/memory/threads/<thread_id>/messages")
def add_thread_messages(path: ThreadPath, body: SaveMessagesBody):
    """Add messages to a thread."""
    thread = get_thread(path.thread_id)
    if not thread or thread.get("resource_id") != path.agent_id:
        return error_response("NOT_FOUND", "Thread not found", HTTPStatus.NOT_FOUND)
    saved = save_messages(path.thread_id, [m.model_dump() for m in body.messages])
    return {"messages": saved, "count": len(saved)}, HTTPStatus.CREATED


# --- Recall endpoint ---


@agent_memory_bp.get("/agents/<agent_id>/memory/recall")
def recall_agent_memory(path: AgentMemoryPath, query: RecallQuery):
    """Search agent memory using full-text search with BM25 ranking."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    results = recall_messages(
        thread_id=query.thread_id,
        query=query.q,
        resource_id=path.agent_id,
        resource_type="agent",
        top_k=query.top_k,
        message_range=query.message_range,
    )
    return {"results": results, "count": len(results), "query": query.q}, HTTPStatus.OK


# --- Working Memory endpoints ---


@agent_memory_bp.get("/agents/<agent_id>/memory/working")
def get_agent_working_memory(path: AgentMemoryPath):
    """Get the agent's working memory."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    wm = get_working_memory(path.agent_id, "agent")
    if not wm:
        return {
            "entity_id": path.agent_id,
            "entity_type": "agent",
            "content": "",
            "template": None,
        }, HTTPStatus.OK
    return wm, HTTPStatus.OK


@agent_memory_bp.put("/agents/<agent_id>/memory/working")
def update_agent_working_memory(path: AgentMemoryPath, body: UpdateWorkingMemoryBody):
    """Update the agent's working memory."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    wm = upsert_working_memory(
        entity_id=path.agent_id,
        entity_type="agent",
        content=body.content,
        template=body.template,
    )
    return wm, HTTPStatus.OK


@agent_memory_bp.delete("/agents/<agent_id>/memory/working")
def clear_agent_working_memory(path: AgentMemoryPath):
    """Clear the agent's working memory."""
    delete_working_memory(path.agent_id, "agent")
    return {"message": "Working memory cleared"}, HTTPStatus.OK


# --- Memory Config endpoint ---


@agent_memory_bp.get("/agents/<agent_id>/memory/config")
def get_memory_config(path: AgentMemoryPath):
    """Get the agent's memory configuration."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    config = {}
    if agent.get("memory_config"):
        try:
            config = json.loads(agent["memory_config"])
        except (json.JSONDecodeError, TypeError):
            pass
    # Return defaults if not configured
    if not config:
        config = {
            "enabled": True,
            "last_messages": 10,
            "semantic_recall": {"enabled": True, "top_k": 5, "message_range": 1},
            "working_memory": {
                "enabled": True,
                "scope": "agent",
                "template": (
                    "# Agent Notes\n- **Current Task**:\n"
                    "- **Key Facts**:\n- **Preferences**:"
                ),
            },
        }
    return config, HTTPStatus.OK


@agent_memory_bp.put("/agents/<agent_id>/memory/config")
def update_memory_config(path: AgentMemoryPath, body: UpdateMemoryConfigBody):
    """Update the agent's memory configuration."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    from ..db.connection import get_connection

    # Merge with existing config
    existing = {}
    if agent.get("memory_config"):
        try:
            existing = json.loads(agent["memory_config"])
        except (json.JSONDecodeError, TypeError):
            pass

    if body.enabled is not None:
        existing["enabled"] = body.enabled
    if body.last_messages is not None:
        existing["last_messages"] = body.last_messages
    if body.semantic_recall is not None:
        existing["semantic_recall"] = body.semantic_recall
    if body.working_memory is not None:
        existing["working_memory"] = body.working_memory

    with get_connection() as conn:
        conn.execute(
            "UPDATE agents SET memory_config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(existing), path.agent_id),
        )
        conn.commit()

    return existing, HTTPStatus.OK
