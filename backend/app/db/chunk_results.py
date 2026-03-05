"""Chunked execution and chunk results CRUD operations.

Stores per-chunk bot outputs and overall chunked execution state
for the smart chunking pipeline (EXE-03).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection
from .ids import _generate_short_id

logger = logging.getLogger(__name__)

CHUNKED_EXEC_ID_PREFIX = "chk-"
CHUNKED_EXEC_ID_LENGTH = 6

CHUNK_RESULT_ID_PREFIX = "chkr-"
CHUNK_RESULT_ID_LENGTH = 6


def _generate_chunked_exec_id() -> str:
    """Generate a unique chunked execution ID."""
    return f"{CHUNKED_EXEC_ID_PREFIX}{_generate_short_id(CHUNKED_EXEC_ID_LENGTH)}"


def _generate_chunk_result_id() -> str:
    """Generate a unique chunk result ID."""
    return f"{CHUNK_RESULT_ID_PREFIX}{_generate_short_id(CHUNK_RESULT_ID_LENGTH)}"


def create_chunked_execution(bot_id: str, total_chunks: int) -> Optional[str]:
    """Create a chunked execution record. Returns chunked_execution_id."""
    with get_connection() as conn:
        try:
            exec_id = _generate_chunked_exec_id()
            conn.execute(
                """INSERT INTO chunked_executions
                   (id, bot_id, total_chunks, status)
                   VALUES (?, ?, ?, 'processing')""",
                (exec_id, bot_id, total_chunks),
            )
            conn.commit()
            return exec_id
        except Exception as e:
            logger.error("Failed to create chunked execution: %s", e)
            return None


def get_chunked_execution(chunked_execution_id: str) -> Optional[dict]:
    """Get a chunked execution by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM chunked_executions WHERE id = ?",
            (chunked_execution_id,),
        ).fetchone()
        return dict(row) if row else None


def update_chunked_execution_status(
    chunked_execution_id: str,
    status: str,
    merged_output: Optional[str] = None,
    unique_findings_count: Optional[int] = None,
    duplicate_count: Optional[int] = None,
) -> bool:
    """Update a chunked execution's status and results."""
    with get_connection() as conn:
        try:
            updates = ["status = ?"]
            values: list = [status]

            if merged_output is not None:
                updates.append("merged_output = ?")
                values.append(merged_output)
            if unique_findings_count is not None:
                updates.append("unique_findings_count = ?")
                values.append(unique_findings_count)
            if duplicate_count is not None:
                updates.append("duplicate_count = ?")
                values.append(duplicate_count)

            if status == "completed":
                updates.append("completed_at = ?")
                values.append(datetime.now(timezone.utc).isoformat())

            values.append(chunked_execution_id)
            conn.execute(
                f"UPDATE chunked_executions SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to update chunked execution: %s", e)
            return False


def create_chunk_result(
    chunked_execution_id: str, chunk_index: int, chunk_content: str
) -> Optional[str]:
    """Create a chunk result record. Returns chunk_result_id."""
    with get_connection() as conn:
        try:
            result_id = _generate_chunk_result_id()
            conn.execute(
                """INSERT INTO chunk_results
                   (id, chunked_execution_id, chunk_index, chunk_content)
                   VALUES (?, ?, ?, ?)""",
                (result_id, chunked_execution_id, chunk_index, chunk_content),
            )
            conn.commit()
            return result_id
        except Exception as e:
            logger.error("Failed to create chunk result: %s", e)
            return None


def update_chunk_result(
    chunk_result_id: str,
    bot_output: str,
    token_count: int,
    status: str = "completed",
) -> bool:
    """Update a chunk result with bot output."""
    with get_connection() as conn:
        try:
            conn.execute(
                """UPDATE chunk_results
                   SET bot_output = ?, token_count = ?, status = ?,
                       completed_at = ?
                   WHERE id = ?""",
                (
                    bot_output,
                    token_count,
                    status,
                    datetime.now(timezone.utc).isoformat(),
                    chunk_result_id,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to update chunk result: %s", e)
            return False


def get_chunk_results(chunked_execution_id: str) -> list[dict]:
    """Get all chunk results for a chunked execution, ordered by chunk_index."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM chunk_results
               WHERE chunked_execution_id = ?
               ORDER BY chunk_index ASC""",
            (chunked_execution_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def increment_completed_chunks(chunked_execution_id: str) -> int:
    """Atomically increment completed_chunks. Returns new count."""
    with get_connection() as conn:
        try:
            conn.execute(
                """UPDATE chunked_executions
                   SET completed_chunks = completed_chunks + 1
                   WHERE id = ?""",
                (chunked_execution_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT completed_chunks FROM chunked_executions WHERE id = ?",
                (chunked_execution_id,),
            ).fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error("Failed to increment completed chunks: %s", e)
            return 0
