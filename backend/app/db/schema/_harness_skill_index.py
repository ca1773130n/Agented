"""FTS5 index for Life-Harness H5 procedural skills (T-final).

Backs ``HarnessBuildService.build_for(..., task_description=...)`` so the
compiler can return top-K skills by BM25 relevance instead of dumping the
entire skill library into every overlay.

The index is maintained eagerly by the layers repo (``create_layer`` /
``supersede_layer`` / ``set_enabled``). A row exists only for ENABLED H5
layers; disabled layers are removed from the index so they don't surface
in retrieval.
"""

from __future__ import annotations


def create_harness_skill_index_tables(conn) -> None:
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS harness_skill_index USING fts5(
            layer_id UNINDEXED,
            bot_id UNINDEXED,
            title,
            when_clause,
            recipe,
            tags
        )
        """
    )
