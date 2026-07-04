"""PR review record helpers for triggers.

Split out of triggers.py in v0.7.3 — pure file move, no logic
changes. Public API unchanged: this module's symbols are
re-exported from `app.db.triggers` for backward compatibility.
"""

import logging
from typing import List, Optional

from . import errors
from .connection import get_connection

logger = logging.getLogger(__name__)


def add_pr_review(
    project_name: str,
    pr_number: int,
    pr_url: str,
    pr_title: str,
    trigger_id: str = "bot-pr-review",
    github_repo_url: str = None,
    pr_author: str = None,
) -> Optional[int]:
    """Add a new PR review record. Returns the row id on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO pr_reviews
                    (trigger_id, project_name, github_repo_url, pr_number, pr_url,
                     pr_title, pr_author)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (trigger_id, project_name, github_repo_url, pr_number, pr_url, pr_title, pr_author),
            )
            conn.commit()
            return cursor.lastrowid
        except errors.IntegrityError:
            return None


def update_pr_review(
    review_id: int,
    pr_status: str = None,
    review_status: str = None,
    review_comment: str = None,
    fixes_applied: int = None,
    fix_comment: str = None,
) -> bool:
    """Update a PR review record. Returns True on success."""
    updates = []
    values = []

    if pr_status is not None:
        updates.append("pr_status = ?")
        values.append(pr_status)
    if review_status is not None:
        updates.append("review_status = ?")
        values.append(review_status)
    if review_comment is not None:
        updates.append("review_comment = ?")
        values.append(review_comment)
    if fixes_applied is not None:
        updates.append("fixes_applied = ?")
        values.append(fixes_applied)
    if fix_comment is not None:
        updates.append("fix_comment = ?")
        values.append(fix_comment)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(review_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE pr_reviews SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def get_pr_review(review_id: int) -> Optional[dict]:
    """Get a single PR review by id."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM pr_reviews WHERE id = ?", (review_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_pr_reviews_for_trigger(
    trigger_id: str = "bot-pr-review",
    limit: int = 50,
    offset: int = 0,
    pr_status: str = None,
    review_status: str = None,
) -> List[dict]:
    """Get PR reviews for a trigger with optional filtering."""
    with get_connection() as conn:
        query = "SELECT * FROM pr_reviews WHERE trigger_id = ?"
        params: list = [trigger_id]

        if pr_status:
            query += " AND pr_status = ?"
            params.append(pr_status)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_pr_reviews_count(
    trigger_id: str = "bot-pr-review", pr_status: str = None, review_status: str = None
) -> int:
    """Get count of PR reviews with optional filtering."""
    with get_connection() as conn:
        query = "SELECT COUNT(*) as cnt FROM pr_reviews WHERE trigger_id = ?"
        params: list = [trigger_id]

        if pr_status:
            query += " AND pr_status = ?"
            params.append(pr_status)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status)

        cursor = conn.execute(query, params)
        return cursor.fetchone()["cnt"]


def get_pr_review_stats(trigger_id: str = "bot-pr-review") -> dict:
    """Get aggregate PR review statistics."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'open' THEN 1 ELSE 0 END), 0) as open_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'merged' THEN 1 ELSE 0 END), 0) as merged_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'closed' THEN 1 ELSE 0 END), 0) as closed_prs,
                COALESCE(SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END), 0) as pending_reviews,
                COALESCE(SUM(CASE WHEN review_status = 'approved' THEN 1 ELSE 0 END), 0) as approved_reviews,
                COALESCE(SUM(CASE WHEN review_status = 'changes_requested' THEN 1 ELSE 0 END), 0) as changes_requested,
                COALESCE(SUM(CASE WHEN review_status = 'fixed' THEN 1 ELSE 0 END), 0) as fixed_reviews
            FROM pr_reviews WHERE trigger_id = ?
        """,
            (trigger_id,),
        )
        row = cursor.fetchone()
        return (
            dict(row)
            if row
            else {
                "total_prs": 0,
                "open_prs": 0,
                "merged_prs": 0,
                "closed_prs": 0,
                "pending_reviews": 0,
                "approved_reviews": 0,
                "changes_requested": 0,
                "fixed_reviews": 0,
            }
        )


def get_all_pr_reviews(limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all PR reviews with pagination."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT pr.*, t.name as trigger_name
            FROM pr_reviews pr
            LEFT JOIN triggers t ON pr.trigger_id = t.id
            ORDER BY pr.updated_at DESC
            LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_pr_review(review_id: int) -> bool:
    """Delete a PR review record. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM pr_reviews WHERE id = ?", (review_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_pr_review_history(trigger_id: str = "bot-pr-review", days: int = 30) -> List[dict]:
    """Get PR activity grouped by date for time-series visualization."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT date(created_at) as date,
                   COUNT(*) as created,
                   SUM(CASE WHEN pr_status = 'merged' THEN 1 ELSE 0 END) as merged,
                   SUM(CASE WHEN pr_status = 'closed' THEN 1 ELSE 0 END) as closed
            FROM pr_reviews
            WHERE trigger_id = ?
              AND created_at >= date('now', ? || ' days')
            GROUP BY date(created_at)
            ORDER BY date ASC
        """,
            (trigger_id, -days),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_pr_review_learning_loop(trigger_id: str = "bot-pr-review") -> List[dict]:
    """Get per-project acceptance signal breakdown for the learning loop.

    Groups PR reviews by project_name and computes acceptance, dismiss, comment,
    and resolve counts along with the last_seen timestamp.  Also computes a
    simple trend by comparing the accept-rate in the most-recent 7 days against
    the preceding 7-day window.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                project_name AS pattern,
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN review_status IN ('approved', 'fixed')
                             THEN 1 ELSE 0 END), 0) AS accepted_count,
                COALESCE(SUM(CASE WHEN review_status = 'changes_requested'
                             THEN 1 ELSE 0 END), 0) AS dismissed_count,
                COALESCE(SUM(CASE WHEN review_comment IS NOT NULL
                             THEN 1 ELSE 0 END), 0) AS commented_count,
                COALESCE(SUM(CASE WHEN fixes_applied > 0
                             THEN 1 ELSE 0 END), 0) AS resolved_count,
                MAX(updated_at) AS last_seen,
                -- recent 7-day window accept count
                COALESCE(SUM(CASE WHEN review_status IN ('approved', 'fixed')
                              AND updated_at >= date('now', '-7 days')
                             THEN 1 ELSE 0 END), 0) AS recent_accepted,
                COALESCE(SUM(CASE WHEN updated_at >= date('now', '-7 days')
                             THEN 1 ELSE 0 END), 0) AS recent_total,
                -- preceding 7-day window accept count
                COALESCE(SUM(CASE WHEN review_status IN ('approved', 'fixed')
                              AND updated_at >= date('now', '-14 days')
                              AND updated_at < date('now', '-7 days')
                             THEN 1 ELSE 0 END), 0) AS prev_accepted,
                COALESCE(SUM(CASE WHEN updated_at >= date('now', '-14 days')
                              AND updated_at < date('now', '-7 days')
                             THEN 1 ELSE 0 END), 0) AS prev_total
            FROM pr_reviews
            WHERE trigger_id = ?
            GROUP BY project_name
            ORDER BY total DESC
            """,
            (trigger_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
