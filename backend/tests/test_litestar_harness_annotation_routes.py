"""Routes test for the Life-Harness annotation endpoints (T1, b).

Exercises:
- ``GET /admin/executions/annotations/summary`` aggregate roll-up
- ``GET /admin/executions/{id}/annotation`` per-execution detail
"""

from __future__ import annotations

from litestar.testing import create_test_client

from app.services.harness_failure_annotator import annotate_from_text
from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


# A minimal Claude-stream stub that the annotator classifies as H2.
H2_STREAM = (
    '{"type": "assistant", "message": {"content": '
    '[{"type": "text", "text": "I will take_action({a:1})"}]}}'
)


def test_per_execution_annotation_returns_payload(isolated_db):
    annotate_from_text(
        "trigger_execution", "exec-aaa", H2_STREAM,
        project_id=None, backend_type="claude", outcome="failed",
    )
    with _client() as c:
        resp = c.get("/admin/executions/exec-aaa/annotation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["annotation"]["primary_layer"] == "h2"
    assert body["annotation"]["h2_count"] >= 1
    assert body["incidents"], "expected at least one incident row"
    assert body["incidents"][0]["layer"] == "h2"


def test_per_execution_annotation_unannotated_returns_nulls(isolated_db):
    """Unannotated is NOT a 404 — the UI distinguishes between
    "execution does not exist" (404 on /admin/executions/{id}) and
    "no annotation yet" (this endpoint returns ``annotation=null``)."""
    with _client() as c:
        resp = c.get("/admin/executions/exec-never-annotated/annotation")
    assert resp.status_code == 200
    assert resp.json() == {"annotation": None, "incidents": []}


def test_summary_aggregates_by_layer(isolated_db):
    # Two H2 failures + one clean run → h2=2, none=1.
    annotate_from_text("trigger_execution", "exec-aaa", H2_STREAM,
                       project_id=None, backend_type="claude", outcome="failed")
    annotate_from_text("trigger_execution", "exec-bbb", H2_STREAM,
                       project_id=None, backend_type="claude", outcome="failed")
    annotate_from_text("trigger_execution", "exec-ccc", "",
                       project_id=None, backend_type="claude", outcome="success")

    with _client() as c:
        resp = c.get("/admin/executions/annotations/summary?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_layer"]["h2"] == 2
    assert body["by_layer"]["none"] == 1
    assert body["by_layer"]["total"] == 3
    # recent_failures excludes the clean run.
    ids = [r["session_id"] for r in body["recent_failures"]]
    assert "exec-ccc" not in ids
    assert set(ids) >= {"exec-aaa", "exec-bbb"}


def test_summary_filters_by_primary_layer(isolated_db):
    annotate_from_text("trigger_execution", "exec-aaa", H2_STREAM,
                       project_id=None, backend_type="claude", outcome="failed")
    # An outcome=failed with NO classifiable trajectory → general bucket.
    annotate_from_text("trigger_execution", "exec-bbb", "",
                       project_id=None, backend_type="claude", outcome="failed")

    with _client() as c:
        resp = c.get(
            "/admin/executions/annotations/summary?primary_layer=h2&limit=5"
        )
    assert resp.status_code == 200
    ids = [r["session_id"] for r in resp.json()["recent_failures"]]
    assert ids == ["exec-aaa"]
