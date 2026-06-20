"""v0.6.0: PerformanceMiddleware tests."""

import re

import pytest


def _make_scope() -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
    }


class _StubSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


async def _stub_next(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
class TestPerformanceMiddleware:
    async def test_server_timing_header_present_on_response(self):
        from app_litestar.middleware import PerformanceMiddleware

        mw = PerformanceMiddleware()
        sender = _StubSend()
        await mw.handle(_make_scope(), None, sender, _stub_next)
        start = next(m for m in sender.messages if m["type"] == "http.response.start")
        names = [name for (name, _) in start["headers"]]
        assert b"server-timing" in names

    async def test_server_timing_value_is_app_dur_format(self):
        from app_litestar.middleware import PerformanceMiddleware

        mw = PerformanceMiddleware()
        sender = _StubSend()
        await mw.handle(_make_scope(), None, sender, _stub_next)
        start = next(m for m in sender.messages if m["type"] == "http.response.start")
        st_value = next(v for (k, v) in start["headers"] if k == b"server-timing")
        text = st_value.decode("latin-1")
        # Format: "app;dur=42.3"
        m = re.match(r"^app;dur=(\d+\.\d+)$", text)
        assert m is not None, f"unexpected Server-Timing format: {text!r}"
        ms = float(m.group(1))
        assert ms >= 0.0

    async def test_non_http_scope_passes_through(self):
        """WebSocket / lifespan scopes shouldn't trigger header injection."""
        from app_litestar.middleware import PerformanceMiddleware

        mw = PerformanceMiddleware()
        sender = _StubSend()
        scope = {"type": "websocket", "path": "/ws"}

        async def ws_next(scope, receive, send):
            await send({"type": "websocket.accept"})

        await mw.handle(scope, None, sender, ws_next)
        # No server-timing injection on non-http.
        for m in sender.messages:
            for name, _ in m.get("headers", []):
                assert name != b"server-timing"
