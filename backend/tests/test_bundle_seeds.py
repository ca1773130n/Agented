"""Tests for bundled teams and super agents seeding."""

import pytest
from app.db import get_connection, init_db
from app.db.bundle_seeds import (
    BUNDLED_DOCUMENTS,
    BUNDLED_SUPER_AGENTS,
    BUNDLED_TEAMS,
    seed_bundled_teams_and_agents,
)


class TestBundleSeeds:
    """Test bundled team and super agent seeding."""

    def test_seed_creates_teams(self, client):
        """All 5 bundled teams are created."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, source FROM teams WHERE source = 'bundle'"
            ).fetchall()
        assert len(rows) == 5
        names = {r["name"] for r in rows}
        assert "Matrix Command" in names
        assert "Matrix Development" in names
        assert "Matrix Research" in names
        assert "Matrix Operations" in names
        assert "Matrix QA" in names

    def test_seed_creates_super_agents(self, client):
        """All 17 bundled super agents are created."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, source FROM super_agents WHERE source = 'bundle'"
            ).fetchall()
        assert len(rows) == 17

    def test_seed_creates_identity_documents(self, client):
        """Each super agent gets SOUL + IDENTITY documents."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT super_agent_id, doc_type FROM super_agent_documents "
                "WHERE super_agent_id IN (SELECT id FROM super_agents WHERE source = 'bundle')"
            ).fetchall()
        # 17 agents × 2 docs each = 34
        assert len(rows) == 34

    def test_seed_creates_team_members(self, client):
        """Team members link super agents to teams with correct roles."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            leaders = conn.execute(
                "SELECT name, role FROM team_members WHERE role = 'leader' "
                "AND super_agent_id IS NOT NULL"
            ).fetchall()
        # 5 teams × 1 leader each
        assert len(leaders) == 5
        leader_names = {r["name"] for r in leaders}
        assert "Morpheus" in leader_names
        assert "Trinity" in leader_names

    def test_seed_is_idempotent(self, client):
        """Running seed twice doesn't create duplicates."""
        seed_bundled_teams_and_agents()
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            teams = conn.execute(
                "SELECT COUNT(*) as c FROM teams WHERE source = 'bundle'"
            ).fetchone()
            agents = conn.execute(
                "SELECT COUNT(*) as c FROM super_agents WHERE source = 'bundle'"
            ).fetchone()
        assert teams["c"] == 5
        assert agents["c"] == 17

    def test_bundled_data_constants(self):
        """Verify constants have expected counts."""
        assert len(BUNDLED_TEAMS) == 5
        assert len(BUNDLED_SUPER_AGENTS) == 17
        assert len(BUNDLED_DOCUMENTS) == 34
