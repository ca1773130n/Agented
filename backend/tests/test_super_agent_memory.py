"""Super-agent layered memory: registry sync (attribution + org hierarchy) and
L1 distilled-runbook read. The Tesserae CLI itself is not exercised here — the
attribution + distill mechanics were verified end-to-end against tesserae 0.21.0
during design; these lock the Agented-side registry composition + artifact parse."""

import json

import pytest

from app.services import super_agent_memory as sam


@pytest.fixture
def project_with_super_agents(isolated_db, tmp_path, monkeypatch):
    """A project whose tesserae root is tmp_path, with two super-agents (a leader
    and its report) that each ran a session in the project."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-1", "P1"))
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type, parent_super_agent_id) VALUES (?,?,?,?)",
            ("super-lead", "Lead", "claude", None),
        )
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type, parent_super_agent_id) VALUES (?,?,?,?)",
            ("super-rep", "Reporter", "claude", "super-lead"),
        )
        for sid, sa in (("s1", "super-lead"), ("s2", "super-rep")):
            conn.execute(
                "INSERT INTO super_agent_sessions (id, super_agent_id, project_id) VALUES (?,?,?)",
                (sid, sa, "proj-1"),
            )
        conn.commit()
    return root


def test_agent_key_is_deterministic():
    assert sam.agent_key("super-abc") == "claude:unknown:super-abc"


def test_sync_registry_maps_hierarchy_and_label_rules(project_with_super_agents):
    root = project_with_super_agents
    path = sam.sync_agent_registry("proj-1")
    assert path == root / ".tesserae" / "agents" / "registry.json"
    reg = json.loads(path.read_text())
    assert reg["version"] == 1
    lead, rep = "claude:unknown:super-lead", "claude:unknown:super-rep"
    # each super-agent → its own agent key, attributed by an agent_label rule
    assert reg["agents"][lead]["match"] == [{"label": "super-lead"}]
    assert reg["agents"][lead]["label"] == "Lead"
    # the report's parent is the leader (org hierarchy from parent_super_agent_id)
    assert reg["agents"][rep]["parent"] == lead
    # the leader has no parent that ran here → reports to org:root
    assert reg["agents"][lead]["parent"] == "org:root"


def test_sync_registry_parent_absent_from_project_falls_back_to_root(
    isolated_db, tmp_path, monkeypatch
):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-1", "P1"))
        # parent exists in super_agents but never ran a session in proj-1
        conn.execute(
            "INSERT INTO super_agents (id, name, parent_super_agent_id) VALUES (?,?,?)",
            ("super-elsewhere", "Elsewhere", None),
        )
        conn.execute(
            "INSERT INTO super_agents (id, name, parent_super_agent_id) VALUES (?,?,?)",
            ("super-child", "Child", "super-elsewhere"),
        )
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id, project_id) VALUES (?,?,?)",
            ("s1", "super-child", "proj-1"),
        )
        conn.commit()
    reg = json.loads(sam.sync_agent_registry("proj-1").read_text())
    # unknown-to-this-project parent would make the registry fail to load, so we
    # must fall back to org:root rather than reference a non-declared agent
    assert reg["agents"]["claude:unknown:super-child"]["parent"] == "org:root"


def test_sync_registry_no_super_agents_returns_none(isolated_db, tmp_path, monkeypatch):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    assert sam.sync_agent_registry("proj-empty") is None


def test_read_agent_memory_parses_distilled_notes(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    key = sam.agent_key("super-lead")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "nodes": [
                    {"type": "DistilledNote", "name": "Gotcha: X", "description": "do Y not Z"},
                    {"type": "ExpertiseProfile", "name": "Expertise", "description": "auth, db"},
                    {"type": "SessionDecision", "name": "ignored", "description": "not a memory type"},
                ]
            }
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-lead")
    assert mem["key"] == key
    assert len(mem["notes"]) == 2  # SessionDecision excluded
    assert "Gotcha: X" in mem["text"] and "do Y not Z" in mem["text"]
    assert "ignored" not in mem["text"]


def test_read_agent_memory_missing_artifact_is_empty_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: tmp_path)
    mem = sam.read_agent_memory("proj-1", "super-none")
    assert mem["notes"] == [] and mem["text"] == ""


def test_read_agent_memory_bounds_output(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    key = sam.agent_key("super-big")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    big = "z" * 5000
    art.write_text(
        json.dumps(
            {"nodes": [{"type": "DistilledNote", "name": f"n{i}", "description": big} for i in range(10)]}
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-big", max_chars=6000)
    assert len(mem["text"]) <= 6100  # a couple notes, not all ten
