"""Execution log full-text search service using SQLite FTS5 with BM25 ranking."""

import logging
import sqlite3
from typing import List, Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


class ExecutionSearchService:
    """Full-text search over execution logs using FTS5 BM25 ranking."""

    @staticmethod
    def search(
        query: str,
        limit: int = 50,
        trigger_id: Optional[str] = None,
        status: Optional[str] = None,
        started_after: Optional[str] = None,
        started_before: Optional[str] = None,
        bot_name: Optional[str] = None,
    ) -> List[dict]:
        """Search execution logs using FTS5 full-text search.

        Args:
            query: Natural language search query (passed directly to FTS5 MATCH).
            limit: Maximum number of results to return.
            trigger_id: Optional trigger ID to filter results.
            status: Optional status filter (running, completed, failed).
            started_after: Optional ISO 8601 timestamp lower bound for started_at.
            started_before: Optional ISO 8601 timestamp upper bound for started_at.
            bot_name: Optional substring filter on trigger/bot name.

        Returns:
            List of dicts with execution details and highlighted snippets,
            ranked by BM25 relevance. Returns empty list on malformed queries.
        """
        try:
            with get_connection() as conn:
                sql = """
                    SELECT
                        e.execution_id,
                        e.trigger_id,
                        t.name AS trigger_name,
                        e.started_at,
                        e.status,
                        e.prompt,
                        snippet(execution_logs_fts, 0, '<mark>', '</mark>', '...', 32) AS stdout_match,
                        snippet(execution_logs_fts, 1, '<mark>', '</mark>', '...', 32) AS stderr_match
                    FROM execution_logs_fts
                    JOIN execution_logs e ON e.id = execution_logs_fts.rowid
                    LEFT JOIN triggers t ON e.trigger_id = t.id
                    WHERE execution_logs_fts MATCH ?
                """
                params: list = [query]

                if trigger_id:
                    sql += " AND e.trigger_id = ?"
                    params.append(trigger_id)

                if status:
                    sql += " AND e.status = ?"
                    params.append(status)

                if started_after:
                    sql += " AND e.started_at >= ?"
                    params.append(started_after)

                if started_before:
                    sql += " AND e.started_at <= ?"
                    params.append(started_before)

                if bot_name:
                    sql += " AND t.name LIKE ?"
                    params.append(f"%{bot_name}%")

                sql += " ORDER BY rank LIMIT ?"
                params.append(limit)

                cursor = conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 search error for query %r: %s", query, exc)
            return []

    @staticmethod
    def get_search_stats() -> dict:
        """Return statistics about the FTS5 search index.

        Returns:
            Dict with indexed_documents count.
        """
        with get_connection() as conn:
            cursor = conn.execute("SELECT count(*) FROM execution_logs_fts")
            count = cursor.fetchone()[0]
            return {"indexed_documents": count}
