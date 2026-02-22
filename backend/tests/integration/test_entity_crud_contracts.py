"""CRUD contract tests for all 6 core entity types.

Validates that backend API responses contain all fields expected by the
frontend TypeScript interfaces (frontend/src/services/api/types.ts).
Uses real Flask test client with isolated_db -- zero mocks.

NOTE: List endpoints return *_count aggregation fields (member_count,
project_count, team_count, component_count) via SQL COUNT JOINs, while
detail endpoints return the actual nested arrays (members, projects, teams,
components). The frontend TypeScript interface declares both as optional
fields on the same type, so both shapes are valid. We validate each
endpoint against its actual response shape.
"""

from tests.integration.conftest import assert_response_contract

# =============================================================================
# Field reference sets derived from frontend/src/services/api/types.ts
# Split into LIST (aggregated count) and DETAIL (nested array) variants
# where the response shapes differ between list and detail endpoints.
# =============================================================================

# Agent -- same fields on both list and detail (no nested sub-entities)
AGENT_REQUIRED_FIELDS = {
    "id",
    "name",
    "backend_type",
    "enabled",
    "creation_status",
}

# Team -- list has member_count; detail has members array instead
TEAM_LIST_REQUIRED_FIELDS = {
    "id",
    "name",
    "color",
    "member_count",
}
TEAM_DETAIL_REQUIRED_FIELDS = {
    "id",
    "name",
    "color",
    "members",
}

# Product -- list has project_count; detail has projects array instead
PRODUCT_LIST_REQUIRED_FIELDS = {
    "id",
    "name",
    "status",
    "project_count",
}
PRODUCT_DETAIL_REQUIRED_FIELDS = {
    "id",
    "name",
    "status",
}

# Project -- list has team_count; detail has teams array instead
PROJECT_LIST_REQUIRED_FIELDS = {
    "id",
    "name",
    "status",
    "team_count",
}
PROJECT_DETAIL_REQUIRED_FIELDS = {
    "id",
    "name",
    "status",
    "teams",
}

# Plugin -- list has component_count; detail has components array instead
PLUGIN_LIST_REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "status",
    "component_count",
}
PLUGIN_DETAIL_REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "status",
    "components",
}

# UserSkill -- same on both (no nested sub-entities)
SKILL_REQUIRED_FIELDS = {
    "id",
    "skill_name",
    "skill_path",
    "enabled",
}


# =============================================================================
# Agent Contract Tests
# =============================================================================


class TestAgentContracts:
    """CRUD contract tests for the Agent entity."""

    def test_list_agents_returns_200(self, client):
        resp = client.get("/admin/agents/")
        assert resp.status_code == 200

    def test_list_agents_has_agents_key(self, client):
        resp = client.get("/admin/agents/")
        data = resp.get_json()
        assert "agents" in data

    def test_create_and_get_agent_contract(self, client):
        # Create
        create_resp = client.post(
            "/admin/agents/",
            json={"name": "Test Agent", "role": "developer", "backend_type": "claude"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        agent_id = create_data["agent_id"]

        # Get detail and validate contract
        detail_resp = client.get(f"/admin/agents/{agent_id}")
        assert detail_resp.status_code == 200
        agent = detail_resp.get_json()
        assert_response_contract(agent, AGENT_REQUIRED_FIELDS, "Agent detail")

    def test_list_agents_item_contract(self, client):
        """Validate that list endpoint items have the expected fields."""
        # Create an agent so the list is not empty
        client.post(
            "/admin/agents/",
            json={"name": "List Agent", "role": "dev", "backend_type": "claude"},
        )
        resp = client.get("/admin/agents/")
        data = resp.get_json()
        assert len(data["agents"]) > 0
        assert_response_contract(data["agents"][0], AGENT_REQUIRED_FIELDS, "Agent list item")

    def test_agent_crud_cycle(self, client):
        # Create
        create_resp = client.post(
            "/admin/agents/",
            json={"name": "CRUD Agent", "role": "tester", "backend_type": "claude"},
        )
        assert create_resp.status_code == 201
        agent_id = create_resp.get_json()["agent_id"]

        # Verify create via GET
        get_resp = client.get(f"/admin/agents/{agent_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["name"] == "CRUD Agent"

        # Update
        update_resp = client.put(
            f"/admin/agents/{agent_id}",
            json={"name": "Updated Agent"},
        )
        assert update_resp.status_code == 200

        # Verify update persisted
        get_resp2 = client.get(f"/admin/agents/{agent_id}")
        assert get_resp2.status_code == 200
        assert get_resp2.get_json()["name"] == "Updated Agent"

        # Delete
        del_resp = client.delete(f"/admin/agents/{agent_id}")
        assert del_resp.status_code == 200

        # Verify deleted
        get_resp3 = client.get(f"/admin/agents/{agent_id}")
        assert get_resp3.status_code == 404


# =============================================================================
# Team Contract Tests
# =============================================================================


class TestTeamContracts:
    """CRUD contract tests for the Team entity."""

    def test_list_teams_returns_200(self, client):
        resp = client.get("/admin/teams/")
        assert resp.status_code == 200

    def test_list_teams_item_contract(self, client):
        """Validate that list endpoint items have member_count."""
        client.post("/admin/teams/", json={"name": "List Team"})
        resp = client.get("/admin/teams/")
        data = resp.get_json()
        assert len(data["teams"]) > 0
        assert_response_contract(data["teams"][0], TEAM_LIST_REQUIRED_FIELDS, "Team list item")

    def test_create_and_get_team_contract(self, client):
        # Create
        create_resp = client.post(
            "/admin/teams/",
            json={"name": "Test Team"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        team = create_data["team"]
        team_id = team["id"]

        # Get detail -- returns members array (not member_count)
        detail_resp = client.get(f"/admin/teams/{team_id}")
        assert detail_resp.status_code == 200
        team_detail = detail_resp.get_json()
        assert_response_contract(team_detail, TEAM_DETAIL_REQUIRED_FIELDS, "Team detail")

    def test_team_crud_cycle(self, client):
        # Create
        create_resp = client.post(
            "/admin/teams/",
            json={"name": "CRUD Team"},
        )
        assert create_resp.status_code == 201
        team_id = create_resp.get_json()["team"]["id"]

        # Verify create via GET
        get_resp = client.get(f"/admin/teams/{team_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["name"] == "CRUD Team"

        # Update
        update_resp = client.put(
            f"/admin/teams/{team_id}",
            json={"name": "Updated Team"},
        )
        assert update_resp.status_code == 200

        # Verify update persisted
        get_resp2 = client.get(f"/admin/teams/{team_id}")
        assert get_resp2.status_code == 200
        assert get_resp2.get_json()["name"] == "Updated Team"

        # Delete
        del_resp = client.delete(f"/admin/teams/{team_id}")
        assert del_resp.status_code == 200

        # Verify deleted
        get_resp3 = client.get(f"/admin/teams/{team_id}")
        assert get_resp3.status_code == 404


# =============================================================================
# Product Contract Tests
# =============================================================================


class TestProductContracts:
    """CRUD contract tests for the Product entity."""

    def test_list_products_returns_200(self, client):
        resp = client.get("/admin/products/")
        assert resp.status_code == 200

    def test_list_products_item_contract(self, client):
        """Validate that list endpoint items have project_count."""
        client.post("/admin/products/", json={"name": "List Product"})
        resp = client.get("/admin/products/")
        data = resp.get_json()
        assert len(data["products"]) > 0
        assert_response_contract(
            data["products"][0], PRODUCT_LIST_REQUIRED_FIELDS, "Product list item"
        )

    def test_create_and_get_product_contract(self, client):
        # Create
        create_resp = client.post(
            "/admin/products/",
            json={"name": "Test Product"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        product = create_data["product"]
        product_id = product["id"]

        # Get detail -- returns projects array (not project_count)
        detail_resp = client.get(f"/admin/products/{product_id}")
        assert detail_resp.status_code == 200
        product_detail = detail_resp.get_json()
        assert_response_contract(product_detail, PRODUCT_DETAIL_REQUIRED_FIELDS, "Product detail")

    def test_product_crud_cycle(self, client):
        # Create
        create_resp = client.post(
            "/admin/products/",
            json={"name": "CRUD Product"},
        )
        assert create_resp.status_code == 201
        product_id = create_resp.get_json()["product"]["id"]

        # Verify create via GET
        get_resp = client.get(f"/admin/products/{product_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["name"] == "CRUD Product"

        # Update
        update_resp = client.put(
            f"/admin/products/{product_id}",
            json={"name": "Updated Product"},
        )
        assert update_resp.status_code == 200

        # Verify update persisted
        get_resp2 = client.get(f"/admin/products/{product_id}")
        assert get_resp2.status_code == 200
        assert get_resp2.get_json()["name"] == "Updated Product"

        # Delete
        del_resp = client.delete(f"/admin/products/{product_id}")
        assert del_resp.status_code == 200

        # Verify deleted
        get_resp3 = client.get(f"/admin/products/{product_id}")
        assert get_resp3.status_code == 404


# =============================================================================
# Project Contract Tests
# =============================================================================


class TestProjectContracts:
    """CRUD contract tests for the Project entity."""

    def test_list_projects_returns_200(self, client):
        resp = client.get("/admin/projects/")
        assert resp.status_code == 200

    def test_list_projects_item_contract(self, client):
        """Validate that list endpoint items have team_count."""
        client.post("/admin/projects/", json={"name": "List Project"})
        resp = client.get("/admin/projects/")
        data = resp.get_json()
        assert len(data["projects"]) > 0
        assert_response_contract(
            data["projects"][0], PROJECT_LIST_REQUIRED_FIELDS, "Project list item"
        )

    def test_create_and_get_project_contract(self, client):
        # Create
        create_resp = client.post(
            "/admin/projects/",
            json={"name": "Test Project"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        project = create_data["project"]
        project_id = project["id"]

        # Get detail -- returns teams array (not team_count)
        detail_resp = client.get(f"/admin/projects/{project_id}")
        assert detail_resp.status_code == 200
        project_detail = detail_resp.get_json()
        assert_response_contract(project_detail, PROJECT_DETAIL_REQUIRED_FIELDS, "Project detail")

    def test_project_crud_cycle(self, client):
        # Create
        create_resp = client.post(
            "/admin/projects/",
            json={"name": "CRUD Project"},
        )
        assert create_resp.status_code == 201
        project_id = create_resp.get_json()["project"]["id"]

        # Verify create via GET
        get_resp = client.get(f"/admin/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.get_json()["name"] == "CRUD Project"

        # Update
        update_resp = client.put(
            f"/admin/projects/{project_id}",
            json={"name": "Updated Project"},
        )
        assert update_resp.status_code == 200

        # Verify update persisted
        get_resp2 = client.get(f"/admin/projects/{project_id}")
        assert get_resp2.status_code == 200
        assert get_resp2.get_json()["name"] == "Updated Project"

        # Delete
        del_resp = client.delete(f"/admin/projects/{project_id}")
        assert del_resp.status_code == 200

        # Verify deleted
        get_resp3 = client.get(f"/admin/projects/{project_id}")
        assert get_resp3.status_code == 404


# =============================================================================
# Plugin Contract Tests
# =============================================================================


class TestPluginContracts:
    """CRUD contract tests for the Plugin entity."""

    def test_list_plugins_returns_200(self, client):
        resp = client.get("/admin/plugins/")
        assert resp.status_code == 200

    def test_list_plugins_item_contract(self, client):
        """Validate that list endpoint items have component_count."""
        client.post(
            "/admin/plugins/",
            json={"name": "List Plugin", "version": "1.0.0"},
        )
        resp = client.get("/admin/plugins/")
        data = resp.get_json()
        assert len(data["plugins"]) > 0
        assert_response_contract(
            data["plugins"][0], PLUGIN_LIST_REQUIRED_FIELDS, "Plugin list item"
        )

    def test_create_and_get_plugin_contract(self, client):
        # Create
        create_resp = client.post(
            "/admin/plugins/",
            json={"name": "Test Plugin", "version": "1.0.0", "status": "draft"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        plugin = create_data["plugin"]
        plugin_id = plugin["id"]

        # Get detail -- returns components array (not component_count)
        detail_resp = client.get(f"/admin/plugins/{plugin_id}")
        assert detail_resp.status_code == 200
        plugin_detail = detail_resp.get_json()
        assert_response_contract(plugin_detail, PLUGIN_DETAIL_REQUIRED_FIELDS, "Plugin detail")


# =============================================================================
# Skill Contract Tests
# =============================================================================


class TestSkillContracts:
    """CRUD contract tests for the UserSkill entity."""

    def test_list_skills_returns_200(self, client):
        resp = client.get("/api/skills/user")
        assert resp.status_code == 200

    def test_create_and_get_skill_contract(self, client):
        # Create
        create_resp = client.post(
            "/api/skills/user",
            json={"skill_name": "test-skill", "skill_path": "/tmp/test"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.get_json()
        skill_id = create_data["id"]

        # Get detail -- wrapped in {"skill": {...}}
        detail_resp = client.get(f"/api/skills/user/{skill_id}")
        assert detail_resp.status_code == 200
        skill_data = detail_resp.get_json()
        skill = skill_data["skill"]
        assert_response_contract(skill, SKILL_REQUIRED_FIELDS, "UserSkill")
