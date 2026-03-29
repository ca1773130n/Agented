"""Knowledge graph operations — entities, relations, traversal."""

import json
import logging

from .connection import get_connection
from .ids import generate_kg_entity_id, generate_kg_relation_id

logger = logging.getLogger(__name__)


def upsert_entity(
    agent_id: str,
    name: str,
    entity_type: str = "concept",
    properties: dict | None = None,
) -> dict:
    """Insert or update a KG entity. Increments mention_count on conflict."""
    props_json = json.dumps(properties) if properties else "{}"
    entity_id = generate_kg_entity_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO kg_entities (id, agent_id, name, entity_type, properties)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(agent_id, name, entity_type) DO UPDATE SET
                   mention_count = kg_entities.mention_count + 1,
                   last_seen = CURRENT_TIMESTAMP,
                   properties = CASE
                       WHEN excluded.properties != '{}' THEN excluded.properties
                       ELSE kg_entities.properties
                   END""",
            (entity_id, agent_id, name.lower().strip(), entity_type, props_json),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM kg_entities WHERE agent_id = ? AND name = ? AND entity_type = ?",
            (agent_id, name.lower().strip(), entity_type),
        )
        row = cursor.fetchone()
        return _entity_row_to_dict(row) if row else {}


def upsert_relation(
    agent_id: str,
    source_name: str,
    source_type: str,
    target_name: str,
    target_type: str,
    relation_type: str,
    confidence: float = 0.5,
    properties: dict | None = None,
) -> dict | None:
    """Create or update a relation between two entities."""
    # Ensure both entities exist
    source = upsert_entity(agent_id, source_name, source_type)
    target = upsert_entity(agent_id, target_name, target_type)
    if not source or not target:
        return None

    props_json = json.dumps(properties) if properties else "{}"
    relation_id = generate_kg_relation_id()
    with get_connection() as conn:
        # Check for existing relation
        cursor = conn.execute(
            """SELECT id, mention_count FROM kg_relations
               WHERE agent_id = ? AND source_id = ? AND target_id = ? AND relation_type = ?""",
            (agent_id, source["id"], target["id"], relation_type),
        )
        existing = cursor.fetchone()
        if existing:
            conn.execute(
                """UPDATE kg_relations SET
                       mention_count = mention_count + 1,
                       last_seen = CURRENT_TIMESTAMP,
                       confidence = MAX(confidence, ?)
                   WHERE id = ?""",
                (confidence, existing["id"]),
            )
            conn.commit()
            cursor = conn.execute("SELECT * FROM kg_relations WHERE id = ?", (existing["id"],))
            row = cursor.fetchone()
            return _relation_row_to_dict(row) if row else None
        else:
            conn.execute(
                """INSERT INTO kg_relations
                       (id, agent_id, source_id, target_id, relation_type, properties, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    relation_id,
                    agent_id,
                    source["id"],
                    target["id"],
                    relation_type,
                    props_json,
                    confidence,
                ),
            )
            conn.commit()
            cursor = conn.execute("SELECT * FROM kg_relations WHERE id = ?", (relation_id,))
            row = cursor.fetchone()
            return _relation_row_to_dict(row) if row else None


def get_entity(agent_id: str, name: str, entity_type: str | None = None) -> dict | None:
    """Get a single entity by name."""
    with get_connection() as conn:
        if entity_type:
            cursor = conn.execute(
                "SELECT * FROM kg_entities WHERE agent_id = ? AND name = ? AND entity_type = ?",
                (agent_id, name.lower().strip(), entity_type),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM kg_entities "
                "WHERE agent_id = ? AND name = ? ORDER BY mention_count DESC",
                (agent_id, name.lower().strip()),
            )
        row = cursor.fetchone()
        return _entity_row_to_dict(row) if row else None


def list_entities(
    agent_id: str,
    entity_type: str | None = None,
    min_importance: float = 0.0,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List entities for an agent, optionally filtered."""
    with get_connection() as conn:
        params: list = [agent_id, min_importance]
        type_filter = ""
        if entity_type:
            type_filter = "AND entity_type = ?"
            params.append(entity_type)
        params.extend([limit, offset])
        cursor = conn.execute(
            f"""SELECT * FROM kg_entities
                WHERE agent_id = ? AND importance_score >= ?
                {type_filter}
                ORDER BY importance_score DESC, mention_count DESC
                LIMIT ? OFFSET ?""",
            params,
        )
        return [_entity_row_to_dict(row) for row in cursor.fetchall()]


def count_entities(agent_id: str) -> int:
    """Count entities for an agent."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM kg_entities WHERE agent_id = ?", (agent_id,))
        return cursor.fetchone()[0]


def count_relations(agent_id: str) -> int:
    """Count relations for an agent."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM kg_relations WHERE agent_id = ?", (agent_id,))
        return cursor.fetchone()[0]


def get_entity_relations(entity_id: str) -> list[dict]:
    """Get all relations for an entity (both incoming and outgoing)."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT r.*,
                      se.name as source_name, se.entity_type as source_entity_type,
                      te.name as target_name, te.entity_type as target_entity_type
               FROM kg_relations r
               JOIN kg_entities se ON se.id = r.source_id
               JOIN kg_entities te ON te.id = r.target_id
               WHERE r.source_id = ? OR r.target_id = ?
               ORDER BY r.mention_count DESC""",
            (entity_id, entity_id),
        )
        results = []
        for row in cursor.fetchall():
            d = _relation_row_to_dict(row)
            d["source_name"] = row["source_name"]
            d["source_entity_type"] = row["source_entity_type"]
            d["target_name"] = row["target_name"]
            d["target_entity_type"] = row["target_entity_type"]
            results.append(d)
        return results


def traverse_graph(
    agent_id: str,
    entity_name: str,
    hops: int = 1,
) -> dict:
    """BFS traversal from a seed entity. Returns subgraph as {entities, relations}."""
    seed = get_entity(agent_id, entity_name)
    if not seed:
        return {"entities": [], "relations": []}

    visited_entities: dict[str, dict] = {seed["id"]: seed}
    visited_relations: dict[str, dict] = {}
    frontier: set[str] = {seed["id"]}

    with get_connection() as conn:
        for _ in range(hops):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for eid in frontier:
                cursor = conn.execute(
                    """SELECT r.*, se.name as source_name, te.name as target_name
                       FROM kg_relations r
                       JOIN kg_entities se ON se.id = r.source_id
                       JOIN kg_entities te ON te.id = r.target_id
                       WHERE (r.source_id = ? OR r.target_id = ?)
                             AND r.agent_id = ?""",
                    (eid, eid, agent_id),
                )
                for row in cursor.fetchall():
                    rel = _relation_row_to_dict(row)
                    visited_relations[rel["id"]] = rel

                    # Add neighbor entities
                    for neighbor_id in [rel["source_id"], rel["target_id"]]:
                        if neighbor_id not in visited_entities:
                            ecursor = conn.execute(
                                "SELECT * FROM kg_entities WHERE id = ?",
                                (neighbor_id,),
                            )
                            erow = ecursor.fetchone()
                            if erow:
                                visited_entities[neighbor_id] = _entity_row_to_dict(erow)
                                next_frontier.add(neighbor_id)
            frontier = next_frontier

    return {
        "entities": list(visited_entities.values()),
        "relations": list(visited_relations.values()),
    }


def search_entities(agent_id: str, query: str, limit: int = 10) -> list[dict]:
    """Search entities by name pattern."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT * FROM kg_entities
               WHERE agent_id = ? AND name LIKE ?
               ORDER BY importance_score DESC, mention_count DESC
               LIMIT ?""",
            (agent_id, f"%{query.lower().strip()}%", limit),
        )
        return [_entity_row_to_dict(row) for row in cursor.fetchall()]


def get_entity_context(agent_id: str, entity_names: list[str]) -> str:
    """Generate natural language summary of entity relationships."""
    if not entity_names:
        return ""
    lines: list[str] = []
    for name in entity_names:
        entity = get_entity(agent_id, name)
        if not entity:
            continue
        relations = get_entity_relations(entity["id"])
        if not relations:
            lines.append(f"- {entity['name']} ({entity['entity_type']})")
            continue
        for rel in relations[:5]:  # Limit to 5 relations per entity
            src = rel.get("source_name", "?")
            tgt = rel.get("target_name", "?")
            lines.append(f"- {src} --[{rel['relation_type']}]--> {tgt}")
    return "\n".join(lines) if lines else ""


def promote_entity(entity_id: str, boost: float = 0.05) -> None:
    """Increase importance of an entity (e.g., when it appears in recall results)."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE kg_entities SET
                   importance_score = MIN(1.0, importance_score + ?),
                   mention_count = mention_count + 1,
                   last_seen = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (boost, entity_id),
        )
        conn.commit()


def delete_entity(entity_id: str) -> bool:
    """Delete an entity and its relations (CASCADE)."""
    with get_connection() as conn:
        # Delete relations first (in case CASCADE isn't enforced)
        conn.execute(
            "DELETE FROM kg_relations WHERE source_id = ? OR target_id = ?",
            (entity_id, entity_id),
        )
        cursor = conn.execute("DELETE FROM kg_entities WHERE id = ?", (entity_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- Helpers ---


def _entity_row_to_dict(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    if d.get("properties"):
        try:
            d["properties"] = json.loads(d["properties"])
        except (json.JSONDecodeError, TypeError):
            d["properties"] = {}
    return d


def _relation_row_to_dict(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    if d.get("properties"):
        try:
            d["properties"] = json.loads(d["properties"])
        except (json.JSONDecodeError, TypeError):
            d["properties"] = {}
    return d
