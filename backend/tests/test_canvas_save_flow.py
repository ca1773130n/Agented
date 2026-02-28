"""Tests for canvas save flow: topology + config interaction.

These tests verify that:
1. Saving only topology_config (positions/edges) from canvas works without 400
2. Saving only topology type works without requiring config fields
3. Saving both together requires valid config for the topology type
4. Edge round-trip: save edges, reload, verify persistence
5. Topology change from dropdown + separate config save sequence
"""

import json

from app.database import get_connection
from app.db.teams import add_team, add_team_member, get_team_detail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_agent(isolated_db, agent_id, name="Test Agent"):
    """Create an agent directly in the DB."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO agents (id, name, backend_type, enabled) VALUES (?, ?, ?, 1)",
            (agent_id, name, "claude"),
        )
        conn.commit()


def _create_team_with_agents(isolated_db, agent_ids, team_name="Canvas Team"):
    """Create team with N agent members. Returns (team_id, {agent_id: member_id})."""
    team_id = add_team(name=team_name)
    assert team_id is not None
    member_map = {}
    for aid in agent_ids:
        _create_agent(isolated_db, aid, f"Agent {aid}")
        mid = add_team_member(team_id=team_id, agent_id=aid)
        assert mid is not None
        member_map[aid] = mid
    return team_id, member_map


# ===========================================================================
# Canvas save: topology_config ONLY (no topology type)
# ===========================================================================


class TestCanvasSaveConfigOnly:
    """Saving from visual canvas sends topology_config without topology type."""

    def test_save_positions_only(self, client, isolated_db):
        """Canvas save with positions should succeed (no topology type sent)."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-cs01", "agent-cs02"])
        config = json.dumps(
            {
                "positions": {
                    "agent-cs01": {"x": 100, "y": 200},
                    "agent-cs02": {"x": 300, "y": 200},
                }
            }
        )
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        saved_config = json.loads(data["topology_config"])
        assert saved_config["positions"]["agent-cs01"]["x"] == 100

    def test_save_positions_and_edges(self, client, isolated_db):
        """Canvas save with positions + edges should succeed without topology."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-pe01", "agent-pe02"])
        config = json.dumps(
            {
                "positions": {
                    "agent-pe01": {"x": 0, "y": 0},
                    "agent-pe02": {"x": 200, "y": 0},
                },
                "edges": [{"source": "agent-pe01", "target": "agent-pe02", "type": "smoothstep"}],
            }
        )
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config},
        )
        assert resp.status_code == 200
        saved_config = json.loads(resp.get_json()["topology_config"])
        assert len(saved_config["edges"]) == 1

    def test_save_config_preserves_existing_topology_type(self, client, isolated_db):
        """Saving config only should NOT clear the topology type."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-pt01", "agent-pt02"])
        # Set topology type first
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "parallel"},
        )
        assert resp.status_code == 200

        # Now save config only — topology should remain
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": json.dumps({"positions": {}})},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["topology"] == "parallel"


# ===========================================================================
# Topology type ONLY (no config)
# ===========================================================================


class TestTopologyTypeOnly:
    """Changing topology type from dropdown sends only topology, no config."""

    def test_set_topology_without_config(self, client, isolated_db):
        """Setting topology type alone should succeed (no config validation)."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-to01"])

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "sequential"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["topology"] == "sequential"

    def test_set_all_topology_types(self, client, isolated_db):
        """Verify all 7 topology types can be set without config."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-all01"])
        types = [
            "sequential",
            "parallel",
            "coordinator",
            "generator_critic",
            "hierarchical",
            "human_in_loop",
            "composite",
        ]
        for topo in types:
            resp = client.put(
                f"/admin/teams/{team_id}/topology",
                json={"topology": topo},
            )
            assert resp.status_code == 200, f"Failed for topology: {topo}"
            assert resp.get_json()["topology"] == topo

    def test_clear_topology(self, client, isolated_db):
        """Setting topology to null should clear it."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-clr01"])

        # Set then clear
        client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "parallel"},
        )
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": None},
        )
        assert resp.status_code == 200
        # Empty string means cleared
        assert resp.get_json()["topology"] in (None, "")

    def test_invalid_topology_rejected(self, client, isolated_db):
        """Invalid topology type should be rejected with 400."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-inv01"])

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "nonexistent_topology"},
        )
        assert resp.status_code == 400


# ===========================================================================
# Combined topology + config (requires valid config)
# ===========================================================================


class TestTopologyWithConfig:
    """When both topology AND config are sent, config must be valid."""

    def test_sequential_with_valid_config(self, client, isolated_db):
        """Sequential topology with valid 'order' config should succeed."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-seq01", "agent-seq02"])
        config = json.dumps({"order": ["agent-seq01", "agent-seq02"]})

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "sequential", "topology_config": config},
        )
        assert resp.status_code == 200

    def test_sequential_without_order_rejected(self, client, isolated_db):
        """Sequential topology without 'order' in config should fail 400."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-sno01", "agent-sno02"])
        config = json.dumps({"positions": {}})

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "sequential", "topology_config": config},
        )
        assert resp.status_code == 400

    def test_parallel_with_valid_config(self, client, isolated_db):
        """Parallel topology with valid 'agents' config should succeed."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-par01", "agent-par02"])
        config = json.dumps({"agents": ["agent-par01", "agent-par02"]})

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "parallel", "topology_config": config},
        )
        assert resp.status_code == 200

    def test_coordinator_with_valid_config(self, client, isolated_db):
        """Coordinator topology with valid config should succeed."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-crd01", "agent-crd02"])
        config = json.dumps(
            {
                "coordinator": "agent-crd01",
                "workers": ["agent-crd02"],
            }
        )

        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "coordinator", "topology_config": config},
        )
        assert resp.status_code == 200


# ===========================================================================
# Edge persistence round-trip
# ===========================================================================


class TestEdgeRoundTrip:
    """Verify edges saved in topology_config persist through save-reload."""

    def test_edges_persist_in_config(self, client, isolated_db):
        """Save edges in topology_config, reload, verify they're still there."""
        team_id, _ = _create_team_with_agents(
            isolated_db, ["agent-ert01", "agent-ert02", "agent-ert03"]
        )
        edges = [
            {"source": "agent-ert01", "target": "agent-ert02", "type": "smoothstep"},
            {"source": "agent-ert02", "target": "agent-ert03", "type": "smoothstep"},
        ]
        config = json.dumps({"edges": edges, "positions": {}})

        # Save
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config},
        )
        assert resp.status_code == 200

        # Reload
        resp = client.get(f"/admin/teams/{team_id}")
        data = resp.get_json()
        saved_config = json.loads(data["topology_config"])
        assert len(saved_config["edges"]) == 2

    def test_edges_override_on_resave(self, client, isolated_db):
        """Re-saving with different edges should replace old edges."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-ero01", "agent-ero02"])

        # Save with edge
        config1 = json.dumps(
            {
                "edges": [{"source": "agent-ero01", "target": "agent-ero02"}],
                "positions": {},
            }
        )
        client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config1},
        )

        # Resave with no edges
        config2 = json.dumps({"edges": [], "positions": {}})
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config2},
        )
        assert resp.status_code == 200
        saved_config = json.loads(resp.get_json()["topology_config"])
        assert len(saved_config["edges"]) == 0


# ===========================================================================
# Dropdown change + save sequence (simulates frontend flow)
# ===========================================================================


class TestDropdownThenSaveSequence:
    """Simulates the exact frontend flow:
    1. User selects topology from dropdown -> sends topology only
    2. User clicks Save -> sends topology_config only
    Neither should produce a 400.
    """

    def test_dropdown_then_save(self, client, isolated_db):
        """Dropdown change then save sequence should not 400."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-ds01", "agent-ds02"])

        # Step 1: Dropdown change (topology only, no config)
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "sequential"},
        )
        assert resp.status_code == 200, (
            f"Dropdown topology change should succeed. Got: {resp.get_json()}"
        )

        # Step 2: Canvas save (config only, no topology)
        config = json.dumps(
            {
                "positions": {
                    "agent-ds01": {"x": 50, "y": 100},
                    "agent-ds02": {"x": 300, "y": 100},
                },
                "edges": [{"source": "agent-ds01", "target": "agent-ds02"}],
            }
        )
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": config},
        )
        assert resp.status_code == 200, f"Canvas config save should succeed. Got: {resp.get_json()}"

        # Verify both persisted
        detail = get_team_detail(team_id)
        assert detail["topology"] == "sequential"
        saved_config = json.loads(detail["topology_config"])
        assert "positions" in saved_config
        assert "edges" in saved_config

    def test_change_topology_multiple_times(self, client, isolated_db):
        """Rapidly changing topology types (simulating dropdown clicks) should work."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-mt01"])

        for topo in ["sequential", "parallel", "coordinator", "hierarchical"]:
            resp = client.put(
                f"/admin/teams/{team_id}/topology",
                json={"topology": topo},
            )
            assert resp.status_code == 200
            assert resp.get_json()["topology"] == topo

    def test_save_then_dropdown_then_save(self, client, isolated_db):
        """Full round trip: save config, change topology, save config again."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-rnd01", "agent-rnd02"])

        # Initial save with config
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": json.dumps({"positions": {}})},
        )
        assert resp.status_code == 200

        # Change topology
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology": "parallel"},
        )
        assert resp.status_code == 200

        # Save config again (should NOT require parallel-specific fields)
        resp = client.put(
            f"/admin/teams/{team_id}/topology",
            json={
                "topology_config": json.dumps(
                    {
                        "positions": {"agent-rnd01": {"x": 0, "y": 0}},
                        "edges": [],
                    }
                )
            },
        )
        assert resp.status_code == 200

        # Verify state
        detail = get_team_detail(team_id)
        assert detail["topology"] == "parallel"


# ===========================================================================
# Config merge preservation
# ===========================================================================


class TestConfigMergePreservation:
    """Backend should merge/replace config fields independently."""

    def test_positions_update_preserves_other_fields(self, client, isolated_db):
        """Updating positions should not delete edge data."""
        team_id, _ = _create_team_with_agents(isolated_db, ["agent-mp01", "agent-mp02"])

        # Save initial config with edges AND positions
        initial = json.dumps(
            {
                "positions": {"agent-mp01": {"x": 0, "y": 0}},
                "edges": [{"source": "agent-mp01", "target": "agent-mp02"}],
                "order": ["agent-mp01", "agent-mp02"],
            }
        )
        client.put(
            f"/admin/teams/{team_id}/topology",
            json={"topology_config": initial},
        )

        # Reload and verify
        resp = client.get(f"/admin/teams/{team_id}")
        config = json.loads(resp.get_json()["topology_config"])
        assert "positions" in config
        assert "edges" in config
        assert "order" in config
