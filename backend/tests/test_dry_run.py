"""Tests for dry-run dispatch and cost estimation endpoints (API-01, API-08)."""

from unittest.mock import patch

from app.database import get_trigger
from app.db.triggers import create_trigger


def _seed_trigger(name="Test Dry Run", prompt="{message} in {paths}"):
    """Create a test trigger and return its ID."""
    return create_trigger(
        name=name,
        prompt_template=prompt,
        backend_type="claude",
        trigger_source="manual",
        model="claude-sonnet-4",
    )


class TestDryRunEndpoint:
    """Tests for POST /admin/triggers/<trigger_id>/dry-run."""

    def test_dry_run_returns_full_preview(self, client, isolated_db):
        tid = _seed_trigger()
        resp = client.post(
            f"/admin/triggers/{tid}/dry-run",
            json={"message": "hello world"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rendered_prompt" in data
        assert "cli_command" in data
        assert "backend_type" in data
        assert "model" in data
        assert "estimated_tokens" in data
        assert data["trigger_id"] == tid
        assert data["trigger_name"] == "Test Dry Run"

    def test_dry_run_renders_placeholders(self, client, isolated_db):
        tid = _seed_trigger()
        resp = client.post(
            f"/admin/triggers/{tid}/dry-run",
            json={"message": "test input"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "test input" in data["rendered_prompt"]

    def test_dry_run_nonexistent_trigger_returns_404(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/trig-nonexist/dry-run",
            json={},
        )
        assert resp.status_code == 404

    def test_dry_run_no_subprocess(self, client, isolated_db):
        """Verify dry-run does NOT spawn any subprocess."""
        tid = _seed_trigger()
        with patch("subprocess.Popen") as mock_popen:
            resp = client.post(
                f"/admin/triggers/{tid}/dry-run",
                json={"message": "should not execute"},
            )
            assert resp.status_code == 200
            mock_popen.assert_not_called()

    def test_dry_run_includes_cost_estimate(self, client, isolated_db):
        tid = _seed_trigger()
        resp = client.post(
            f"/admin/triggers/{tid}/dry-run",
            json={"message": "cost check"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        est = data["estimated_tokens"]
        assert "estimated_input_tokens" in est
        assert "estimated_output_tokens" in est
        assert "estimated_cost_usd" in est
        assert est["model"] == "claude-sonnet-4"


class TestEstimateCostEndpoint:
    """Tests for POST /admin/triggers/<trigger_id>/estimate-cost."""

    def test_estimate_cost_returns_fields(self, client, isolated_db):
        tid = _seed_trigger()
        resp = client.post(
            f"/admin/triggers/{tid}/estimate-cost",
            json={"message": "estimate me"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["trigger_id"] == tid
        assert data["model"] == "claude-sonnet-4"
        assert "estimate" in data
        assert "estimated_input_tokens" in data["estimate"]
        assert "estimated_cost_usd" in data["estimate"]

    def test_estimate_cost_nonexistent_trigger_returns_404(self, client, isolated_db):
        resp = client.post(
            "/admin/triggers/trig-nonexist/estimate-cost",
            json={},
        )
        assert resp.status_code == 404
