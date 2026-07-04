"""Upsert-path parity tests (26-01 #3).

Two ``INSERT ... ON CONFLICT DO UPDATE`` sites replaced legacy
``INSERT OR REPLACE``: ``grd.upsert_project_sync_state`` (on the
``project_sync_state (project_id, file_path)`` unique key) and
``embedding_service.embed_and_store`` (on ``memory_embeddings (message_id,
model)``). Neither target table has FK children, so DO-UPDATE is semantically
equivalent to the old OR-REPLACE on SQLite and is portable to Postgres.

These tests prove the upsert is correct: insert a row, upsert the SAME conflict
key with NEW values, and assert exactly ONE row remains carrying the UPDATED
values. They run on both backends automatically via the ``isolated_db`` fixture
(SQLite always; Postgres too when DATABASE_URL is a postgres URL).
"""

from __future__ import annotations

import app.services.embedding_service as embedding_service
from app.db.connection import get_connection
from app.db.grd import get_project_sync_state, upsert_project_sync_state
from app.db.projects import create_project


def test_project_sync_state_upsert_updates_in_place(isolated_db):
    project_id = create_project(name="upsert-sync-parity")

    assert upsert_project_sync_state(project_id, "docs/a.md", "hash-v1", "doc") is True
    # Same (project_id, file_path) conflict key, new values.
    assert (
        upsert_project_sync_state(project_id, "docs/a.md", "hash-v2", "note", entity_id="ent-9")
        is True
    )

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT content_hash, entity_type, entity_id FROM project_sync_state "
            "WHERE project_id = ? AND file_path = ?",
            (project_id, "docs/a.md"),
        ).fetchall()

    assert len(rows) == 1  # upsert replaced in place, no duplicate row
    assert rows[0]["content_hash"] == "hash-v2"
    assert rows[0]["entity_type"] == "note"
    assert rows[0]["entity_id"] == "ent-9"

    state = get_project_sync_state(project_id, "docs/a.md")
    assert state is not None
    assert state["content_hash"] == "hash-v2"


def test_embedding_cache_upsert_updates_in_place(isolated_db, monkeypatch):
    # Avoid loading the real sentence-transformers model: stub availability and
    # the embedding vector so the test exercises the upsert SQL, not the model.
    monkeypatch.setattr(embedding_service, "is_available", lambda: True)
    vec = {"v": [0.1, 0.2, 0.3]}
    monkeypatch.setattr(embedding_service, "embed_text", lambda _text: list(vec["v"]))

    first_id = embedding_service.embed_and_store("msg-upsert", "first content")
    assert first_id is not None

    vec["v"] = [0.9, 0.8, 0.7]  # re-embed the SAME message with new values
    second_id = embedding_service.embed_and_store("msg-upsert", "second content")
    assert second_id is not None

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, embedding FROM memory_embeddings WHERE message_id = ?",
            ("msg-upsert",),
        ).fetchall()

    assert len(rows) == 1  # upsert replaced in place, not a second cache row
    assert rows[0]["id"] == second_id  # id column updated via excluded.id
    # embedding blob is the LATEST vector, not the original.
    assert bytes(rows[0]["embedding"]) == embedding_service.serialize_embedding([0.9, 0.8, 0.7])
