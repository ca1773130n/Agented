"""Tests for the team YAML authoring service (Phase 26 / REQ-40).

Covers:
- Pure round-trip equivalence (dump -> load is lossless).
- DB-backed round-trip (import a YAML team, export it, re-load and compare spec).
- Invalid YAML is rejected before any DB write (partial-state guard):
  a malformed document never leaves a partially-created team behind.
"""

import pytest

from app.database import count_teams, get_team_by_name, get_team_edges, get_team_members
from app.services import yaml_authoring_service as yas


# ---------------------------------------------------------------------------
# Pure round-trip (no DB)
# ---------------------------------------------------------------------------


def _sample_config() -> dict:
    return {
        "version": yas.CONFIG_VERSION,
        "kind": yas.CONFIG_KIND,
        "metadata": {"name": "Alpha Team", "description": "desc", "color": "#123456"},
        "spec": {
            "topology": "coordinator",
            "topology_config": {"coordinator": "lead", "workers": ["w1"]},
            "trigger_source": None,
            "members": [
                {"ref": "lead", "name": "lead", "role": "leader", "layer": "backend"},
                {"ref": "w1", "name": "w1", "role": "member", "layer": "backend"},
            ],
            "edges": [
                {
                    "source": "lead",
                    "target": "w1",
                    "edge_type": "delegation",
                    "label": None,
                    "weight": 1,
                }
            ],
        },
    }


def test_dump_load_round_trip_is_lossless():
    cfg = _sample_config()
    text = yas.dump_team_config(cfg)
    assert isinstance(text, str)
    assert yas.load_team_config(text) == cfg


def test_valid_config_passes_validation():
    ok, err = yas.validate_team_config(_sample_config())
    assert ok is True
    assert err is None


# ---------------------------------------------------------------------------
# Invalid YAML / config rejection (partial-state guard)
# ---------------------------------------------------------------------------


def test_load_rejects_malformed_yaml():
    with pytest.raises(ValueError):
        yas.load_team_config("foo: [1, 2\nbar: baz")


def test_import_malformed_yaml_writes_nothing(isolated_db):
    before = count_teams()
    with pytest.raises(ValueError):
        yas.import_team("foo: [1, 2\n  bad indent")
    assert count_teams() == before


def test_import_missing_spec_writes_nothing(isolated_db):
    before = count_teams()
    bad = "version: '1.0'\nkind: team\nmetadata:\n  name: NoSpec\n"
    with pytest.raises(ValueError):
        yas.import_team(bad)
    assert count_teams() == before


def test_import_bad_topology_writes_nothing(isolated_db):
    cfg = _sample_config()
    cfg["metadata"]["name"] = "BadTopo"
    cfg["spec"]["topology"] = "not_a_real_topology"
    before = count_teams()
    with pytest.raises(ValueError):
        yas.import_team(yas.dump_team_config(cfg))
    assert count_teams() == before


def test_import_edge_to_unknown_member_writes_nothing(isolated_db):
    cfg = _sample_config()
    cfg["metadata"]["name"] = "DanglingEdge"
    cfg["spec"]["edges"][0]["target"] = "ghost"
    before = count_teams()
    with pytest.raises(ValueError):
        yas.import_team(yas.dump_team_config(cfg))
    assert count_teams() == before


# ---------------------------------------------------------------------------
# DB-backed round-trip
# ---------------------------------------------------------------------------


def test_import_then_export_round_trip(isolated_db):
    cfg = _sample_config()
    text = yas.dump_team_config(cfg)

    team_id, status = yas.import_team(text)
    assert status == "created"
    assert team_id

    # Materialized in the DB.
    members = get_team_members(team_id)
    assert len(members) == 2
    edges = get_team_edges(team_id)
    assert len(edges) == 1

    # Export and re-load; the spec must be structurally equivalent.
    exported = yas.export_team(team_id)
    assert exported is not None
    round_tripped = yas.load_team_config(exported)

    assert round_tripped["metadata"]["name"] == "Alpha Team"
    assert round_tripped["spec"]["topology"] == "coordinator"

    refs = sorted(m["ref"] for m in round_tripped["spec"]["members"])
    assert refs == ["lead", "w1"]

    edge = round_tripped["spec"]["edges"][0]
    assert (edge["source"], edge["target"], edge["edge_type"]) == ("lead", "w1", "delegation")


def test_import_duplicate_name_rejected_without_upsert(isolated_db):
    cfg = _sample_config()
    cfg["metadata"]["name"] = "DupTeam"
    text = yas.dump_team_config(cfg)
    yas.import_team(text)
    with pytest.raises(ValueError):
        yas.import_team(text)


def test_import_upsert_replaces_existing(isolated_db):
    cfg = _sample_config()
    cfg["metadata"]["name"] = "UpsertTeam"
    yas.import_team(yas.dump_team_config(cfg))

    cfg["spec"]["members"].append({"ref": "w2", "name": "w2", "role": "member", "layer": "backend"})
    team_id, status = yas.import_team(yas.dump_team_config(cfg), upsert=True)
    assert status == "updated"
    assert len(get_team_members(team_id)) == 3


# ---------------------------------------------------------------------------
# Atomicity / rollback (Codex finding #3 — data-loss guard)
# ---------------------------------------------------------------------------


def test_import_bad_agent_ref_raises_and_writes_nothing(isolated_db):
    """A member pointing at a non-existent agent is rejected before any write."""
    cfg = _sample_config()
    cfg["metadata"]["name"] = "BadAgentRef"
    cfg["spec"]["members"] = [
        {"ref": "ghost", "agent_id": "agent-nope99", "role": "member", "layer": "backend"}
    ]
    cfg["spec"]["edges"] = []
    before = count_teams()
    with pytest.raises(ValueError, match="unknown agent_id"):
        yas.import_team(yas.dump_team_config(cfg))
    assert count_teams() == before


def test_import_duplicate_edge_rolls_back_and_creates_nothing(isolated_db):
    """A duplicate edge passes structural validation but fails at insert.

    The whole create must roll back — no partial team survives.
    """
    cfg = _sample_config()
    cfg["metadata"]["name"] = "DupEdge"
    # Two structurally identical edges -> UNIQUE(team, src, tgt, type) violation.
    cfg["spec"]["edges"] = [
        {"source": "lead", "target": "w1", "edge_type": "delegation", "weight": 1},
        {"source": "lead", "target": "w1", "edge_type": "delegation", "weight": 1},
    ]
    before = count_teams()
    with pytest.raises(ValueError, match="Failed to add edge"):
        yas.import_team(yas.dump_team_config(cfg))
    # Nothing committed: no team, no orphan members/edges.
    assert count_teams() == before
    assert get_team_by_name("DupEdge") is None


def test_import_upsert_rollback_preserves_prior_team(isolated_db):
    """A failing upsert must NOT destroy the pre-existing team (data-loss guard)."""
    good = _sample_config()
    good["metadata"]["name"] = "SurvivorTeam"
    orig_id, _ = yas.import_team(yas.dump_team_config(good))
    before_count = count_teams()

    # Replacement is structurally valid but has a duplicate edge -> insert fails
    # AFTER the delete + create statements run inside the transaction.
    bad = _sample_config()
    bad["metadata"]["name"] = "SurvivorTeam"
    bad["spec"]["edges"] = [
        {"source": "lead", "target": "w1", "edge_type": "delegation", "weight": 1},
        {"source": "lead", "target": "w1", "edge_type": "delegation", "weight": 1},
    ]
    with pytest.raises(ValueError):
        yas.import_team(yas.dump_team_config(bad), upsert=True)

    # The prior team is untouched: same id, same membership, same count.
    survivor = get_team_by_name("SurvivorTeam")
    assert survivor is not None
    assert survivor["id"] == orig_id
    assert count_teams() == before_count
    assert len(get_team_members(orig_id)) == 2
    assert len(get_team_edges(orig_id)) == 1
