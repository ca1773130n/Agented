"""Knowledge graph API endpoints — entities, relations, graph traversal."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.agents import get_agent
from ..db.knowledge_graph import (
    count_entities,
    count_relations,
    delete_entity,
    get_entity_relations,
    list_entities,
    search_entities,
    traverse_graph,
    _entity_row_to_dict,
)
from ..models.knowledge_graph import KGAgentPath, KGEntityPath, KGGraphQuery

tag = Tag(name="knowledge-graph", description="Agent knowledge graph — entities and relations")
knowledge_graph_bp = APIBlueprint("knowledge_graph", __name__, url_prefix="/admin", abp_tags=[tag])


def _validate_agent(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        return None, error_response("NOT_FOUND", "Agent not found", HTTPStatus.NOT_FOUND)
    return agent, None


@knowledge_graph_bp.get("/agents/<agent_id>/knowledge/entities")
def list_agent_entities(path: KGAgentPath):
    """List knowledge graph entities for an agent."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    entities = list_entities(path.agent_id)
    total = count_entities(path.agent_id)
    return {"entities": entities, "total": total}, HTTPStatus.OK


@knowledge_graph_bp.get("/agents/<agent_id>/knowledge/entities/<entity_id>")
def get_agent_entity(path: KGEntityPath):
    """Get an entity with its relations."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    from ..db.connection import get_connection

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM kg_entities WHERE id = ? AND agent_id = ?",
            (path.entity_id, path.agent_id),
        )
        row = cursor.fetchone()
    if not row:
        return error_response("NOT_FOUND", "Entity not found", HTTPStatus.NOT_FOUND)
    entity = _entity_row_to_dict(row)
    entity["relations"] = get_entity_relations(path.entity_id)
    return entity, HTTPStatus.OK


@knowledge_graph_bp.get("/agents/<agent_id>/knowledge/graph")
def query_agent_graph(path: KGAgentPath, query: KGGraphQuery):
    """Traverse knowledge graph from a seed entity."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    subgraph = traverse_graph(path.agent_id, query.seed, query.hops)
    return subgraph, HTTPStatus.OK


@knowledge_graph_bp.get("/agents/<agent_id>/knowledge/search")
def search_agent_entities(path: KGAgentPath):
    """Search entities by name pattern."""
    from flask import request

    q = request.args.get("q", "")
    if not q:
        return {"entities": [], "total": 0}, HTTPStatus.OK
    entities = search_entities(path.agent_id, q)
    return {"entities": entities, "total": len(entities)}, HTTPStatus.OK


@knowledge_graph_bp.get("/agents/<agent_id>/knowledge/stats")
def get_agent_kg_stats(path: KGAgentPath):
    """Get knowledge graph statistics."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    entity_count = count_entities(path.agent_id)
    relation_count = count_relations(path.agent_id)
    top = list_entities(path.agent_id, limit=10)
    # Get last consolidation
    from ..db.connection import get_connection

    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT created_at FROM memory_consolidation_log
               WHERE agent_id = ? ORDER BY created_at DESC LIMIT 1""",
            (path.agent_id,),
        )
        row = cursor.fetchone()
        last_consolidation = row["created_at"] if row else None
    return {
        "entity_count": entity_count,
        "relation_count": relation_count,
        "top_entities": top,
        "last_consolidation": last_consolidation,
    }, HTTPStatus.OK


@knowledge_graph_bp.post("/agents/<agent_id>/knowledge/consolidate")
def trigger_consolidation(path: KGAgentPath):
    """Manually trigger memory consolidation for an agent."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    from ..db.agent_memory import list_threads
    from ..services.memory_evolution import consolidate_thread

    threads = list_threads(path.agent_id, "agent")
    results = []
    for thread in threads:
        result = consolidate_thread(path.agent_id, thread["id"])
        if result:
            results.append(result)
    return {
        "consolidated": len(results),
        "details": results,
    }, HTTPStatus.OK


@knowledge_graph_bp.delete("/agents/<agent_id>/knowledge/entities/<entity_id>")
def delete_agent_entity(path: KGEntityPath):
    """Delete an entity and its relations."""
    agent, err = _validate_agent(path.agent_id)
    if err:
        return err
    deleted = delete_entity(path.entity_id)
    if not deleted:
        return error_response("NOT_FOUND", "Entity not found", HTTPStatus.NOT_FOUND)
    return {"message": f"Entity {path.entity_id} deleted"}, HTTPStatus.OK
