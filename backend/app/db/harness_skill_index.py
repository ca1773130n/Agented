"""Repository helpers for the harness H5 skill FTS5 index (T-final)."""

from __future__ import annotations

import re
from typing import Any, Optional

from .connection import get_connection


def upsert(layer_id: str, bot_id: str, payload: dict[str, Any]) -> None:
    """Replace any existing index row for this layer with a fresh one."""
    title = str(payload.get("title") or "")
    when_clause = str(payload.get("when") or "")
    recipe = str(payload.get("recipe") or "")
    tags = " ".join(payload.get("tags") or [])
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM harness_skill_index WHERE layer_id = ?", (layer_id,),
        )
        conn.execute(
            """INSERT INTO harness_skill_index
                   (layer_id, bot_id, title, when_clause, recipe, tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (layer_id, bot_id, title, when_clause, recipe, tags),
        )
        conn.commit()


def remove(layer_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM harness_skill_index WHERE layer_id = ?", (layer_id,),
        )
        conn.commit()


def top_k(
    bot_id: str, query: str, *, k: int = 3,
) -> list[str]:
    """Return the ``k`` most BM25-relevant H5 layer ids for the bot.

    Returns ``[]`` when the query is empty / malformed (FTS5 has its own
    query grammar that rejects bare parens etc.). The caller falls back
    to "all skills" in that case.
    """
    # Extract alphanumeric tokens and join with OR. Phrase-mode (``"..."``)
    # would require the tokens to appear *consecutively* in the indexed
    # text — too strict for free-form task descriptions like "customer
    # wants to refund their order" matching a skill titled "Refund a
    # digital order". OR ranking is what we want: BM25 surfaces the
    # entries that share the most tokens.
    tokens = re.findall(r"[a-zA-Z0-9]+", query or "")
    if not tokens:
        return []
    safe = " OR ".join(tokens)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT layer_id FROM harness_skill_index
                   WHERE bot_id = ? AND harness_skill_index MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (bot_id, safe, int(k)),
            ).fetchall()
    except Exception:
        return []
    return [r["layer_id"] for r in rows]
