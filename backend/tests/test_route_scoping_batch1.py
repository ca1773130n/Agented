"""Wave 46: end-to-end scoping for /admin/projects, /admin/teams, /admin/agents."""

from app.db.connection import get_connection
from app.db.rbac import create_user_role
from app.db.users import create_user


def _two_users_with_keys(isolated_db):
    alice = create_user("alice@example.com", "Alice")
    bob = create_user("bob@example.com", "Bob")
    create_user_role("alice-key", "Alice", "admin", user_id=alice)
    create_user_role("bob-key", "Bob", "admin", user_id=bob)
    return alice, bob


def _seed_team(team_id: str, name: str, user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teams (id, name, user_id) VALUES (?, ?, ?)",
            (team_id, name, user_id),
        )
        conn.commit()


def _seed_project(project_id: str, name: str, user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, user_id) VALUES (?, ?, ?)",
            (project_id, name, user_id),
        )
        conn.commit()


def _seed_agent(agent_id: str, name: str, user_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, user_id) VALUES (?, ?, ?)",
            (agent_id, name, user_id),
        )
        conn.commit()


class TestProjectsScoping:
    def test_user_sees_only_own_projects(self, client, isolated_db):
        alice, bob = _two_users_with_keys(isolated_db)
        _seed_project("proj-aaaaaa", "Alice Proj", alice)
        _seed_project("proj-bbbbbb", "Bob Proj", bob)
        resp = client.get("/admin/projects/", headers={"X-API-Key": "alice-key"})
        names = {p["name"] for p in resp.get_json()["projects"]}
        assert names == {"Alice Proj"}


class TestTeamsScoping:
    def test_user_sees_only_own_teams(self, client, isolated_db):
        alice, bob = _two_users_with_keys(isolated_db)
        _seed_team("team-aaaaaa", "Alice Team", alice)
        _seed_team("team-bbbbbb", "Bob Team", bob)
        resp = client.get("/admin/teams/", headers={"X-API-Key": "alice-key"})
        names = {t["name"] for t in resp.get_json()["teams"]}
        assert names == {"Alice Team"}


class TestAgentsScoping:
    def test_user_sees_only_own_agents(self, client, isolated_db):
        alice, bob = _two_users_with_keys(isolated_db)
        _seed_agent("agent-aaaaaa", "Alice Agent", alice)
        _seed_agent("agent-bbbbbb", "Bob Agent", bob)
        resp = client.get("/admin/agents/", headers={"X-API-Key": "alice-key"})
        names = {a["name"] for a in resp.get_json()["agents"]}
        assert names == {"Alice Agent"}
