"""Tests for conversation services: base, agent, command, hook, rule, branch."""

import datetime
import json
import threading
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest

from app.services.base_conversation_service import (
    BaseConversationService,
    ConversationMessage,
    WordBoundaryAccumulator,
)
from app.services.command_conversation_service import CommandConversationService
from app.services.hook_conversation_service import HookConversationService
from app.services.rule_conversation_service import RuleConversationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_command_service_state():
    """Reset class-level mutable state between tests."""
    CommandConversationService._conversations.clear()
    CommandConversationService._subscribers.clear()
    CommandConversationService._start_times.clear()
    yield
    CommandConversationService._conversations.clear()
    CommandConversationService._subscribers.clear()
    CommandConversationService._start_times.clear()


@pytest.fixture(autouse=True)
def reset_hook_service_state():
    """Reset hook service state between tests."""
    HookConversationService._conversations.clear()
    HookConversationService._subscribers.clear()
    HookConversationService._start_times.clear()
    yield
    HookConversationService._conversations.clear()
    HookConversationService._subscribers.clear()
    HookConversationService._start_times.clear()


@pytest.fixture(autouse=True)
def reset_rule_service_state():
    """Reset rule service state between tests."""
    RuleConversationService._conversations.clear()
    RuleConversationService._subscribers.clear()
    RuleConversationService._start_times.clear()
    yield
    RuleConversationService._conversations.clear()
    RuleConversationService._subscribers.clear()
    RuleConversationService._start_times.clear()


def _seed_conversation(cls, conv_id="cmd_test123", messages=None, processing=False):
    """Seed a conversation into the given service's in-memory state."""
    if messages is None:
        messages = [
            ConversationMessage(
                role="system",
                content="System prompt",
                timestamp=datetime.datetime.now().isoformat(),
            ),
        ]
    cls._conversations[conv_id] = {"messages": messages, "processing": processing}
    cls._subscribers[conv_id] = []
    cls._start_times[conv_id] = datetime.datetime.now()
    return conv_id


# ---------------------------------------------------------------------------
# WordBoundaryAccumulator
# ---------------------------------------------------------------------------


class TestWordBoundaryAccumulator:
    def test_flushes_on_space(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t))
        acc.add("hello ")
        assert flushed == ["hello "]
        assert acc.buffer == ""

    def test_flushes_on_newline(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t))
        acc.add("line\n")
        assert flushed == ["line\n"]

    def test_flushes_on_tab(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t))
        acc.add("col\t")
        assert flushed == ["col\t"]

    def test_flushes_on_max_buffer(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t), max_buffer=5)
        acc.add("abcde")
        assert flushed == ["abcde"]

    def test_accumulates_without_boundary(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t), max_buffer=100)
        acc.add("abc")
        assert flushed == []
        assert acc.buffer == "abc"

    def test_manual_flush(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t))
        acc.add("partial")
        assert flushed == []
        acc.flush()
        assert flushed == ["partial"]
        assert acc.buffer == ""

    def test_flush_empty_noop(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t))
        acc.flush()
        assert flushed == []

    def test_multiple_adds(self):
        flushed = []
        acc = WordBoundaryAccumulator(flush_callback=lambda t: flushed.append(t), max_buffer=100)
        acc.add("hello")
        acc.add(" world")
        # Second add contains space -> flushes accumulated "hello world"
        assert flushed == ["hello world"]


# ---------------------------------------------------------------------------
# BaseConversationService via CommandConversationService
# ---------------------------------------------------------------------------


class TestBaseConversationServiceViaCommand:
    """Test inherited BaseConversationService methods using CommandConversationService."""

    def test_generate_conv_id_prefix(self):
        conv_id = CommandConversationService._generate_conv_id()
        assert conv_id.startswith("cmd_")
        assert len(conv_id) == 4 + 16  # prefix + random chars

    def test_generate_conv_id_uniqueness(self):
        ids = {CommandConversationService._generate_conv_id() for _ in range(50)}
        assert len(ids) == 50

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_start_conversation(self, mock_process):
        """v0.7.81 (issue #124 / WARN 3) — ``start_conversation``
        no longer fires the LLM thread directly. It seeds the
        conv with the kickoff user message, persists, and sets
        ``needs_kickoff=True``; the actual LLM call is deferred
        until a subscriber attaches. This test pins that contract
        so a future revert to eager firing fails loudly.
        """
        result, status = CommandConversationService.start_conversation()
        assert status == HTTPStatus.CREATED
        conv_id = result["conversation_id"]
        assert conv_id.startswith("cmd_")
        assert conv_id in CommandConversationService._conversations

        conv = CommandConversationService._conversations[conv_id]
        # Kickoff user message must be present in memory.
        user_msgs = [m for m in conv["messages"] if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content.strip()
        # Deferred-fire flag must be set.
        assert conv.get("needs_kickoff") is True
        # LLM call must NOT have been spawned yet.
        mock_process.assert_not_called()

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_start_conversation_persists_kickoff(self, mock_process):
        """v0.7.81 (issue #124 / WARN 1) — the kickoff must hit
        the DB before ``start_conversation`` returns so a crash
        in the brief window before the LLM call finishes doesn't
        leave the resume path with only the system prompt.
        """
        from app.database import get_design_conversation

        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        row = get_design_conversation(conv_id)
        assert row is not None
        messages = json.loads(row["messages"] or "[]")
        roles = [m["role"] for m in messages]
        assert "user" in roles, (
            "Kickoff user message must be persisted before start_conversation returns"
        )
        mock_process.assert_not_called()

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_subscribe_fires_deferred_kickoff(self, mock_process):
        """v0.7.81 (issue #124 / WARN 3) — the first ``subscribe``
        call after ``start_conversation`` triggers the LLM thread
        and atomically clears ``needs_kickoff``. We drive the
        generator far enough to enter the streaming loop (which
        is where the kickoff is fired) and then close it.
        """
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        assert mock_process.call_count == 0

        gen = CommandConversationService.subscribe(conv_id)
        # First yield emits the kickoff user message that
        # ``start_conversation`` seeded; consuming it forces the
        # generator past the ``_maybe_fire_kickoff`` call.
        next(gen)
        gen.close()

        # Wait briefly for the spawned thread to register itself;
        # the patch on _process_with_claude makes the thread
        # return immediately, but we still need a join to be
        # deterministic. Threads spawned in _maybe_fire_kickoff
        # are not tracked, so we poll the call count.
        for _ in range(50):
            if mock_process.call_count >= 1:
                break
            threading.Event().wait(0.01)
        assert mock_process.call_count == 1, (
            "subscribe() must fire the deferred kickoff on first attach"
        )
        # Flag must be cleared so a second subscriber doesn't
        # double-spawn.
        assert (
            CommandConversationService._conversations[conv_id].get("needs_kickoff")
            is False
        )

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_second_subscribe_does_not_double_fire(self, mock_process):
        """v0.7.81 (issue #124 / WARN 3) — a second subscriber
        attaching after the first must NOT re-fire the kickoff.
        Without the atomic check-and-clear, two browser tabs
        opening the wizard simultaneously would each spawn a
        full LLM round-trip.
        """
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]

        gen1 = CommandConversationService.subscribe(conv_id)
        next(gen1)
        for _ in range(50):
            if mock_process.call_count >= 1:
                break
            threading.Event().wait(0.01)
        assert mock_process.call_count == 1

        gen2 = CommandConversationService.subscribe(conv_id)
        next(gen2)
        # Give the would-be second spawn a chance to land.
        threading.Event().wait(0.05)
        assert mock_process.call_count == 1, (
            "Second subscribe must not re-fire the kickoff"
        )
        gen1.close()
        gen2.close()

    def test_get_conversation_in_memory(self):
        conv_id = _seed_conversation(CommandConversationService)
        # Add a user message so there's something visible
        CommandConversationService._conversations[conv_id]["messages"].append(
            ConversationMessage(
                role="user", content="Hello", timestamp=datetime.datetime.now().isoformat()
            )
        )
        result, status = CommandConversationService.get_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert result["id"] == conv_id
        assert result["status"] == "active"
        # System messages filtered out, user message visible
        assert len(result["messages_parsed"]) == 1
        assert result["messages_parsed"][0]["role"] == "user"

    def test_get_conversation_not_found(self):
        result, status = CommandConversationService.get_conversation("cmd_nonexistent")
        assert status == HTTPStatus.NOT_FOUND

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_get_conversation_from_db(self, mock_process):
        """Start a conversation, remove from memory, then get from DB."""
        result, status = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]

        # Persist a message so DB has content
        CommandConversationService._persist_messages(conv_id)

        # Remove from memory
        CommandConversationService._conversations.pop(conv_id, None)

        result, status = CommandConversationService.get_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert result["id"] == conv_id

    def test_send_message_not_found(self):
        result, status = CommandConversationService.send_message("cmd_nonexistent", "hi")
        assert status == HTTPStatus.NOT_FOUND

    def test_send_message_while_processing(self):
        conv_id = _seed_conversation(CommandConversationService, processing=True)
        result, status = CommandConversationService.send_message(conv_id, "hi")
        assert status == HTTPStatus.CONFLICT

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_send_message_success(self, mock_process):
        conv_id = _seed_conversation(CommandConversationService)
        result, status = CommandConversationService.send_message(conv_id, "Create a deploy command")
        assert status == HTTPStatus.OK
        assert result["status"] == "processing"
        # User message appended
        msgs = CommandConversationService._conversations[conv_id]["messages"]
        user_msgs = [m for m in msgs if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Create a deploy command"

    def test_abandon_conversation_in_memory(self):
        conv_id = _seed_conversation(CommandConversationService)
        result, status = CommandConversationService.abandon_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert conv_id not in CommandConversationService._conversations

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_abandon_conversation_from_db(self, mock_process):
        """Abandon a conversation that exists in DB but not in memory."""
        result, status = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        # Remove from memory
        CommandConversationService._cleanup_conversation(conv_id)
        assert conv_id not in CommandConversationService._conversations

        result, status = CommandConversationService.abandon_conversation(conv_id)
        assert status == HTTPStatus.OK

    def test_abandon_conversation_not_found(self):
        result, status = CommandConversationService.abandon_conversation("cmd_nonexistent")
        assert status == HTTPStatus.NOT_FOUND

    def test_list_conversations(self):
        result, status = CommandConversationService.list_conversations()
        assert status == HTTPStatus.OK
        assert "conversations" in result
        assert isinstance(result["conversations"], list)

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_resume_conversation_from_db(self, mock_process):
        """Start a conversation, remove from memory, resume it."""
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        CommandConversationService._persist_messages(conv_id)

        # Remove from memory
        CommandConversationService._conversations.pop(conv_id, None)
        CommandConversationService._subscribers.pop(conv_id, None)
        CommandConversationService._start_times.pop(conv_id, None)

        result, status = CommandConversationService.resume_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert conv_id in CommandConversationService._conversations

    def test_resume_already_active(self):
        conv_id = _seed_conversation(CommandConversationService)
        result, status = CommandConversationService.resume_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert "already active" in result["message"]

    def test_resume_not_found(self):
        result, status = CommandConversationService.resume_conversation("cmd_nonexistent")
        assert status == HTTPStatus.NOT_FOUND

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_resume_abandoned_conversation(self, mock_process):
        """Cannot resume an abandoned conversation."""
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        CommandConversationService.abandon_conversation(conv_id)

        result, status = CommandConversationService.resume_conversation(conv_id)
        assert status == HTTPStatus.GONE

    def test_cleanup_conversation(self):
        conv_id = _seed_conversation(CommandConversationService)
        CommandConversationService._cleanup_conversation(conv_id)
        assert conv_id not in CommandConversationService._conversations
        assert conv_id not in CommandConversationService._subscribers
        assert conv_id not in CommandConversationService._start_times

    def test_broadcast(self):
        from queue import Queue

        conv_id = _seed_conversation(CommandConversationService)
        q = Queue()
        CommandConversationService._subscribers[conv_id].append(q)

        CommandConversationService._broadcast(conv_id, "test_event", {"key": "value"})

        event = q.get_nowait()
        assert "event: test_event" in event
        assert '"key": "value"' in event

    def test_broadcast_no_subscribers(self):
        # Should not raise
        CommandConversationService._broadcast("nonexistent", "test", {})


# ---------------------------------------------------------------------------
# _extract_config_from_conversation
# ---------------------------------------------------------------------------


class TestExtractConfig:
    def test_extracts_valid_config(self):
        config_json = json.dumps({"name": "my-cmd", "description": "test"})
        msg = ConversationMessage(
            role="assistant",
            content=f"Here is your config:\n---COMMAND_CONFIG---\n{config_json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = _seed_conversation(
            CommandConversationService,
            messages=[
                ConversationMessage(
                    role="system", content="sys", timestamp=datetime.datetime.now().isoformat()
                ),
                msg,
            ],
        )
        config = CommandConversationService._extract_config_from_conversation(conv_id)
        assert config is not None
        assert config["name"] == "my-cmd"

    def test_returns_none_when_no_config(self):
        conv_id = _seed_conversation(CommandConversationService)
        config = CommandConversationService._extract_config_from_conversation(conv_id)
        assert config is None

    def test_returns_none_for_invalid_json(self):
        msg = ConversationMessage(
            role="assistant",
            content="---COMMAND_CONFIG---\n{invalid json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = _seed_conversation(CommandConversationService, messages=[msg])
        config = CommandConversationService._extract_config_from_conversation(conv_id)
        assert config is None

    def test_returns_none_for_unknown_conv(self):
        config = CommandConversationService._extract_config_from_conversation("cmd_unknown")
        assert config is None

    def test_searches_backwards_through_messages(self):
        """Later message config wins over earlier one."""
        old_msg = ConversationMessage(
            role="assistant",
            content='---COMMAND_CONFIG---\n{"name": "old"}\n---END_CONFIG---',
            timestamp=datetime.datetime.now().isoformat(),
        )
        new_msg = ConversationMessage(
            role="assistant",
            content='---COMMAND_CONFIG---\n{"name": "new"}\n---END_CONFIG---',
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = _seed_conversation(CommandConversationService, messages=[old_msg, new_msg])
        config = CommandConversationService._extract_config_from_conversation(conv_id)
        assert config["name"] == "new"


# ---------------------------------------------------------------------------
# _process_with_claude
# ---------------------------------------------------------------------------


def _seed_with_user_message(cls, conv_id="cmd_test123"):
    """Seed a conversation that has both the system prompt and a
    user kickoff already appended. v0.7.80 — ``_process_with_claude``
    now requires at least one non-empty user message in
    ``conv["messages"]`` before issuing an LLM call (defense in
    depth against the empty-content-block proxy error). Tests
    that exercise the success path of ``_process_with_claude``
    must seed that user message just like ``start_conversation``
    and ``send_message`` do in production.
    """
    return _seed_conversation(
        cls,
        conv_id=conv_id,
        messages=[
            ConversationMessage(
                role="system",
                content="System prompt",
                timestamp=datetime.datetime.now().isoformat(),
            ),
            ConversationMessage(
                role="user",
                content="hello",
                timestamp=datetime.datetime.now().isoformat(),
            ),
        ],
    )


class TestProcessWithClaude:
    @patch("app.services.base_conversation_service.BaseConversationService._stream_and_accumulate")
    def test_process_appends_assistant_message(self, mock_stream):
        mock_stream.return_value = "I can help with that!"
        conv_id = _seed_with_user_message(CommandConversationService)

        CommandConversationService._process_with_claude(conv_id, "hello")

        msgs = CommandConversationService._conversations[conv_id]["messages"]
        assistant_msgs = [m for m in msgs if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].content == "I can help with that!"

    @patch("app.services.base_conversation_service.BaseConversationService._stream_and_accumulate")
    def test_process_sets_processing_flag(self, mock_stream):
        mock_stream.return_value = "response"
        conv_id = _seed_with_user_message(CommandConversationService)

        CommandConversationService._process_with_claude(conv_id, "hello")

        # Processing should be False after completion
        assert CommandConversationService._conversations[conv_id]["processing"] is False

    @patch("app.services.base_conversation_service.BaseConversationService._stream_and_accumulate")
    def test_process_handles_exception(self, mock_stream):
        mock_stream.side_effect = RuntimeError("API error")
        conv_id = _seed_with_user_message(CommandConversationService)

        # Should not raise
        CommandConversationService._process_with_claude(conv_id, "hello")

        assert CommandConversationService._conversations[conv_id]["processing"] is False

    def test_process_with_missing_conversation(self):
        # Should not raise
        CommandConversationService._process_with_claude("cmd_missing", "hello")

    @patch("app.services.base_conversation_service.BaseConversationService._stream_and_accumulate")
    def test_process_skips_llm_when_no_user_message(self, mock_stream):
        """v0.7.80 — the defense-in-depth guard must skip the LLM
        call entirely when ``conv["messages"]`` contains only a
        system prompt (or no user message at all), so a regression
        that re-introduces the v0.7.76 "missing kickoff" pattern
        gets caught here instead of producing the upstream "text
        content blocks must be non-empty" error.
        """
        conv_id = _seed_conversation(CommandConversationService)  # system-only

        CommandConversationService._process_with_claude(conv_id, "hello")

        # _stream_and_accumulate must NOT have been invoked.
        mock_stream.assert_not_called()
        # No assistant message should have been appended.
        msgs = CommandConversationService._conversations[conv_id]["messages"]
        assert not any(m.role == "assistant" for m in msgs)
        # Processing flag should be reset by the ``finally`` block.
        assert CommandConversationService._conversations[conv_id]["processing"] is False

    @patch("app.services.base_conversation_service.BaseConversationService._stream_and_accumulate")
    def test_process_skips_llm_when_user_message_blank(self, mock_stream):
        """Whitespace-only user messages should also trip the
        guard — CLIProxyAPI's translation strips empty content
        blocks before validation, so a ``"   "`` user message is
        functionally identical to no user message at all.
        """
        conv_id = _seed_conversation(
            CommandConversationService,
            messages=[
                ConversationMessage(
                    role="system",
                    content="System prompt",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
                ConversationMessage(
                    role="user",
                    content="   \n  ",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            ],
        )

        CommandConversationService._process_with_claude(conv_id, "hello")

        mock_stream.assert_not_called()
        assert CommandConversationService._conversations[conv_id]["processing"] is False


# ---------------------------------------------------------------------------
# Defense-guard parity for Plugin + Skill services. v0.7.80 duplicates
# the empty-content-block filter into three services that don't share
# a base class. Cover Plugin + Skill here so a future refactor that
# drops the guard from one of them fails loudly.
# ---------------------------------------------------------------------------


class TestPluginDefenseGuard:
    @patch("app.services.conversation_streaming.stream_llm_response")
    def test_plugin_skips_llm_when_no_user_message(self, mock_stream):
        from app.services.plugin_conversation_service import (
            ConversationMessage as PluginMsg,
        )
        from app.services.plugin_conversation_service import (
            PluginConversationService,
        )

        conv_id = "plugin_guardtest1"
        PluginConversationService._conversations[conv_id] = {
            "messages": [
                PluginMsg(
                    role="system",
                    content="sys",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            ],
            "processing": False,
        }
        PluginConversationService._subscribers[conv_id] = []
        PluginConversationService._start_times[conv_id] = datetime.datetime.now()

        PluginConversationService._process_with_claude(conv_id, "hi")

        mock_stream.assert_not_called()
        assert PluginConversationService._conversations[conv_id]["processing"] is False
        # Cleanup so we don't leak between tests.
        PluginConversationService._conversations.pop(conv_id, None)
        PluginConversationService._subscribers.pop(conv_id, None)
        PluginConversationService._start_times.pop(conv_id, None)

    @patch("app.services.conversation_streaming.stream_llm_response")
    def test_plugin_skips_llm_when_user_message_blank(self, mock_stream):
        from app.services.plugin_conversation_service import (
            ConversationMessage as PluginMsg,
        )
        from app.services.plugin_conversation_service import (
            PluginConversationService,
        )

        conv_id = "plugin_guardtest2"
        PluginConversationService._conversations[conv_id] = {
            "messages": [
                PluginMsg(
                    role="system",
                    content="sys",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
                PluginMsg(
                    role="user",
                    content="   \n\t",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            ],
            "processing": False,
        }
        PluginConversationService._subscribers[conv_id] = []
        PluginConversationService._start_times[conv_id] = datetime.datetime.now()

        PluginConversationService._process_with_claude(conv_id, "hi")

        mock_stream.assert_not_called()
        assert PluginConversationService._conversations[conv_id]["processing"] is False
        PluginConversationService._conversations.pop(conv_id, None)
        PluginConversationService._subscribers.pop(conv_id, None)
        PluginConversationService._start_times.pop(conv_id, None)


class TestSkillDefenseGuard:
    @patch("app.services.conversation_streaming.stream_llm_response")
    def test_skill_skips_llm_when_no_user_message(self, mock_stream):
        from app.services.skill_conversation_service import (
            ConversationMessage as SkillMsg,
        )
        from app.services.skill_conversation_service import (
            SkillConversationService,
        )

        conv_id = "skill_guardtest111"
        SkillConversationService._conversations[conv_id] = {
            "messages": [
                SkillMsg(
                    role="system",
                    content="sys",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            ],
            "processing": False,
            "user_id": None,
        }
        SkillConversationService._subscribers[conv_id] = []
        SkillConversationService._start_times[conv_id] = datetime.datetime.now()

        SkillConversationService._process_with_claude(conv_id, "hi")

        mock_stream.assert_not_called()
        assert SkillConversationService._conversations[conv_id]["processing"] is False
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)
        SkillConversationService._start_times.pop(conv_id, None)

    @patch("app.services.conversation_streaming.stream_llm_response")
    def test_skill_skips_llm_when_user_message_blank(self, mock_stream):
        from app.services.skill_conversation_service import (
            ConversationMessage as SkillMsg,
        )
        from app.services.skill_conversation_service import (
            SkillConversationService,
        )

        conv_id = "skill_guardtest222"
        SkillConversationService._conversations[conv_id] = {
            "messages": [
                SkillMsg(
                    role="system",
                    content="sys",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
                SkillMsg(
                    role="user",
                    content=" \t\n ",
                    timestamp=datetime.datetime.now().isoformat(),
                ),
            ],
            "processing": False,
            "user_id": None,
        }
        SkillConversationService._subscribers[conv_id] = []
        SkillConversationService._start_times[conv_id] = datetime.datetime.now()

        SkillConversationService._process_with_claude(conv_id, "hi")

        mock_stream.assert_not_called()
        assert SkillConversationService._conversations[conv_id]["processing"] is False
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)
        SkillConversationService._start_times.pop(conv_id, None)


# ---------------------------------------------------------------------------
# _persist_messages
# ---------------------------------------------------------------------------


class TestPersistMessages:
    @patch.object(CommandConversationService, "_process_with_claude")
    def test_persist_messages_writes_to_db(self, mock_process):
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]

        CommandConversationService._persist_messages(conv_id)

        from app.database import get_design_conversation

        db_conv = get_design_conversation(conv_id)
        assert db_conv is not None
        messages = json.loads(db_conv["messages"])
        assert len(messages) >= 1

    def test_persist_messages_noop_missing_conv(self):
        # Should not raise
        CommandConversationService._persist_messages("cmd_missing")


# ---------------------------------------------------------------------------
# _cleanup_stale_conversations
# ---------------------------------------------------------------------------


class TestCleanupStale:
    @patch("app.services.base_conversation_service.STALE_CONVERSATION_THRESHOLD", 0)
    @patch.object(CommandConversationService, "_process_with_claude")
    def test_cleans_up_stale(self, mock_process):
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        # Force start_time to the past
        CommandConversationService._start_times[conv_id] = datetime.datetime(2020, 1, 1)

        CommandConversationService._cleanup_stale_conversations()

        assert conv_id not in CommandConversationService._conversations


# ---------------------------------------------------------------------------
# HookConversationService — subclass-specific markers
# ---------------------------------------------------------------------------


class TestHookConversationService:
    def test_entity_type(self):
        assert HookConversationService._get_entity_type() == "hook"

    def test_conv_id_prefix(self):
        assert HookConversationService._get_conv_id_prefix() == "hook_"
        conv_id = HookConversationService._generate_conv_id()
        assert conv_id.startswith("hook_")

    def test_config_markers(self):
        assert HookConversationService._get_config_start_marker() == "---HOOK_CONFIG---"
        assert HookConversationService._get_config_end_marker() == "---END_CONFIG---"

    def test_extract_hook_config(self):
        config_json = json.dumps({"name": "lint-check", "event": "PreToolUse"})
        msg = ConversationMessage(
            role="assistant",
            content=f"---HOOK_CONFIG---\n{config_json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = "hook_test123"
        HookConversationService._conversations[conv_id] = {
            "messages": [msg],
            "processing": False,
        }
        HookConversationService._subscribers[conv_id] = []
        HookConversationService._start_times[conv_id] = datetime.datetime.now()

        config = HookConversationService._extract_config_from_conversation(conv_id)
        assert config["name"] == "lint-check"
        assert config["event"] == "PreToolUse"

    @patch.object(HookConversationService, "_process_with_claude")
    def test_finalize_hook_entity(self, mock_process):
        """Test _finalize_entity creates a hook in the DB."""
        config_json = json.dumps(
            {
                "name": "test-hook",
                "event": "Stop",
                "description": "A test hook",
                "content": "echo done",
                "enabled": True,
            }
        )
        msg = ConversationMessage(
            role="assistant",
            content=f"---HOOK_CONFIG---\n{config_json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = "hook_finalize1"
        HookConversationService._conversations[conv_id] = {
            "messages": [msg],
            "processing": False,
        }
        HookConversationService._subscribers[conv_id] = []
        HookConversationService._start_times[conv_id] = datetime.datetime.now()

        result, status = HookConversationService._finalize_entity(conv_id)
        assert status == HTTPStatus.CREATED
        assert "hook_id" in result
        assert result["message"] == "Hook created successfully"

    def test_finalize_entity_not_found(self):
        result, status = HookConversationService._finalize_entity("hook_missing")
        assert status == HTTPStatus.NOT_FOUND

    def test_finalize_entity_no_config(self):
        conv_id = "hook_noconfig"
        HookConversationService._conversations[conv_id] = {
            "messages": [
                ConversationMessage(
                    role="assistant",
                    content="No config here",
                    timestamp=datetime.datetime.now().isoformat(),
                )
            ],
            "processing": False,
        }
        HookConversationService._subscribers[conv_id] = []
        HookConversationService._start_times[conv_id] = datetime.datetime.now()

        result, status = HookConversationService._finalize_entity(conv_id)
        assert status == HTTPStatus.BAD_REQUEST


# ---------------------------------------------------------------------------
# RuleConversationService — subclass-specific markers
# ---------------------------------------------------------------------------


class TestRuleConversationService:
    def test_entity_type(self):
        assert RuleConversationService._get_entity_type() == "rule"

    def test_conv_id_prefix(self):
        conv_id = RuleConversationService._generate_conv_id()
        assert conv_id.startswith("rule_")

    def test_config_markers(self):
        assert RuleConversationService._get_config_start_marker() == "---RULE_CONFIG---"

    @patch.object(RuleConversationService, "_process_with_claude")
    def test_finalize_rule_entity(self, mock_process):
        config_json = json.dumps(
            {
                "name": "no-console",
                "rule_type": "validation",
                "description": "No console.log",
                "condition": "when files contain console.log",
                "action": "warn",
                "enabled": True,
            }
        )
        msg = ConversationMessage(
            role="assistant",
            content=f"---RULE_CONFIG---\n{config_json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = "rule_finalize1"
        RuleConversationService._conversations[conv_id] = {
            "messages": [msg],
            "processing": False,
        }
        RuleConversationService._subscribers[conv_id] = []
        RuleConversationService._start_times[conv_id] = datetime.datetime.now()

        result, status = RuleConversationService._finalize_entity(conv_id)
        assert status == HTTPStatus.CREATED
        assert "rule_id" in result


# ---------------------------------------------------------------------------
# CommandConversationService._finalize_entity
# ---------------------------------------------------------------------------


class TestCommandFinalize:
    @patch.object(CommandConversationService, "_process_with_claude")
    def test_finalize_command_entity(self, mock_process):
        config_json = json.dumps(
            {
                "name": "deploy",
                "description": "Deploy to production",
                "content": "Run deploy script",
                "arguments": [{"name": "env", "type": "string", "description": "Target env"}],
                "enabled": True,
            }
        )
        msg = ConversationMessage(
            role="assistant",
            content=f"---COMMAND_CONFIG---\n{config_json}\n---END_CONFIG---",
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv_id = "cmd_finalize1"
        CommandConversationService._conversations[conv_id] = {
            "messages": [msg],
            "processing": False,
        }
        CommandConversationService._subscribers[conv_id] = []
        CommandConversationService._start_times[conv_id] = datetime.datetime.now()

        result, status = CommandConversationService._finalize_entity(conv_id)
        assert status == HTTPStatus.CREATED
        assert "command_id" in result

    def test_finalize_command_not_found(self):
        result, status = CommandConversationService._finalize_entity("cmd_missing")
        assert status == HTTPStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# ConversationBranchService
# ---------------------------------------------------------------------------


class TestConversationBranchService:
    def _create_agent_conversation_with_messages(self):
        """Create an agent conversation with messages in the DB, return conv_id."""
        from app.database import create_agent_conversation, update_agent_conversation

        conv_id = create_agent_conversation()
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Help me"},
            {"role": "assistant", "content": "Sure thing!"},
        ]
        update_agent_conversation(conv_id, messages=json.dumps(messages))
        return conv_id

    def test_create_branch(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_branch(conv_id, fork_message_index=2, name="fix")
        assert branch is not None
        assert branch.get("conversation_id") == conv_id
        assert branch.get("name") == "fix"

    def test_create_branch_copies_messages_up_to_index(self):
        from app.services.conversation_branch_service import ConversationBranchService
        from app.db.conversation_branches import get_messages_for_branch

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_branch(conv_id, fork_message_index=2)
        branch_id = branch["id"]

        msgs = get_messages_for_branch(branch_id, conv_id)
        assert len(msgs) == 3  # indices 0, 1, 2
        assert msgs[0]["role"] == "system"
        assert msgs[2]["role"] == "assistant"

    def test_create_branch_not_found(self):
        from app.services.conversation_branch_service import ConversationBranchService

        with pytest.raises(ValueError, match="Conversation not found"):
            ConversationBranchService.create_branch("conv_missing", fork_message_index=0)

    def test_create_branch_index_out_of_bounds(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        with pytest.raises(ValueError, match="out of bounds"):
            ConversationBranchService.create_branch(conv_id, fork_message_index=99)

    def test_create_branch_negative_index(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        with pytest.raises(ValueError, match="out of bounds"):
            ConversationBranchService.create_branch(conv_id, fork_message_index=-1)

    def test_create_main_branch(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_main_branch(conv_id)
        assert branch is not None
        assert branch.get("name") == "main"

    def test_create_main_branch_copies_all_messages(self):
        from app.services.conversation_branch_service import ConversationBranchService
        from app.db.conversation_branches import get_messages_for_branch

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_main_branch(conv_id)

        msgs = get_messages_for_branch(branch["id"], conv_id)
        assert len(msgs) == 5

    def test_create_main_branch_not_found(self):
        from app.services.conversation_branch_service import ConversationBranchService

        with pytest.raises(ValueError, match="Conversation not found"):
            ConversationBranchService.create_main_branch("conv_missing")

    def test_add_message_to_branch(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_branch(conv_id, fork_message_index=1)
        branch_id = branch["id"]

        msg = ConversationBranchService.add_message(branch_id, "user", "New question")
        assert msg is not None
        assert msg.get("role") == "user"
        assert msg.get("content") == "New question"

    def test_add_message_branch_not_found(self):
        from app.services.conversation_branch_service import ConversationBranchService

        with pytest.raises(ValueError, match="Branch not found"):
            ConversationBranchService.add_message("branch-missing", "user", "hi")

    def test_get_branch_messages(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        branch = ConversationBranchService.create_branch(conv_id, fork_message_index=1)
        branch_id = branch["id"]

        msgs = ConversationBranchService.get_branch_messages(branch_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_get_branch_messages_not_found(self):
        from app.services.conversation_branch_service import ConversationBranchService

        with pytest.raises(ValueError, match="Branch not found"):
            ConversationBranchService.get_branch_messages("branch-missing")

    def test_get_conversation_branches(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        ConversationBranchService.create_main_branch(conv_id)
        ConversationBranchService.create_branch(conv_id, fork_message_index=2, name="fix")

        branches = ConversationBranchService.get_conversation_branches(conv_id)
        assert len(branches) == 2
        # Each branch should have message_count
        for b in branches:
            assert "message_count" in b

    def test_get_conversation_branches_empty(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        branches = ConversationBranchService.get_conversation_branches(conv_id)
        assert branches == []

    def test_get_branch_tree(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        ConversationBranchService.create_main_branch(conv_id)

        tree = ConversationBranchService.get_branch_tree(conv_id)
        assert tree["conversation_id"] == conv_id
        assert len(tree["branches"]) >= 1

    def test_get_branch_tree_empty(self):
        from app.services.conversation_branch_service import ConversationBranchService

        conv_id = self._create_agent_conversation_with_messages()
        tree = ConversationBranchService.get_branch_tree(conv_id)
        assert tree["branches"] == []


# ---------------------------------------------------------------------------
# Conversation lifecycle integration
# ---------------------------------------------------------------------------


class TestConversationLifecycle:
    @patch.object(CommandConversationService, "_process_with_claude")
    def test_start_send_abandon(self, mock_process):
        """Full lifecycle: start -> send message -> abandon."""
        result, status = CommandConversationService.start_conversation()
        assert status == HTTPStatus.CREATED
        conv_id = result["conversation_id"]

        result, status = CommandConversationService.send_message(conv_id, "Make a lint command")
        assert status == HTTPStatus.OK

        result, status = CommandConversationService.abandon_conversation(conv_id)
        assert status == HTTPStatus.OK
        assert conv_id not in CommandConversationService._conversations

    @patch.object(CommandConversationService, "_process_with_claude")
    def test_start_remove_resume_send(self, mock_process):
        """Lifecycle: start -> evict from memory -> resume -> send."""
        result, _ = CommandConversationService.start_conversation()
        conv_id = result["conversation_id"]
        CommandConversationService._persist_messages(conv_id)

        # Evict from memory
        CommandConversationService._conversations.pop(conv_id, None)
        CommandConversationService._subscribers.pop(conv_id, None)
        CommandConversationService._start_times.pop(conv_id, None)

        # Resume
        result, status = CommandConversationService.resume_conversation(conv_id)
        assert status == HTTPStatus.OK

        # Send message to resumed conversation
        result, status = CommandConversationService.send_message(conv_id, "continue")
        assert status == HTTPStatus.OK


# ---------------------------------------------------------------------------
# State isolation between subclasses
# ---------------------------------------------------------------------------


class TestSubclassStateIsolation:
    """Verify that each subclass has independent state dictionaries."""

    @patch.object(CommandConversationService, "_process_with_claude")
    @patch.object(HookConversationService, "_process_with_claude")
    def test_conversations_not_shared(self, mock_hook_process, mock_cmd_process):
        cmd_result, _ = CommandConversationService.start_conversation()
        cmd_id = cmd_result["conversation_id"]

        hook_result, _ = HookConversationService.start_conversation()
        hook_id = hook_result["conversation_id"]

        assert cmd_id in CommandConversationService._conversations
        assert cmd_id not in HookConversationService._conversations
        assert hook_id in HookConversationService._conversations
        assert hook_id not in CommandConversationService._conversations
