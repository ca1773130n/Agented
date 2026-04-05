"""Memory evolution engine — entity extraction, consolidation, decay, cross-thread synthesis."""

import logging
import math
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Decay constants
HALF_LIFE_DAYS = 30
BASE_LAMBDA = math.log(2) / HALF_LIFE_DAYS
ARCHIVE_THRESHOLD = 0.1


def extract_entities_from_text(text: str) -> list[dict]:
    """Extract entities and relations from text using regex patterns.

    Returns list of {name, type, relations: [{target, relation_type}]}.
    This is the fast, synchronous extraction path. LLM-based extraction
    can be added as an async enhancement later.
    """
    entities = []
    seen: set[str] = set()

    # Pattern-based extraction for common entity types
    patterns = {
        "technology": (
            r"\b(?:Python|JavaScript|TypeScript|React|Vue|Flask|Django|"
            r"SQLite|PostgreSQL|Redis|Docker|Kubernetes|Git|GitHub|"
            r"LangChain|LangGraph|OpenAI|Anthropic|Claude|GPT|"
            r"RAG|CRAG|FTS5|BM25|RRF|NER|LLM|API|CLI|MCP|SSE)\b"
        ),
        "tool": (
            r"\b(?:pytest|ruff|vite|vitest|npm|pip|uv|gunicorn|nginx|"
            r"sentence-transformers|APScheduler|Pydantic|playwright)\b"
        ),
        "concept": (
            r"\b(?:webhook|endpoint|blueprint|middleware|scheduler|"
            r"embedding|vector|knowledge graph|entity extraction|"
            r"consolidation|decay|recall|retrieval|orchestrator)\b"
        ),
    }

    for entity_type, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            name = match.group(0).lower().strip()
            if name not in seen and len(name) > 1:
                seen.add(name)
                entities.append(
                    {
                        "name": name,
                        "type": entity_type,
                        "relations": [],
                    }
                )

    # Extract simple co-occurrence relations
    for i, e1 in enumerate(entities):
        for e2 in entities[i + 1 :]:
            e1["relations"].append(
                {
                    "target": e2["name"],
                    "target_type": e2["type"],
                    "relation_type": "co_occurs_with",
                }
            )

    return entities


def process_message_entities(agent_id: str, message_content: str) -> int:
    """Extract entities from a message and upsert them into the KG.

    Returns number of entities processed.
    """
    from ..db.knowledge_graph import upsert_entity, upsert_relation

    entities = extract_entities_from_text(message_content)
    count = 0

    for entity_data in entities:
        try:
            upsert_entity(agent_id, entity_data["name"], entity_data["type"])
            count += 1

            for rel in entity_data.get("relations", []):
                try:
                    upsert_relation(
                        agent_id=agent_id,
                        source_name=entity_data["name"],
                        source_type=entity_data["type"],
                        target_name=rel["target"],
                        target_type=rel.get("target_type", "concept"),
                        relation_type=rel["relation_type"],
                        confidence=0.3,  # Co-occurrence is low confidence
                    )
                except Exception as e:
                    logger.debug("Failed to upsert relation: %s", e)
        except Exception as e:
            logger.debug("Failed to upsert entity %s: %s", entity_data["name"], e)

    return count


def process_pending_extractions(batch_size: int = 10) -> int:
    """Process messages that haven't had entity extraction yet.

    Designed to be called by APScheduler periodically.
    Returns total entities extracted.
    """
    from ..db.connection import get_connection

    total = 0
    with get_connection() as conn:
        # Get agent_ids with pending messages (via thread lookup)
        cursor = conn.execute(
            """SELECT DISTINCT t.resource_id as agent_id, m.id, m.content
               FROM memory_messages m
               JOIN memory_threads t ON t.id = m.thread_id
               WHERE m.id NOT IN (SELECT message_id FROM kg_extraction_log)
               AND t.resource_type = 'agent'
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (batch_size,),
        )
        pending = cursor.fetchall()

    for row in pending:
        agent_id = row["agent_id"]
        msg_id = row["id"]
        content = row["content"]

        try:
            count = process_message_entities(agent_id, content)
            total += count
            # Mark as processed
            with get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO kg_extraction_log (message_id) VALUES (?)",
                    (msg_id,),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Entity extraction failed for message %s: %s", msg_id, e)

    if total > 0:
        logger.info("Extracted %d entities from %d messages", total, len(pending))
    return total


def apply_decay(agent_id: str) -> int:
    """Apply exponential importance decay to all entities for an agent.

    decay formula: importance *= exp(-effective_lambda * days_since_seen)
    effective_lambda = BASE_LAMBDA / log(1 + mention_count)

    Archives entities below ARCHIVE_THRESHOLD.
    Returns number of entities decayed.
    """
    from ..db.connection import get_connection

    count = 0
    now = datetime.utcnow()

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, importance_score, mention_count, last_seen "
            "FROM kg_entities WHERE agent_id = ?",
            (agent_id,),
        )
        entities = cursor.fetchall()

        for entity in entities:
            last_seen_str = entity["last_seen"]
            if not last_seen_str:
                continue

            try:
                # Parse last_seen timestamp
                if "T" in last_seen_str:
                    last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
                    last_seen = last_seen.replace(tzinfo=None)
                else:
                    last_seen = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue

            days_since = (now - last_seen).total_seconds() / 86400
            if days_since < 1:
                continue

            mention_count = entity["mention_count"] or 1
            effective_lambda = BASE_LAMBDA / math.log(1 + mention_count)
            decay_factor = math.exp(-effective_lambda * days_since)
            new_importance = entity["importance_score"] * decay_factor

            if new_importance < ARCHIVE_THRESHOLD:
                # Archive (soft delete by setting importance to 0)
                conn.execute(
                    "UPDATE kg_entities SET importance_score = 0 WHERE id = ?",
                    (entity["id"],),
                )
            else:
                conn.execute(
                    "UPDATE kg_entities SET importance_score = ? WHERE id = ?",
                    (round(new_importance, 4), entity["id"]),
                )
            count += 1

        if count > 0:
            conn.commit()
            logger.info("Applied decay to %d entities for agent %s", count, agent_id)

    return count


def should_consolidate(agent_id: str, thread_id: str, threshold: int = 50) -> bool:
    """Check if consolidation should run (AND logic: count + time floor)."""
    from ..db.agent_memory import count_messages
    from ..db.connection import get_connection

    msg_count = count_messages(thread_id)
    if msg_count < threshold:
        return False

    # Check if enough time has passed since last consolidation
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT created_at FROM memory_consolidation_log
               WHERE agent_id = ? AND thread_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (agent_id, thread_id),
        )
        row = cursor.fetchone()

    if row:
        try:
            last = row["created_at"]
            if "T" in last:
                last_time = datetime.fromisoformat(last.replace("Z", "+00:00"))
                last_time = last_time.replace(tzinfo=None)
            else:
                last_time = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")

            # Must be at least 1 hour since last consolidation
            if datetime.utcnow() - last_time < timedelta(hours=1):
                return False

            # Check if enough new messages since last consolidation
            # Simple heuristic: if msg_count mod threshold is near 0
            if msg_count % threshold > 5:
                return False
        except (ValueError, TypeError):
            pass

    return True


def consolidate_thread(agent_id: str, thread_id: str) -> dict | None:
    """Summarize a thread and log the consolidation.

    Extracts entities from all unprocessed messages and creates a
    consolidation record.
    """
    from ..db.agent_memory import get_messages
    from ..db.connection import get_connection
    from ..db.ids import generate_consolidation_id

    messages = get_messages(thread_id, limit=100)
    if not messages:
        return None

    # Process entities from all messages
    total_entities = 0
    for msg in messages:
        total_entities += process_message_entities(agent_id, msg.get("content", ""))

    # Create consolidation log entry
    consolidation_id = generate_consolidation_id()
    summary = f"Consolidated {len(messages)} messages, extracted {total_entities} entities"

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO memory_consolidation_log
               (id, agent_id, thread_id, consolidation_type, summary,
                entity_count)
               VALUES (?, ?, ?, 'entity_extraction', ?, ?)""",
            (consolidation_id, agent_id, thread_id, summary, total_entities),
        )
        conn.commit()

    logger.info("Consolidated thread %s: %s", thread_id, summary)
    return {
        "id": consolidation_id,
        "agent_id": agent_id,
        "thread_id": thread_id,
        "summary": summary,
        "entity_count": total_entities,
    }


def find_related_threads(agent_id: str, thread_id: str) -> list[dict]:
    """Find threads related to the given thread via shared KG entities."""
    from ..db.connection import get_connection

    with get_connection() as conn:
        # Get entities mentioned in messages of this thread
        cursor = conn.execute(
            """SELECT DISTINCT e.name
               FROM kg_entities e
               WHERE e.agent_id = ?
               AND e.name IN (
                   SELECT DISTINCT LOWER(
                       SUBSTR(m.content,
                              INSTR(LOWER(m.content), LOWER(e2.name)),
                              LENGTH(e2.name))
                   )
                   FROM memory_messages m
                   JOIN memory_threads t ON t.id = m.thread_id
                   JOIN kg_entities e2 ON e2.agent_id = ?
                   WHERE t.id = ? AND t.resource_type = 'agent'
               )""",
            (agent_id, agent_id, thread_id),
        )
        entity_names = [row["name"] for row in cursor.fetchall()]

        if not entity_names:
            return []

        # Find other threads that contain these entity names
        placeholders = ",".join(["?" for _ in entity_names])
        cursor = conn.execute(
            f"""SELECT DISTINCT t.id, t.title, t.updated_at,
                       COUNT(DISTINCT e.name) as shared_entities
                FROM memory_threads t
                JOIN memory_messages m ON m.thread_id = t.id
                JOIN kg_entities e ON e.agent_id = ?
                    AND e.name IN ({placeholders})
                WHERE t.id != ? AND t.resource_id = ?
                    AND t.resource_type = 'agent'
                    AND LOWER(m.content) LIKE '%' || e.name || '%'
                GROUP BY t.id
                ORDER BY shared_entities DESC, t.updated_at DESC
                LIMIT 10""",
            [agent_id] + entity_names + [thread_id, agent_id],
        )
        return [dict(row) for row in cursor.fetchall()]


def run_decay_all() -> int:
    """Run decay for all agents. Designed for APScheduler."""
    from ..db.connection import get_connection

    total = 0
    with get_connection() as conn:
        cursor = conn.execute("SELECT DISTINCT agent_id FROM kg_entities")
        agent_ids = [row["agent_id"] for row in cursor.fetchall()]

    for agent_id in agent_ids:
        try:
            total += apply_decay(agent_id)
        except Exception as e:
            logger.warning("Decay failed for agent %s: %s", agent_id, e)

    return total


def run_consolidation_check() -> int:
    """Check all threads for consolidation triggers. Designed for APScheduler."""
    from ..db.agent_memory import list_threads
    from ..db.connection import get_connection

    total = 0
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT DISTINCT resource_id FROM memory_threads WHERE resource_type = 'agent'"
        )
        agent_ids = [row["resource_id"] for row in cursor.fetchall()]

    for agent_id in agent_ids:
        threads = list_threads(agent_id, "agent")
        for thread in threads:
            try:
                if should_consolidate(agent_id, thread["id"]):
                    result = consolidate_thread(agent_id, thread["id"])
                    if result:
                        total += 1
            except Exception as e:
                logger.warning(
                    "Consolidation check failed for thread %s: %s",
                    thread["id"],
                    e,
                )

    return total
