"""Cross-entity reference integration tests.

Validates that creating entities with relationships produces valid linked
data in API responses. Tests the entity relationships the frontend renders:
team-agent membership, product-project linking, trigger-path association,
agent optional fields, and execution-trigger references.

Uses real Flask test client with isolated_db -- zero mocks.
"""


class TestTeamMembersLinkedToAgents:
    """Verify that team members reference real agents."""

    def test_team_members_linked_to_agents(self, client):
        # Create an agent
        agent_resp = client.post(
            "/admin/agents/",
            json={"name": "Team Agent", "role": "developer", "backend_type": "claude"},
        )
        assert agent_resp.status_code == 201
        agent_id = agent_resp.get_json()["agent_id"]

        # Create a team
        team_resp = client.post(
            "/admin/teams/",
            json={"name": "Linked Team"},
        )
        assert team_resp.status_code == 201
        team_id = team_resp.get_json()["team"]["id"]

        # Add the agent as a team member
        member_resp = client.post(
            f"/admin/teams/{team_id}/members",
            json={"name": "Team Agent", "agent_id": agent_id, "role": "member", "layer": "backend"},
        )
        assert member_resp.status_code == 201

        # GET the team detail and verify members contain agent reference
        detail_resp = client.get(f"/admin/teams/{team_id}")
        assert detail_resp.status_code == 200
        team_detail = detail_resp.get_json()

        assert "members" in team_detail
        assert len(team_detail["members"]) == 1

        member = team_detail["members"][0]
        assert member["agent_id"] == agent_id
        assert member["team_id"] == team_id
        assert "name" in member
        assert "role" in member


class TestProductWithProjects:
    """Verify that product-project references work correctly."""

    def test_product_with_projects(self, client):
        # Create a product
        product_resp = client.post(
            "/admin/products/",
            json={"name": "Test Product"},
        )
        assert product_resp.status_code == 201
        product_id = product_resp.get_json()["product"]["id"]

        # Create a project linked to the product
        project_resp = client.post(
            "/admin/projects/",
            json={"name": "Test Project", "product_id": product_id},
        )
        assert project_resp.status_code == 201
        project_id = project_resp.get_json()["project"]["id"]

        # Verify the project has product_id set
        project_detail = client.get(f"/admin/projects/{project_id}")
        assert project_detail.status_code == 200
        project_data = project_detail.get_json()
        assert project_data["product_id"] == product_id

        # Verify the product detail includes the project in list view
        # The product list endpoint returns project_count
        product_list = client.get("/admin/products/")
        assert product_list.status_code == 200
        products = product_list.get_json()["products"]
        our_product = next((p for p in products if p["id"] == product_id), None)
        assert our_product is not None
        assert our_product["project_count"] == 1


class TestTriggerWithPaths:
    """Verify that trigger path associations work correctly."""

    def test_trigger_with_paths(self, tmp_path, client):
        # Use the predefined trigger bot-security
        trigger_id = "bot-security"

        # Create a temporary directory to use as project path
        test_project_dir = tmp_path / "test-project"
        test_project_dir.mkdir()

        # Add a project path
        path_resp = client.post(
            f"/admin/triggers/{trigger_id}/paths",
            json={"local_project_path": str(test_project_dir)},
        )
        assert path_resp.status_code in (200, 201)

        # GET the trigger detail and verify paths are included
        detail_resp = client.get(f"/admin/triggers/{trigger_id}")
        assert detail_resp.status_code == 200
        trigger_data = detail_resp.get_json()

        assert "paths" in trigger_data
        assert len(trigger_data["paths"]) >= 1

        # At least one path should match our added path
        path_values = [p["local_project_path"] for p in trigger_data["paths"]]
        assert str(test_project_dir) in path_values


class TestAgentDetailIncludesOptionalFields:
    """Verify that agent optional fields are returned when provided."""

    def test_agent_detail_includes_optional_fields(self, client):
        # Create an agent with all optional fields
        create_resp = client.post(
            "/admin/agents/",
            json={
                "name": "Full Agent",
                "role": "architect",
                "backend_type": "claude",
                "description": "A fully configured test agent",
                "goals": ["goal1", "goal2"],
                "context": "Test context",
                "system_prompt": "You are a test agent",
                "skills": ["skill1", "skill2"],
                "documents": [{"name": "doc1", "type": "inline", "content": "test content"}],
            },
        )
        assert create_resp.status_code == 201
        agent_id = create_resp.get_json()["agent_id"]

        # GET the agent detail
        detail_resp = client.get(f"/admin/agents/{agent_id}")
        assert detail_resp.status_code == 200
        agent = detail_resp.get_json()

        # Verify all provided optional fields are returned
        assert agent["description"] == "A fully configured test agent"
        assert agent["goals"] == ["goal1", "goal2"]
        assert agent["context"] == "Test context"
        assert agent["system_prompt"] == "You are a test agent"
        assert agent["skills"] == ["skill1", "skill2"]
        assert isinstance(agent["documents"], list)
        assert len(agent["documents"]) == 1
        assert agent["documents"][0]["name"] == "doc1"


class TestExecutionDetailReturnsTriggerID:
    """Verify that execution detail includes trigger_id reference."""

    def test_execution_detail_returns_trigger_id(self, client, seed_test_execution):
        """GET /admin/executions/{id} returns trigger_id without trigger_name.

        The single-execution detail endpoint calls get_execution_log() which
        does SELECT * FROM execution_logs (no JOIN). Therefore trigger_name
        is NOT present -- only trigger_id is available.
        """
        execution_id = seed_test_execution

        resp = client.get(f"/admin/executions/{execution_id}")
        assert resp.status_code == 200

        execution = resp.get_json()
        # trigger_id should be present and reference the seeded trigger
        assert "trigger_id" in execution
        assert execution["trigger_id"] == "bot-security"

        # trigger_name should NOT be present (no JOIN in single-execution query)
        # This documents the current behavior -- the frontend handles this
        assert "trigger_name" not in execution

        # Verify other basic execution fields
        assert execution["execution_id"] == execution_id
        assert execution["status"] == "success"
        assert execution["backend_type"] == "claude"
