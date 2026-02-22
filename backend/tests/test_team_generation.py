"""Tests for TeamGenerationService and the generate endpoint."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateEndpoint:
    """Tests for the POST /admin/teams/generate endpoint."""

    def test_generate_endpoint_returns_config(self, client, isolated_db):
        """Mock subprocess.run to return a valid JSON config string."""
        mock_config = {
            "name": "Security Team",
            "description": "A team focused on security audits",
            "topology": "sequential",
            "topology_config": {"order": []},
            "color": "#ff0000",
            "agents": [
                {
                    "agent_id": None,
                    "name": "Security Auditor",
                    "role": "Performs security scans",
                    "assignments": [],
                }
            ],
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(mock_config)
        mock_result.stderr = ""

        with patch("app.services.team_generation_service.subprocess.run", return_value=mock_result):
            response = client.post(
                "/admin/teams/generate",
                json={"description": "Create a security team that audits code for vulnerabilities"},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert "config" in data
        assert data["config"]["name"] == "Security Team"
        assert data["config"]["topology"] == "sequential"

    def test_generate_validates_agent_references(self, client, isolated_db):
        """Mock subprocess.run to return config referencing a non-existent agent_id."""
        mock_config = {
            "name": "Test Team",
            "description": "Test",
            "topology": "parallel",
            "topology_config": {"agents": []},
            "color": "#00ff00",
            "agents": [
                {
                    "agent_id": "agent-nonexistent",
                    "name": "Fake Agent",
                    "role": "Does not exist",
                    "assignments": [],
                }
            ],
        }

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(mock_config)
        mock_result.stderr = ""

        with patch("app.services.team_generation_service.subprocess.run", return_value=mock_result):
            response = client.post(
                "/admin/teams/generate",
                json={"description": "A test team with agents that do not exist"},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert "warnings" in data
        assert any("agent-nonexistent" in w for w in data["warnings"])
        # The agent should be marked as invalid
        assert data["config"]["agents"][0]["valid"] is False

    def test_generate_requires_description(self, client, isolated_db):
        """POST with empty body should return 400."""
        response = client.post(
            "/admin/teams/generate",
            json={},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_generate_requires_min_length_description(self, client, isolated_db):
        """POST with too-short description should return 400."""
        response = client.post(
            "/admin/teams/generate",
            json={"description": "short"},
        )
        assert response.status_code == 400

    def test_generate_handles_subprocess_timeout(self, client, isolated_db):
        """Mock subprocess.run to raise TimeoutExpired, verify 503 response."""
        with patch(
            "app.services.team_generation_service.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120),
        ):
            response = client.post(
                "/admin/teams/generate",
                json={"description": "Create a team that takes forever to generate"},
            )

        assert response.status_code == 503
        data = response.get_json()
        assert "timed out" in data["error"].lower()

    def test_generate_handles_cli_not_found(self, client, isolated_db):
        """Mock subprocess.run to raise FileNotFoundError, verify 503 response."""
        with patch(
            "app.services.team_generation_service.subprocess.run",
            side_effect=FileNotFoundError("claude not found"),
        ):
            response = client.post(
                "/admin/teams/generate",
                json={"description": "Create a team but claude cli is missing"},
            )

        assert response.status_code == 503
        data = response.get_json()
        assert "not found" in data["error"].lower()

    def test_prompt_includes_available_entities(self, client, isolated_db):
        """Verify the prompt passed to subprocess.run includes agent/skill names from DB."""
        from app.database import add_agent, add_user_skill

        # Add test entities to the DB
        add_agent(name="Test Agent Alpha", role="code reviewer", backend_type="claude")
        add_user_skill(skill_name="code-review", skill_path="/skills/code-review")

        captured_prompt = {}

        def mock_run(cmd, **kwargs):
            # Capture the prompt argument
            captured_prompt["value"] = cmd[2] if len(cmd) > 2 else ""
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps(
                {
                    "name": "Gen Team",
                    "description": "Generated",
                    "topology": "sequential",
                    "topology_config": {},
                    "color": "#000000",
                    "agents": [],
                }
            )
            result.stderr = ""
            return result

        with patch("app.services.team_generation_service.subprocess.run", side_effect=mock_run):
            response = client.post(
                "/admin/teams/generate",
                json={"description": "Create a code review team with available agents"},
            )

        assert response.status_code == 200
        prompt = captured_prompt.get("value", "")
        assert "Test Agent Alpha" in prompt
        assert "code-review" in prompt


class TestTeamGenerationService:
    """Unit tests for TeamGenerationService directly."""

    def test_parse_json_clean(self):
        """Parse clean JSON output."""
        from app.services.team_generation_service import TeamGenerationService

        config = TeamGenerationService._parse_json('{"name": "test"}')
        assert config["name"] == "test"

    def test_parse_json_mixed_text(self):
        """Parse JSON embedded in mixed text output."""
        from app.services.team_generation_service import TeamGenerationService

        text = 'Here is the config:\n{"name": "test", "topology": "parallel"}\nDone!'
        config = TeamGenerationService._parse_json(text)
        assert config["name"] == "test"
        assert config["topology"] == "parallel"

    def test_parse_json_no_json_raises(self):
        """Raise RuntimeError when no JSON object found."""
        from app.services.team_generation_service import TeamGenerationService

        with pytest.raises(RuntimeError, match="Could not find"):
            TeamGenerationService._parse_json("no json here at all")

    def test_validate_config_marks_valid_topology(self, isolated_db):
        """Valid topology should not produce warnings."""
        from app.services.team_generation_service import TeamGenerationService

        config = {
            "topology": "sequential",
            "agents": [],
        }
        validated, warnings = TeamGenerationService._validate(config)
        topology_warnings = [w for w in warnings if "topology" in w.lower()]
        assert len(topology_warnings) == 0

    def test_validate_config_marks_invalid_topology(self, isolated_db):
        """Invalid topology should produce a warning."""
        from app.services.team_generation_service import TeamGenerationService

        config = {
            "topology": "invalid_topo",
            "agents": [],
        }
        validated, warnings = TeamGenerationService._validate(config)
        assert any("Invalid topology" in w for w in warnings)

    def test_build_prompt_includes_description(self, isolated_db):
        """The built prompt should include the user's description."""
        from app.services.team_generation_service import TeamGenerationService

        prompt = TeamGenerationService._build_prompt(
            "Build a code review pipeline",
            {"agents": [], "skills": [], "commands": [], "hooks": [], "rules": []},
        )
        assert "Build a code review pipeline" in prompt
        assert "team configuration generator" in prompt
