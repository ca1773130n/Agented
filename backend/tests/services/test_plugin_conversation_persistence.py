"""Tests for the v0.7.83 plugin-conversation persistence layer.

Mirrors test_skill_conversation_persistence.py (v0.7.78). Covers:
DB CRUD, _ensure_loaded rehydration, write-through on send /
finalize / abandon, list_active filtering, cold-abandon path.
"""

from __future__ import annotations

import pytest

from app.db import (
    create_plugin_conversation,
    delete_plugin_conversation,
    get_plugin_conversation,
    list_active_plugin_conversations,
    upsert_plugin_conversation,
)
from app.services.plugin_conversation_service import (
    ConversationMessage,
    PluginConversationService,
)

# -----------------------------------------------------------------
# DB module
# -----------------------------------------------------------------


def test_create_and_get(isolated_db):
    del isolated_db
    create_plugin_conversation(
        "plugin_aaaaaaaaaaaaaaaa",
        [{"role": "system", "content": "sys", "timestamp": "t"}],
        user_id=None,
    )
    row = get_plugin_conversation("plugin_aaaaaaaaaaaaaaaa")
    assert row is not None
    assert row["status"] == "active"
    assert row["messages"][0]["role"] == "system"


def test_upsert_appends_messages(isolated_db):
    del isolated_db
    cid = "plugin_bbbbbbbbbbbbbbbb"
    create_plugin_conversation(cid, [{"role": "system", "content": "s", "timestamp": "t"}])
    upsert_plugin_conversation(
        cid,
        [
            {"role": "system", "content": "s", "timestamp": "t"},
            {"role": "user", "content": "u", "timestamp": "t"},
        ],
    )
    row = get_plugin_conversation(cid)
    assert len(row["messages"]) == 2
    assert row["messages"][1]["role"] == "user"


def test_upsert_status_change(isolated_db):
    del isolated_db
    cid = "plugin_cccccccccccccccc"
    create_plugin_conversation(cid, [{"role": "system", "content": "s", "timestamp": "t"}])
    upsert_plugin_conversation(
        cid, [{"role": "system", "content": "s", "timestamp": "t"}], status="finalized"
    )
    row = get_plugin_conversation(cid)
    assert row["status"] == "finalized"


def test_list_active_excludes_finalized(isolated_db):
    del isolated_db
    create_plugin_conversation(
        "plugin_dddddddddddddddd", [{"role": "system", "content": "s", "timestamp": "t"}]
    )
    create_plugin_conversation(
        "plugin_eeeeeeeeeeeeeeee", [{"role": "system", "content": "s", "timestamp": "t"}]
    )
    upsert_plugin_conversation(
        "plugin_eeeeeeeeeeeeeeee",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        status="finalized",
    )
    active = list_active_plugin_conversations()
    ids = {c["id"] for c in active}
    assert "plugin_dddddddddddddddd" in ids
    assert "plugin_eeeeeeeeeeeeeeee" not in ids


def test_delete(isolated_db):
    del isolated_db
    create_plugin_conversation(
        "plugin_ffffffffffffffff", [{"role": "system", "content": "s", "timestamp": "t"}]
    )
    assert delete_plugin_conversation("plugin_ffffffffffffffff") is True
    assert get_plugin_conversation("plugin_ffffffffffffffff") is None
    assert delete_plugin_conversation("plugin_nonexistent") is False


# -----------------------------------------------------------------
# Service: write-through + rehydrate
# -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_service_state():
    PluginConversationService._conversations.clear()
    PluginConversationService._subscribers.clear()
    PluginConversationService._start_times.clear()
    yield
    PluginConversationService._conversations.clear()
    PluginConversationService._subscribers.clear()
    PluginConversationService._start_times.clear()


def _seed_db_conv(conv_id: str, messages=None):
    create_plugin_conversation(
        conv_id,
        messages
        or [
            {"role": "system", "content": "sys", "timestamp": "t"},
            {"role": "user", "content": "kickoff", "timestamp": "t"},
        ],
    )


def test_ensure_loaded_rehydrates_from_db(isolated_db):
    del isolated_db
    cid = "plugin_rehydrate1aaaa"
    _seed_db_conv(cid)
    assert cid not in PluginConversationService._conversations
    assert PluginConversationService._ensure_loaded(cid) is True
    conv = PluginConversationService._conversations[cid]
    assert len(conv["messages"]) == 2
    assert conv["messages"][0].role == "system"


def test_ensure_loaded_skips_finalized(isolated_db):
    del isolated_db
    cid = "plugin_finalrowxxxxx"
    create_plugin_conversation(cid, [{"role": "system", "content": "s", "timestamp": "t"}])
    upsert_plugin_conversation(
        cid, [{"role": "system", "content": "s", "timestamp": "t"}], status="finalized"
    )
    assert PluginConversationService._ensure_loaded(cid) is False
    assert cid not in PluginConversationService._conversations


def test_start_conversation_persists(isolated_db):
    del isolated_db
    result, status = PluginConversationService.start_conversation()
    assert status == 201
    cid = result["conversation_id"]
    row = get_plugin_conversation(cid)
    assert row is not None
    assert row["status"] == "active"
    roles = [m["role"] for m in row["messages"]]
    assert "system" in roles
    assert "user" in roles  # kickoff


def test_persist_after_in_memory_mutation(isolated_db):
    del isolated_db
    cid = "plugin_mutateabcdefgh"
    _seed_db_conv(cid)
    PluginConversationService._ensure_loaded(cid)
    PluginConversationService._conversations[cid]["messages"].append(
        ConversationMessage(role="user", content="new msg", timestamp="t2")
    )
    PluginConversationService._persist(cid)
    row = get_plugin_conversation(cid)
    assert any(m["content"] == "new msg" for m in row["messages"])


def test_list_active_excludes_other_users(isolated_db):
    del isolated_db
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?), (?, ?)",
            ("user-1", "u1@test.local", "user-2", "u2@test.local"),
        )
        conn.commit()
    create_plugin_conversation(
        "plugin_mineownedaaaaa",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-1",
    )
    create_plugin_conversation(
        "plugin_yoursownedbbbb",
        [{"role": "system", "content": "s", "timestamp": "t"}],
        user_id="user-2",
    )
    res, status = PluginConversationService.list_active(user_id="user-1")
    assert status == 200
    ids = [c["id"] for c in res["active_conversations"]]
    assert "plugin_mineownedaaaaa" in ids
    assert "plugin_yoursownedbbbb" not in ids


def test_abandon_marks_db_row_abandoned(isolated_db):
    del isolated_db
    cid = "plugin_abandonabcdefg"
    _seed_db_conv(cid)
    PluginConversationService._ensure_loaded(cid)
    result, status = PluginConversationService.abandon_conversation(cid)
    assert status == 200
    row = get_plugin_conversation(cid)
    assert row["status"] == "abandoned"
    assert cid not in PluginConversationService._conversations


def test_abandon_cross_user_returns_404(isolated_db):
    """v0.7.83 — operator B abandoning operator A's conv → 404,
    row stays active.
    """
    del isolated_db
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?), (?, ?)",
            ("user-1", "u1@test.local", "user-2", "u2@test.local"),
        )
        conn.commit()
    cid = "plugin_alicesdontkill"
    create_plugin_conversation(
        cid,
        [
            {"role": "system", "content": "s", "timestamp": "t"},
            {"role": "user", "content": "u", "timestamp": "t"},
        ],
        user_id="user-1",
    )
    result, status = PluginConversationService.abandon_conversation(cid, caller_user_id="user-2")
    assert status == 404
    row = get_plugin_conversation(cid)
    assert row["status"] == "active"
