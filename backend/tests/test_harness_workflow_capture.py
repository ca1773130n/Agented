"""Regression: workflow session capture must key on the execution-row id."""

from __future__ import annotations

import inspect

import pytest

from app.database import get_connection
from app.services import workflow_execution_service as wes
from app.services.harness_failure_annotator import _fetch_workflow


@pytest.fixture()
def _wf_rows(isolated_db):
    with get_connection() as conn:
        # Parent workflow template row required by FK on workflow_executions
        conn.execute("INSERT INTO workflows (id, name) VALUES ('wf-tmpl-1', 'Test Workflow')")
        conn.execute(
            "INSERT INTO workflow_executions (id, workflow_id, version, status) "
            "VALUES ('wfex-1', 'wf-tmpl-1', 1, 'completed')"
        )
        conn.execute(
            "INSERT INTO workflow_node_executions "
            "(execution_id, node_id, node_type, output_json, error) "
            "VALUES ('wfex-1', 'node-1', 'agent', '{\"result\": \"ok\"}', NULL)"
        )
        conn.commit()


def test_fetch_workflow_resolves_by_execution_row_id(_wf_rows):
    payload = _fetch_workflow("wfex-1")
    assert payload is not None
    assert "ok" in payload.text


def test_fetch_workflow_returns_none_for_template_id(_wf_rows):
    payload = _fetch_workflow("wf-tmpl-1")
    assert payload is None


def test_workflow_emit_passes_execution_id_not_template_id():
    src = inspect.getsource(wes)
    assert 'emit_execution_complete("workflow", execution_id' in src
    assert 'emit_execution_complete("workflow", workflow_id' not in src
