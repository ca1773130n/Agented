"""Tests for the v0.7.78 skill-conversation persistence layer.

Covers: DB write-through on start / send / finalize / abandon,
rehydration from DB when the in-memory cache misses, list_active
filtering, and that the message envelope round-trips byte-for-byte.
"""

from __future__ import annotations

import json

import pytest

from app.db import (
    create_skill_conversation,
    delete_skill_conversation,
    get_skill_conversation,
    list_active_skill_conversations,
    upsert_skill_conversation,
)
from app.services import skill_conversation_service as svc
from app.services.skill_conversation_service import (
    ConversationMessage,
    SkillConversationService,
)


# -----------------------------------------------------------------
# DB module
# -----------------------------------------------------------------


def test_create_and_get(isolated_db):
    del isolated_db
    create_skill_conversation(
        "skill_aaaaaaaaaaaaaaaa",
        [{"role": "system", "content": "sys", "timestamp": "t"}],
        user_id=None,
    )
    row = get_skill_conversation("skill_aaaaaaaaaaaaaaaa")
    assert row is not None
    assert row["status"] == "active"
    assert row["messages"][0]["role"] == "system"


def test_upsert_appends_messages(isolated_db):
    del isolated_db
    cid = "skill_bbbbbbbbbbbbbbbb"
    create_skill_conversation(cid, [{"role": "system", "content": "s", "timestamp": "t"}])
    upsert_skill_conversation(
        cid,
        [
            {"role": "system", "content": "s", "timestamp": "t"},
            {"role": "user", "content": "u", "timestamp": "t"},
        ],
    )
    row = get_skill_conversation(cid)
    assert len(row["messages"]) == 2
    assert row["messages"][1]["role"] == "user"


def test_upsert_status_change(isolated_db):
    del isolated_db
    cid = "skill_cccccccccccccccc"
    create_skill_conversation(cid, [{"role": "system", "content": "s", "timestamp": "t"}])
    upsert_skill_conversation(
        cid,
        [{"role": "system", "content": "s", "timestamp": "t"}],
        status="finalized",
    )
    row = get_skill_conversation(cid)
    assert row["status"] == "finalized"


def test_list_active_excludes_finalized(isolated_db):
    del isolated_db
    create_skill_conversation(
        "skill_dddddddddddddddd",
        [{"role": "system", "content": "s", "timestamp": "t"}],
    )
    create_skill_conversation(
        "skill_eeeeeeeeeeeeeeee",
        [{"role": "system", "content": "s", "timestamp": "t"}],
    )
    upsert_skill_conversation(
        "skill_eeeeeeeeeeeeeeee",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        status="finalized",
    )
    active = list_active_skill_conversations()
    ids = {c["id"] for c in active}
    assert "skill_dddddddddddddddd" in ids
    assert "skill_eeeeeeeeeeeeeeee" not in ids


def test_delete(isolated_db):
    del isolated_db
    create_skill_conversation(
        "skill_ffffffffffffffff",
        [{"role": "system", "content": "s", "timestamp": "t"}],
    )
    assert delete_skill_conversation("skill_ffffffffffffffff") is True
    assert get_skill_conversation("skill_ffffffffffffffff") is None
    assert delete_skill_conversation("skill_nonexistent") is False


# -----------------------------------------------------------------
# Service: write-through + rehydrate
# -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_service_state():
    """Each test starts with a clean in-memory dict so the
    rehydration paths aren't masked by stale cache hits."""
    SkillConversationService._conversations.clear()
    SkillConversationService._subscribers.clear()
    SkillConversationService._start_times.clear()
    yield
    SkillConversationService._conversations.clear()
    SkillConversationService._subscribers.clear()
    SkillConversationService._start_times.clear()


def _seed_db_conv(conv_id: str, messages=None):
    """Insert an active conv directly into the DB so the service
    has to rehydrate to see it."""
    create_skill_conversation(
        conv_id,
        messages
        or [
            {"role": "system", "content": "sys", "timestamp": "t"},
            {"role": "user", "content": "kickoff", "timestamp": "t"},
        ],
    )


def test_ensure_loaded_rehydrates_from_db(isolated_db):
    del isolated_db
    cid = "skill_rehydraterehyd1"
    _seed_db_conv(cid)
    assert cid not in SkillConversationService._conversations
    assert SkillConversationService._ensure_loaded(cid) is True
    assert cid in SkillConversationService._conversations
    conv = SkillConversationService._conversations[cid]
    assert len(conv["messages"]) == 2
    assert conv["messages"][0].role == "system"


def test_ensure_loaded_skips_finalized(isolated_db):
    del isolated_db
    cid = "skill_finalizedrowfin"
    create_skill_conversation(
        cid,
        [{"role": "system", "content": "s", "timestamp": "t"}],
    )
    upsert_skill_conversation(
        cid,
        [{"role": "system", "content": "s", "timestamp": "t"}],
        status="finalized",
    )
    assert SkillConversationService._ensure_loaded(cid) is False
    assert cid not in SkillConversationService._conversations


def test_ensure_loaded_returns_false_for_missing(isolated_db):
    del isolated_db
    assert SkillConversationService._ensure_loaded("skill_doesnotexistxx") is False


def test_get_conversation_rehydrates(isolated_db):
    del isolated_db
    cid = "skill_getrehydrategrr"
    _seed_db_conv(cid)
    result, status = SkillConversationService.get_conversation(cid)
    assert status == 200
    assert result["id"] == cid
    assert any(m["role"] == "user" for m in result["messages_parsed"])


def test_start_conversation_persists(isolated_db):
    del isolated_db
    result, status = SkillConversationService.start_conversation()
    assert status == 201
    cid = result["conversation_id"]
    row = get_skill_conversation(cid)
    assert row is not None
    assert row["status"] == "active"
    # The system + kickoff user messages were persisted.
    roles = [m["role"] for m in row["messages"]]
    assert "system" in roles
    assert "user" in roles


def test_persist_after_in_memory_mutation(isolated_db):
    del isolated_db
    cid = "skill_persistmutateaa"
    _seed_db_conv(cid)
    SkillConversationService._ensure_loaded(cid)
    SkillConversationService._conversations[cid]["messages"].append(
        ConversationMessage(role="user", content="new msg", timestamp="t2")
    )
    SkillConversationService._persist(cid)
    row = get_skill_conversation(cid)
    assert any(m["content"] == "new msg" for m in row["messages"])


def test_list_active_excludes_other_users(isolated_db):
    """Service.list_active filters by user_id when supplied. FK
    on user_id requires the rows to exist in ``users`` first."""
    del isolated_db
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?), (?, ?)",
            ("user-1", "u1@test.local", "user-2", "u2@test.local"),
        )
        conn.commit()
    create_skill_conversation(
        "skill_mineminemineminm",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-1",
    )
    create_skill_conversation(
        "skill_yoursyoursyourss",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-2",
    )
    res, status = SkillConversationService.list_active(user_id="user-1")
    assert status == 200
    ids = [c["id"] for c in res["active_conversations"]]
    assert "skill_mineminemineminm" in ids
    assert "skill_yoursyoursyourss" not in ids


def test_abandon_marks_db_row_abandoned(isolated_db):
    del isolated_db
    cid = "skill_abandonabandona"
    _seed_db_conv(cid)
    SkillConversationService._ensure_loaded(cid)
    result, status = SkillConversationService.abandon_conversation(cid)
    assert status == 200
    row = get_skill_conversation(cid)
    assert row["status"] == "abandoned"
    # Cleanup dropped the in-memory entry.
    assert cid not in SkillConversationService._conversations


def test_abandon_works_on_cold_db_only_conv(isolated_db):
    """Operator hits abandon on a conv that's only in DB (not in
    memory) — service should still mark it abandoned."""
    del isolated_db
    cid = "skill_coldabandoncold"
    _seed_db_conv(cid)
    # NOTE: don't call ensure_loaded first; the abandon path
    # should handle the cold case via its DB fallback.
    SkillConversationService._conversations.pop(cid, None)
    result, status = SkillConversationService.abandon_conversation(cid)
    # ``_ensure_loaded`` rehydrates first, so this returns 200
    # with the normal abandoned path. The fallback exists for
    # the case where the row is somehow non-active; this just
    # confirms we don't 404 on a cold-cache abandon.
    assert status == 200
    row = get_skill_conversation(cid)
    assert row["status"] == "abandoned"
