"""Tests for enhanced workflow DAG validation (API-09)."""

import pytest


@pytest.fixture
def client(isolated_db):
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# =============================================================================
# Direct service tests
# =============================================================================


class TestValidateWorkflowDag:
    def test_valid_linear_dag(self):
        """Valid linear DAG A->B->C passes validation."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is True
        # Filter out warnings
        real_errors = [e for e in errors if not e.startswith("WARNING:")]
        assert len(real_errors) == 0

    def test_cycle_detection(self):
        """Cycle A->B->C->A is detected with descriptive error."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "A"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is False
        assert any("ycle" in e for e in errors)
        # Should list the cycle nodes
        cycle_error = [e for e in errors if "ycle" in e][0]
        assert "A" in cycle_error or "B" in cycle_error or "C" in cycle_error

    def test_missing_node_reference(self):
        """Edge referencing non-existent node returns descriptive error."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [{"source": "A", "target": "X"}],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is False
        assert any("X" in e and "missing" in e.lower() for e in errors)

    def test_invalid_condition_expression(self):
        """Node with invalid condition syntax returns syntax error."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [
                {"id": "A"},
                {
                    "id": "condition-1",
                    "type": "condition",
                    "condition": "if x ==== y",
                },
                {"id": "B"},
            ],
            "edges": [
                {"source": "A", "target": "condition-1"},
                {"source": "condition-1", "target": "B"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is False
        assert any("SyntaxError" in e and "condition-1" in e for e in errors)

    def test_dangerous_expression_rejected(self):
        """Node with dangerous expression (__import__) is rejected."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [
                {"id": "A"},
                {
                    "id": "condition-1",
                    "type": "condition",
                    "condition": "__import__('os').system('rm -rf /')",
                },
                {"id": "B"},
            ],
            "edges": [
                {"source": "A", "target": "condition-1"},
                {"source": "condition-1", "target": "B"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is False
        assert any("forbidden" in e.lower() or "dangerous" in e.lower() for e in errors)

    def test_valid_condition_expression(self):
        """Valid condition expression passes."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [
                {"id": "A"},
                {
                    "id": "condition-1",
                    "type": "condition",
                    "condition": "output.status == 'success'",
                },
                {"id": "B"},
            ],
            "edges": [
                {"source": "A", "target": "condition-1"},
                {"source": "condition-1", "target": "B"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is True

    def test_empty_graph(self):
        """Empty graph (no nodes) returns error."""
        from app.services.workflow_validation_service import validate_workflow_dag

        is_valid, errors = validate_workflow_dag({"nodes": [], "edges": []})
        assert is_valid is False
        assert any("at least one node" in e.lower() for e in errors)

    def test_isolated_node_warning(self):
        """Isolated node produces warning but does not reject."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}, {"id": "isolated"}],
            "edges": [{"source": "A", "target": "B"}],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is True
        warnings = [e for e in errors if e.startswith("WARNING:")]
        assert any("isolated" in w for w in warnings)

    def test_condition_in_data_field(self):
        """Condition expression inside node.data.condition is also validated."""
        from app.services.workflow_validation_service import validate_workflow_dag

        graph = {
            "nodes": [
                {"id": "A"},
                {
                    "id": "cond-1",
                    "type": "branch",
                    "data": {"condition": "x ==="},
                },
                {"id": "B"},
            ],
            "edges": [
                {"source": "A", "target": "cond-1"},
                {"source": "cond-1", "target": "B"},
            ],
        }
        is_valid, errors = validate_workflow_dag(graph)
        assert is_valid is False
        assert any("SyntaxError" in e for e in errors)


# =============================================================================
# Endpoint tests
# =============================================================================


class TestValidateEndpoint:
    def test_standalone_validation_valid(self, client):
        """Standalone validation endpoint returns valid=True for valid DAG."""
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [{"source": "A", "target": "B"}],
        }
        resp = client.post("/admin/workflows/validate", json={"graph": graph})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        real_errors = [e for e in data["errors"] if not e.startswith("WARNING:")]
        assert len(real_errors) == 0

    def test_standalone_validation_invalid(self, client):
        """Standalone validation endpoint returns valid=False with errors for cycle."""
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "A"},
            ],
        }
        resp = client.post("/admin/workflows/validate", json={"graph": graph})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_workflow_creation_with_cycle_rejected(self, client):
        """Creating a workflow with a cyclic graph is rejected (400)."""
        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "A"},
            ],
        }
        resp = client.post(
            "/admin/workflows/",
            json={"name": "Cyclic Workflow", "graph": graph},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "errors" in data or ("details" in data and "errors" in data["details"])

    def test_workflow_creation_without_graph_passes(self, client):
        """Creating a workflow without a graph still works (no validation needed)."""
        resp = client.post(
            "/admin/workflows/",
            json={"name": "Simple Workflow"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "workflow_id" in data

    def test_workflow_update_with_cycle_rejected(self, client):
        """Updating a workflow with a cyclic graph is rejected."""
        # Create workflow first
        resp = client.post("/admin/workflows/", json={"name": "Test WF"})
        wf_id = resp.get_json()["workflow_id"]

        graph = {
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "A"},
            ],
        }
        resp = client.put(f"/admin/workflows/{wf_id}", json={"name": "Updated", "graph": graph})
        assert resp.status_code == 400
