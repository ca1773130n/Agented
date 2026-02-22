"""Tests for project team topology edge CRUD and routes."""

import json

import pytest

from app.db.projects import (
    add_project,
    add_project_team_edge,
    delete_project_team_edge,
    delete_project_team_edges_by_project,
    get_project,
    get_project_team_edges,
    update_project_team_topology_config,
)
from app.db.teams import add_team


@pytest.fixture
def sample_project(isolated_db):
    """Create a sample project."""
    pid = add_project(name="Test Project", local_path="/tmp/test")
    assert pid is not None
    return pid


@pytest.fixture
def sample_teams(isolated_db):
    """Create two sample teams."""
    t1 = add_team(name="Frontend Team")
    t2 = add_team(name="Backend Team")
    assert t1 is not None
    assert t2 is not None
    return t1, t2


class TestProjectTeamEdgeCRUD:
    def test_add_edge(self, sample_project, sample_teams):
        t1, t2 = sample_teams
        edge_id = add_project_team_edge(sample_project, t1, t2)
        assert edge_id is not None
        assert edge_id > 0

    def test_get_edges(self, sample_project, sample_teams):
        t1, t2 = sample_teams
        add_project_team_edge(sample_project, t1, t2, label="depends on")
        edges = get_project_team_edges(sample_project)
        assert len(edges) == 1
        assert edges[0]["source_team_id"] == t1
        assert edges[0]["target_team_id"] == t2
        assert edges[0]["label"] == "depends on"

    def test_delete_edge(self, sample_project, sample_teams):
        t1, t2 = sample_teams
        edge_id = add_project_team_edge(sample_project, t1, t2)
        assert delete_project_team_edge(edge_id)
        assert len(get_project_team_edges(sample_project)) == 0

    def test_delete_edges_by_project(self, sample_project, sample_teams):
        t1, t2 = sample_teams
        add_project_team_edge(sample_project, t1, t2)
        count = delete_project_team_edges_by_project(sample_project)
        assert count == 1

    def test_duplicate_edge_rejected(self, sample_project, sample_teams):
        t1, t2 = sample_teams
        assert add_project_team_edge(sample_project, t1, t2) is not None
        assert add_project_team_edge(sample_project, t1, t2) is None

    def test_update_topology_config(self, sample_project):
        config = json.dumps({"positions": {"team-a": {"x": 100, "y": 200}}})
        assert update_project_team_topology_config(sample_project, config)
        project = get_project(sample_project)
        assert project["team_topology_config"] == config


class TestProjectTeamEdgeRoutes:
    def test_list_edges(self, client, sample_project, sample_teams):
        t1, t2 = sample_teams
        add_project_team_edge(sample_project, t1, t2)
        resp = client.get(f"/admin/projects/{sample_project}/team-edges")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["edges"]) == 1

    def test_create_edge(self, client, sample_project, sample_teams):
        t1, t2 = sample_teams
        resp = client.post(
            f"/admin/projects/{sample_project}/team-edges",
            json={"source_team_id": t1, "target_team_id": t2},
        )
        assert resp.status_code == 201
        assert "edge_id" in resp.get_json()

    def test_delete_edge(self, client, sample_project, sample_teams):
        t1, t2 = sample_teams
        edge_id = add_project_team_edge(sample_project, t1, t2)
        resp = client.delete(f"/admin/projects/{sample_project}/team-edges/{edge_id}")
        assert resp.status_code == 200

    def test_update_topology_config(self, client, sample_project):
        resp = client.put(
            f"/admin/projects/{sample_project}/team-topology",
            json={"team_topology_config": {"positions": {}}},
        )
        assert resp.status_code == 200
