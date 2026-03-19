"""Tests for project-scoped SA and team instance CRUD and migration."""

from app.db.connection import get_connection
from app.db.ids import PSA_ID_PREFIX, PTI_ID_PREFIX, generate_psa_id, generate_pti_id
from app.db.project_sa_instances import (
    create_project_sa_instance,
    delete_project_sa_instance,
    get_project_sa_instance,
    get_project_sa_instances_for_project,
    update_project_sa_instance,
)
from app.db.project_team_instances import (
    create_project_team_instance,
    delete_project_team_instance,
    get_project_team_instance,
    get_project_team_instances_for_project,
)
from app.db.projects import create_project
from app.db.super_agents import (
    add_super_agent_session,
    create_super_agent,
    get_sessions_for_instance,
    get_super_agent_session,
)
from app.db.teams import create_team

# =============================================================================
# ID generation tests
# =============================================================================


class TestIdGeneration:
    def test_psa_id_prefix(self):
        """generate_psa_id() returns ID with psa- prefix."""
        psa_id = generate_psa_id()
        assert psa_id.startswith(PSA_ID_PREFIX)
        assert len(psa_id) == len(PSA_ID_PREFIX) + 6

    def test_pti_id_prefix(self):
        """generate_pti_id() returns ID with pti- prefix."""
        pti_id = generate_pti_id()
        assert pti_id.startswith(PTI_ID_PREFIX)
        assert len(pti_id) == len(PTI_ID_PREFIX) + 6

    def test_psa_ids_unique(self):
        """Generated PSA IDs should be unique."""
        ids = {generate_psa_id() for _ in range(100)}
        assert len(ids) == 100

    def test_pti_ids_unique(self):
        """Generated PTI IDs should be unique."""
        ids = {generate_pti_id() for _ in range(100)}
        assert len(ids) == 100


# =============================================================================
# Project SA Instance CRUD tests
# =============================================================================


def _create_sa_and_project(isolated_db):
    """Helper to create a super agent and project, returns (sa_id, proj_id)."""
    sa_id = create_super_agent(name="Test SA", backend_type="claude")
    proj_id = create_project(name="Test Project")
    return sa_id, proj_id


class TestCreateProjectSaInstance:
    def test_create_returns_psa_id(self, isolated_db):
        """create_project_sa_instance returns a psa- prefixed ID."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        assert psa_id is not None
        assert psa_id.startswith("psa-")

    def test_create_with_all_fields(self, isolated_db):
        """create_project_sa_instance stores all optional fields."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(
            proj_id,
            sa_id,
            worktree_path="/tmp/worktree",
            default_chat_mode="work",
            config_overrides='{"key": "value"}',
        )
        assert psa_id is not None
        inst = get_project_sa_instance(psa_id)
        assert inst["project_id"] == proj_id
        assert inst["template_sa_id"] == sa_id
        assert inst["worktree_path"] == "/tmp/worktree"
        assert inst["default_chat_mode"] == "work"
        assert inst["config_overrides"] == '{"key": "value"}'

    def test_create_unique_constraint(self, isolated_db):
        """Creating duplicate (project_id, template_sa_id) returns None."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id1 = create_project_sa_instance(proj_id, sa_id)
        psa_id2 = create_project_sa_instance(proj_id, sa_id)
        assert psa_id1 is not None
        assert psa_id2 is None

    def test_create_different_projects_same_sa(self, isolated_db):
        """Same SA can be instanced in different projects."""
        sa_id = create_super_agent(name="Shared SA", backend_type="claude")
        proj_id1 = create_project(name="Project A")
        proj_id2 = create_project(name="Project B")
        psa_id1 = create_project_sa_instance(proj_id1, sa_id)
        psa_id2 = create_project_sa_instance(proj_id2, sa_id)
        assert psa_id1 is not None
        assert psa_id2 is not None
        assert psa_id1 != psa_id2


class TestGetProjectSaInstance:
    def test_get_existing(self, isolated_db):
        """get_project_sa_instance returns dict with all fields."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        inst = get_project_sa_instance(psa_id)
        assert inst is not None
        assert inst["id"] == psa_id
        assert inst["project_id"] == proj_id
        assert inst["template_sa_id"] == sa_id
        assert inst["default_chat_mode"] == "management"
        assert "created_at" in inst
        assert "updated_at" in inst

    def test_get_nonexistent(self, isolated_db):
        """get_project_sa_instance returns None for unknown ID."""
        inst = get_project_sa_instance("psa-nonexist")
        assert inst is None


class TestGetProjectSaInstancesForProject:
    def test_list_instances(self, isolated_db):
        """get_project_sa_instances_for_project returns all instances."""
        proj_id = create_project(name="Multi SA Project")
        sa_id1 = create_super_agent(name="SA 1", backend_type="claude")
        sa_id2 = create_super_agent(name="SA 2", backend_type="claude")
        create_project_sa_instance(proj_id, sa_id1)
        create_project_sa_instance(proj_id, sa_id2)
        instances = get_project_sa_instances_for_project(proj_id)
        assert len(instances) == 2

    def test_list_empty_project(self, isolated_db):
        """get_project_sa_instances_for_project returns [] for project with no instances."""
        proj_id = create_project(name="Empty Project")
        instances = get_project_sa_instances_for_project(proj_id)
        assert instances == []


class TestUpdateProjectSaInstance:
    def test_update_worktree_path(self, isolated_db):
        """update_project_sa_instance updates worktree_path."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        result = update_project_sa_instance(psa_id, worktree_path="/new/path")
        assert result is True
        inst = get_project_sa_instance(psa_id)
        assert inst["worktree_path"] == "/new/path"

    def test_update_chat_mode(self, isolated_db):
        """update_project_sa_instance updates default_chat_mode."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        result = update_project_sa_instance(psa_id, default_chat_mode="work")
        assert result is True
        inst = get_project_sa_instance(psa_id)
        assert inst["default_chat_mode"] == "work"

    def test_update_no_fields_returns_false(self, isolated_db):
        """update_project_sa_instance returns False when no fields given."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        result = update_project_sa_instance(psa_id)
        assert result is False

    def test_update_nonexistent_returns_false(self, isolated_db):
        """update_project_sa_instance returns False for unknown ID."""
        result = update_project_sa_instance("psa-nonexist", worktree_path="/x")
        assert result is False


class TestDeleteProjectSaInstance:
    def test_delete_existing(self, isolated_db):
        """delete_project_sa_instance removes the instance."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        result = delete_project_sa_instance(psa_id)
        assert result is True
        assert get_project_sa_instance(psa_id) is None

    def test_delete_nonexistent(self, isolated_db):
        """delete_project_sa_instance returns False for unknown ID."""
        result = delete_project_sa_instance("psa-nonexist")
        assert result is False


# =============================================================================
# Project Team Instance CRUD tests
# =============================================================================


class TestCreateProjectTeamInstance:
    def test_create_returns_pti_id(self, isolated_db):
        """create_project_team_instance returns a pti- prefixed ID."""
        proj_id = create_project(name="Team Project")
        team_id = create_team(name="Test Team")
        pti_id = create_project_team_instance(proj_id, team_id)
        assert pti_id is not None
        assert pti_id.startswith("pti-")

    def test_create_with_config_overrides(self, isolated_db):
        """create_project_team_instance stores config_overrides."""
        proj_id = create_project(name="Config Project")
        team_id = create_team(name="Config Team")
        pti_id = create_project_team_instance(
            proj_id, team_id, config_overrides='{"topology": "parallel"}'
        )
        inst = get_project_team_instance(pti_id)
        assert inst["config_overrides"] == '{"topology": "parallel"}'

    def test_create_unique_constraint(self, isolated_db):
        """Creating duplicate (project_id, template_team_id) returns None."""
        proj_id = create_project(name="Dup Project")
        team_id = create_team(name="Dup Team")
        pti_id1 = create_project_team_instance(proj_id, team_id)
        pti_id2 = create_project_team_instance(proj_id, team_id)
        assert pti_id1 is not None
        assert pti_id2 is None


class TestGetProjectTeamInstance:
    def test_get_existing(self, isolated_db):
        """get_project_team_instance returns dict with all fields."""
        proj_id = create_project(name="Get Project")
        team_id = create_team(name="Get Team")
        pti_id = create_project_team_instance(proj_id, team_id)
        inst = get_project_team_instance(pti_id)
        assert inst is not None
        assert inst["id"] == pti_id
        assert inst["project_id"] == proj_id
        assert inst["template_team_id"] == team_id
        assert "created_at" in inst
        assert "updated_at" in inst

    def test_get_nonexistent(self, isolated_db):
        """get_project_team_instance returns None for unknown ID."""
        inst = get_project_team_instance("pti-nonexist")
        assert inst is None


class TestGetProjectTeamInstancesForProject:
    def test_list_instances(self, isolated_db):
        """get_project_team_instances_for_project returns all instances."""
        proj_id = create_project(name="Multi Team Project")
        team_id1 = create_team(name="Team A")
        team_id2 = create_team(name="Team B")
        create_project_team_instance(proj_id, team_id1)
        create_project_team_instance(proj_id, team_id2)
        instances = get_project_team_instances_for_project(proj_id)
        assert len(instances) == 2

    def test_list_empty(self, isolated_db):
        """get_project_team_instances_for_project returns [] for empty project."""
        proj_id = create_project(name="Empty Team Project")
        instances = get_project_team_instances_for_project(proj_id)
        assert instances == []


class TestDeleteProjectTeamInstance:
    def test_delete_existing(self, isolated_db):
        """delete_project_team_instance removes the instance."""
        proj_id = create_project(name="Del Project")
        team_id = create_team(name="Del Team")
        pti_id = create_project_team_instance(proj_id, team_id)
        result = delete_project_team_instance(pti_id)
        assert result is True
        assert get_project_team_instance(pti_id) is None

    def test_delete_nonexistent(self, isolated_db):
        """delete_project_team_instance returns False for unknown ID."""
        result = delete_project_team_instance("pti-nonexist")
        assert result is False


# =============================================================================
# Session instance_id support tests
# =============================================================================


class TestSessionInstanceId:
    def test_create_session_with_instance_id(self, isolated_db):
        """add_super_agent_session with instance_id stores the reference."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        sess_id = add_super_agent_session(sa_id, instance_id=psa_id)
        assert sess_id is not None
        session = get_super_agent_session(sess_id)
        assert session["instance_id"] == psa_id

    def test_create_session_without_instance_id(self, isolated_db):
        """add_super_agent_session without instance_id stores NULL."""
        sa_id = create_super_agent(name="No Instance SA", backend_type="claude")
        sess_id = add_super_agent_session(sa_id)
        assert sess_id is not None
        session = get_super_agent_session(sess_id)
        assert session["instance_id"] is None

    def test_get_sessions_for_instance(self, isolated_db):
        """get_sessions_for_instance returns sessions linked to the instance."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        sess_id1 = add_super_agent_session(sa_id, instance_id=psa_id)
        sess_id2 = add_super_agent_session(sa_id, instance_id=psa_id)
        # Session without instance
        add_super_agent_session(sa_id)

        sessions = get_sessions_for_instance(psa_id)
        assert len(sessions) == 2
        session_ids = {s["id"] for s in sessions}
        assert sess_id1 in session_ids
        assert sess_id2 in session_ids

    def test_get_sessions_for_instance_empty(self, isolated_db):
        """get_sessions_for_instance returns [] when no sessions linked."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        sessions = get_sessions_for_instance(psa_id)
        assert sessions == []

    def test_instance_delete_sets_null(self, isolated_db):
        """Deleting a project SA instance sets session.instance_id to NULL."""
        sa_id, proj_id = _create_sa_and_project(isolated_db)
        psa_id = create_project_sa_instance(proj_id, sa_id)
        sess_id = add_super_agent_session(sa_id, instance_id=psa_id)
        delete_project_sa_instance(psa_id)
        session = get_super_agent_session(sess_id)
        assert session["instance_id"] is None


# =============================================================================
# Cascade delete tests
# =============================================================================


class TestCascadeDeletes:
    def test_project_delete_cascades_sa_instances(self, isolated_db):
        """Deleting a project cascade-deletes its SA instances."""
        from app.db.projects import delete_project

        sa_id = create_super_agent(name="Cascade SA", backend_type="claude")
        proj_id = create_project(name="Cascade Project")
        psa_id = create_project_sa_instance(proj_id, sa_id)
        assert get_project_sa_instance(psa_id) is not None
        delete_project(proj_id)
        assert get_project_sa_instance(psa_id) is None

    def test_project_delete_cascades_team_instances(self, isolated_db):
        """Deleting a project cascade-deletes its team instances."""
        from app.db.projects import delete_project

        team_id = create_team(name="Cascade Team")
        proj_id = create_project(name="Cascade Team Project")
        pti_id = create_project_team_instance(proj_id, team_id)
        assert get_project_team_instance(pti_id) is not None
        delete_project(proj_id)
        assert get_project_team_instance(pti_id) is None


# =============================================================================
# Schema tests (verify tables exist in fresh DB)
# =============================================================================


class TestSchema:
    def test_project_sa_instances_table_exists(self, isolated_db):
        """project_sa_instances table exists in a fresh database."""
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_sa_instances'"
            )
            assert cursor.fetchone() is not None

    def test_project_team_instances_table_exists(self, isolated_db):
        """project_team_instances table exists in a fresh database."""
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_team_instances'"
            )
            assert cursor.fetchone() is not None

    def test_super_agent_sessions_has_instance_id(self, isolated_db):
        """super_agent_sessions table has instance_id column."""
        with get_connection() as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(super_agent_sessions)").fetchall()
            }
            assert "instance_id" in columns

    def test_psa_indexes_exist(self, isolated_db):
        """project_sa_instances indexes exist."""
        with get_connection() as conn:
            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='project_sa_instances'"
                ).fetchall()
            }
            assert "idx_psa_project" in indexes
            assert "idx_psa_template" in indexes

    def test_pti_indexes_exist(self, isolated_db):
        """project_team_instances indexes exist."""
        with get_connection() as conn:
            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='project_team_instances'"
                ).fetchall()
            }
            assert "idx_pti_project" in indexes

    def test_sas_instance_index_exists(self, isolated_db):
        """super_agent_sessions instance_id index exists."""
        with get_connection() as conn:
            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='super_agent_sessions'"
                ).fetchall()
            }
            assert "idx_sas_instance" in indexes
