"""Wave 68 — leaf CRUD batch D (~32 routes).

knowledge_graph + collaborative + campaigns + execution_tagging + pr_assignment.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.db.agents import get_agent
from app.db.campaigns import (
    delete_campaign,
    get_campaign,
    list_campaign_executions,
    list_campaigns,
)
from app.db.execution_tags import (
    add_tag_to_execution,
    create_tag,
    delete_tag,
    get_executions_with_tags,
    list_tags,
    remove_tag_from_execution,
)
from app.db.knowledge_graph import (
    _entity_row_to_dict,
    count_entities,
    count_relations,
    delete_entity,
    get_entity_relations,
    list_entities,
    search_entities,
    traverse_graph,
)
from app.db.pr_assignment import (
    add_ownership_rule,
    delete_ownership_rule,
    get_ownership_rules,
)
from app.db.settings import get_setting, set_setting
from app.db.triggers import get_pr_reviews_for_trigger
from app.db.viewer_comments import delete_comment as db_delete_comment
from app.db.viewer_comments import get_comment
from app_litestar.route_helpers import MAX_LIST_LIMIT, clamp_limit
from app.services.campaign_service import get_campaign_results, start_campaign
from app.services.collaborative_viewer_service import CollaborativeViewerService
from app_litestar.auth import Caller

# 07.M4 — bound the campaign name length.
_NAME_MAX_LEN = 255


# ===========================================================================
# /admin/agents/{id}/knowledge/* (7)
# ===========================================================================


def _ensure_agent(agent_id: str) -> None:
    if not get_agent(agent_id):
        raise NotFoundException(detail="Agent not found")


@get("/{agent_id:str}/knowledge/entities", sync_to_thread=False)
def list_kg_entities(agent_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    entities = list_entities(agent_id)
    return {"entities": entities, "total": count_entities(agent_id)}


@get("/{agent_id:str}/knowledge/entities/{entity_id:str}", sync_to_thread=False)
def get_kg_entity(agent_id: str, entity_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    from app.db.connection import get_connection

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM kg_entities WHERE id = ? AND agent_id = ?",
            (entity_id, agent_id),
        )
        row = cursor.fetchone()
    if not row:
        raise NotFoundException(detail="Entity not found")
    entity = _entity_row_to_dict(row)
    entity["relations"] = get_entity_relations(entity_id)
    return entity


@get("/{agent_id:str}/knowledge/graph", sync_to_thread=False)
def query_kg_graph(agent_id: str, seed: str = "", hops: int = 2) -> Any:
    _ensure_agent(agent_id)
    return traverse_graph(agent_id, seed, hops)


@get("/{agent_id:str}/knowledge/search", sync_to_thread=False)
def search_kg_entities(agent_id: str, q: str = "") -> dict[str, Any]:
    if not q:
        return {"entities": [], "total": 0}
    entities = search_entities(agent_id, q)
    return {"entities": entities, "total": len(entities)}


@get("/{agent_id:str}/knowledge/stats", sync_to_thread=False)
def kg_stats(agent_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    from app.db.connection import get_connection

    entity_count = count_entities(agent_id)
    relation_count = count_relations(agent_id)
    top = list_entities(agent_id, limit=10)
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT created_at FROM memory_consolidation_log "
            "WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        row = cursor.fetchone()
        last_consolidation = row["created_at"] if row else None
    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "top_entities": top,
        "last_consolidation": last_consolidation,
    }


@post("/{agent_id:str}/knowledge/consolidate", sync_to_thread=False)
def consolidate_kg(agent_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    from app.db.agent_memory import list_threads
    from app.services.memory_evolution import consolidate_thread

    threads = list_threads(agent_id, "agent")
    results = []
    for thread in threads:
        result = consolidate_thread(agent_id, thread["id"])
        if result:
            results.append(result)
    return {"consolidated": len(results), "details": results}


@delete(
    "/{agent_id:str}/knowledge/entities/{entity_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def delete_kg_entity(agent_id: str, entity_id: str) -> dict[str, Any]:
    _ensure_agent(agent_id)
    if not delete_entity(entity_id):
        raise NotFoundException(detail="Entity not found")
    return {"message": f"Entity {entity_id} deleted"}


knowledge_graph_router = Router(
    path="/admin/agents",
    route_handlers=[
        list_kg_entities,
        get_kg_entity,
        query_kg_graph,
        search_kg_entities,
        kg_stats,
        consolidate_kg,
        delete_kg_entity,
    ],
)


# ===========================================================================
# /admin/executions/{id}/viewers + /comments — collaborative (7)
# ===========================================================================


def _viewer_id_from_caller(caller: Caller, data: dict) -> str:
    """07.M1 — derive the viewer id from the authenticated caller, never from
    the request body (impersonation guard). Falls back to a body-supplied id
    only in bootstrap mode (no authenticated user)."""
    if caller.user_id:
        return caller.user_id
    body_id = (data or {}).get("viewer_id")
    if not body_id:
        raise ClientException(detail="viewer_id is required")
    return body_id


@post("/executions/{execution_id:str}/viewers/join", sync_to_thread=False)
def viewer_join(execution_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    viewer_id = _viewer_id_from_caller(caller, data)
    name = (data or {}).get("name")
    if not name:
        raise ClientException(detail="name is required")
    return {"viewers": CollaborativeViewerService.join(execution_id, viewer_id, name)}


@post("/executions/{execution_id:str}/viewers/leave", sync_to_thread=False)
def viewer_leave(execution_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    viewer_id = _viewer_id_from_caller(caller, data)
    CollaborativeViewerService.leave(execution_id, viewer_id)
    return {"status": "left"}


@post("/executions/{execution_id:str}/viewers/heartbeat", sync_to_thread=False)
def viewer_heartbeat(execution_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    viewer_id = _viewer_id_from_caller(caller, data)
    CollaborativeViewerService.heartbeat(execution_id, viewer_id)
    return {"status": "ok"}


@get("/executions/{execution_id:str}/viewers", sync_to_thread=False)
def list_viewers(execution_id: str) -> dict[str, Any]:
    return {"viewers": CollaborativeViewerService.get_viewers(execution_id)}


@post("/executions/{execution_id:str}/comments", status_code=201, sync_to_thread=False)
def post_inline_comment(execution_id: str, data: dict, caller: Caller) -> Any:
    body = data or {}
    # 07.M1 — author the comment as the authenticated caller, not body-supplied
    # viewer_id (impersonation guard). viewer_name remains a display label.
    viewer_id = _viewer_id_from_caller(caller, body)
    viewer_name = body.get("viewer_name") or viewer_id
    line_number = body.get("line_number")
    content = body.get("content")
    if not content or line_number is None:
        raise ClientException(detail="line_number and content are required")
    try:
        return CollaborativeViewerService.post_comment(
            execution_id=execution_id,
            viewer_id=viewer_id,
            viewer_name=viewer_name,
            line_number=int(line_number),
            content=content,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@get("/executions/{execution_id:str}/comments", sync_to_thread=False)
def list_comments(execution_id: str) -> dict[str, Any]:
    return {"comments": CollaborativeViewerService.get_execution_comments(execution_id)}


@delete("/comments/{comment_id:str}", status_code=200, sync_to_thread=False)
def delete_inline_comment(comment_id: str) -> dict[str, Any]:
    if not get_comment(comment_id):
        raise NotFoundException(detail="Comment not found")
    db_delete_comment(comment_id)
    return {"status": "deleted"}


collaborative_router = Router(
    path="/admin",
    route_handlers=[
        viewer_join,
        viewer_leave,
        viewer_heartbeat,
        list_viewers,
        post_inline_comment,
        list_comments,
        delete_inline_comment,
    ],
)


# ===========================================================================
# /admin/campaigns/* + /admin/triggers/{id}/campaigns (6)
# ===========================================================================


@post("/campaigns", status_code=201, sync_to_thread=False)
def create_campaign(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = data.get("name")
    trigger_id = data.get("trigger_id")
    repo_urls = data.get("repo_urls", [])
    if not name or not trigger_id:
        raise ClientException(detail="name and trigger_id are required")
    if len(name) > _NAME_MAX_LEN:  # 07.M4 — bound name length
        raise ClientException(detail=f"name must be at most {_NAME_MAX_LEN} characters")
    campaign_id = start_campaign(name=name, trigger_id=trigger_id, repo_urls=repo_urls)
    if not campaign_id:
        raise HTTPException(status_code=500, detail="Failed to create campaign")
    return {"campaign": get_campaign(campaign_id)}


@get("/campaigns", sync_to_thread=False)
def list_all_campaigns(
    trigger_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    items = list_campaigns(trigger_id=trigger_id, status=status)
    total = len(items)
    # 07.M2 — list_campaigns has no limit param; slice at the route layer.
    capped = clamp_limit(limit, default=MAX_LIST_LIMIT)
    start = max(offset, 0)
    return {"campaigns": items[start : start + capped], "total": total}


@get("/campaigns/{campaign_id:str}", sync_to_thread=False)
def get_campaign_detail(campaign_id: str) -> dict[str, Any]:
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise NotFoundException(detail="Campaign not found")
    return {"campaign": campaign, "executions": list_campaign_executions(campaign_id)}


@get("/campaigns/{campaign_id:str}/results", sync_to_thread=False)
def campaign_results(campaign_id: str) -> Any:
    results = get_campaign_results(campaign_id)
    if not results:
        raise NotFoundException(detail="Campaign not found")
    return results


@delete("/campaigns/{campaign_id:str}", status_code=200, sync_to_thread=False)
def delete_campaign_endpoint(campaign_id: str) -> dict[str, Any]:
    if not delete_campaign(campaign_id):
        raise NotFoundException(detail="Campaign not found")
    return {"deleted": True}


@get("/triggers/{trigger_id:str}/campaigns", sync_to_thread=False)
def list_trigger_campaigns(trigger_id: str) -> dict[str, Any]:
    items = list_campaigns(trigger_id=trigger_id)
    return {"campaigns": items, "total": len(items)}


campaigns_router = Router(
    path="/admin",
    route_handlers=[
        create_campaign,
        list_all_campaigns,
        get_campaign_detail,
        campaign_results,
        delete_campaign_endpoint,
        list_trigger_campaigns,
    ],
)


# ===========================================================================
# /admin/execution-tags/* + /admin/execution-tagging/* (6)
# ===========================================================================


_VALID_TAG_COLORS = {"blue", "green", "amber", "red", "purple"}


@get("/execution-tags", sync_to_thread=False)
def list_execution_tags(limit: Optional[int] = None, offset: int = 0) -> dict[str, Any]:
    tags = list_tags()
    total = len(tags)
    # 07.M2 — list_tags has no limit param; slice at the route layer.
    capped = clamp_limit(limit, default=MAX_LIST_LIMIT)
    start = max(offset, 0)
    return {"tags": tags[start : start + capped], "total": total}


@post("/execution-tags", status_code=201, sync_to_thread=False)
def create_execution_tag(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    color = (data.get("color") or "blue").strip()
    if not name:
        raise ClientException(detail="name is required")
    if color not in _VALID_TAG_COLORS:
        raise ClientException(
            detail=f"color must be one of: {', '.join(sorted(_VALID_TAG_COLORS))}"
        )
    result = create_tag(name=name, color=color)
    if result is None:
        raise HTTPException(status_code=409, detail=f"A tag named '{name}' already exists")
    return {"tag": result}


@delete("/execution-tags/{tag_id:str}", status_code=200, sync_to_thread=False)
def delete_execution_tag(tag_id: str) -> dict[str, Any]:
    if not delete_tag(tag_id):
        raise NotFoundException(detail="Tag not found")
    return {"message": "Tag deleted"}


@get("/execution-tagging", sync_to_thread=False)
def list_tagged_executions(
    tag_ids: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = clamp_limit(limit, default=50)
    ids = [t.strip() for t in tag_ids.split(",") if t.strip()] if tag_ids else None
    executions = get_executions_with_tags(limit=limit, offset=offset, tag_ids=ids)
    return {"executions": executions, "total": len(executions)}


@post(
    "/execution-tagging/{execution_id:str}/tags",
    status_code=201,
    sync_to_thread=False,
)
def add_tag_to_execution_endpoint(execution_id: str, data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    tag_id = (data.get("tag_id") or "").strip()
    if not tag_id:
        raise ClientException(detail="tag_id is required")
    if not add_tag_to_execution(tag_id=tag_id, execution_id=execution_id):
        raise ClientException(
            detail="Failed to add tag — tag or execution may not exist, or tag already applied"
        )
    return {"message": "Tag added to execution"}


@delete(
    "/execution-tagging/{execution_id:str}/tags/{tag_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def remove_tag_from_execution_endpoint(execution_id: str, tag_id: str) -> dict[str, Any]:
    if not remove_tag_from_execution(tag_id=tag_id, execution_id=execution_id):
        raise NotFoundException(detail="Tag assignment not found for this execution")
    return {"message": "Tag removed from execution"}


execution_tagging_router = Router(
    path="/admin",
    route_handlers=[
        list_execution_tags,
        create_execution_tag,
        delete_execution_tag,
        list_tagged_executions,
        add_tag_to_execution_endpoint,
        remove_tag_from_execution_endpoint,
    ],
)


# ===========================================================================
# /api/pr-assignment/* (6)
# ===========================================================================


_PR_ASSIGNMENT_KEYS = [
    "pr_assignment_enabled",
    "pr_assignment_min_confidence",
    "pr_assignment_max_reviewers",
]


@get("/rules", sync_to_thread=False)
def list_pr_rules() -> dict[str, Any]:
    return {"rules": get_ownership_rules()}


@post("/rules", status_code=201, sync_to_thread=False)
def create_pr_rule(data: dict) -> dict[str, Any]:
    body = data or {}
    pattern = (body.get("pattern") or "").strip()
    team = (body.get("team") or "").strip()
    reviewers = body.get("reviewers", [])
    # 07.L4 — clamp priority to a sane non-negative range (avoid overflow / abuse).
    try:
        priority = int(body.get("priority", 0))
    except (TypeError, ValueError):
        priority = 0
    priority = max(0, min(priority, 1000))
    if not pattern or not team:
        raise ClientException(detail="pattern and team are required")
    if isinstance(reviewers, str):
        reviewers = [r.strip() for r in reviewers.split(",") if r.strip()]
    rule_id = add_ownership_rule(pattern=pattern, team=team, reviewers=reviewers, priority=priority)
    return {
        "id": rule_id,
        "pattern": pattern,
        "team": team,
        "reviewers": reviewers,
        "priority": priority,
    }


@delete("/rules/{rule_id:str}", status_code=200, sync_to_thread=False)
def delete_pr_rule(rule_id: str) -> dict[str, Any]:
    if not delete_ownership_rule(rule_id):
        raise NotFoundException(detail="Rule not found")
    return {"deleted": True, "id": rule_id}


@get("/settings", sync_to_thread=False)
def get_pr_settings() -> dict[str, str]:
    result = {key: get_setting(key) for key in _PR_ASSIGNMENT_KEYS}
    if result["pr_assignment_enabled"] is None:
        result["pr_assignment_enabled"] = "true"
    if result["pr_assignment_min_confidence"] is None:
        result["pr_assignment_min_confidence"] = "70"
    if result["pr_assignment_max_reviewers"] is None:
        result["pr_assignment_max_reviewers"] = "2"
    return result


@put("/settings", sync_to_thread=False)
def update_pr_settings(data: dict) -> dict[str, Any]:
    body = data or {}
    updated: dict[str, str] = {}
    for key in _PR_ASSIGNMENT_KEYS:
        if key in body:
            set_setting(key, str(body[key]))
            updated[key] = str(body[key])
    return {"updated": updated}


@get("/recent", sync_to_thread=False)
def list_recent_assignments(limit: int = 20) -> dict[str, Any]:
    limit = clamp_limit(limit, default=20)
    reviews = get_pr_reviews_for_trigger(limit=limit)
    assignments = [
        {
            "id": str(r["id"]),
            "prNumber": r.get("pr_number"),
            "prTitle": r.get("pr_title", ""),
            "assignedTo": [r["pr_author"]] if r.get("pr_author") else [],
            "reason": r.get("review_comment") or "Matched ownership rule",
            "confidence": 80,
            "timestamp": r.get("created_at", ""),
        }
        for r in reviews
    ]
    return {"assignments": assignments}


pr_assignment_router = Router(
    path="/api/pr-assignment",
    route_handlers=[
        list_pr_rules,
        create_pr_rule,
        delete_pr_rule,
        get_pr_settings,
        update_pr_settings,
        list_recent_assignments,
    ],
)
