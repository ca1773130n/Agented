"""Tests for Workflow CRUD, version tracking, DAG validation, and execution tracking."""

import json

from app.db.workflows import validate_workflow_graph

SAMPLE_WORKFLOW = {
    "name": "Deploy Pipeline",
    "description": "Automated deploy",
    "trigger_type": "manual",
}

VALID_DAG_GRAPH = json.dumps(
    {
        "nodes": [
            {"id": "A", "type": "trigger", "label": "Start", "config": {}},
            {"id": "B", "type": "command", "label": "Build", "config": {}},
            {"id": "C", "type": "script", "label": "Deploy", "config": {}},
        ],
        "edges": [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
        ],
    }
)

CYCLIC_DAG_GRAPH = json.dumps(
    {
        "nodes": [
            {"id": "A", "type": "trigger", "label": "Start", "config": {}},
            {"id": "B", "type": "command", "label": "Build", "config": {}},
            {"id": "C", "type": "script", "label": "Deploy", "config": {}},
        ],
        "edges": [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "C", "target": "A"},
        ],
    }
)

BRANCHING_DAG_GRAPH = json.dumps(
    {
        "nodes": [
            {"id": "A", "type": "trigger", "label": "Start", "config": {}},
            {"id": "B", "type": "command", "label": "Branch 1", "config": {}},
            {"id": "C", "type": "command", "label": "Branch 2", "config": {}},
            {"id": "D", "type": "script", "label": "Merge", "config": {}},
        ],
        "edges": [
            {"source": "A", "target": "B"},
            {"source": "A", "target": "C"},
            {"source": "B", "target": "D"},
            {"source": "C", "target": "D"},
        ],
    }
)


def _create_workflow(client, **overrides):
    """Helper to create a workflow via API."""
    data = {**SAMPLE_WORKFLOW, **overrides}
    return client.post("/admin/workflows/", json=data)


def _create_version(client, workflow_id, graph_json):
    """Helper to create a workflow version via API."""
    return client.post(
        f"/admin/workflows/{workflow_id}/versions",
        json={"graph_json": graph_json},
    )


class TestCreateWorkflow:
    def test_create_workflow(self, client):
        """POST returns 201 with wf-* ID."""
        resp = _create_workflow(client)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Workflow created"
        assert body["workflow_id"].startswith("wf-")
        assert len(body["workflow_id"]) == 9  # wf- + 6 chars

    def test_create_workflow_missing_name(self, client):
        """POST without name returns 400."""
        resp = client.post("/admin/workflows/", json={"description": "No name"})
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"].lower()


class TestListWorkflows:
    def test_list_workflows(self, client):
        """GET / returns all created workflows."""
        _create_workflow(client, name="Pipeline A")
        _create_workflow(client, name="Pipeline B")
        resp = client.get("/admin/workflows/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["workflows"]) == 2

    def test_list_workflows_empty(self, client):
        """GET / returns empty list when none exist."""
        resp = client.get("/admin/workflows/")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["workflows"] == []


class TestGetWorkflow:
    def test_get_workflow(self, client):
        """GET /:id returns correct fields."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = client.get(f"/admin/workflows/{wf_id}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["id"] == wf_id
        assert body["name"] == "Deploy Pipeline"
        assert body["description"] == "Automated deploy"
        assert body["trigger_type"] == "manual"
        assert body["enabled"] == 1
        assert "created_at" in body
        assert "updated_at" in body

    def test_get_workflow_not_found(self, client):
        """GET /:id returns 404 for unknown ID."""
        resp = client.get("/admin/workflows/wf-doesnt-exist")
        assert resp.status_code == 404


class TestUpdateWorkflow:
    def test_update_workflow(self, client):
        """PUT updates name and returns 200."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = client.put(f"/admin/workflows/{wf_id}", json={"name": "Updated Pipeline"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["name"] == "Updated Pipeline"

    def test_update_workflow_not_found(self, client):
        """PUT returns 404 for unknown ID."""
        resp = client.put("/admin/workflows/wf-doesnt-exist", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteWorkflow:
    def test_delete_workflow(self, client):
        """DELETE returns 200."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = client.delete(f"/admin/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Workflow deleted"

        # Verify it's gone
        get_resp = client.get(f"/admin/workflows/{wf_id}")
        assert get_resp.status_code == 404

    def test_delete_workflow_not_found(self, client):
        """DELETE returns 404 for unknown ID."""
        resp = client.delete("/admin/workflows/wf-doesnt-exist")
        assert resp.status_code == 404

    def test_delete_workflow_cascades_versions(self, client):
        """After delete, versions are also gone."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        # Create a version
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        # Verify version exists
        versions_resp = client.get(f"/admin/workflows/{wf_id}/versions")
        assert len(versions_resp.get_json()["versions"]) == 1

        # Delete workflow
        client.delete(f"/admin/workflows/{wf_id}")

        # Versions endpoint returns empty (workflow gone, no versions)
        from app.db.workflows import get_workflow_versions

        versions = get_workflow_versions(wf_id)
        assert len(versions) == 0


class TestWorkflowVersions:
    def test_create_version(self, client):
        """POST creates version 1 with 201."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = _create_version(client, wf_id, VALID_DAG_GRAPH)
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["message"] == "Version created"
        assert body["version"] == 1

    def test_create_version_auto_increment(self, client):
        """Second POST creates version 2."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp1 = _create_version(client, wf_id, VALID_DAG_GRAPH)
        assert resp1.get_json()["version"] == 1

        resp2 = _create_version(client, wf_id, VALID_DAG_GRAPH)
        assert resp2.status_code == 201
        assert resp2.get_json()["version"] == 2

    def test_create_version_invalid_json(self, client):
        """POST with non-JSON graph_json returns 400."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = _create_version(client, wf_id, "not valid json {{{")
        assert resp.status_code == 400
        assert "JSON" in resp.get_json()["error"]

    def test_create_version_cyclic_graph(self, client):
        """POST with CYCLIC_DAG_GRAPH returns 400 with cycle error message."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = _create_version(client, wf_id, CYCLIC_DAG_GRAPH)
        assert resp.status_code == 400
        assert "cycle" in resp.get_json()["error"].lower()

    def test_create_version_valid_dag(self, client):
        """POST with VALID_DAG_GRAPH returns 201."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = _create_version(client, wf_id, VALID_DAG_GRAPH)
        assert resp.status_code == 201

    def test_create_version_branching_dag(self, client):
        """POST with BRANCHING_DAG_GRAPH returns 201."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        resp = _create_version(client, wf_id, BRANCHING_DAG_GRAPH)
        assert resp.status_code == 201

    def test_list_versions(self, client):
        """GET returns all versions ordered by version DESC."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        _create_version(client, wf_id, VALID_DAG_GRAPH)
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        resp = client.get(f"/admin/workflows/{wf_id}/versions")
        assert resp.status_code == 200
        versions = resp.get_json()["versions"]
        assert len(versions) == 2
        # DESC order: version 2 first, version 1 second
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_get_latest_version(self, client):
        """GET /latest returns the highest version."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]

        _create_version(client, wf_id, VALID_DAG_GRAPH)
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        resp = client.get(f"/admin/workflows/{wf_id}/versions/latest")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["version"] == 2


class TestWorkflowExecutions:
    def test_run_workflow_returns_execution_id(self, client):
        """POST /run returns 202 with wfx-* ID."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["message"] == "Workflow execution started"
        assert body["execution_id"].startswith("wfx-")
        assert len(body["execution_id"]) == 12  # wfx- + 8 chars

    def test_list_executions(self, client):
        """GET /executions returns execution records."""
        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        client.post(f"/admin/workflows/{wf_id}/run")
        client.post(f"/admin/workflows/{wf_id}/run")

        resp = client.get(f"/admin/workflows/{wf_id}/executions")
        assert resp.status_code == 200
        executions = resp.get_json()["executions"]
        assert len(executions) == 2

    def test_get_execution_detail(self, client):
        """GET /executions/:id returns execution + node_executions."""
        import time

        create_resp = _create_workflow(client)
        wf_id = create_resp.get_json()["workflow_id"]
        _create_version(client, wf_id, VALID_DAG_GRAPH)

        run_resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = run_resp.get_json()["execution_id"]

        # Wait briefly for background execution thread to complete
        for _ in range(20):
            resp = client.get(f"/admin/workflows/executions/{exec_id}")
            body = resp.get_json()
            if body["execution"]["status"] not in ("running", "pending"):
                break
            time.sleep(0.1)

        assert resp.status_code == 200
        assert body["execution"]["id"] == exec_id
        assert body["execution"]["status"] in ("running", "completed", "failed")
        assert isinstance(body["node_executions"], list)


class TestDAGValidation:
    """Direct unit tests for validate_workflow_graph()."""

    def test_validate_empty_graph(self):
        """Graph with no nodes returns error."""
        graph = json.dumps({"nodes": [], "edges": []})
        valid, error = validate_workflow_graph(graph)
        assert not valid
        assert "at least one node" in error.lower()

    def test_validate_single_node(self):
        """Graph with one node, no edges is valid."""
        graph = json.dumps(
            {
                "nodes": [{"id": "A", "type": "trigger", "label": "Start", "config": {}}],
                "edges": [],
            }
        )
        valid, error = validate_workflow_graph(graph)
        assert valid
        assert error == ""

    def test_validate_linear_chain(self):
        """A->B->C is valid."""
        valid, error = validate_workflow_graph(VALID_DAG_GRAPH)
        assert valid
        assert error == ""

    def test_validate_diamond(self):
        """A->{B,C}->D is valid."""
        valid, error = validate_workflow_graph(BRANCHING_DAG_GRAPH)
        assert valid
        assert error == ""

    def test_validate_self_loop(self):
        """A->A returns cycle error."""
        graph = json.dumps(
            {
                "nodes": [{"id": "A", "type": "trigger", "label": "Start", "config": {}}],
                "edges": [{"source": "A", "target": "A"}],
            }
        )
        valid, error = validate_workflow_graph(graph)
        assert not valid
        assert "cycle" in error.lower()

    def test_validate_two_node_cycle(self):
        """A->B->A returns cycle error."""
        graph = json.dumps(
            {
                "nodes": [
                    {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                    {"id": "B", "type": "command", "label": "Build", "config": {}},
                ],
                "edges": [
                    {"source": "A", "target": "B"},
                    {"source": "B", "target": "A"},
                ],
            }
        )
        valid, error = validate_workflow_graph(graph)
        assert not valid
        assert "cycle" in error.lower()

    def test_validate_edge_unknown_node(self):
        """Edge referencing non-existent node returns error."""
        graph = json.dumps(
            {
                "nodes": [{"id": "A", "type": "trigger", "label": "Start", "config": {}}],
                "edges": [{"source": "A", "target": "Z"}],
            }
        )
        valid, error = validate_workflow_graph(graph)
        assert not valid
        assert "unknown" in error.lower()
