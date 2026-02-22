"""Tests for CLIProxyManager, CLIProxyChatService, and ChatState models.

Covers:
- Pydantic model validation (ChatDelta, ChatStateSnapshot, ChatMessage)
- Mock streaming with content deltas
- Tool call argument accumulation across fragmented chunks
- Finish signal handling
- CLIProxyManager lifecycle with mocked subprocess and httpx
- DB proxy columns (get_proxy_enabled_accounts, update_account_proxy_config)
"""

from unittest.mock import MagicMock, patch

from app.models.chat_state import ChatDelta, ChatDeltaType, ChatMessage, ChatStateSnapshot
from app.services.cliproxy_chat_service import CLIProxyChatService
from app.services.cliproxy_manager import CLIProxyManager

# =============================================================================
# Model validation
# =============================================================================


class TestChatDeltaModel:
    """ChatDelta validates with all field combinations."""

    def test_content_delta(self):
        d = ChatDelta(type=ChatDeltaType.CONTENT_DELTA, text="hello")
        assert d.type == ChatDeltaType.CONTENT_DELTA
        assert d.text == "hello"
        assert d.tool_call_id is None

    def test_tool_call_delta(self):
        d = ChatDelta(
            type=ChatDeltaType.TOOL_CALL,
            tool_call_id="tc-1",
            function_name="search",
            arguments_json='{"q": "test"}',
        )
        assert d.type == ChatDeltaType.TOOL_CALL
        assert d.function_name == "search"
        assert d.arguments_json == '{"q": "test"}'

    def test_finish_delta(self):
        d = ChatDelta(type=ChatDeltaType.FINISH, finish_reason="stop")
        assert d.finish_reason == "stop"

    def test_error_delta(self):
        d = ChatDelta(type=ChatDeltaType.ERROR, error_message="timeout")
        assert d.error_message == "timeout"

    def test_minimal_delta(self):
        d = ChatDelta(type=ChatDeltaType.CONTENT_DELTA)
        assert d.text is None


class TestChatStateSnapshotModel:
    """ChatStateSnapshot validates with defaults and full data."""

    def test_defaults(self):
        s = ChatStateSnapshot(seq=0, timestamp="2026-02-17T00:00:00Z")
        assert s.seq == 0
        assert s.messages == []
        assert s.streaming_delta == ""
        assert s.process_groups == []
        assert s.status == "idle"

    def test_full_data(self):
        s = ChatStateSnapshot(
            seq=5,
            messages=[{"role": "user", "content": "hi"}],
            streaming_delta="partial...",
            process_groups=[{"id": "pg-1", "type": "tool"}],
            status="streaming",
            timestamp="2026-02-17T01:00:00Z",
        )
        assert s.seq == 5
        assert len(s.messages) == 1
        assert s.status == "streaming"


class TestChatMessageModel:
    """ChatMessage validates with all fields."""

    def test_basic_message(self):
        m = ChatMessage(role="user", content="hello", timestamp="2026-02-17T00:00:00Z")
        assert m.role == "user"
        assert m.tool_calls is None

    def test_with_tool_calls(self):
        m = ChatMessage(
            role="assistant",
            content="",
            timestamp="2026-02-17T00:00:00Z",
            tool_calls=[{"id": "tc-1", "function": {"name": "run"}}],
        )
        assert len(m.tool_calls) == 1


# =============================================================================
# CLIProxyChatService streaming
# =============================================================================


import json as _json
from contextlib import contextmanager


def _sse_line(data: dict) -> str:
    """Build an SSE data line from a dict."""
    return f"data: {_json.dumps(data)}"


def _sse_chunk(content=None, tool_calls=None, finish_reason=None):
    """Build an SSE data line for an OpenAI-compatible streaming chunk."""
    delta = {}
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls
    choice = {"delta": delta, "finish_reason": finish_reason}
    return _sse_line({"choices": [choice]})


def _mock_httpx_stream(lines, status_code=200):
    """Create a mock for httpx.stream() context manager returning SSE lines."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.iter_lines.return_value = iter(lines)

    @contextmanager
    def _stream(*args, **kwargs):
        yield mock_response

    return _stream


class TestStreamChatContentDeltas:
    """Mock httpx streaming SSE with content, verify ChatDelta yields."""

    @patch("app.services.cliproxy_chat_service.httpx")
    def test_yields_content_deltas(self, mock_httpx):
        lines = [
            _sse_chunk(content="Hello"),
            _sse_chunk(content=" world"),
            _sse_chunk(finish_reason="stop"),
            "data: [DONE]",
        ]
        mock_httpx.stream = _mock_httpx_stream(lines)
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = Exception

        deltas = list(
            CLIProxyChatService.stream_chat(
                base_url="http://127.0.0.1:18301/v1",
                messages=[{"role": "user", "content": "hi"}],
            )
        )

        assert len(deltas) == 3
        assert deltas[0].type == ChatDeltaType.CONTENT_DELTA
        assert deltas[0].text == "Hello"
        assert deltas[1].type == ChatDeltaType.CONTENT_DELTA
        assert deltas[1].text == " world"
        assert deltas[2].type == ChatDeltaType.FINISH
        assert deltas[2].finish_reason == "stop"


class TestStreamChatToolCallAccumulation:
    """Mock tool_call chunks with fragmented arguments, verify accumulated JSON."""

    @patch("app.services.cliproxy_chat_service.httpx")
    def test_accumulates_tool_call_fragments(self, mock_httpx):
        tc_frag1 = [
            {"index": 0, "id": "tc-1", "function": {"name": "search", "arguments": '{"q":'}}
        ]
        tc_frag2 = [{"index": 0, "id": None, "function": {"arguments": ' "test"}'}}]

        lines = [
            _sse_chunk(tool_calls=tc_frag1),
            _sse_chunk(tool_calls=tc_frag2),
            _sse_chunk(finish_reason="stop"),
            "data: [DONE]",
        ]
        mock_httpx.stream = _mock_httpx_stream(lines)
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = Exception

        deltas = list(
            CLIProxyChatService.stream_chat(
                base_url="http://127.0.0.1:18301/v1",
                messages=[{"role": "user", "content": "search"}],
            )
        )

        # Should yield: tool_call (accumulated) then finish
        assert len(deltas) == 2
        tc_delta = deltas[0]
        assert tc_delta.type == ChatDeltaType.TOOL_CALL
        assert tc_delta.tool_call_id == "tc-1"
        assert tc_delta.function_name == "search"
        assert tc_delta.arguments_json == '{"q": "test"}'

        assert deltas[1].type == ChatDeltaType.FINISH


class TestStreamChatFinish:
    """Mock finish_reason='stop', verify finish ChatDelta."""

    @patch("app.services.cliproxy_chat_service.httpx")
    def test_finish_stop(self, mock_httpx):
        lines = [
            _sse_chunk(finish_reason="stop"),
            "data: [DONE]",
        ]
        mock_httpx.stream = _mock_httpx_stream(lines)
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = Exception

        deltas = list(
            CLIProxyChatService.stream_chat(
                base_url="http://127.0.0.1:18301/v1",
                messages=[{"role": "user", "content": "x"}],
            )
        )

        assert len(deltas) == 1
        assert deltas[0].type == ChatDeltaType.FINISH
        assert deltas[0].finish_reason == "stop"


class TestStreamChatProxyError:
    """Verify error handling for proxy errors."""

    @patch("app.services.cliproxy_chat_service.httpx")
    def test_http_error_yields_error_delta(self, mock_httpx):
        error_body = _json.dumps({"error": {"message": "Model not found"}}).encode()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.read.return_value = error_body
        mock_httpx.TimeoutException = Exception
        mock_httpx.ConnectError = Exception

        @contextmanager
        def _stream(*args, **kwargs):
            yield mock_response

        mock_httpx.stream = _stream

        deltas = list(
            CLIProxyChatService.stream_chat(
                base_url="http://127.0.0.1:18301/v1",
                messages=[{"role": "user", "content": "x"}],
            )
        )

        assert len(deltas) == 1
        assert deltas[0].type == ChatDeltaType.ERROR
        assert "Model not found" in deltas[0].error_message


# =============================================================================
# CLIProxyManager lifecycle
# =============================================================================


class TestCLIProxyManagerLifecycle:
    """Test single global CLIProxyManager lifecycle with mocked subprocess and httpx."""

    def setup_method(self):
        """Ensure clean state before each test."""
        CLIProxyManager._process = None

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_base_url_when_healthy(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        url = CLIProxyManager.get_base_url()
        assert url == "http://127.0.0.1:8317/v1"

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_base_url_when_unhealthy(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("connection refused")
        url = CLIProxyManager.get_base_url()
        assert url is None

    @patch("app.services.cliproxy_manager.httpx")
    def test_get_url_and_key_when_healthy(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        result = CLIProxyManager.get_url_and_key()
        assert result is not None
        base_url, api_key = result
        assert base_url == f"http://127.0.0.1:{CLIProxyManager._port}/v1"
        assert isinstance(api_key, str) and len(api_key) > 0

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_healthy(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert CLIProxyManager.is_healthy() is True

    @patch("app.services.cliproxy_manager.httpx")
    def test_is_not_healthy(self, mock_httpx):
        mock_httpx.get.side_effect = Exception("refused")
        assert CLIProxyManager.is_healthy() is False

    @patch("app.services.cliproxy_manager.httpx")
    def test_legacy_get_instance(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert CLIProxyManager.get_instance(1) is not None

    @patch("app.services.cliproxy_manager.httpx")
    def test_legacy_list_instances(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        listing = CLIProxyManager.list_instances()
        assert 0 in listing
        assert listing[0]["port"] == 8317
        assert listing[0]["healthy"] is True

    def test_stop_noop_when_no_process(self):
        """stop is a no-op when no process is running."""
        CLIProxyManager.stop()  # Should not raise


# =============================================================================
# DB proxy columns
# =============================================================================


class TestProxyDBColumns:
    """Test get_proxy_enabled_accounts and update_account_proxy_config with isolated_db."""

    def test_proxy_columns_exist_in_schema(self, isolated_db):
        """Verify proxy_port and use_proxy columns exist after fresh init."""
        from app.db.connection import get_connection

        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(backend_accounts)")
            columns = {row[1] for row in cursor.fetchall()}

        assert "proxy_port" in columns
        assert "use_proxy" in columns

    def test_get_proxy_enabled_accounts_empty(self, isolated_db):
        """No accounts with use_proxy=1 by default."""
        from app.db.backends import get_proxy_enabled_accounts

        result = get_proxy_enabled_accounts()
        assert result == []

    def test_update_and_get_proxy_accounts(self, isolated_db):
        """Create account, enable proxy, verify it appears."""
        from app.db.backends import (
            create_backend_account,
            get_proxy_enabled_accounts,
            update_account_proxy_config,
        )
        from app.db.connection import get_connection

        # Ensure a backend exists for the FK
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ai_backends (id, name, type) VALUES ('claude', 'Claude', 'claude')"
            )
            conn.commit()

        acct_id = create_backend_account(
            backend_id="claude",
            account_name="test-acct",
            email="test@test.com",
            config_path="/tmp/auth",
            api_key_env=None,
            is_default=1,
            plan="pro",
            usage_data=None,
        )

        # Enable proxy
        updated = update_account_proxy_config(acct_id, proxy_port=18301, use_proxy=1)
        assert updated is True

        # Should appear in proxy-enabled list
        accounts = get_proxy_enabled_accounts()
        assert len(accounts) == 1
        assert accounts[0]["id"] == acct_id
        assert accounts[0]["proxy_port"] == 18301
        assert accounts[0]["use_proxy"] == 1
