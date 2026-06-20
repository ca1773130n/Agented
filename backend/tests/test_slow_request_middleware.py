"""v0.6.2: SlowRequestMiddleware tests."""

import asyncio
import logging

import pytest


def _make_scope(method: str = "GET", path: str = "/test") -> dict:
    return {"type": "http", "method": method, "path": path, "headers": []}


class _StubSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
class TestSlowRequestMiddleware:
    async def test_fast_request_does_not_log(self, monkeypatch, caplog):
        from app_litestar.middleware import SlowRequestMiddleware

        monkeypatch.setenv("SLOW_REQUEST_THRESHOLD_MS", "5000")  # high
        mw = SlowRequestMiddleware()

        async def quick_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        with caplog.at_level(logging.WARNING, logger="app.request"):
            await mw.handle(_make_scope(), None, _StubSend(), quick_app)
        assert not any("slow request" in r.message for r in caplog.records)

    async def test_slow_request_logs_warning(self, monkeypatch, caplog):
        from app_litestar.middleware import SlowRequestMiddleware

        monkeypatch.setenv("SLOW_REQUEST_THRESHOLD_MS", "10")  # low — easy trigger
        mw = SlowRequestMiddleware()

        async def slow_app(scope, receive, send):
            await asyncio.sleep(0.05)  # 50ms > 10ms threshold
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        with caplog.at_level(logging.WARNING, logger="app.request"):
            await mw.handle(_make_scope("POST", "/api/slow"), None, _StubSend(), slow_app)
        slow_records = [r for r in caplog.records if "slow request" in r.message]
        assert len(slow_records) == 1
        assert "POST /api/slow" in slow_records[0].message
        assert "threshold 10ms" in slow_records[0].message

    async def test_non_http_scope_is_no_op(self):
        from app_litestar.middleware import SlowRequestMiddleware

        mw = SlowRequestMiddleware()
        sender = _StubSend()

        async def ws_next(scope, receive, send):
            await send({"type": "websocket.accept"})

        scope = {"type": "websocket", "path": "/ws"}
        await mw.handle(scope, None, sender, ws_next)
        # Should not raise; pass through unchanged.
        assert any(m["type"] == "websocket.accept" for m in sender.messages)
