"""PR ownership rules CRUD operations."""

import logging

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)


def get_ownership_rules() -> list[dict]:
    """Return all PR ownership rules ordered by priority descending."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM pr_ownership_rules ORDER BY priority DESC, created_at ASC"
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["reviewers"] = [r.strip() for r in record["reviewers"].split(",") if r.strip()]
            result.append(record)
        return result


def add_ownership_rule(pattern: str, team: str, reviewers: list[str], priority: int = 0) -> str:
    """Insert a new ownership rule. Returns the new rule ID."""
    rule_id = generate_id("rule-", 6)
    reviewers_str = ",".join(r.strip() for r in reviewers if r.strip())
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO pr_ownership_rules (id, pattern, team, reviewers, priority)
               VALUES (?, ?, ?, ?, ?)""",
            (rule_id, pattern, team, reviewers_str, priority),
        )
        conn.commit()
    return rule_id


def delete_ownership_rule(rule_id: str) -> bool:
    """Delete an ownership rule by ID. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM pr_ownership_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return cursor.rowcount > 0
