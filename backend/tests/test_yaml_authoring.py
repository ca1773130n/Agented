"""Tests for the team YAML authoring service (Phase 26 / REQ-40).

Covers:
- Pure round-trip equivalence (dump -> load is lossless).
- DB-backed round-trip (import a YAML team, export it, re-load and compare spec).
- Invalid YAML is rejected before any DB write (partial-state guard):
  a malformed document never leaves a partially-created team behind.
"""

import pytest

from app.database import count_teams, get_team_edges, get_team_members
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
