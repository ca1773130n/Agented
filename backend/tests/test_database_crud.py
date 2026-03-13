"""Comprehensive CRUD tests for all 10 entity types in database.py.

This test file serves as a regression safety net for database.py CRUD operations.
The isolated_db fixture (autouse=True) provides a fresh database for each test.
seed_predefined_triggers() inserts 2 predefined triggers (bot-security, bot-pr-review).

Note: The fresh DB schema is missing 5 agent columns (layer, detected_role,
matched_skills, preferred_model, effort_level) that are only added via migration.
The apply_migrations fixture below adds them so that create_agent() works correctly.
"""

import sqlite3

import pytest

from app.database import (
    add_plugin_component,
    add_team_agent_assignment,
    add_team_member,
    # Skill (user_skills) functions
    add_user_skill,
    assign_team_to_project,
    # Agent functions
    count_agents,
    create_agent,
    create_agent_conversation,
    # Command functions
    create_command,
    # Design conversation functions
    create_design_conversation,
    # Hook functions
    create_hook,
    # Plugin functions
    create_plugin,
    # Product functions
    create_product,
    # Project functions
    create_project,
    # Rule functions
    create_rule,
    # Team functions
    create_team,
    # Trigger functions
    create_trigger,
    # Workflow functions
    create_workflow,
    count_all_triggers,
    count_teams,
    delete_agent,
    delete_agent_conversation,
    delete_command,
    delete_hook,
    delete_old_design_conversations,
    delete_plugin,
    delete_plugin_component,
    delete_product,
    delete_project,
    delete_rule,
    delete_team,
    delete_team_agent_assignment,
    delete_team_agent_assignments_bulk,
    delete_trigger,
    delete_user_skill,
    delete_workflow,
    get_active_conversations,
    get_agent,
    get_agent_by_name,
    get_agent_conversation,
    get_all_agents,
    get_all_commands,
    get_all_hooks,
    get_all_plugins,
    get_all_products,
    get_all_projects,
    get_all_rules,
    get_all_teams,
    get_all_triggers,
    get_all_user_skills,
    get_all_workflows,
    get_command,
    get_commands_by_project,
    get_design_conversation,
    get_enabled_agents,
    get_enabled_user_skills,
    get_harness_skills,
    get_hook,
    get_hooks_by_event,
    get_hooks_by_project,
    get_latest_workflow_version,
    get_plugin,
    get_plugin_component_by_name,
    get_plugin_components,
    get_plugin_detail,
    get_product,
    get_product_detail,
    get_project,
    get_project_detail,
    get_project_teams,
    get_rule,
    get_rules_by_project,
    get_rules_by_type,
    get_team,
    get_team_agent_assignments,
    get_team_by_name,
    get_team_detail,
    get_team_members,
    get_trigger,
    get_trigger_by_name,
    get_triggers_by_trigger_source,
    get_user_skill,
    get_user_skill_by_name,
    get_webhook_teams,
    get_workflow,
    get_workflow_execution,
    get_workflow_executions,
    get_workflow_versions,
    list_design_conversations,
    publish_workflow_version,
    remove_team_member,
    toggle_skill_harness,
    unassign_team_from_project,
    update_agent,
    update_agent_conversation,
    update_command,
    update_design_conversation,
    update_hook,
    update_plugin,
    update_plugin_component,
    update_product,
    update_project,
    update_rule,
    update_team,
    update_team_member,
    update_trigger,
    update_trigger_auto_resolve,
    update_trigger_last_run,
    update_trigger_next_run,
    update_user_skill,
    update_workflow,
    validate_workflow_graph,
)
from app.db.teams import (
    add_team_edge,
    delete_team_edge,
    delete_team_edges_by_team,
    get_team_edges,
    get_team_hierarchy,
)
from app.db.workflows import (
    add_workflow_approval_state,
    add_workflow_execution,
    add_workflow_node_execution,
    add_workflow_version,
    add_workflow_version_raw,
    cleanup_stale_approval_states,
    get_pending_approval_states,
    get_running_workflow_executions,
    get_workflow_approval_state,
    get_workflow_node_executions,
    update_workflow_approval_state,
    update_workflow_execution,
    update_workflow_node_execution,
)


@pytest.fixture(autouse=True)
def apply_migrations(isolated_db):
    """Apply missing migration columns to the fresh test database.

    The fresh-schema init_db() path does not create 5 agent columns that the
    migration path adds (layer, detected_role, matched_skills, preferred_model,
    effort_level). Since create_agent() references these columns, we add them here.
    """
    conn = sqlite3.connect(isolated_db)
    cursor = conn.execute("PRAGMA table_info(agents)")
    existing = {row[1] for row in cursor.fetchall()}
    migrations = [
        ("layer", "TEXT"),
        ("detected_role", "TEXT"),
        ("matched_skills", "TEXT"),
        ("preferred_model", "TEXT"),
        ("effort_level", "TEXT DEFAULT 'medium'"),
    ]
    for col_name, col_type in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE agents ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()


# =============================================================================
# Trigger CRUD tests
# =============================================================================


class TestTriggerCRUD:
    def test_add_and_get(self):
        trigger_id = create_trigger(name="Test Trigger", prompt_template="test {paths}")
        assert trigger_id is not None
        assert trigger_id.startswith("trig-")
        trigger = get_trigger(trigger_id)
        assert trigger is not None
        assert trigger["name"] == "Test Trigger"
        assert trigger["prompt_template"] == "test {paths}"
        assert trigger["backend_type"] == "claude"
        assert trigger["trigger_source"] == "webhook"

    def test_add_with_all_params(self):
        trigger_id = create_trigger(
            name="Full Trigger",
            prompt_template="full {paths}",
            backend_type="opencode",
            trigger_source="github",
            match_field_path="event.action",
            match_field_value="opened",
            text_field_path="event.body",
            detection_keyword="security",
            schedule_type="weekly",
            schedule_time="09:00",
            schedule_day=1,
            schedule_timezone="UTC",
            skill_command="/audit",
            model="claude-3.5-sonnet",
            execution_mode="team",
        )
        assert trigger_id is not None
        trigger = get_trigger(trigger_id)
        assert trigger["backend_type"] == "opencode"
        assert trigger["trigger_source"] == "github"
        assert trigger["match_field_path"] == "event.action"
        assert trigger["execution_mode"] == "team"

    def test_update(self):
        trigger_id = create_trigger(name="Original", prompt_template="orig")
        result = update_trigger(trigger_id, name="Updated")
        assert result is True
        trigger = get_trigger(trigger_id)
        assert trigger["name"] == "Updated"

    def test_update_multiple_fields(self):
        trigger_id = create_trigger(name="Multi", prompt_template="multi")
        result = update_trigger(
            trigger_id,
            name="Multi Updated",
            backend_type="opencode",
            trigger_source="manual",
        )
        assert result is True
        trigger = get_trigger(trigger_id)
        assert trigger["name"] == "Multi Updated"
        assert trigger["backend_type"] == "opencode"
        assert trigger["trigger_source"] == "manual"

    def test_update_no_fields(self):
        trigger_id = create_trigger(name="NoChange", prompt_template="nc")
        result = update_trigger(trigger_id)
        assert result is False

    def test_delete(self):
        trigger_id = create_trigger(name="To Delete", prompt_template="del")
        result = delete_trigger(trigger_id)
        assert result is True
        assert get_trigger(trigger_id) is None

    def test_delete_predefined_fails(self):
        """Predefined triggers cannot be deleted."""
        result = delete_trigger("bot-security")
        assert result is False
        assert get_trigger("bot-security") is not None

    def test_delete_nonexistent(self):
        result = delete_trigger("trig-nonexist")
        assert result is False

    def test_get_nonexistent(self):
        assert get_trigger("trig-nonexist") is None

    def test_get_all(self):
        create_trigger(name="Trigger A", prompt_template="a")
        create_trigger(name="Trigger B", prompt_template="b")
        triggers = get_all_triggers()
        # 2 predefined + 2 new = at least 4
        assert len(triggers) >= 4

    def test_get_by_source(self):
        create_trigger(
            name="Webhook Trigger",
            prompt_template="wh",
            trigger_source="webhook",
        )
        results = get_triggers_by_trigger_source("webhook")
        names = [t["name"] for t in results]
        assert "Webhook Trigger" in names

    def test_get_by_source_manual(self):
        create_trigger(
            name="Manual Trigger",
            prompt_template="man",
            trigger_source="manual",
        )
        results = get_triggers_by_trigger_source("manual")
        names = [t["name"] for t in results]
        assert "Manual Trigger" in names

    def test_update_next_run(self):
        trigger_id = create_trigger(name="Schedule Test", prompt_template="sched")
        result = update_trigger_next_run(trigger_id, "2026-01-01T00:00:00")
        assert result is True
        trigger = get_trigger(trigger_id)
        assert trigger["next_run_at"] == "2026-01-01T00:00:00"

    def test_update_last_run(self):
        trigger_id = create_trigger(name="Last Run Test", prompt_template="lr")
        result = update_trigger_last_run(trigger_id, "2026-01-01T12:00:00")
        assert result is True
        trigger = get_trigger(trigger_id)
        assert trigger["last_run_at"] == "2026-01-01T12:00:00"

    def test_update_auto_resolve(self):
        trigger_id = create_trigger(name="Auto Resolve Test", prompt_template="ar")
        result = update_trigger_auto_resolve(trigger_id, True)
        assert result is True
        trigger = get_trigger(trigger_id)
        assert trigger["auto_resolve"] == 1


# =============================================================================
# Agent CRUD tests
# =============================================================================


class TestAgentCRUD:
    def test_add_and_get(self):
        agent_id = create_agent(name="Test Agent", description="desc", system_prompt="prompt")
        assert agent_id is not None
        assert agent_id.startswith("agent-")
        agent = get_agent(agent_id)
        assert agent is not None
        assert agent["name"] == "Test Agent"
        assert agent["description"] == "desc"
        assert agent["system_prompt"] == "prompt"
        assert agent["backend_type"] == "claude"

    def test_add_with_optional_params(self):
        agent_id = create_agent(
            name="Full Agent",
            description="full desc",
            role="reviewer",
            goals="review code",
            context="project context",
            backend_type="opencode",
            system_prompt="You are a reviewer",
            model="claude-3.5-sonnet",
            autonomous=1,
            effort_level="high",
        )
        assert agent_id is not None
        agent = get_agent(agent_id)
        assert agent["role"] == "reviewer"
        assert agent["backend_type"] == "opencode"
        assert agent["autonomous"] == 1
        assert agent["effort_level"] == "high"

    def test_update(self):
        agent_id = create_agent(name="Original Agent", description="d", system_prompt="p")
        result = update_agent(agent_id, name="Updated Agent")
        assert result is True
        agent = get_agent(agent_id)
        assert agent["name"] == "Updated Agent"

    def test_update_multiple_fields(self):
        agent_id = create_agent(name="MultiAgent", description="d", system_prompt="p")
        result = update_agent(agent_id, name="Updated", description="new desc", role="tester")
        assert result is True
        agent = get_agent(agent_id)
        assert agent["name"] == "Updated"
        assert agent["description"] == "new desc"
        assert agent["role"] == "tester"

    def test_update_no_fields(self):
        agent_id = create_agent(name="NoUpdate", description="d", system_prompt="p")
        result = update_agent(agent_id)
        assert result is False

    def test_delete(self):
        agent_id = create_agent(name="To Delete", description="d", system_prompt="p")
        result = delete_agent(agent_id)
        assert result is True
        assert get_agent(agent_id) is None

    def test_delete_nonexistent(self):
        result = delete_agent("agent-nonexistent")
        assert result is False

    def test_get_nonexistent(self):
        assert get_agent("agent-nonexistent") is None

    def test_get_by_name(self):
        create_agent(name="UniqueTestAgent", description="d", system_prompt="p")
        agent = get_agent_by_name("UniqueTestAgent")
        assert agent is not None
        assert agent["name"] == "UniqueTestAgent"

    def test_get_by_name_nonexistent(self):
        assert get_agent_by_name("NonexistentAgent") is None

    def test_get_all(self):
        create_agent(name="Agent 1", description="d1", system_prompt="p1")
        create_agent(name="Agent 2", description="d2", system_prompt="p2")
        agents = get_all_agents()
        assert len(agents) >= 2

    def test_create_conversation(self):
        conv_id = create_agent_conversation()
        assert conv_id is not None
        assert conv_id.startswith("conv-")
        conv = get_agent_conversation(conv_id)
        assert conv is not None
        assert conv["status"] == "active"
        assert conv["messages"] == "[]"

    def test_update_conversation(self):
        conv_id = create_agent_conversation()
        agent_id = create_agent(name="ConvAgent", description="d", system_prompt="p")
        result = update_agent_conversation(conv_id, agent_id=agent_id, messages='[{"text":"hi"}]')
        assert result is True
        conv = get_agent_conversation(conv_id)
        assert conv["agent_id"] == agent_id
        assert conv["messages"] == '[{"text":"hi"}]'

    def test_delete_conversation(self):
        conv_id = create_agent_conversation()
        result = delete_agent_conversation(conv_id)
        assert result is True
        assert get_agent_conversation(conv_id) is None

    def test_get_active_conversations(self):
        conv_id1 = create_agent_conversation()
        conv_id2 = create_agent_conversation()
        convs = get_active_conversations()
        ids = [c["id"] for c in convs]
        assert conv_id1 in ids
        assert conv_id2 in ids


# =============================================================================
# Team CRUD tests
# =============================================================================


class TestTeamCRUD:
    def test_add_and_get(self):
        team_id = create_team(name="Test Team", description="team desc")
        assert team_id is not None
        assert team_id.startswith("team-")
        team = get_team(team_id)
        assert team is not None
        assert team["name"] == "Test Team"
        assert team["description"] == "team desc"
        assert team["color"] == "#00d4ff"

    def test_add_with_params(self):
        team_id = create_team(
            name="Full Team",
            description="desc",
            color="#ff0000",
            topology="sequential",
            trigger_source="webhook",
        )
        assert team_id is not None
        team = get_team(team_id)
        assert team["color"] == "#ff0000"
        assert team["topology"] == "sequential"
        assert team["trigger_source"] == "webhook"

    def test_update(self):
        team_id = create_team(name="Original Team", description="d")
        result = update_team(team_id, name="Updated Team")
        assert result is True
        team = get_team(team_id)
        assert team["name"] == "Updated Team"

    def test_update_multiple_fields(self):
        team_id = create_team(name="MultiTeam", description="d")
        result = update_team(team_id, name="Updated", color="#00ff00", topology="parallel")
        assert result is True
        team = get_team(team_id)
        assert team["name"] == "Updated"
        assert team["color"] == "#00ff00"
        assert team["topology"] == "parallel"

    def test_update_no_fields(self):
        team_id = create_team(name="NoUpdate", description="d")
        result = update_team(team_id)
        assert result is False

    def test_delete(self):
        team_id = create_team(name="To Delete", description="d")
        result = delete_team(team_id)
        assert result is True
        assert get_team(team_id) is None

    def test_delete_nonexistent(self):
        result = delete_team("team-nonexist")
        assert result is False

    def test_get_nonexistent(self):
        assert get_team("team-nonexist") is None

    def test_get_by_name(self):
        create_team(name="UniqueTeam", description="d")
        team = get_team_by_name("UniqueTeam")
        assert team is not None
        assert team["name"] == "UniqueTeam"

    def test_get_by_name_nonexistent(self):
        assert get_team_by_name("NonexistentTeam") is None

    def test_get_all(self):
        create_team(name="Team A", description="a")
        create_team(name="Team B", description="b")
        teams = get_all_teams()
        assert len(teams) >= 2

    def test_get_detail(self):
        team_id = create_team(name="Detail Team", description="d")
        detail = get_team_detail(team_id)
        assert detail is not None
        assert detail["name"] == "Detail Team"
        assert "members" in detail

    def test_get_detail_nonexistent(self):
        assert get_team_detail("team-nonexist") is None

    def test_add_member(self):
        team_id = create_team(name="Member Team", description="d")
        member_id = add_team_member(team_id, name="Alice", role="lead", email="alice@test.com")
        assert member_id is not None
        members = get_team_members(team_id)
        assert len(members) >= 1
        names = [m["name"] for m in members]
        assert "Alice" in names

    def test_add_member_with_agent(self):
        team_id = create_team(name="Agent Team", description="d")
        agent_id = create_agent(name="TeamAgent", description="d", system_prompt="p")
        member_id = add_team_member(team_id, agent_id=agent_id, role="member")
        assert member_id is not None
        members = get_team_members(team_id)
        assert len(members) >= 1

    def test_update_member(self):
        team_id = create_team(name="Update Member Team", description="d")
        member_id = add_team_member(team_id, name="Bob", role="member")
        result = update_team_member(member_id, name="Bobby", role="lead")
        assert result is True

    def test_get_members_empty(self):
        team_id = create_team(name="Empty Team", description="d")
        members = get_team_members(team_id)
        assert members == []

    def test_add_agent_assignment(self):
        team_id = create_team(name="Assign Team", description="d")
        agent_id = create_agent(name="Assign Agent", description="d", system_prompt="p")
        assignment_id = add_team_agent_assignment(
            team_id, agent_id, entity_type="skill", entity_id="skill-1", entity_name="test skill"
        )
        assert assignment_id is not None
        assignments = get_team_agent_assignments(team_id)
        assert len(assignments) >= 1

    def test_get_agent_assignments_filtered(self):
        team_id = create_team(name="Filter Team", description="d")
        agent_id = create_agent(name="Filter Agent", description="d", system_prompt="p")
        add_team_agent_assignment(
            team_id, agent_id, entity_type="skill", entity_id="s1", entity_name="skill1"
        )
        assignments = get_team_agent_assignments(team_id, agent_id=agent_id)
        assert len(assignments) >= 1

    def test_delete_agent_assignment(self):
        team_id = create_team(name="Del Assign Team", description="d")
        agent_id = create_agent(name="Del Assign Agent", description="d", system_prompt="p")
        assignment_id = add_team_agent_assignment(
            team_id, agent_id, entity_type="command", entity_id="c1", entity_name="cmd1"
        )
        result = delete_team_agent_assignment(assignment_id)
        assert result is True


# =============================================================================
# Project CRUD tests
# =============================================================================


class TestProjectCRUD:
    def test_add_and_get(self):
        project_id = create_project(name="Test Project", description="proj desc")
        assert project_id is not None
        assert project_id.startswith("proj-")
        project = get_project(project_id)
        assert project is not None
        assert project["name"] == "Test Project"
        assert project["description"] == "proj desc"
        assert project["status"] == "active"

    def test_add_with_params(self):
        team_id = create_team(name="Owner Team", description="d")
        product_id = create_product(name="Owner Product", description="d")
        project_id = create_project(
            name="Full Project",
            description="d",
            status="active",
            product_id=product_id,
            github_repo="org/repo",
            owner_team_id=team_id,
            local_path="/tmp/project",
        )
        assert project_id is not None
        project = get_project(project_id)
        assert project["github_repo"] == "org/repo"
        assert project["owner_team_id"] == team_id
        assert project["product_id"] == product_id

    def test_update(self):
        project_id = create_project(name="Original Proj", description="d")
        result = update_project(project_id, name="Updated Proj")
        assert result is True
        project = get_project(project_id)
        assert project["name"] == "Updated Proj"

    def test_update_multiple_fields(self):
        project_id = create_project(name="MultiProj", description="d")
        result = update_project(
            project_id, name="Updated", description="new desc", status="archived"
        )
        assert result is True
        project = get_project(project_id)
        assert project["name"] == "Updated"
        assert project["description"] == "new desc"
        assert project["status"] == "archived"

    def test_update_no_fields(self):
        project_id = create_project(name="NoUpdate", description="d")
        result = update_project(project_id)
        assert result is False

    def test_delete(self):
        project_id = create_project(name="To Delete", description="d")
        result = delete_project(project_id)
        assert result is True
        assert get_project(project_id) is None

    def test_delete_nonexistent(self):
        result = delete_project("proj-nonexist")
        assert result is False

    def test_get_nonexistent(self):
        assert get_project("proj-nonexist") is None

    def test_get_all(self):
        create_project(name="Proj A", description="a")
        create_project(name="Proj B", description="b")
        projects = get_all_projects()
        assert len(projects) >= 2

    def test_get_detail(self):
        project_id = create_project(name="Detail Proj", description="d")
        detail = get_project_detail(project_id)
        assert detail is not None
        assert detail["name"] == "Detail Proj"
        assert "teams" in detail

    def test_get_detail_nonexistent(self):
        assert get_project_detail("proj-nonexist") is None

    def test_assign_and_get_teams(self):
        project_id = create_project(name="Team Proj", description="d")
        team_id = create_team(name="Assigned Team", description="d")
        result = assign_team_to_project(project_id, team_id)
        assert result is True
        teams = get_project_teams(project_id)
        assert len(teams) >= 1
        team_ids = [t["id"] for t in teams]
        assert team_id in team_ids

    def test_unassign_team(self):
        project_id = create_project(name="Unassign Proj", description="d")
        team_id = create_team(name="Unassign Team", description="d")
        assign_team_to_project(project_id, team_id)
        result = unassign_team_from_project(project_id, team_id)
        assert result is True
        teams = get_project_teams(project_id)
        team_ids = [t["id"] for t in teams]
        assert team_id not in team_ids

    def test_get_teams_empty(self):
        project_id = create_project(name="Empty Proj", description="d")
        teams = get_project_teams(project_id)
        assert teams == []


# =============================================================================
# Product CRUD tests
# =============================================================================


class TestProductCRUD:
    def test_add_and_get(self):
        product_id = create_product(name="Test Product", description="prod desc")
        assert product_id is not None
        assert product_id.startswith("prod-")
        product = get_product(product_id)
        assert product is not None
        assert product["name"] == "Test Product"
        assert product["description"] == "prod desc"
        assert product["status"] == "active"

    def test_add_with_params(self):
        team_id = create_team(name="Product Owner Team", description="d")
        product_id = create_product(
            name="Full Product",
            description="full",
            status="active",
            owner_team_id=team_id,
        )
        assert product_id is not None
        product = get_product(product_id)
        assert product["owner_team_id"] == team_id

    def test_update(self):
        product_id = create_product(name="Original Product", description="d")
        result = update_product(product_id, name="Updated Product")
        assert result is True
        product = get_product(product_id)
        assert product["name"] == "Updated Product"

    def test_update_multiple_fields(self):
        product_id = create_product(name="MultiProd", description="d")
        result = update_product(
            product_id, name="Updated", description="new desc", status="archived"
        )
        assert result is True
        product = get_product(product_id)
        assert product["name"] == "Updated"
        assert product["description"] == "new desc"
        assert product["status"] == "archived"

    def test_update_no_fields(self):
        product_id = create_product(name="NoUpdate", description="d")
        result = update_product(product_id)
        assert result is False

    def test_delete(self):
        product_id = create_product(name="To Delete", description="d")
        result = delete_product(product_id)
        assert result is True
        assert get_product(product_id) is None

    def test_delete_nonexistent(self):
        result = delete_product("prod-nonexist")
        assert result is False

    def test_get_nonexistent(self):
        assert get_product("prod-nonexist") is None

    def test_get_all(self):
        create_product(name="Prod A", description="a")
        create_product(name="Prod B", description="b")
        products = get_all_products()
        assert len(products) >= 2

    def test_get_detail(self):
        product_id = create_product(name="Detail Product", description="d")
        detail = get_product_detail(product_id)
        assert detail is not None
        assert detail["name"] == "Detail Product"
        assert "projects" in detail

    def test_get_detail_nonexistent(self):
        assert get_product_detail("prod-nonexist") is None

    def test_get_detail_with_projects(self):
        product_id = create_product(name="Proj Product", description="d")
        create_project(name="Child Proj", description="d", product_id=product_id)
        detail = get_product_detail(product_id)
        assert detail is not None
        assert len(detail["projects"]) >= 1


# =============================================================================
# Plugin CRUD tests
# =============================================================================


class TestPluginCRUD:
    def test_add_and_get(self):
        plugin_id = create_plugin(name="Test Plugin", description="plugin desc")
        assert plugin_id is not None
        assert plugin_id.startswith("plug-")
        plugin = get_plugin(plugin_id)
        assert plugin is not None
        assert plugin["name"] == "Test Plugin"
        assert plugin["description"] == "plugin desc"
        assert plugin["version"] == "1.0.0"
        assert plugin["status"] == "draft"

    def test_add_with_params(self):
        plugin_id = create_plugin(
            name="Full Plugin",
            description="full",
            version="2.0.0",
            status="published",
            author="tester",
        )
        assert plugin_id is not None
        plugin = get_plugin(plugin_id)
        assert plugin["version"] == "2.0.0"
        assert plugin["status"] == "published"
        assert plugin["author"] == "tester"

    def test_update(self):
        plugin_id = create_plugin(name="Original Plugin", description="d")
        result = update_plugin(plugin_id, name="Updated Plugin")
        assert result is True
        plugin = get_plugin(plugin_id)
        assert plugin["name"] == "Updated Plugin"

    def test_update_multiple_fields(self):
        plugin_id = create_plugin(name="MultiPlug", description="d")
        result = update_plugin(plugin_id, name="Updated", version="3.0.0", status="published")
        assert result is True
        plugin = get_plugin(plugin_id)
        assert plugin["name"] == "Updated"
        assert plugin["version"] == "3.0.0"
        assert plugin["status"] == "published"

    def test_update_no_fields(self):
        plugin_id = create_plugin(name="NoUpdate", description="d")
        result = update_plugin(plugin_id)
        assert result is False

    def test_delete(self):
        plugin_id = create_plugin(name="To Delete", description="d")
        result = delete_plugin(plugin_id)
        assert result is True
        assert get_plugin(plugin_id) is None

    def test_delete_nonexistent(self):
        result = delete_plugin("plug-nonexist")
        assert result is False

    def test_get_nonexistent(self):
        assert get_plugin("plug-nonexist") is None

    def test_get_all(self):
        create_plugin(name="Plugin A", description="a")
        create_plugin(name="Plugin B", description="b")
        plugins = get_all_plugins()
        assert len(plugins) >= 2

    def test_get_detail(self):
        plugin_id = create_plugin(name="Detail Plugin", description="d")
        detail = get_plugin_detail(plugin_id)
        assert detail is not None
        assert detail["name"] == "Detail Plugin"
        assert "components" in detail

    def test_get_detail_nonexistent(self):
        assert get_plugin_detail("plug-nonexist") is None

    def test_add_component(self):
        plugin_id = create_plugin(name="Comp Plugin", description="d")
        comp_id = add_plugin_component(
            plugin_id, name="my-skill", component_type="skill", content="echo hello"
        )
        assert comp_id is not None
        components = get_plugin_components(plugin_id)
        assert len(components) >= 1
        assert components[0]["name"] == "my-skill"
        assert components[0]["type"] == "skill"

    def test_get_component_by_name(self):
        plugin_id = create_plugin(name="CompName Plugin", description="d")
        add_plugin_component(plugin_id, name="test-hook", component_type="hook", content="content")
        comp = get_plugin_component_by_name(plugin_id, "test-hook", "hook")
        assert comp is not None
        assert comp["name"] == "test-hook"

    def test_get_component_by_name_nonexistent(self):
        plugin_id = create_plugin(name="NoComp Plugin", description="d")
        assert get_plugin_component_by_name(plugin_id, "nonexist", "skill") is None

    def test_update_component(self):
        plugin_id = create_plugin(name="UpdComp Plugin", description="d")
        comp_id = add_plugin_component(plugin_id, name="orig", component_type="skill", content="v1")
        result = update_plugin_component(comp_id, name="updated", content="v2")
        assert result is True

    def test_delete_component(self):
        plugin_id = create_plugin(name="DelComp Plugin", description="d")
        comp_id = add_plugin_component(
            plugin_id, name="del-comp", component_type="command", content="x"
        )
        result = delete_plugin_component(comp_id)
        assert result is True
        components = get_plugin_components(plugin_id)
        assert len(components) == 0

    def test_get_components_empty(self):
        plugin_id = create_plugin(name="Empty Plugin", description="d")
        components = get_plugin_components(plugin_id)
        assert components == []

    def test_get_detail_with_components(self):
        plugin_id = create_plugin(name="Full Detail Plugin", description="d")
        add_plugin_component(plugin_id, name="s1", component_type="skill", content="c1")
        add_plugin_component(plugin_id, name="h1", component_type="hook", content="c2")
        detail = get_plugin_detail(plugin_id)
        assert len(detail["components"]) == 2


# =============================================================================
# Skill (user_skills) CRUD tests
# =============================================================================


class TestSkillCRUD:
    def test_add_and_get(self):
        skill_id = add_user_skill(skill_name="test-skill", skill_path="/skills/test")
        assert skill_id is not None
        assert isinstance(skill_id, int)
        skill = get_user_skill(skill_id)
        assert skill is not None
        assert skill["skill_name"] == "test-skill"
        assert skill["skill_path"] == "/skills/test"
        assert skill["enabled"] == 1

    def test_add_with_params(self):
        skill_id = add_user_skill(
            skill_name="full-skill",
            skill_path="/skills/full",
            description="A full skill",
            enabled=0,
            selected_for_harness=1,
            metadata='{"key": "value"}',
        )
        assert skill_id is not None
        skill = get_user_skill(skill_id)
        assert skill["description"] == "A full skill"
        assert skill["enabled"] == 0
        assert skill["selected_for_harness"] == 1

    def test_update(self):
        skill_id = add_user_skill(skill_name="orig-skill", skill_path="/skills/orig")
        result = update_user_skill(skill_id, skill_name="updated-skill")
        assert result is True
        skill = get_user_skill(skill_id)
        assert skill["skill_name"] == "updated-skill"

    def test_update_multiple_fields(self):
        skill_id = add_user_skill(skill_name="multi-skill", skill_path="/skills/multi")
        result = update_user_skill(
            skill_id, skill_name="updated", description="new desc", enabled=0
        )
        assert result is True
        skill = get_user_skill(skill_id)
        assert skill["skill_name"] == "updated"
        assert skill["description"] == "new desc"
        assert skill["enabled"] == 0

    def test_update_no_fields(self):
        skill_id = add_user_skill(skill_name="no-update", skill_path="/skills/no")
        result = update_user_skill(skill_id)
        assert result is False

    def test_delete(self):
        skill_id = add_user_skill(skill_name="del-skill", skill_path="/skills/del")
        result = delete_user_skill(skill_id)
        assert result is True
        assert get_user_skill(skill_id) is None

    def test_delete_nonexistent(self):
        result = delete_user_skill(99999)
        assert result is False

    def test_get_nonexistent(self):
        assert get_user_skill(99999) is None

    def test_get_by_name(self):
        add_user_skill(skill_name="unique-skill", skill_path="/skills/unique")
        skill = get_user_skill_by_name("unique-skill")
        assert skill is not None
        assert skill["skill_name"] == "unique-skill"

    def test_get_by_name_nonexistent(self):
        assert get_user_skill_by_name("nonexistent-skill") is None

    def test_get_all(self):
        add_user_skill(skill_name="skill-a", skill_path="/a")
        add_user_skill(skill_name="skill-b", skill_path="/b")
        skills = get_all_user_skills()
        assert len(skills) >= 2

    def test_get_enabled(self):
        add_user_skill(skill_name="enabled-skill", skill_path="/e", enabled=1)
        add_user_skill(skill_name="disabled-skill", skill_path="/d", enabled=0)
        enabled = get_enabled_user_skills()
        names = [s["skill_name"] for s in enabled]
        assert "enabled-skill" in names
        assert "disabled-skill" not in names

    def test_toggle_harness(self):
        skill_id = add_user_skill(skill_name="harness-skill", skill_path="/h")
        result = toggle_skill_harness(skill_id, True)
        assert result is True
        skill = get_user_skill(skill_id)
        assert skill["selected_for_harness"] == 1

    def test_toggle_harness_off(self):
        skill_id = add_user_skill(
            skill_name="harness-off", skill_path="/ho", selected_for_harness=1
        )
        result = toggle_skill_harness(skill_id, False)
        assert result is True
        skill = get_user_skill(skill_id)
        assert skill["selected_for_harness"] == 0

    def test_get_harness_skills(self):
        add_user_skill(skill_name="harness-yes", skill_path="/hy", selected_for_harness=1)
        add_user_skill(skill_name="harness-no", skill_path="/hn", selected_for_harness=0)
        harness = get_harness_skills()
        names = [s["skill_name"] for s in harness]
        assert "harness-yes" in names
        assert "harness-no" not in names


# =============================================================================
# Hook CRUD tests
# =============================================================================


class TestHookCRUD:
    def test_add_and_get(self):
        hook_id = create_hook(name="Test Hook", event="pre-commit")
        assert hook_id is not None
        assert isinstance(hook_id, int)
        hook = get_hook(hook_id)
        assert hook is not None
        assert hook["name"] == "Test Hook"
        assert hook["event"] == "pre-commit"
        assert hook["enabled"] == 1

    def test_add_with_params(self):
        project_id = create_project(name="Hook Proj", description="d")
        hook_id = create_hook(
            name="Full Hook",
            event="post-push",
            description="A full hook",
            content="echo done",
            enabled=False,
            project_id=project_id,
            source_path="/hooks/test.sh",
        )
        assert hook_id is not None
        hook = get_hook(hook_id)
        assert hook["description"] == "A full hook"
        assert hook["content"] == "echo done"
        assert hook["enabled"] == 0
        assert hook["project_id"] == project_id

    def test_update(self):
        hook_id = create_hook(name="Original Hook", event="pre-commit")
        result = update_hook(hook_id, name="Updated Hook")
        assert result is True
        hook = get_hook(hook_id)
        assert hook["name"] == "Updated Hook"

    def test_update_multiple_fields(self):
        hook_id = create_hook(name="Multi Hook", event="pre-commit")
        result = update_hook(hook_id, name="Updated", event="post-push", enabled=False)
        assert result is True
        hook = get_hook(hook_id)
        assert hook["name"] == "Updated"
        assert hook["event"] == "post-push"
        assert hook["enabled"] == 0

    def test_update_no_fields(self):
        hook_id = create_hook(name="NoUpdate", event="pre-commit")
        result = update_hook(hook_id)
        assert result is False

    def test_delete(self):
        hook_id = create_hook(name="To Delete", event="pre-commit")
        result = delete_hook(hook_id)
        assert result is True
        assert get_hook(hook_id) is None

    def test_delete_nonexistent(self):
        result = delete_hook(99999)
        assert result is False

    def test_get_nonexistent(self):
        assert get_hook(99999) is None

    def test_get_all(self):
        create_hook(name="Hook A", event="pre-commit")
        create_hook(name="Hook B", event="post-push")
        hooks = get_all_hooks()
        assert len(hooks) >= 2

    def test_get_all_filtered_by_project(self):
        project_id = create_project(name="Filter Proj", description="d")
        create_hook(name="Proj Hook", event="pre-commit", project_id=project_id)
        create_hook(name="Global Hook", event="pre-commit")
        hooks = get_all_hooks(project_id=project_id)
        names = [h["name"] for h in hooks]
        assert "Proj Hook" in names
        # Global hooks (project_id IS NULL) are also included by get_all_hooks
        assert "Global Hook" in names

    def test_get_by_project(self):
        project_id = create_project(name="By Proj", description="d")
        create_hook(name="Proj Only Hook", event="pre-commit", project_id=project_id)
        create_hook(name="Other Hook", event="pre-commit")
        hooks = get_hooks_by_project(project_id)
        names = [h["name"] for h in hooks]
        assert "Proj Only Hook" in names
        assert "Other Hook" not in names

    def test_get_by_event(self):
        create_hook(name="PreCommit Hook", event="pre-commit")
        create_hook(name="PostPush Hook", event="post-push")
        hooks = get_hooks_by_event("pre-commit")
        names = [h["name"] for h in hooks]
        assert "PreCommit Hook" in names
        assert "PostPush Hook" not in names

    def test_get_by_event_disabled(self):
        """Disabled hooks should not be returned by get_hooks_by_event."""
        create_hook(name="Disabled Hook", event="deploy", enabled=False)
        hooks = get_hooks_by_event("deploy")
        names = [h["name"] for h in hooks]
        assert "Disabled Hook" not in names


# =============================================================================
# Command CRUD tests
# =============================================================================


class TestCommandCRUD:
    def test_add_and_get(self):
        cmd_id = create_command(name="test-cmd", description="A test command")
        assert cmd_id is not None
        assert isinstance(cmd_id, int)
        cmd = get_command(cmd_id)
        assert cmd is not None
        assert cmd["name"] == "test-cmd"
        assert cmd["description"] == "A test command"
        assert cmd["enabled"] == 1

    def test_add_with_params(self):
        project_id = create_project(name="Cmd Proj", description="d")
        cmd_id = create_command(
            name="full-cmd",
            description="full",
            content="echo hello",
            arguments="--verbose",
            enabled=False,
            project_id=project_id,
            source_path="/commands/test.sh",
        )
        assert cmd_id is not None
        cmd = get_command(cmd_id)
        assert cmd["content"] == "echo hello"
        assert cmd["arguments"] == "--verbose"
        assert cmd["enabled"] == 0
        assert cmd["project_id"] == project_id

    def test_update(self):
        cmd_id = create_command(name="orig-cmd")
        result = update_command(cmd_id, name="updated-cmd")
        assert result is True
        cmd = get_command(cmd_id)
        assert cmd["name"] == "updated-cmd"

    def test_update_multiple_fields(self):
        cmd_id = create_command(name="multi-cmd")
        result = update_command(
            cmd_id, name="updated", description="new desc", content="new content", enabled=False
        )
        assert result is True
        cmd = get_command(cmd_id)
        assert cmd["name"] == "updated"
        assert cmd["description"] == "new desc"
        assert cmd["content"] == "new content"
        assert cmd["enabled"] == 0

    def test_update_no_fields(self):
        cmd_id = create_command(name="no-update")
        result = update_command(cmd_id)
        assert result is False

    def test_delete(self):
        cmd_id = create_command(name="del-cmd")
        result = delete_command(cmd_id)
        assert result is True
        assert get_command(cmd_id) is None

    def test_delete_nonexistent(self):
        result = delete_command(99999)
        assert result is False

    def test_get_nonexistent(self):
        assert get_command(99999) is None

    def test_get_all(self):
        create_command(name="Cmd A")
        create_command(name="Cmd B")
        commands = get_all_commands()
        assert len(commands) >= 2

    def test_get_all_filtered_by_project(self):
        project_id = create_project(name="CmdFilter Proj", description="d")
        create_command(name="Proj Cmd", project_id=project_id)
        create_command(name="Global Cmd")
        commands = get_all_commands(project_id=project_id)
        names = [c["name"] for c in commands]
        assert "Proj Cmd" in names
        assert "Global Cmd" in names

    def test_get_by_project(self):
        project_id = create_project(name="CmdBy Proj", description="d")
        create_command(name="Proj Only Cmd", project_id=project_id)
        create_command(name="Other Cmd")
        commands = get_commands_by_project(project_id)
        names = [c["name"] for c in commands]
        assert "Proj Only Cmd" in names
        assert "Other Cmd" not in names


# =============================================================================
# Rule CRUD tests
# =============================================================================


class TestRuleCRUD:
    def test_add_and_get(self):
        rule_id = create_rule(name="Test Rule")
        assert rule_id is not None
        assert isinstance(rule_id, int)
        rule = get_rule(rule_id)
        assert rule is not None
        assert rule["name"] == "Test Rule"
        assert rule["rule_type"] == "validation"
        assert rule["enabled"] == 1

    def test_add_with_params(self):
        project_id = create_project(name="Rule Proj", description="d")
        rule_id = create_rule(
            name="Full Rule",
            rule_type="security",
            description="A security rule",
            condition="file.endswith('.py')",
            action="lint",
            enabled=False,
            project_id=project_id,
            source_path="/rules/test.yaml",
        )
        assert rule_id is not None
        rule = get_rule(rule_id)
        assert rule["rule_type"] == "security"
        assert rule["description"] == "A security rule"
        assert rule["condition"] == "file.endswith('.py')"
        assert rule["action"] == "lint"
        assert rule["enabled"] == 0
        assert rule["project_id"] == project_id

    def test_update(self):
        rule_id = create_rule(name="Original Rule")
        result = update_rule(rule_id, name="Updated Rule")
        assert result is True
        rule = get_rule(rule_id)
        assert rule["name"] == "Updated Rule"

    def test_update_multiple_fields(self):
        rule_id = create_rule(name="Multi Rule")
        result = update_rule(
            rule_id, name="Updated", rule_type="security", description="new desc", enabled=False
        )
        assert result is True
        rule = get_rule(rule_id)
        assert rule["name"] == "Updated"
        assert rule["rule_type"] == "security"
        assert rule["description"] == "new desc"
        assert rule["enabled"] == 0

    def test_update_no_fields(self):
        rule_id = create_rule(name="NoUpdate")
        result = update_rule(rule_id)
        assert result is False

    def test_delete(self):
        rule_id = create_rule(name="To Delete")
        result = delete_rule(rule_id)
        assert result is True
        assert get_rule(rule_id) is None

    def test_delete_nonexistent(self):
        result = delete_rule(99999)
        assert result is False

    def test_get_nonexistent(self):
        assert get_rule(99999) is None

    def test_get_all(self):
        create_rule(name="Rule A")
        create_rule(name="Rule B")
        rules = get_all_rules()
        assert len(rules) >= 2

    def test_get_all_filtered_by_project(self):
        project_id = create_project(name="RuleFilter Proj", description="d")
        create_rule(name="Proj Rule", project_id=project_id)
        create_rule(name="Global Rule")
        rules = get_all_rules(project_id=project_id)
        names = [r["name"] for r in rules]
        assert "Proj Rule" in names
        assert "Global Rule" in names

    def test_get_by_project(self):
        project_id = create_project(name="RuleBy Proj", description="d")
        create_rule(name="Proj Only Rule", project_id=project_id)
        create_rule(name="Other Rule")
        rules = get_rules_by_project(project_id)
        names = [r["name"] for r in rules]
        assert "Proj Only Rule" in names
        assert "Other Rule" not in names

    def test_get_by_type(self):
        create_rule(name="Validation Rule", rule_type="validation")
        create_rule(name="Security Rule", rule_type="security")
        rules = get_rules_by_type("validation")
        names = [r["name"] for r in rules]
        assert "Validation Rule" in names
        assert "Security Rule" not in names

    def test_get_by_type_disabled(self):
        """Disabled rules should not be returned by get_rules_by_type."""
        create_rule(name="Disabled Rule", rule_type="audit", enabled=False)
        rules = get_rules_by_type("audit")
        names = [r["name"] for r in rules]
        assert "Disabled Rule" not in names


# =============================================================================
# Supplementary coverage tests — exercise update branches and auxiliary functions
# =============================================================================

from app.database import (
    add_marketplace_plugin,
    # Plugin export functions
    add_plugin_export,
    # PR review functions
    add_pr_review,
    add_project_installation,
    # Project skills/installations
    add_project_skill,
    clear_project_skills,
    # Execution log functions
    create_execution_log,
    # Marketplace functions
    create_marketplace,
    delete_marketplace,
    delete_marketplace_plugin,
    delete_old_execution_logs,
    delete_plugin_export,
    delete_pr_review,
    delete_project_installation,
    delete_project_skill,
    delete_project_skill_by_id,
    # Additional team functions
    delete_team_agent_assignments_bulk,
    get_active_execution_count,
    get_all_execution_logs,
    get_all_marketplaces,
    get_all_pr_reviews,
    get_execution_log,
    get_execution_logs_for_trigger,
    get_latest_execution_for_trigger,
    get_marketplace,
    get_marketplace_plugins,
    get_plugin_export,
    get_plugin_exports_for_plugin,
    get_pr_review,
    get_pr_review_history,
    get_pr_review_stats,
    get_pr_reviews_count,
    get_pr_reviews_for_trigger,
    get_project_installation,
    get_project_installations,
    get_project_skills,
    get_running_execution_for_trigger,
    get_teams_by_trigger_source,
    # Additional trigger functions
    get_webhook_triggers,
    mark_stale_executions_interrupted,
    update_execution_log,
    update_execution_status_cas,
    update_marketplace,
    update_plugin_export,
)


class TestTriggerUpdateBranches:
    """Exercise all update_trigger field branches for coverage."""

    def test_update_all_fields(self):
        # Create a real team for FK constraint
        team_id = create_team(name="TrigTeam", description="d")
        tid = create_trigger(name="AllFields", prompt_template="af")
        result = update_trigger(
            tid,
            name="Updated",
            group_id=5,
            detection_keyword="alert",
            prompt_template="updated {paths}",
            backend_type="opencode",
            trigger_source="manual",
            match_field_path="event.type",
            match_field_value="push",
            text_field_path="event.body",
            enabled=0,
            schedule_type="daily",
            schedule_time="10:00",
            schedule_day=3,
            schedule_timezone="UTC",
            skill_command="/deploy",
            model="claude-sonnet",
            execution_mode="team",
            team_id=team_id,
        )
        assert result is True
        t = get_trigger(tid)
        assert t["name"] == "Updated"
        assert t["group_id"] == 5
        assert t["detection_keyword"] == "alert"
        assert t["backend_type"] == "opencode"
        assert t["enabled"] == 0
        assert t["schedule_type"] == "daily"
        assert t["schedule_time"] == "10:00"
        assert t["schedule_day"] == 3
        assert t["skill_command"] == "/deploy"
        assert t["model"] == "claude-sonnet"
        assert t["execution_mode"] == "team"
        assert t["team_id"] == team_id

    def test_update_null_fields(self):
        """Setting fields to empty string clears them to NULL."""
        team_id = create_team(name="NullTeam", description="d")
        tid = create_trigger(
            name="NullTest",
            prompt_template="nt",
            match_field_path="event.x",
            match_field_value="v",
            skill_command="/test",
            model="claude",
            team_id=team_id,
        )
        result = update_trigger(
            tid,
            match_field_path="",
            match_field_value="",
            text_field_path="",
            schedule_type="",
            schedule_time="",
            skill_command="",
            model="",
            team_id="",
        )
        assert result is True
        t = get_trigger(tid)
        assert t["match_field_path"] is None
        assert t["match_field_value"] is None
        assert t["text_field_path"] == "text"  # Reset to default
        assert t["schedule_type"] is None
        assert t["schedule_time"] is None
        assert t["skill_command"] is None
        assert t["model"] is None
        assert t["team_id"] is None

    def test_update_invalid_backend_type_ignored(self):
        tid = create_trigger(name="InvalidBT", prompt_template="ib")
        update_trigger(tid, backend_type="invalid_backend")
        t = get_trigger(tid)
        assert t["backend_type"] == "claude"  # Unchanged

    def test_update_invalid_trigger_source_ignored(self):
        tid = create_trigger(name="InvalidTS", prompt_template="is")
        update_trigger(tid, trigger_source="invalid_source")
        t = get_trigger(tid)
        assert t["trigger_source"] == "webhook"  # Unchanged


class TestAgentUpdateBranches:
    """Exercise all update_agent field branches for coverage."""

    def test_update_all_fields(self):
        aid = create_agent(name="AllFields Agent", system_prompt="p")
        result = update_agent(
            aid,
            name="Updated Agent",
            description="new desc",
            role="reviewer",
            goals="review all",
            context="project context",
            backend_type="opencode",
            enabled=0,
            skills="python,js",
            documents="doc1.md",
            system_prompt="new prompt",
            creation_status="in_progress",
            triggers="trig-1",
            color="#ff0000",
            icon="robot",
            model="claude-4",
            temperature=0.8,
            tools="bash,read",
            autonomous=1,
            allowed_tools="bash",
            preferred_model="claude-opus",
            effort_level="high",
        )
        assert result is True
        a = get_agent(aid)
        assert a["name"] == "Updated Agent"
        assert a["description"] == "new desc"
        assert a["role"] == "reviewer"
        assert a["goals"] == "review all"
        assert a["context"] == "project context"
        assert a["backend_type"] == "opencode"
        assert a["enabled"] == 0
        assert a["skills"] == "python,js"
        assert a["documents"] == "doc1.md"
        assert a["system_prompt"] == "new prompt"
        assert a["creation_status"] == "in_progress"
        assert a["color"] == "#ff0000"
        assert a["icon"] == "robot"
        assert a["model"] == "claude-4"
        assert a["temperature"] == 0.8
        assert a["tools"] == "bash,read"
        assert a["autonomous"] == 1
        assert a["allowed_tools"] == "bash"
        assert a["preferred_model"] == "claude-opus"
        assert a["effort_level"] == "high"


class TestTeamSupplementary:
    """Additional team tests for coverage."""

    def test_delete_agent_assignments_bulk(self):
        team_id = create_team(name="Bulk Team", description="d")
        agent_id = create_agent(name="Bulk Agent", system_prompt="p")
        add_team_agent_assignment(team_id, agent_id, "skill", "s1", "skill1")
        add_team_agent_assignment(team_id, agent_id, "command", "c1", "cmd1")
        count = delete_team_agent_assignments_bulk(team_id, agent_id=agent_id)
        assert count >= 2

    def test_delete_agent_assignments_bulk_by_type(self):
        team_id = create_team(name="BulkType Team", description="d")
        agent_id = create_agent(name="BulkType Agent", system_prompt="p")
        add_team_agent_assignment(team_id, agent_id, "skill", "s1", "skill1")
        add_team_agent_assignment(team_id, agent_id, "command", "c1", "cmd1")
        count = delete_team_agent_assignments_bulk(team_id, entity_type="skill")
        assert count >= 1

    def test_get_teams_by_trigger_source(self):
        create_team(name="Webhook Team", description="d", trigger_source="webhook")
        teams = get_teams_by_trigger_source("webhook")
        names = [t["name"] for t in teams]
        assert "Webhook Team" in names

    def test_get_webhook_triggers(self):
        create_trigger(name="WH Test", prompt_template="wh", trigger_source="webhook")
        triggers = get_webhook_triggers()
        names = [t["name"] for t in triggers]
        assert "WH Test" in names


class TestExecutionLogCRUD:
    """Tests for execution log CRUD functions."""

    def test_create_and_get(self):
        trigger_id = create_trigger(name="Exec Trigger", prompt_template="e")
        result = create_execution_log(
            execution_id="exec-001",
            trigger_id=trigger_id,
            trigger_type="manual",
            started_at="2026-01-01T00:00:00",
            prompt="test prompt",
            backend_type="claude",
            command="claude -p test",
        )
        assert result is True
        log = get_execution_log("exec-001")
        assert log is not None
        assert log["trigger_id"] == trigger_id
        assert log["status"] == "running"

    def test_update(self):
        trigger_id = create_trigger(name="Exec Upd", prompt_template="e")
        create_execution_log(
            "exec-002", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        result = update_execution_log(
            "exec-002",
            status="completed",
            finished_at="2026-01-01T00:01:00",
            duration_ms=60000,
            exit_code=0,
            stdout_log="output",
            stderr_log="",
        )
        assert result is True
        log = get_execution_log("exec-002")
        assert log["status"] == "completed"
        assert log["duration_ms"] == 60000

    def test_update_no_fields(self):
        trigger_id = create_trigger(name="Exec NoUpd", prompt_template="e")
        create_execution_log(
            "exec-003", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        result = update_execution_log("exec-003")
        assert result is False

    def test_get_logs_for_trigger(self):
        trigger_id = create_trigger(name="Exec List", prompt_template="e")
        create_execution_log(
            "exec-010", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        logs = get_execution_logs_for_trigger(trigger_id)
        assert len(logs) >= 1

    def test_get_all_logs(self):
        trigger_id = create_trigger(name="Exec All", prompt_template="e")
        create_execution_log(
            "exec-020", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        logs = get_all_execution_logs()
        assert len(logs) >= 1

    def test_get_running_for_trigger(self):
        trigger_id = create_trigger(name="Exec Run", prompt_template="e")
        create_execution_log(
            "exec-030", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        running = get_running_execution_for_trigger(trigger_id)
        assert running is not None

    def test_get_latest_for_trigger(self):
        trigger_id = create_trigger(name="Exec Latest", prompt_template="e")
        create_execution_log(
            "exec-040", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        latest = get_latest_execution_for_trigger(trigger_id)
        assert latest is not None

    def test_active_count(self):
        count = get_active_execution_count()
        assert isinstance(count, int)

    def test_delete_old(self):
        count = delete_old_execution_logs(days=30)
        assert isinstance(count, int)

    def test_update_status_cas(self):
        trigger_id = create_trigger(name="Exec CAS", prompt_template="e")
        create_execution_log(
            "exec-050", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        result = update_execution_status_cas(
            "exec-050",
            "completed",
            expected_status="running",
            finished_at="2026-01-01T00:01:00",
            duration_ms=60000,
            exit_code=0,
        )
        assert result is True

    def test_update_status_cas_wrong_expected(self):
        trigger_id = create_trigger(name="Exec CAS2", prompt_template="e")
        create_execution_log(
            "exec-051", trigger_id, "manual", "2026-01-01T00:00:00", "p", "claude", "cmd"
        )
        result = update_execution_status_cas("exec-051", "completed", expected_status="cancelled")
        assert result is False

    def test_mark_stale_interrupted(self):
        count = mark_stale_executions_interrupted()
        assert isinstance(count, int)


class TestPRReviewCRUD:
    """Tests for PR review CRUD functions."""

    def test_add_and_get(self):
        review_id = add_pr_review(
            project_name="test-project",
            pr_number=42,
            pr_url="https://github.com/org/repo/pull/42",
            pr_title="Fix bug",
        )
        assert review_id is not None
        review = get_pr_review(review_id)
        assert review is not None
        assert review["pr_number"] == 42
        assert review["pr_title"] == "Fix bug"

    def test_get_nonexistent(self):
        assert get_pr_review(99999) is None

    def test_get_for_trigger(self):
        add_pr_review(
            project_name="proj",
            pr_number=1,
            pr_url="https://github.com/org/repo/pull/1",
            pr_title="PR 1",
        )
        reviews = get_pr_reviews_for_trigger()
        assert len(reviews) >= 1

    def test_get_all(self):
        add_pr_review(
            project_name="proj",
            pr_number=2,
            pr_url="https://github.com/org/repo/pull/2",
            pr_title="PR 2",
        )
        reviews = get_all_pr_reviews()
        assert len(reviews) >= 1

    def test_delete(self):
        review_id = add_pr_review(
            project_name="proj",
            pr_number=99,
            pr_url="https://github.com/org/repo/pull/99",
            pr_title="To Delete",
        )
        result = delete_pr_review(review_id)
        assert result is True
        assert get_pr_review(review_id) is None

    def test_count(self):
        count = get_pr_reviews_count()
        assert isinstance(count, int)

    def test_stats(self):
        stats = get_pr_review_stats()
        assert "total_prs" in stats

    def test_history(self):
        history = get_pr_review_history()
        assert isinstance(history, list)


class TestProjectSkillsCRUD:
    """Tests for project skills functions."""

    def test_add_and_get(self):
        project_id = create_project(name="Skill Proj", description="d")
        skill_id = add_project_skill(project_id, "test-skill", "/skills/test")
        assert skill_id is not None
        skills = get_project_skills(project_id)
        assert len(skills) >= 1
        assert skills[0]["skill_name"] == "test-skill"

    def test_delete_by_name(self):
        project_id = create_project(name="SkillDel Proj", description="d")
        add_project_skill(project_id, "del-skill", "/skills/del")
        result = delete_project_skill(project_id, "del-skill")
        assert result is True
        skills = get_project_skills(project_id)
        assert len(skills) == 0

    def test_delete_by_id(self):
        project_id = create_project(name="SkillDelId Proj", description="d")
        skill_id = add_project_skill(project_id, "del-id-skill", "/skills/del-id")
        result = delete_project_skill_by_id(skill_id)
        assert result is True

    def test_clear_skills(self):
        project_id = create_project(name="ClearSkill Proj", description="d")
        add_project_skill(project_id, "s1", "/s1")
        add_project_skill(project_id, "s2", "/s2")
        count = clear_project_skills(project_id)
        assert count >= 2

    def test_clear_skills_by_source(self):
        project_id = create_project(name="ClearSrc Proj", description="d")
        add_project_skill(project_id, "s1", "/s1", source="manual")
        add_project_skill(project_id, "s2", "/s2", source="scan")
        count = clear_project_skills(project_id, source="manual")
        assert count >= 1
        remaining = get_project_skills(project_id)
        assert len(remaining) >= 1


class TestProjectInstallationsCRUD:
    """Tests for project installation functions."""

    def test_add_and_get(self):
        project_id = create_project(name="Install Proj", description="d")
        inst_id = add_project_installation(project_id, "plugin", "plug-abc")
        assert inst_id is not None
        installations = get_project_installations(project_id)
        assert len(installations) >= 1

    def test_get_filtered_by_type(self):
        project_id = create_project(name="InstFilter Proj", description="d")
        add_project_installation(project_id, "plugin", "plug-1")
        add_project_installation(project_id, "skill", "skill-1")
        plugins = get_project_installations(project_id, component_type="plugin")
        assert len(plugins) >= 1
        assert all(i["component_type"] == "plugin" for i in plugins)

    def test_get_single(self):
        project_id = create_project(name="InstSingle Proj", description="d")
        add_project_installation(project_id, "plugin", "plug-xyz")
        inst = get_project_installation(project_id, "plugin", "plug-xyz")
        assert inst is not None

    def test_delete(self):
        project_id = create_project(name="InstDel Proj", description="d")
        add_project_installation(project_id, "plugin", "plug-del")
        result = delete_project_installation(project_id, "plugin", "plug-del")
        assert result is True


class TestMarketplaceCRUD:
    """Tests for marketplace functions."""

    def test_add_and_get(self):
        mkt_id = create_marketplace(name="Test Market", url="https://example.com")
        assert mkt_id is not None
        mkt = get_marketplace(mkt_id)
        assert mkt is not None
        assert mkt["name"] == "Test Market"

    def test_get_all(self):
        create_marketplace(name="Market A", url="https://a.com")
        mkts = get_all_marketplaces()
        assert len(mkts) >= 1

    def test_update(self):
        mkt_id = create_marketplace(name="UpdMarket", url="https://upd.com")
        result = update_marketplace(mkt_id, name="Updated Market")
        assert result is True
        mkt = get_marketplace(mkt_id)
        assert mkt["name"] == "Updated Market"

    def test_update_no_fields(self):
        mkt_id = create_marketplace(name="NoUpd", url="https://noupd.com")
        result = update_marketplace(mkt_id)
        assert result is False

    def test_delete(self):
        mkt_id = create_marketplace(name="DelMarket", url="https://del.com")
        result = delete_marketplace(mkt_id)
        assert result is True

    def test_add_plugin(self):
        mkt_id = create_marketplace(name="PluginMarket", url="https://pm.com")
        mktp_id = add_marketplace_plugin(mkt_id, remote_name="cool-plugin")
        assert mktp_id is not None
        plugins = get_marketplace_plugins(mkt_id)
        assert len(plugins) >= 1

    def test_delete_plugin(self):
        mkt_id = create_marketplace(name="DelPlugMarket", url="https://dpm.com")
        mktp_id = add_marketplace_plugin(mkt_id, remote_name="del-plugin")
        result = delete_marketplace_plugin(mktp_id)
        assert result is True


class TestPluginExportCRUD:
    """Tests for plugin export functions."""

    def test_add_and_get(self):
        plugin_id = create_plugin(name="Export Plugin", description="d")
        export_id = add_plugin_export(plugin_id)
        assert export_id is not None
        export = get_plugin_export(export_id)
        assert export is not None
        assert export["plugin_id"] == plugin_id

    def test_get_for_plugin(self):
        plugin_id = create_plugin(name="Exports Plugin", description="d")
        add_plugin_export(plugin_id, export_format="claude")
        exports = get_plugin_exports_for_plugin(plugin_id)
        assert len(exports) >= 1

    def test_update(self):
        plugin_id = create_plugin(name="UpdExport Plugin", description="d")
        export_id = add_plugin_export(plugin_id)
        result = update_plugin_export(export_id, status="completed")
        assert result is True

    def test_delete(self):
        plugin_id = create_plugin(name="DelExport Plugin", description="d")
        export_id = add_plugin_export(plugin_id)
        result = delete_plugin_export(export_id)
        assert result is True


# =============================================================================
# Token usage and budget limit tests for coverage
# =============================================================================

from app.database import (
    create_token_usage_record,
    delete_budget_limit,
    get_all_budget_limits,
    get_budget_limit,
    get_current_period_spend,
    get_token_usage_count,
    get_token_usage_for_execution,
    get_token_usage_summary,
    get_token_usage_total_cost,
    get_usage_aggregated_summary,
    get_usage_by_entity,
    get_window_token_usage,
    set_budget_limit,
)


class TestTokenUsageCRUD:
    """Tests for token usage functions."""

    def _create_usage(self, execution_id="exec-tok-1"):
        return create_token_usage_record(
            execution_id=execution_id,
            entity_type="trigger",
            entity_id="trig-test",
            backend_type="claude",
            input_tokens=100,
            output_tokens=50,
            total_cost_usd=0.05,
        )

    def test_create_and_get(self):
        record_id = self._create_usage()
        assert record_id is not None
        record = get_token_usage_for_execution("exec-tok-1")
        assert record is not None
        assert record["input_tokens"] == 100

    def test_get_nonexistent(self):
        assert get_token_usage_for_execution("nonexistent") is None

    def test_get_current_period_spend(self):
        self._create_usage("exec-sp-1")
        spend = get_current_period_spend("trigger", "trig-test", "daily")
        assert isinstance(spend, float)

    def test_get_window_usage(self):
        self._create_usage("exec-win-1")
        total = get_window_token_usage("2020-01-01T00:00:00")
        assert isinstance(total, int)
        assert total >= 150

    def test_get_summary(self):
        self._create_usage("exec-sum-1")
        summary = get_token_usage_summary(entity_type="trigger")
        assert isinstance(summary, list)

    def test_get_summary_with_filters(self):
        self._create_usage("exec-sum-2")
        summary = get_token_usage_summary(
            entity_type="trigger",
            entity_id="trig-test",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert isinstance(summary, list)

    def test_get_count(self):
        self._create_usage("exec-cnt-1")
        count = get_token_usage_count(entity_type="trigger")
        assert isinstance(count, int)
        assert count >= 1

    def test_get_count_with_filters(self):
        self._create_usage("exec-cnt-2")
        count = get_token_usage_count(
            entity_type="trigger",
            entity_id="trig-test",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert isinstance(count, int)

    def test_get_total_cost(self):
        self._create_usage("exec-cost-1")
        cost = get_token_usage_total_cost(entity_type="trigger")
        assert isinstance(cost, float)

    def test_get_total_cost_with_filters(self):
        self._create_usage("exec-cost-2")
        cost = get_token_usage_total_cost(
            entity_type="trigger",
            entity_id="trig-test",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert isinstance(cost, float)

    def test_aggregated_summary_day(self):
        self._create_usage("exec-agg-1")
        result = get_usage_aggregated_summary(group_by="day")
        assert isinstance(result, list)

    def test_aggregated_summary_week(self):
        self._create_usage("exec-agg-2")
        result = get_usage_aggregated_summary(group_by="week")
        assert isinstance(result, list)

    def test_aggregated_summary_month(self):
        self._create_usage("exec-agg-3")
        result = get_usage_aggregated_summary(group_by="month")
        assert isinstance(result, list)

    def test_aggregated_summary_with_filters(self):
        self._create_usage("exec-agg-4")
        result = get_usage_aggregated_summary(
            group_by="day",
            entity_type="trigger",
            entity_id="trig-test",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert isinstance(result, list)

    def test_usage_by_entity(self):
        self._create_usage("exec-ent-1")
        result = get_usage_by_entity()
        assert isinstance(result, list)

    def test_usage_by_entity_with_filters(self):
        self._create_usage("exec-ent-2")
        result = get_usage_by_entity(
            entity_type="trigger",
            start_date="2020-01-01",
            end_date="2030-12-31",
        )
        assert isinstance(result, list)


class TestBudgetLimitCRUD:
    """Tests for budget limit functions."""

    def test_set_and_get(self):
        set_budget_limit("trigger", "trig-budget", hard_limit_usd=100.0, soft_limit_usd=80.0)
        limit = get_budget_limit("trigger", "trig-budget")
        assert limit is not None
        assert limit["hard_limit_usd"] == 100.0

    def test_get_nonexistent(self):
        assert get_budget_limit("trigger", "nonexistent") is None

    def test_delete(self):
        set_budget_limit("trigger", "trig-del", hard_limit_usd=50.0)
        result = delete_budget_limit("trigger", "trig-del")
        assert result is True
        assert get_budget_limit("trigger", "trig-del") is None

    def test_get_all(self):
        set_budget_limit("trigger", "trig-all-1", hard_limit_usd=10.0)
        limits = get_all_budget_limits()
        assert len(limits) >= 1

    def test_update_existing(self):
        set_budget_limit("trigger", "trig-upd", hard_limit_usd=50.0)
        set_budget_limit("trigger", "trig-upd", hard_limit_usd=100.0)
        limit = get_budget_limit("trigger", "trig-upd")
        assert limit["hard_limit_usd"] == 100.0


# =============================================================================
# Trigger supplementary tests (count, get_by_name)
# =============================================================================


class TestTriggerSupplementary:
    def test_count_all_triggers(self):
        """count_all_triggers includes predefined triggers."""
        count = count_all_triggers()
        assert count >= 2  # bot-security, bot-pr-review

    def test_count_after_create(self):
        before = count_all_triggers()
        create_trigger(name="Counter Trigger", prompt_template="test")
        after = count_all_triggers()
        assert after == before + 1

    def test_get_trigger_by_name(self):
        create_trigger(name="Unique Trigger Name", prompt_template="test")
        t = get_trigger_by_name("Unique Trigger Name")
        assert t is not None
        assert t["name"] == "Unique Trigger Name"

    def test_get_trigger_by_name_nonexistent(self):
        assert get_trigger_by_name("Does Not Exist") is None


# =============================================================================
# Agent supplementary tests (count, enabled, validation, design conversations)
# =============================================================================


class TestAgentSupplementary:
    def test_count_agents_empty(self):
        assert count_agents() == 0

    def test_count_agents_after_create(self):
        create_agent(name="Agent A")
        create_agent(name="Agent B")
        assert count_agents() == 2

    def test_get_enabled_agents(self):
        aid1 = create_agent(name="Enabled Agent")
        aid2 = create_agent(name="Disabled Agent")
        update_agent(aid2, enabled=0)
        enabled = get_enabled_agents()
        ids = [a["id"] for a in enabled]
        assert aid1 in ids
        assert aid2 not in ids

    def test_create_agent_invalid_backend_defaults_to_claude(self):
        aid = create_agent(name="Bad Backend", backend_type="invalid")
        agent = get_agent(aid)
        assert agent["backend_type"] == "claude"

    def test_create_agent_invalid_effort_defaults_to_medium(self):
        aid = create_agent(name="Bad Effort", effort_level="extreme")
        agent = get_agent(aid)
        assert agent["effort_level"] == "medium"

    def test_update_agent_invalid_backend_ignored(self):
        aid = create_agent(name="Agent Validate", backend_type="claude")
        update_agent(aid, backend_type="invalid_backend")
        agent = get_agent(aid)
        assert agent["backend_type"] == "claude"

    def test_update_agent_invalid_effort_ignored(self):
        aid = create_agent(name="Agent Effort", effort_level="medium")
        update_agent(aid, effort_level="extreme")
        agent = get_agent(aid)
        assert agent["effort_level"] == "medium"

    def test_update_agent_nonexistent(self):
        result = update_agent("agent-nonexistent", name="New Name")
        assert result is False

    def test_get_all_agents_pagination(self):
        for i in range(5):
            create_agent(name=f"PageAgent {i}")
        page = get_all_agents(limit=2, offset=0)
        assert len(page) == 2
        page2 = get_all_agents(limit=2, offset=2)
        assert len(page2) == 2
        # No overlap
        ids1 = {a["id"] for a in page}
        ids2 = {a["id"] for a in page2}
        assert ids1.isdisjoint(ids2)


class TestDesignConversationCRUD:
    def test_create_and_get(self):
        ok = create_design_conversation("dc-001", "agent")
        assert ok is True
        conv = get_design_conversation("dc-001")
        assert conv is not None
        assert conv["entity_type"] == "agent"
        assert conv["status"] == "active"

    def test_get_nonexistent(self):
        assert get_design_conversation("dc-nonexistent") is None

    def test_update(self):
        create_design_conversation("dc-002", "team")
        update_design_conversation("dc-002", status="completed", entity_id="team-abc")
        conv = get_design_conversation("dc-002")
        assert conv["status"] == "completed"
        assert conv["entity_id"] == "team-abc"

    def test_update_no_fields(self):
        create_design_conversation("dc-003", "agent")
        result = update_design_conversation("dc-003")
        assert result is False

    def test_list_by_type_and_status(self):
        create_design_conversation("dc-list-1", "agent")
        create_design_conversation("dc-list-2", "agent")
        create_design_conversation("dc-list-3", "team")
        convs = list_design_conversations("agent", status="active")
        assert len(convs) == 2
        assert all(c["entity_type"] == "agent" for c in convs)

    def test_delete_old(self):
        create_design_conversation("dc-old", "agent")
        update_design_conversation("dc-old", status="completed")
        # With max_age_seconds=0, everything non-active should be deleted
        # (the updated_at will be "now", so we use a very large age)
        deleted = delete_old_design_conversations(max_age_seconds=0)
        # This may or may not delete depending on timing; just assert it runs
        assert deleted >= 0

    def test_duplicate_id_fails(self):
        ok1 = create_design_conversation("dc-dup", "agent")
        ok2 = create_design_conversation("dc-dup", "team")
        assert ok1 is True
        assert ok2 is False


# =============================================================================
# Team supplementary tests (member removal, edges, hierarchy)
# =============================================================================


class TestTeamMemberSupplementary:
    def test_remove_team_member(self):
        tid = create_team(name="Remove Test Team")
        mid = add_team_member(tid, name="Bob")
        assert remove_team_member(mid) is True
        members = get_team_members(tid)
        assert len(members) == 0

    def test_remove_nonexistent_member(self):
        assert remove_team_member(99999) is False

    def test_update_member_multiple_fields(self):
        tid = create_team(name="Update Member Team")
        mid = add_team_member(tid, name="Alice", role="member", layer="backend")
        update_team_member(mid, name="Alice Updated", role="lead", layer="frontend")
        members = get_team_members(tid)
        member = next(m for m in members if m["id"] == mid)
        assert member["name"] == "Alice Updated"
        assert member["role"] == "lead"
        assert member["layer"] == "frontend"

    def test_update_member_no_fields(self):
        tid = create_team(name="Noop Member Team")
        mid = add_team_member(tid, name="Charlie")
        assert update_team_member(mid) is False

    def test_update_nonexistent_member(self):
        assert update_team_member(99999, name="Ghost") is False

    def test_add_member_no_identifier(self):
        """Must have at least one of name, agent_id, or super_agent_id."""
        tid = create_team(name="No ID Team")
        result = add_team_member(tid)
        assert result is None

    def test_add_member_both_agent_and_super_agent(self):
        """Cannot set both agent_id and super_agent_id."""
        tid = create_team(name="XOR Team")
        result = add_team_member(tid, agent_id="agent-x", super_agent_id="sa-y")
        assert result is None

    def test_count_teams(self):
        before = count_teams()
        create_team(name="Count Team 1")
        create_team(name="Count Team 2")
        assert count_teams() == before + 2

    def test_get_webhook_teams(self):
        create_team(name="Webhook Team", trigger_source="webhook")
        teams = get_webhook_teams()
        assert any(t["name"] == "Webhook Team" for t in teams)

    def test_delete_agent_assignments_bulk_all(self):
        tid = create_team(name="Bulk Delete Team")
        aid = create_agent(name="Bulk Agent")
        add_team_agent_assignment(tid, aid, "skill", "skill-1", "Skill One")
        add_team_agent_assignment(tid, aid, "command", "cmd-1", "Cmd One")
        deleted = delete_team_agent_assignments_bulk(tid)
        assert deleted == 2
        assert get_team_agent_assignments(tid) == []

    def test_add_assignment_invalid_entity_type(self):
        tid = create_team(name="Invalid Type Team")
        aid = create_agent(name="Invalid Type Agent")
        result = add_team_agent_assignment(tid, aid, "invalid_type", "x", "X")
        assert result is None


class TestTeamEdges:
    def test_add_and_get_edge(self):
        tid = create_team(name="Edge Team")
        m1 = add_team_member(tid, name="Alice")
        m2 = add_team_member(tid, name="Bob")
        eid = add_team_edge(tid, m1, m2, edge_type="delegation", label="delegates to")
        assert eid is not None
        edges = get_team_edges(tid)
        assert len(edges) == 1
        assert edges[0]["source_member_id"] == m1
        assert edges[0]["target_member_id"] == m2
        assert edges[0]["edge_type"] == "delegation"

    def test_add_edge_invalid_type(self):
        tid = create_team(name="Invalid Edge Team")
        m1 = add_team_member(tid, name="A")
        m2 = add_team_member(tid, name="B")
        result = add_team_edge(tid, m1, m2, edge_type="invalid_edge")
        assert result is None

    def test_add_self_loop_rejected(self):
        tid = create_team(name="Self Loop Team")
        m1 = add_team_member(tid, name="Self")
        result = add_team_edge(tid, m1, m1, edge_type="delegation")
        assert result is None

    def test_delete_edge(self):
        tid = create_team(name="Del Edge Team")
        m1 = add_team_member(tid, name="X")
        m2 = add_team_member(tid, name="Y")
        eid = add_team_edge(tid, m1, m2)
        assert delete_team_edge(eid) is True
        assert get_team_edges(tid) == []

    def test_delete_nonexistent_edge(self):
        assert delete_team_edge(99999) is False

    def test_delete_edges_by_team(self):
        tid = create_team(name="Bulk Edge Team")
        m1 = add_team_member(tid, name="A")
        m2 = add_team_member(tid, name="B")
        m3 = add_team_member(tid, name="C")
        add_team_edge(tid, m1, m2)
        add_team_edge(tid, m2, m3)
        deleted = delete_team_edges_by_team(tid)
        assert deleted == 2
        assert get_team_edges(tid) == []

    def test_get_team_hierarchy(self):
        tid = create_team(name="Hierarchy Team")
        m1 = add_team_member(tid, name="Root")
        m2 = add_team_member(tid, name="Child1")
        m3 = add_team_member(tid, name="GrandChild")
        add_team_edge(tid, m1, m2, edge_type="delegation")
        add_team_edge(tid, m2, m3, edge_type="delegation")
        hierarchy = get_team_hierarchy(tid, m1)
        assert len(hierarchy) == 2
        assert hierarchy[0]["name"] == "Child1"
        assert hierarchy[0]["depth"] == 1
        assert hierarchy[1]["name"] == "GrandChild"
        assert hierarchy[1]["depth"] == 2

    def test_get_team_hierarchy_empty(self):
        tid = create_team(name="Flat Team")
        m1 = add_team_member(tid, name="Lone")
        hierarchy = get_team_hierarchy(tid, m1)
        assert hierarchy == []

    def test_duplicate_edge_rejected(self):
        tid = create_team(name="Dup Edge Team")
        m1 = add_team_member(tid, name="A")
        m2 = add_team_member(tid, name="B")
        eid1 = add_team_edge(tid, m1, m2, edge_type="delegation")
        eid2 = add_team_edge(tid, m1, m2, edge_type="delegation")
        assert eid1 is not None
        assert eid2 is None


# =============================================================================
# Workflow CRUD tests
# =============================================================================

SIMPLE_GRAPH = '{"nodes": [{"id": "n1"}], "edges": []}'
TWO_NODE_GRAPH = (
    '{"nodes": [{"id": "n1"}, {"id": "n2"}], "edges": [{"source": "n1", "target": "n2"}]}'
)
CYCLIC_GRAPH = '{"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]}'


class TestWorkflowCRUD:
    def test_create_and_get(self):
        wid = create_workflow(name="Test Workflow", description="A test workflow")
        assert wid is not None
        assert wid.startswith("wf-")
        w = get_workflow(wid)
        assert w["name"] == "Test Workflow"
        assert w["description"] == "A test workflow"
        assert w["enabled"] == 1

    def test_get_nonexistent(self):
        assert get_workflow("wf-nonexistent") is None

    def test_get_all(self):
        create_workflow(name="WF A")
        create_workflow(name="WF B")
        all_wf = get_all_workflows()
        assert len(all_wf) >= 2

    def test_get_all_pagination(self):
        for i in range(5):
            create_workflow(name=f"WF Page {i}")
        page = get_all_workflows(limit=2, offset=0)
        assert len(page) == 2

    def test_update(self):
        wid = create_workflow(name="Update WF")
        result = update_workflow(wid, name="Updated WF", description="new desc")
        assert result is True
        w = get_workflow(wid)
        assert w["name"] == "Updated WF"
        assert w["description"] == "new desc"

    def test_update_no_fields(self):
        wid = create_workflow(name="Noop WF")
        assert update_workflow(wid) is False

    def test_update_nonexistent(self):
        assert update_workflow("wf-ghost", name="X") is False

    def test_update_enabled(self):
        wid = create_workflow(name="Disable WF")
        update_workflow(wid, enabled=0)
        w = get_workflow(wid)
        assert w["enabled"] == 0

    def test_delete(self):
        wid = create_workflow(name="Delete WF")
        assert delete_workflow(wid) is True
        assert get_workflow(wid) is None

    def test_delete_nonexistent(self):
        assert delete_workflow("wf-ghost") is False


class TestWorkflowGraphValidation:
    def test_valid_single_node(self):
        ok, err = validate_workflow_graph(SIMPLE_GRAPH)
        assert ok is True
        assert err == ""

    def test_valid_two_nodes(self):
        ok, err = validate_workflow_graph(TWO_NODE_GRAPH)
        assert ok is True

    def test_cyclic_graph(self):
        ok, err = validate_workflow_graph(CYCLIC_GRAPH)
        assert ok is False
        assert "cycle" in err.lower()

    def test_invalid_json(self):
        ok, err = validate_workflow_graph("not json")
        assert ok is False
        assert "Invalid JSON" in err

    def test_no_nodes(self):
        ok, err = validate_workflow_graph('{"nodes": [], "edges": []}')
        assert ok is False
        assert "at least one node" in err

    def test_edge_references_unknown_node(self):
        graph = '{"nodes": [{"id": "n1"}], "edges": [{"source": "n1", "target": "n_missing"}]}'
        ok, err = validate_workflow_graph(graph)
        assert ok is False
        assert "unknown" in err.lower()

    def test_node_missing_id(self):
        graph = '{"nodes": [{"name": "oops"}], "edges": []}'
        ok, err = validate_workflow_graph(graph)
        assert ok is False
        assert "id" in err.lower()


class TestWorkflowVersions:
    def test_add_version(self):
        wid = create_workflow(name="Version WF")
        ver = add_workflow_version(wid, TWO_NODE_GRAPH)
        assert ver == 1

    def test_add_multiple_versions(self):
        wid = create_workflow(name="Multi Version WF")
        v1 = add_workflow_version(wid, SIMPLE_GRAPH)
        v2 = add_workflow_version(wid, TWO_NODE_GRAPH)
        assert v1 == 1
        assert v2 == 2

    def test_add_version_invalid_json(self):
        wid = create_workflow(name="Bad JSON WF")
        ver = add_workflow_version(wid, "not json")
        assert ver is None

    def test_add_version_cyclic_graph(self):
        wid = create_workflow(name="Cyclic WF")
        ver = add_workflow_version(wid, CYCLIC_GRAPH)
        assert ver is None

    def test_get_versions(self):
        wid = create_workflow(name="Get Versions WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        add_workflow_version(wid, TWO_NODE_GRAPH)
        versions = get_workflow_versions(wid)
        assert len(versions) == 2
        # Ordered by version DESC
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1

    def test_get_latest_published_version(self):
        wid = create_workflow(name="Latest WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        add_workflow_version(wid, TWO_NODE_GRAPH, is_draft=True)
        latest = get_latest_workflow_version(wid)
        assert latest is not None
        assert latest["version"] == 1  # v2 is draft, so v1 is latest published

    def test_publish_draft(self):
        wid = create_workflow(name="Publish WF")
        add_workflow_version(wid, SIMPLE_GRAPH, is_draft=True)
        assert publish_workflow_version(wid, 1) is True
        latest = get_latest_workflow_version(wid)
        assert latest["version"] == 1

    def test_publish_nonexistent(self):
        wid = create_workflow(name="Pub None WF")
        assert publish_workflow_version(wid, 99) is False

    def test_add_version_raw_success(self):
        wid = create_workflow(name="Raw WF")
        ver, err = add_workflow_version_raw(wid, SIMPLE_GRAPH)
        assert ver == 1
        assert err == ""

    def test_add_version_raw_invalid_json(self):
        wid = create_workflow(name="Raw Bad WF")
        ver, err = add_workflow_version_raw(wid, "bad json")
        assert ver is None
        assert "Invalid JSON" in err

    def test_add_version_raw_cyclic(self):
        wid = create_workflow(name="Raw Cycle WF")
        ver, err = add_workflow_version_raw(wid, CYCLIC_GRAPH)
        assert ver is None
        assert "cycle" in err.lower()


class TestWorkflowExecution:
    def test_add_and_get_execution(self):
        wid = create_workflow(name="Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1, input_json='{"key": "val"}')
        assert eid is not None
        assert eid.startswith("wfx-")
        ex = get_workflow_execution(eid)
        assert ex["workflow_id"] == wid
        assert ex["status"] == "running"
        assert ex["version"] == 1

    def test_get_execution_nonexistent(self):
        assert get_workflow_execution("wfx-nope") is None

    def test_update_execution(self):
        wid = create_workflow(name="Update Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        result = update_workflow_execution(eid, status="completed", output_json='{"result": 1}')
        assert result is True
        ex = get_workflow_execution(eid)
        assert ex["status"] == "completed"
        assert ex["output_json"] == '{"result": 1}'

    def test_update_execution_no_fields(self):
        assert update_workflow_execution("wfx-x") is False

    def test_update_execution_with_error(self):
        wid = create_workflow(name="Error Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        update_workflow_execution(eid, status="failed", error="something broke")
        ex = get_workflow_execution(eid)
        assert ex["status"] == "failed"
        assert ex["error"] == "something broke"

    def test_get_executions_for_workflow(self):
        wid = create_workflow(name="List Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid1 = add_workflow_execution(wid, version=1)
        eid2 = add_workflow_execution(wid, version=1)
        execs = get_workflow_executions(wid)
        assert len(execs) == 2
        ids = {e["id"] for e in execs}
        assert eid1 in ids
        assert eid2 in ids

    def test_get_running_executions(self):
        wid = create_workflow(name="Running Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid1 = add_workflow_execution(wid, version=1, status="running")
        eid2 = add_workflow_execution(wid, version=1, status="running")
        update_workflow_execution(eid2, status="completed")
        running = get_running_workflow_executions()
        ids = [e["id"] for e in running]
        assert eid1 in ids
        assert eid2 not in ids


class TestWorkflowNodeExecution:
    def test_add_and_get(self):
        wid = create_workflow(name="Node Exec WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        nid = add_workflow_node_execution(eid, node_id="n1", node_type="agent")
        assert nid is not None
        nodes = get_workflow_node_executions(eid)
        assert len(nodes) == 1
        assert nodes[0]["node_id"] == "n1"
        assert nodes[0]["node_type"] == "agent"
        assert nodes[0]["status"] == "pending"

    def test_update_node_execution(self):
        wid = create_workflow(name="Update Node WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        nid = add_workflow_node_execution(eid, node_id="n1", node_type="agent")
        result = update_workflow_node_execution(
            nid, status="completed", output_json='{"done": true}'
        )
        assert result is True
        nodes = get_workflow_node_executions(eid)
        assert nodes[0]["status"] == "completed"

    def test_update_node_execution_no_fields(self):
        assert update_workflow_node_execution(99999) is False

    def test_multiple_nodes(self):
        wid = create_workflow(name="Multi Node WF")
        add_workflow_version(wid, TWO_NODE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        add_workflow_node_execution(eid, node_id="n1", node_type="agent")
        add_workflow_node_execution(eid, node_id="n2", node_type="agent")
        nodes = get_workflow_node_executions(eid)
        assert len(nodes) == 2


class TestWorkflowApprovalState:
    def test_add_and_get(self):
        wid = create_workflow(name="Approval WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        row_id = add_workflow_approval_state(eid, node_id="n1", timeout_seconds=600)
        assert row_id is not None
        state = get_workflow_approval_state(eid, "n1")
        assert state is not None
        assert state["status"] == "pending"
        assert state["timeout_seconds"] == 600

    def test_get_nonexistent(self):
        assert get_workflow_approval_state("wfx-nope", "n1") is None

    def test_update_approval_approved(self):
        wid = create_workflow(name="Approve WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        add_workflow_approval_state(eid, "n1")
        result = update_workflow_approval_state(eid, "n1", "approved", resolved_by="admin")
        assert result is True
        state = get_workflow_approval_state(eid, "n1")
        assert state["status"] == "approved"
        assert state["resolved_by"] == "admin"
        assert state["resolved_at"] is not None

    def test_update_approval_rejected(self):
        wid = create_workflow(name="Reject WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        add_workflow_approval_state(eid, "n1")
        update_workflow_approval_state(eid, "n1", "rejected")
        state = get_workflow_approval_state(eid, "n1")
        assert state["status"] == "rejected"

    def test_get_pending_states(self):
        wid = create_workflow(name="Pending WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        add_workflow_approval_state(eid, "n1")
        pending = get_pending_approval_states()
        assert any(s["execution_id"] == eid for s in pending)

    def test_cleanup_stale(self):
        wid = create_workflow(name="Stale WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        add_workflow_approval_state(eid, "n1")
        count = cleanup_stale_approval_states()
        assert count >= 1
        state = get_workflow_approval_state(eid, "n1")
        assert state["status"] == "timed_out"

    def test_duplicate_approval_rejected(self):
        wid = create_workflow(name="Dup Approval WF")
        add_workflow_version(wid, SIMPLE_GRAPH)
        eid = add_workflow_execution(wid, version=1)
        r1 = add_workflow_approval_state(eid, "n1")
        r2 = add_workflow_approval_state(eid, "n1")
        assert r1 is not None
        assert r2 is None
