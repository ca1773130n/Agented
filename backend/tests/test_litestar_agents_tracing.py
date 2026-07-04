"""Smoke tests for the Litestar agents + tracing routers (wave 60)."""

import pytest
from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.agents_and_tracing import agents_router, tracing_router


def _client():
    return create_test_client(
        route_handlers=[agents_router, tracing_router],
        dependencies={"caller": provide_caller},
    )


# Agents


def test_list_agents_bootstrap(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/")
    assert resp.status_code == 200
    assert "agents" in resp.json()


def test_unknown_agent_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/agents/missing-id")
    assert resp.status_code == 404


# Traces


def test_list_traces_empty(isolated_db):
    with _client() as c:
        resp = c.get("/admin/traces/")
    assert resp.status_code == 200
    body = resp.json()
    assert "traces" in body and "total" in body


def test_create_trace(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/traces/",
            json={
                "name": "Test trace",
                "entity_type": "agent",
                "entity_id": "agent-x",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Test trace"


def test_unknown_trace_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/traces/missing-id")
    assert resp.status_code == 404


def test_trace_stats(isolated_db):
    with _client() as c:
        resp = c.get("/admin/traces/stats")
    assert resp.status_code == 200


def test_end_unknown_trace_404(isolated_db):
    with _client() as c:
        resp = c.put(
            "/admin/traces/missing-id/end",
            json={"status": "ok"},
        )
    assert resp.status_code == 404


def test_create_span_for_unknown_trace_404(isolated_db):
    with _client() as c:
        resp = c.post(
            "/admin/traces/missing-id/spans",
            json={"name": "test span"},
        )
    assert resp.status_code == 404


def test_list_spans_for_unknown_trace_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/traces/missing-id/spans")
    assert resp.status_code == 404


def test_unknown_span_404(isolated_db):
    with _client() as c:
        resp = c.get("/admin/traces/some-trace/spans/missing-span")
    assert resp.status_code == 404


@pytest.mark.skip(
    reason="Deadlocks the whole suite: these read an infinite SSE stream through the "
    "Litestar TestClient's anyio blocking portal, which cannot return the streaming "
    "response for a synchronous long-lived generator — c.stream() blocks in "
    "portal.call().result() at establishment (uninterruptible, main thread in "
    "waiter.acquire()). This is a test-harness limitation, not a product bug: the "
    "/admin/traces/{id}/stream endpoint serves SSE correctly under real ASGI "
    "(gunicorn/uvicorn). Rework as httpx-ASGI streaming with a read deadline to re-enable."
)
class TestStreamTrace:
    """v0.5.10: SSE stream of trace events for live trace observability."""

    def _client_with_router(self):
        from litestar.testing import create_test_client

        from app_litestar.auth import provide_caller
        from app_litestar.routes.agents_and_tracing import tracing_router

        return create_test_client(
            route_handlers=[tracing_router],
            dependencies={"caller": provide_caller},
        )

    def test_stream_trace_emits_span_started_for_existing_spans(self, isolated_db):
        from app.db.tracing import create_span, create_trace

        trace = create_trace("T", "agent", "agent-01")
        s1 = create_span(trace["id"], "S1", "AGENT_RUN")
        with self._client_with_router() as c:
            # The polling loop emits initial snapshot on first iteration.
            # Use a streaming GET with a tight read deadline.
            with c.stream("GET", f"/admin/traces/{trace['id']}/stream") as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                # Read up to N bytes; first iteration should emit the
                # span_started for S1.
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if b"span_started" in body and s1["id"].encode() in body:
                        break
                    if len(body) > 65_536:
                        break
        assert b"span_started" in body
        assert s1["id"].encode() in body

    def test_stream_trace_unknown_trace_emits_error(self, isolated_db):
        with self._client_with_router() as c:
            with c.stream("GET", "/admin/traces/missing/stream") as resp:
                assert resp.status_code == 200
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if b"error" in body and b"not_found" in body:
                        break
                    if len(body) > 4096:
                        break
        assert b"event: error" in body
        assert b"not_found" in body

    def test_stream_trace_completed_emits_trace_ended_and_closes(self, isolated_db):
        from app.db.tracing import create_trace, end_trace

        trace = create_trace("T", "agent", "agent-01")
        end_trace(trace["id"], "completed")  # already terminal
        with self._client_with_router() as c:
            with c.stream("GET", f"/admin/traces/{trace['id']}/stream") as resp:
                assert resp.status_code == 200
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if b"trace_ended" in body:
                        break
                    if len(body) > 16_384:
                        break
        assert b"event: trace_ended" in body
