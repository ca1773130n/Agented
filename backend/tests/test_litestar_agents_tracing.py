"""Smoke tests for the Litestar agents + tracing routers (wave 60)."""

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
