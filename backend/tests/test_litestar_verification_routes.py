"""GET/POST verification records over the Litestar app (Phase 2 P5)."""

from __future__ import annotations

import os

os.environ.setdefault("AGENTED_LITESTAR_SKIP_STARTUP", "1")

from litestar.testing import create_test_client

from app.db import verification_records as vr
from app_litestar.auth import provide_caller
from app_litestar.routes.verification import verification_router


def _client():
    return create_test_client(
        route_handlers=[verification_router],
        dependencies={"caller": provide_caller},
    )


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="claude",
        command="echo hi",
    )


def test_get_returns_records(isolated_db):
    _make_execution()
    vr.record_verification("exec-1", "no secrets", status="passed")
    with _client() as client:
        resp = client.get("/api/executions/exec-1/verifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["claim"] == "no secrets"


def test_post_records_a_verification(isolated_db):
    _make_execution()
    with _client() as client:
        resp = client.post(
            "/api/executions/exec-1/verifications",
            json={"claim": "lint clean", "status": "passed", "evidence_ref": "ci.log"},
        )
    assert resp.status_code in (200, 201)
    rows = vr.list_verifications("exec-1")
    assert rows[0]["claim"] == "lint clean"


def test_post_rejects_invalid_status_with_400(isolated_db):
    """An out-of-range status must be rejected cleanly (ClientException 400),
    not surface as a misleading IntegrityError/409 from the CHECK constraint."""
    _make_execution()
    with _client() as client:
        resp = client.post(
            "/api/executions/exec-1/verifications",
            json={"claim": "x", "status": "bogus"},
        )
    assert resp.status_code == 400
    assert vr.list_verifications("exec-1") == []
