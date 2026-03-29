"""Structured tracing — traces and spans for agent/bot executions."""

import json
import logging
from datetime import datetime, timezone

from .connection import get_connection, safe_set_clause
from .ids import generate_span_id, generate_trace_id

logger = logging.getLogger(__name__)


def _build_trace_filter(
    entity_type: str | None = None,
    entity_id: str | None = None,
    status: str | None = None,
) -> tuple[str, list]:
    """Build a WHERE clause and params for trace queries."""
    conditions: list[str] = []
    params: list = []
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, params


# --- Trace CRUD ---


def create_trace(
    name: str,
    entity_type: str,
    entity_id: str,
    execution_id: str | None = None,
    input_data: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    trace_id = generate_trace_id()
    now = datetime.now(timezone.utc).isoformat()
    input_json = json.dumps(input_data) if input_data else None
    meta_json = json.dumps(metadata) if metadata else None
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO traces (id, name, entity_type, entity_id, execution_id,
                   status, input, metadata, started_at)
               VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
            (trace_id, name, entity_type, entity_id, execution_id, input_json, meta_json, now),
        )
        conn.commit()
        return get_trace(trace_id)


def get_trace(trace_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,))
        row = cursor.fetchone()
        return _trace_row_to_dict(row) if row else None


def get_trace_with_spans(trace_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,))
        row = cursor.fetchone()
        if not row:
            return None
        trace = _trace_row_to_dict(row)
        cursor = conn.execute(
            "SELECT * FROM trace_spans WHERE trace_id = ? ORDER BY started_at ASC",
            (trace_id,),
        )
        spans = [_span_row_to_dict(r) for r in cursor.fetchall()]
    trace["spans"] = _build_span_tree(spans)
    trace["span_count"] = len(spans)
    return trace


def list_traces(
    entity_type: str | None = None,
    entity_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where, params = _build_trace_filter(entity_type, entity_id, status)
    params.extend([limit, offset])
    with get_connection() as conn:
        cursor = conn.execute(
            f"SELECT * FROM traces {where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
            params,
        )
        return [_trace_row_to_dict(row) for row in cursor.fetchall()]


def count_traces(
    entity_type: str | None = None,
    entity_id: str | None = None,
    status: str | None = None,
) -> int:
    where, params = _build_trace_filter(entity_type, entity_id, status)
    with get_connection() as conn:
        cursor = conn.execute(f"SELECT COUNT(*) FROM traces {where}", params)
        return cursor.fetchone()[0]


def end_trace(
    trace_id: str,
    status: str = "completed",
    output_data: dict | None = None,
    error_message: str | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    output_json = json.dumps(output_data) if output_data else None
    with get_connection() as conn:
        # Calculate duration
        cursor = conn.execute("SELECT started_at FROM traces WHERE id = ?", (trace_id,))
        row = cursor.fetchone()
        duration_ms = None
        if row:
            started = datetime.fromisoformat(row["started_at"])
            finished = datetime.fromisoformat(now)
            duration_ms = int((finished - started).total_seconds() * 1000)
        conn.execute(
            """UPDATE traces SET status = ?, output = ?, error_message = ?,
                   duration_ms = ?, finished_at = ?
               WHERE id = ?""",
            (status, output_json, error_message, duration_ms, now, trace_id),
        )
        conn.commit()
    return get_trace(trace_id)


def delete_trace(trace_id: str) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM trace_spans WHERE trace_id = ?", (trace_id,))
        cursor = conn.execute("DELETE FROM traces WHERE id = ?", (trace_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- Span CRUD ---


def create_span(
    trace_id: str,
    name: str,
    span_type: str,
    parent_span_id: str | None = None,
    input_data: dict | None = None,
    attributes: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    span_id = generate_span_id()
    now = datetime.now(timezone.utc).isoformat()
    input_json = json.dumps(input_data) if input_data else None
    attr_json = json.dumps(attributes) if attributes else None
    meta_json = json.dumps(metadata) if metadata else None
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO trace_spans (id, trace_id, parent_span_id, name, span_type,
                   status, input, attributes, metadata, started_at)
               VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
            (
                span_id,
                trace_id,
                parent_span_id,
                name,
                span_type,
                input_json,
                attr_json,
                meta_json,
                now,
            ),
        )
        conn.commit()
        return get_span(span_id)


def get_span(span_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM trace_spans WHERE id = ?", (span_id,))
        row = cursor.fetchone()
        return _span_row_to_dict(row) if row else None


def list_spans(trace_id: str) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM trace_spans WHERE trace_id = ? ORDER BY started_at ASC",
            (trace_id,),
        )
        return [_span_row_to_dict(row) for row in cursor.fetchall()]


def end_span(
    span_id: str,
    status: str = "completed",
    output_data: dict | None = None,
    error_message: str | None = None,
    attributes: dict | None = None,
) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    output_json = json.dumps(output_data) if output_data else None
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT started_at, attributes FROM trace_spans WHERE id = ?", (span_id,)
        )
        row = cursor.fetchone()
        duration_ms = None
        merged_attrs = None
        if row:
            started = datetime.fromisoformat(row["started_at"])
            finished = datetime.fromisoformat(now)
            duration_ms = int((finished - started).total_seconds() * 1000)
            # Merge attributes
            if attributes:
                existing = {}
                if row["attributes"]:
                    try:
                        existing = json.loads(row["attributes"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                existing.update(attributes)
                merged_attrs = json.dumps(existing)

        update_exprs = [
            "status = ?",
            "output = ?",
            "error_message = ?",
            "duration_ms = ?",
            "finished_at = ?",
        ]
        params: list = [status, output_json, error_message, duration_ms, now]
        if merged_attrs:
            update_exprs.append("attributes = ?")
            params.append(merged_attrs)
        params.append(span_id)
        conn.execute(
            f"UPDATE trace_spans SET {safe_set_clause(update_exprs)} WHERE id = ?",
            params,
        )
        conn.commit()
    return get_span(span_id)


def update_span(
    span_id: str,
    attributes: dict | None = None,
    metadata: dict | None = None,
) -> dict | None:
    with get_connection() as conn:
        updates = []
        params: list = []
        if attributes:
            cursor = conn.execute("SELECT attributes FROM trace_spans WHERE id = ?", (span_id,))
            row = cursor.fetchone()
            existing = {}
            if row and row["attributes"]:
                try:
                    existing = json.loads(row["attributes"])
                except (json.JSONDecodeError, TypeError):
                    pass
            existing.update(attributes)
            updates.append("attributes = ?")
            params.append(json.dumps(existing))
        if metadata:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))
        if updates:
            params.append(span_id)
            conn.execute(
                f"UPDATE trace_spans SET {safe_set_clause(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
    return get_span(span_id)


# --- Statistics ---


def get_trace_stats(
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> dict:
    where, params = _build_trace_filter(entity_type, entity_id)
    with get_connection() as conn:
        cursor = conn.execute(
            f"""SELECT
                   COUNT(*) as total_traces,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                   SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
                   AVG(duration_ms) as avg_duration_ms,
                   MAX(duration_ms) as max_duration_ms,
                   MIN(duration_ms) as min_duration_ms
               FROM traces {where}""",
            params,
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


# --- Helpers ---


def _build_span_tree(spans: list[dict]) -> list[dict]:
    span_map = {s["id"]: {**s, "children": []} for s in spans}
    roots = []
    for s in spans:
        node = span_map[s["id"]]
        parent_id = s.get("parent_span_id")
        if parent_id and parent_id in span_map:
            span_map[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _parse_json_field(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Failed to parse JSON field: %s", value[:100] if isinstance(value, str) else value
        )
        return None


def _trace_row_to_dict(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    for field in ("input", "output", "metadata"):
        d[field] = _parse_json_field(d.get(field))
    return d


def _span_row_to_dict(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    for field in ("input", "output", "attributes", "metadata"):
        d[field] = _parse_json_field(d.get(field))
    return d
