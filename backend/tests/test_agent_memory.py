"""Tests for the agent memory system — threads, messages, working memory, recall."""

import json

import pytest

from app.db.agent_memory import (
    count_messages,
    count_threads,
    create_thread,
    delete_thread,
    delete_working_memory,
    get_messages,
    get_thread,
    get_working_memory,
    list_threads,
    recall_messages,
    save_messages,
    update_thread,
    upsert_working_memory,
)


class TestMemoryThreads:
    """Thread CRUD operations."""

    def test_create_thread(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Test Thread")
        assert thread["id"].startswith("thrd-")
        assert thread["resource_id"] == "agent-test01"
        assert thread["resource_type"] == "agent"
        assert thread["title"] == "Test Thread"

    def test_create_thread_with_metadata(self, isolated_db):
        meta = {"key": "value", "count": 42}
        thread = create_thread("agent-test01", "agent", "Meta Thread", metadata=meta)
        assert thread["metadata"] == meta

    def test_get_thread(self, isolated_db):
        created = create_thread("agent-test01", "agent", "Get Test")
        fetched = get_thread(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_nonexistent_thread(self, isolated_db):
        result = get_thread("thrd-nonexistent")
        assert result is None

    def test_list_threads(self, isolated_db):
        create_thread("agent-test01", "agent", "Thread 1")
        create_thread("agent-test01", "agent", "Thread 2")
        create_thread("agent-other", "agent", "Other Agent Thread")

        threads = list_threads("agent-test01", "agent")
        assert len(threads) == 2

    def test_count_threads(self, isolated_db):
        create_thread("agent-test01", "agent", "T1")
        create_thread("agent-test01", "agent", "T2")
        assert count_threads("agent-test01", "agent") == 2
        assert count_threads("agent-other", "agent") == 0

    def test_update_thread(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Original")
        updated = update_thread(thread["id"], title="Updated Title")
        assert updated["title"] == "Updated Title"

    def test_delete_thread(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "To Delete")
        assert delete_thread(thread["id"]) is True
        assert get_thread(thread["id"]) is None
        assert delete_thread(thread["id"]) is False


class TestMemoryMessages:
    """Message CRUD operations."""

    def test_save_and_get_messages(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Msg Test")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        saved = save_messages(thread["id"], messages)
        assert len(saved) == 2
        assert saved[0]["id"].startswith("mmsg-")

        fetched = get_messages(thread["id"])
        assert len(fetched) == 2
        assert fetched[0]["role"] == "user"
        assert fetched[1]["role"] == "assistant"

    def test_count_messages(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Count Test")
        save_messages(
            thread["id"],
            [
                {"role": "user", "content": "Msg 1"},
                {"role": "assistant", "content": "Msg 2"},
                {"role": "user", "content": "Msg 3"},
            ],
        )
        assert count_messages(thread["id"]) == 3

    def test_messages_with_metadata(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Meta Msg")
        save_messages(
            thread["id"],
            [
                {
                    "role": "tool",
                    "content": "result",
                    "type": "tool_result",
                    "metadata": {"tool_name": "search"},
                },
            ],
        )
        fetched = get_messages(thread["id"])
        assert fetched[0]["type"] == "tool_result"
        assert fetched[0]["metadata"]["tool_name"] == "search"

    def test_cascade_delete(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Cascade")
        save_messages(thread["id"], [{"role": "user", "content": "will be deleted"}])
        assert count_messages(thread["id"]) == 1
        delete_thread(thread["id"])
        assert count_messages(thread["id"]) == 0


class TestWorkingMemory:
    """Working memory CRUD."""

    def test_upsert_and_get(self, isolated_db):
        wm = upsert_working_memory("agent-test01", "agent", "# Notes\n- Fact 1")
        assert wm["content"] == "# Notes\n- Fact 1"
        assert wm["entity_id"] == "agent-test01"

        fetched = get_working_memory("agent-test01", "agent")
        assert fetched["content"] == "# Notes\n- Fact 1"

    def test_upsert_update(self, isolated_db):
        upsert_working_memory("agent-test01", "agent", "v1")
        wm = upsert_working_memory("agent-test01", "agent", "v2")
        assert wm["content"] == "v2"

    def test_upsert_with_template(self, isolated_db):
        template = "# Profile\n- **Name**:\n- **Role**:"
        wm = upsert_working_memory("agent-test01", "agent", "", template=template)
        assert wm["template"] == template

    def test_get_nonexistent(self, isolated_db):
        assert get_working_memory("agent-nonexistent", "agent") is None

    def test_delete(self, isolated_db):
        upsert_working_memory("agent-test01", "agent", "to delete")
        assert delete_working_memory("agent-test01", "agent") is True
        assert get_working_memory("agent-test01", "agent") is None

    def test_json_content(self, isolated_db):
        content = json.dumps({"name": "TestBot", "preferences": {"lang": "en"}})
        wm = upsert_working_memory("agent-test01", "agent", content)
        assert wm["content_parsed"]["name"] == "TestBot"


class TestSemanticRecall:
    """FTS5-based semantic recall."""

    def test_recall_basic(self, isolated_db):
        thread = create_thread("agent-test01", "agent", "Recall Test")
        save_messages(
            thread["id"],
            [
                {"role": "user", "content": "The project deadline is next Friday"},
                {"role": "assistant", "content": "I'll make sure to prioritize tasks"},
                {"role": "user", "content": "We need to fix the login bug"},
                {"role": "assistant", "content": "I'll look into the authentication issue"},
            ],
        )

        results = recall_messages(
            thread_id=thread["id"],
            query="deadline Friday",
            top_k=2,
            message_range=0,
        )
        assert len(results) >= 1
        assert any("deadline" in r["content"] for r in results)

    def test_recall_across_threads(self, isolated_db):
        t1 = create_thread("agent-test01", "agent", "Thread 1")
        t2 = create_thread("agent-test01", "agent", "Thread 2")
        save_messages(t1["id"], [{"role": "user", "content": "Python is great for scripting"}])
        save_messages(t2["id"], [{"role": "user", "content": "JavaScript for frontend work"}])

        results = recall_messages(
            thread_id=None,
            query="Python scripting",
            resource_id="agent-test01",
            resource_type="agent",
            top_k=5,
            message_range=0,
        )
        assert len(results) >= 1

    def test_recall_empty_query(self, isolated_db):
        results = recall_messages(thread_id=None, query="test", resource_id=None)
        assert results == []
