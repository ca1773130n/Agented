"""Wave 70 — leaf CRUD batch F (~26 routes).

agent_memory + bulk + replay + conversation_branches.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.db.agent_memory import (
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
    upsert_working_memory,
)
from app.db.agents import get_agent
from app.db.replay import get_replay_comparison, get_replay_comparisons_for_execution
from app.services.bulk_service import BulkService
from app.services.conversation_branch_service import ConversationBranchService
from app.services.diff_context_service import DiffContextService
from app.services.execution_log_service import ExecutionLogService
from app.services.replay_service import ReplayService


# ===========================================================================
# /admin/agents/{id}/memory/* (12)
# ===========================================================================


def _ensure_agent(agent_id: str) -> dict:
    agent = get_agent(agent_id)
    if not agent:
        raise NotFoundException(detail="Agent not found")
    return agent


def _ensure_thread(thread_id: str, agent_id: str) -> dict:
    thread = get_thread(thread_id)
    if not thread or thread.get("resource_id") != agent_id:
        raise NotFoundException(detail="Thread not found")
    return thread


@get("/{agent_id:str}/memory/threads", sync_to_thread=False)
def list_memory_threads(agent_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    threads = list_threads(agent_id, "agent")
    return {"threads": threads, "total": count_threads(agent_id, "agent")}


@post("/{agent_id:str}/memory/threads", status_code=201, sync_to_thread=False)
def create_memory_thread(agent_id: str, data: dict) -> Any:
    _ensure_agent(agent_id)
    body = data or {}
    return create_thread(
        resource_id=agent_id,
        resource_type="agent",
        title=body.get("title", ""),
        metadata=body.get("metadata") or {},
    )


@get("/{agent_id:str}/memory/threads/{thread_id:str}", sync_to_thread=False)
def get_memory_thread(agent_id: str, thread_id: str) -> Any:
    thread = _ensure_thread(thread_id, agent_id)
    thread["message_count"] = count_messages(thread_id)
    return thread


@delete(
    "/{agent_id:str}/memory/threads/{thread_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_memory_thread(agent_id: str, thread_id: str) -> dict[str, Any]:
    _ensure_thread(thread_id, agent_id)
    delete_thread(thread_id)
    return {"message": f"Thread {thread_id} deleted"}


@get(
    "/{agent_id:str}/memory/threads/{thread_id:str}/messages",
    sync_to_thread=False,
)
def list_thread_messages(agent_id: str, thread_id: str) -> dict[str, Any]:
    _ensure_thread(thread_id, agent_id)
    return {
        "messages": get_messages(thread_id, limit=100),
        "total": count_messages(thread_id),
    }


@post(
    "/{agent_id:str}/memory/threads/{thread_id:str}/messages",
    status_code=201,
    sync_to_thread=False,
)
def add_thread_messages(agent_id: str, thread_id: str, data: dict) -> dict[str, Any]:
    _ensure_thread(thread_id, agent_id)
    messages = (data or {}).get("messages") or []
    if not messages:
        raise ClientException(detail="messages array is required")
    saved = save_messages(thread_id, messages)
    return {"messages": saved, "count": len(saved)}


@get("/{agent_id:str}/memory/recall", sync_to_thread=False)
def recall_agent_memory(
    agent_id: str,
    q: str = "",
    thread_id: Optional[str] = None,
    top_k: int = 5,
    message_range: int = 1,
    alpha: float = 0.5,
    search_mode: str = "fts",
    use_crag: bool = False,
    graph_hops: int = 1,
    include_cross_thread: bool = False,
) -> dict[str, Any]:
    _ensure_agent(agent_id)
    if not q:
        raise ClientException(detail="q is required")
    effective_thread = None if include_cross_thread else thread_id

    if use_crag:
        from app.services.memory_orchestrator import orchestrated_recall

        return orchestrated_recall(
            query=q,
            agent_id=agent_id,
            thread_id=effective_thread,
            top_k=top_k,
            message_range=message_range,
            alpha=alpha,
            use_crag=True,
            graph_hops=graph_hops,
            include_cross_thread=include_cross_thread,
        )

    if search_mode == "vector":
        from app.db.agent_memory import vector_recall

        vec_results = vector_recall(
            query=q,
            resource_id=agent_id,
            thread_id=effective_thread,
            resource_type="agent",
            top_k=top_k,
        )
        results = [msg for msg, _score in vec_results]
        max_score = vec_results[0][1] if vec_results else 0.0
    elif search_mode == "hybrid":
        from app.db.agent_memory import hybrid_recall

        results = hybrid_recall(
            query=q,
            resource_id=agent_id,
            thread_id=effective_thread,
            resource_type="agent",
            top_k=top_k,
            message_range=message_range,
            alpha=alpha,
        )
        max_score = 1.0
    else:
        results = recall_messages(
            thread_id=effective_thread,
            query=q,
            resource_id=agent_id,
            resource_type="agent",
            top_k=top_k,
            message_range=message_range,
        )
        max_score = 1.0

    return {
        "results": results,
        "count": len(results),
        "query": q,
        "search_mode": search_mode,
        "relevance_score": round(max_score, 4),
    }


@get("/{agent_id:str}/memory/working", sync_to_thread=False)
def get_agent_working_memory(agent_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    wm = get_working_memory(agent_id, "agent")
    if not wm:
        return {
            "entity_id": agent_id,
            "entity_type": "agent",
            "content": "",
            "template": None,
        }
    return wm


@put("/{agent_id:str}/memory/working", sync_to_thread=False)
def update_agent_working_memory(agent_id: str, data: dict) -> Any:
    _ensure_agent(agent_id)
    body = data or {}
    return upsert_working_memory(
        entity_id=agent_id,
        entity_type="agent",
        content=body.get("content", ""),
        template=body.get("template"),
    )


@delete("/{agent_id:str}/memory/working", status_code=200, sync_to_thread=False)
def clear_agent_working_memory(agent_id: str) -> dict[str, Any]:
    delete_working_memory(agent_id, "agent")
    return {"message": "Working memory cleared"}


@get(
    "/{agent_id:str}/memory/threads/{thread_id:str}/related",
    sync_to_thread=False,
)
def get_related_threads(agent_id: str, thread_id: str) -> dict[str, Any]:
    _ensure_thread(thread_id, agent_id)
    from app.services.memory_evolution import find_related_threads

    related = find_related_threads(agent_id, thread_id)
    return {"related_threads": related, "count": len(related)}


@get("/{agent_id:str}/memory/config", sync_to_thread=False)
def get_memory_config(agent_id: str) -> dict[str, Any]:
    agent = _ensure_agent(agent_id)
    config: dict[str, Any] = {}
    if agent.get("memory_config"):
        try:
            config = json.loads(agent["memory_config"])
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "get_memory_config: corrupt memory_config JSON for agent %s; "
                "returning defaults. raw=%r",
                agent_id,
                str(agent["memory_config"])[:200],
            )
    if not config:
        config = {
            "enabled": True,
            "last_messages": 10,
            "semantic_recall": {"enabled": True, "top_k": 5, "message_range": 1},
            "working_memory": {
                "enabled": True,
                "scope": "agent",
                "template": (
                    "# Agent Notes\n- **Current Task**:\n- **Key Facts**:\n- **Preferences**:"
                ),
            },
            "vector_search": {"enabled": True},
            "knowledge_graph": {"enabled": True},
            "crag_evaluation": {"enabled": False},
            "cross_thread": {"enabled": False},
        }
    return config


@put("/{agent_id:str}/memory/config", sync_to_thread=False)
def update_memory_config(agent_id: str, data: dict) -> dict[str, Any]:
    agent = _ensure_agent(agent_id)
    body = data or {}
    from app.db.connection import get_connection

    existing: dict[str, Any] = {}
    if agent.get("memory_config"):
        try:
            existing = json.loads(agent["memory_config"])
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "update_memory_config: corrupt memory_config JSON for agent %s; "
                "previous config will be lost (only body keys will be set). raw=%r",
                agent_id,
                str(agent["memory_config"])[:200],
            )

    for key in (
        "enabled",
        "last_messages",
        "semantic_recall",
        "working_memory",
        "vector_search",
        "knowledge_graph",
        "crag_evaluation",
        "cross_thread",
    ):
        if body.get(key) is not None:
            existing[key] = body[key]

    with get_connection() as conn:
        conn.execute(
            "UPDATE agents SET memory_config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(existing), agent_id),
        )
        conn.commit()
    return existing


agent_memory_router = Router(
    path="/admin/agents",
    route_handlers=[
        list_memory_threads,
        create_memory_thread,
        get_memory_thread,
        delete_memory_thread,
        list_thread_messages,
        add_thread_messages,
        recall_agent_memory,
        get_agent_working_memory,
        update_agent_working_memory,
        clear_agent_working_memory,
        get_related_threads,
        get_memory_config,
        update_memory_config,
    ],
)


# ===========================================================================
# /admin/bulk/* (4)
# ===========================================================================


def _bulk(entity_type: str, data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    action = data.get("action")
    items = data.get("items")
    if not action:
        raise ClientException(
            detail="The 'action' field is required (create, update, or delete)"
        )
    if items is None or not isinstance(items, list):
        raise ClientException(detail="The 'items' field must be a JSON array")
    try:
        results = BulkService.process(entity_type, action, items)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e
    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    return {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
    }


@post("/agents", sync_to_thread=False)
def bulk_agents(data: dict) -> dict[str, Any]:
    return _bulk("agent", data)


@post("/triggers", sync_to_thread=False)
def bulk_triggers(data: dict) -> dict[str, Any]:
    return _bulk("trigger", data)


@post("/plugins", sync_to_thread=False)
def bulk_plugins(data: dict) -> dict[str, Any]:
    return _bulk("plugin", data)


@post("/hooks", sync_to_thread=False)
def bulk_hooks(data: dict) -> dict[str, Any]:
    return _bulk("hook", data)


bulk_router = Router(
    path="/admin/bulk",
    route_handlers=[bulk_agents, bulk_triggers, bulk_plugins, bulk_hooks],
)


# ===========================================================================
# /admin/executions/{id}/replay + /replay-comparisons/* + /diff-context (5)
# ===========================================================================


@post("/executions/{execution_id:str}/replay", status_code=201, sync_to_thread=False)
def replay_execution(execution_id: str, data: dict) -> Any:
    notes = (data or {}).get("notes")
    try:
        return ReplayService.replay_execution(execution_id, notes=notes)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise NotFoundException(detail=msg) from e
        raise ClientException(detail=msg) from e


@get("/executions/{execution_id:str}/comparisons", sync_to_thread=False)
def list_execution_comparisons(execution_id: str) -> dict[str, Any]:
    comparisons = get_replay_comparisons_for_execution(execution_id)
    return {"comparisons": comparisons, "total": len(comparisons)}


@get("/replay-comparisons/{comparison_id:str}", sync_to_thread=False)
def get_comparison(comparison_id: str) -> Any:
    comparison = get_replay_comparison(comparison_id)
    if not comparison:
        raise NotFoundException(detail="Comparison not found")
    return comparison


@get("/replay-comparisons/{comparison_id:str}/diff", sync_to_thread=False)
def get_comparison_diff(comparison_id: str) -> Any:
    comparison = get_replay_comparison(comparison_id)
    if not comparison:
        raise NotFoundException(detail="Comparison not found")
    original_id = comparison["original_execution_id"]
    replay_id = comparison["replay_execution_id"]
    if ExecutionLogService.is_running(original_id) or ExecutionLogService.is_running(replay_id):
        raise HTTPException(
            status_code=409,
            detail="Cannot diff: one or both executions are still running",
        )
    try:
        return ReplayService.compare_outputs(original_id, replay_id)
    except ValueError as e:
        raise NotFoundException(detail=str(e)) from e


@post("/diff-context/preview", sync_to_thread=False)
def preview_diff_context(data: dict) -> dict[str, Any]:
    body = data or {}
    if "diff_text" not in body:
        raise ClientException(detail="Missing required field: diff_text")
    diff_text = body["diff_text"]
    context_lines = body.get("context_lines")
    context = DiffContextService.extract_pr_diff_context(diff_text, context_lines)
    return {
        "context": context,
        "token_estimate": DiffContextService.estimate_token_reduction(diff_text, context),
    }


replay_router = Router(
    path="/admin",
    route_handlers=[
        replay_execution,
        list_execution_comparisons,
        get_comparison,
        get_comparison_diff,
        preview_diff_context,
    ],
)


# ===========================================================================
# /admin/conversations/{id}/branches + /admin/branches/{id}/messages (5)
# ===========================================================================


@post(
    "/conversations/{conversation_id:str}/branches",
    status_code=201,
    sync_to_thread=False,
)
def create_branch(conversation_id: str, data: dict) -> Any:
    body = data or {}
    fork_message_index = body.get("fork_message_index")
    if fork_message_index is None:
        raise ClientException(detail="Missing required field: fork_message_index")
    try:
        fork_message_index = int(fork_message_index)
    except (TypeError, ValueError) as e:
        raise ClientException(detail="fork_message_index must be an integer") from e
    try:
        return ConversationBranchService.create_branch(
            conversation_id, fork_message_index, name=body.get("name")
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise NotFoundException(detail=msg) from e
        raise ClientException(detail=msg) from e


@get("/conversations/{conversation_id:str}/branches", sync_to_thread=False)
def list_conversation_branches(conversation_id: str) -> dict[str, Any]:
    branches = ConversationBranchService.get_conversation_branches(conversation_id)
    return {"branches": branches, "total": len(branches)}


@get("/conversations/{conversation_id:str}/branches/tree", sync_to_thread=False)
def get_branch_tree(conversation_id: str) -> Any:
    return ConversationBranchService.get_branch_tree(conversation_id)


@get("/branches/{branch_id:str}/messages", sync_to_thread=False)
def get_branch_messages(branch_id: str) -> dict[str, Any]:
    try:
        messages = ConversationBranchService.get_branch_messages(branch_id)
    except ValueError as e:
        raise NotFoundException(detail=str(e)) from e
    return {"messages": messages, "total": len(messages)}


@post("/branches/{branch_id:str}/messages", status_code=201, sync_to_thread=False)
def add_branch_message(branch_id: str, data: dict) -> Any:
    body = data or {}
    role = body.get("role")
    content = body.get("content")
    if not role or not content:
        raise ClientException(detail="Missing required fields: role, content")
    try:
        return ConversationBranchService.add_message(branch_id, role, content)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise NotFoundException(detail=msg) from e
        raise ClientException(detail=msg) from e


conversation_branches_router = Router(
    path="/admin",
    route_handlers=[
        create_branch,
        list_conversation_branches,
        get_branch_tree,
        get_branch_messages,
        add_branch_message,
    ],
)
