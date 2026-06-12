"""materialize_primitives projects bound primitives into .claude/."""

from __future__ import annotations

import pytest

from app.database import get_connection
from app.db import rules as rules_repo
from app.db import commands as commands_repo
from app.db import project_forge_bindings as bindings_repo
from app.services.forge_materialization_service import (
    MaterializationResult,
    materialize_primitives,
)


@pytest.fixture()
def _project_with_primitives(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-1', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="no-force-push",
        rule_type="validation",
        description="Never force-push to main",
        project_id="proj-1",
    )
    cid = commands_repo.create_command(
        name="deploy",
        description="Deploy",
        content="run deploy.sh",
        project_id="proj-1",
    )
    bindings_repo.add_binding("proj-1", "rule", str(rid))
    bindings_repo.add_binding("proj-1", "command", str(cid))
    return {"id": "proj-1"}


def test_materialize_writes_command_and_rule(_project_with_primitives, tmp_path):
    result = materialize_primitives(_project_with_primitives, ["rule", "command"], tmp_path)
    assert isinstance(result, MaterializationResult)
    cmd_file = tmp_path / ".claude" / "commands" / "deploy.md"
    rule_file = tmp_path / ".claude" / "agented-forge" / "rules" / "no-force-push.md"
    assert cmd_file.exists()
    assert "run deploy.sh" in cmd_file.read_text()
    assert rule_file.exists()
    rule_text = rule_file.read_text()
    assert 'agented-kind: "rule"' in rule_text
    assert 'agented-source: "forge"' in rule_text
    rels = {w.rel_path for w in result.written}
    assert ".claude/commands/deploy.md" in rels
    assert ".claude/agented-forge/rules/no-force-push.md" in rels


def test_materialize_is_deterministic(_project_with_primitives, tmp_path):
    r1 = materialize_primitives(_project_with_primitives, ["command"], tmp_path)
    text1 = (tmp_path / ".claude" / "commands" / "deploy.md").read_text()
    r2 = materialize_primitives(_project_with_primitives, ["command"], tmp_path)
    text2 = (tmp_path / ".claude" / "commands" / "deploy.md").read_text()
    assert text1 == text2
    assert {w.rel_path for w in r1.written} == {w.rel_path for w in r2.written}


def test_frontmatter_value_with_colon_and_newline_is_yaml_safe(isolated_db, tmp_path):
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-2', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(
        name="tricky",
        rule_type="validation",
        description="line one: with colon\nline two",
        project_id="proj-2",
    )
    bindings_repo.add_binding("proj-2", "rule", str(rid))
    materialize_primitives({"id": "proj-2"}, ["rule"], tmp_path)
    text = (tmp_path / ".claude" / "agented-forge" / "rules" / "tricky.md").read_text()
    # frontmatter must remain a valid, parseable block (exactly two '---' lines)
    assert text.count("---") == 2
    import yaml  # PyYAML is available in this project

    fm = text.split("---")[1]
    parsed = yaml.safe_load(fm)
    assert parsed["description"] == "line one: with colon\nline two"


def test_non_numeric_asset_id_skipped_not_crash(isolated_db, tmp_path):
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-3', 'P', 'active')")
        conn.commit()
    bindings_repo.add_binding("proj-3", "rule", "not-a-number")
    # Must not raise; just produces no rule file.
    result = materialize_primitives({"id": "proj-3"}, ["rule"], tmp_path)
    assert result.written == []


def test_materialize_writes_hook_and_settings(isolated_db, tmp_path):
    import json as _json
    from app.db import hooks as hooks_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-h', 'P', 'active')")
        conn.commit()
    hid = hooks_repo.create_hook(
        name="guard",
        event="PreToolUse",
        description="block force push",
        content="#!/bin/sh\necho block",
        project_id="proj-h",
    )
    bindings_repo.add_binding("proj-h", "hook", str(hid))

    materialize_primitives({"id": "proj-h"}, ["hook"], tmp_path)

    sh = tmp_path / ".claude" / "hooks" / "guard.sh"
    settings = tmp_path / ".claude" / "settings.json"
    assert sh.exists()
    assert "echo block" in sh.read_text()
    data = _json.loads(settings.read_text())
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["hooks"][0]["command"] == ".claude/hooks/guard.sh"
    assert entry["hooks"][0]["type"] == "command"


def test_hook_materialization_is_idempotent(isolated_db, tmp_path):
    import json as _json
    from app.db import hooks as hooks_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-hi', 'P', 'active')")
        conn.commit()
    hid = hooks_repo.create_hook(
        name="guard",
        event="PreToolUse",
        description="d",
        content="#!/bin/sh\necho x",
        project_id="proj-hi",
    )
    bindings_repo.add_binding("proj-hi", "hook", str(hid))
    materialize_primitives({"id": "proj-hi"}, ["hook"], tmp_path)
    materialize_primitives({"id": "proj-hi"}, ["hook"], tmp_path)  # second run
    data = _json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(data["hooks"]["PreToolUse"]) == 1  # not duplicated
    # executable bit set
    import os, stat

    mode = (tmp_path / ".claude" / "hooks" / "guard.sh").stat().st_mode
    assert mode & stat.S_IXUSR


def test_hook_materialization_preserves_operator_entries(isolated_db, tmp_path):
    import json as _json
    from app.db import hooks as hooks_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    # Pre-seed an operator-authored settings.json with a hook entry (no marker).
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        _json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": ".*", "hooks": [{"type": "command", "command": "operator.sh"}]}
                    ]
                }
            }
        )
    )
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-ho', 'P', 'active')")
        conn.commit()
    hid = hooks_repo.create_hook(
        name="guard", event="PreToolUse", description="d", content="echo x", project_id="proj-ho"
    )
    bindings_repo.add_binding("proj-ho", "hook", str(hid))
    materialize_primitives({"id": "proj-ho"}, ["hook"], tmp_path)
    data = _json.loads((tmp_path / ".claude" / "settings.json").read_text())
    cmds = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert "operator.sh" in cmds  # operator entry preserved
    assert ".claude/hooks/guard.sh" in cmds  # agented entry added


def test_materialize_writes_mcp_json_idempotent_and_operator_safe(isolated_db, tmp_path):
    import json as _json
    from app.db import mcp_servers as mcp_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolver import _find_mcp_server_id_by_name
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-m', 'P', 'active')")
        conn.commit()
    # operator-authored mcp.json with a non-agented server
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "mcp.json").write_text(
        _json.dumps({"mcpServers": {"operator-srv": {"command": "op"}}})
    )
    mcp_repo.create_mcp_server(
        name="ctx",
        description="ctx",
        server_type="stdio",
        command="ctx-server",
        args=None,
        env_json=None,
        url=None,
    )
    mid = _find_mcp_server_id_by_name("ctx")
    bindings_repo.add_binding("proj-m", "mcp_server", str(mid))

    materialize_primitives({"id": "proj-m"}, ["mcp_server"], tmp_path)
    materialize_primitives({"id": "proj-m"}, ["mcp_server"], tmp_path)  # idempotent

    data = _json.loads((tmp_path / ".claude" / "mcp.json").read_text())
    assert data["mcpServers"]["ctx"]["command"] == "ctx-server"
    assert data["mcpServers"]["operator-srv"]["command"] == "op"  # operator preserved
    assert data["_agented_mcp_servers"] == ["ctx"]
    assert list(data["mcpServers"].keys()).count("ctx") == 1  # no dup


def test_cleanup_removes_stale_per_asset_file(isolated_db, tmp_path):
    from app.db import commands as commands_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-cl', 'P', 'active')")
        conn.commit()
    cid = commands_repo.create_command(
        name="deploy", description="d", content="x", project_id="proj-cl"
    )
    bindings_repo.add_binding("proj-cl", "command", str(cid))
    materialize_primitives({"id": "proj-cl"}, ["command"], tmp_path)
    assert (tmp_path / ".claude" / "commands" / "deploy.md").exists()

    # Unbind the command (remove_binding takes the BINDING ROW id), re-run.
    for b in bindings_repo.list_bindings("proj-cl"):
        if b["kind"] == "command":
            bindings_repo.remove_binding(b["id"])
    result = materialize_primitives({"id": "proj-cl"}, ["command"], tmp_path)
    assert not (tmp_path / ".claude" / "commands" / "deploy.md").exists()
    assert ".claude/commands/deploy.md" in result.deleted


def test_manifest_written(isolated_db, tmp_path):
    import json as _json
    from app.db import commands as commands_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-mf', 'P', 'active')")
        conn.commit()
    cid = commands_repo.create_command(
        name="deploy", description="d", content="x", project_id="proj-mf"
    )
    bindings_repo.add_binding("proj-mf", "command", str(cid))
    materialize_primitives({"id": "proj-mf"}, ["command"], tmp_path)
    manifest = tmp_path / ".claude" / "agented-forge" / "manifest.json"
    assert manifest.exists()
    data = _json.loads(manifest.read_text())
    assert ".claude/commands/deploy.md" in data["paths_by_kind"]["command"]


def test_partial_kinds_run_does_not_delete_other_kinds(isolated_db, tmp_path):
    """A subsequent kinds=['command'] run must NOT delete still-bound rule files."""
    import json as _json
    from app.db import commands as commands_repo
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-pk', 'P', 'active')")
        conn.commit()
    cid = commands_repo.create_command(
        name="deploy", description="d", content="x", project_id="proj-pk"
    )
    rid = rules_repo.create_rule(
        name="guard", rule_type="validation", description="d", project_id="proj-pk"
    )
    bindings_repo.add_binding("proj-pk", "command", str(cid))
    bindings_repo.add_binding("proj-pk", "rule", str(rid))
    # full run materializes both
    materialize_primitives({"id": "proj-pk"}, ["command", "rule"], tmp_path)
    rule_file = tmp_path / ".claude" / "agented-forge" / "rules" / "guard.md"
    assert rule_file.exists()
    # partial run for command only must NOT delete the still-bound rule file
    materialize_primitives({"id": "proj-pk"}, ["command"], tmp_path)
    assert rule_file.exists()


def test_cleanup_never_deletes_shared_files(isolated_db, tmp_path):
    # settings.json / mcp.json must survive even when no hooks/mcp are bound this run.
    import json as _json
    from app.db import hooks as hooks_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-sh', 'P', 'active')")
        conn.commit()
    hid = hooks_repo.create_hook(
        name="g", event="PreToolUse", description="d", content="echo x", project_id="proj-sh"
    )
    bindings_repo.add_binding("proj-sh", "hook", str(hid))
    materialize_primitives({"id": "proj-sh"}, ["hook"], tmp_path)
    assert (tmp_path / ".claude" / "settings.json").exists()
    # Unbind the hook, re-run with hooks kind → settings.json must still exist (marker-managed), not manifest-deleted.
    for b in bindings_repo.list_bindings("proj-sh"):
        if b["kind"] == "hook":
            bindings_repo.remove_binding(b["id"])
    materialize_primitives({"id": "proj-sh"}, ["hook"], tmp_path)
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_materialize_writes_subagent(isolated_db, tmp_path):
    """A bound subagent materializes to .claude/agents/<safe>.md with Agented
    frontmatter markers, and is tracked in the manifest's subagent bucket."""
    from app.db import subagents as subagents_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-sa', 'P', 'active')")
        conn.commit()
    sa = subagents_repo.create_subagent(
        name="code-reviewer",
        description="Reviews code for bugs",
        content="You are a meticulous code reviewer. Find bugs.",
        project_id="proj-sa",
    )
    bindings_repo.add_binding("proj-sa", "subagent", sa["id"])

    result = materialize_primitives({"id": "proj-sa"}, ["subagent"], tmp_path)

    agent_file = tmp_path / ".claude" / "agents" / "code-reviewer.md"
    assert agent_file.exists()
    text = agent_file.read_text()
    assert 'agented-kind: "subagent"' in text
    assert f'agented-asset-id: "{sa["id"]}"' in text
    assert 'agented-source: "forge"' in text
    assert 'name: "code-reviewer"' in text
    assert 'description: "Reviews code for bugs"' in text
    assert "meticulous code reviewer" in text

    rels = {w.rel_path for w in result.written}
    assert ".claude/agents/code-reviewer.md" in rels

    import json as _json

    manifest = _json.loads(
        (tmp_path / ".claude" / "agented-forge" / "manifest.json").read_text()
    )
    assert ".claude/agents/code-reviewer.md" in manifest["paths_by_kind"]["subagent"]


def test_materialize_subagent_is_deterministic(isolated_db, tmp_path):
    """A second identical run yields byte-identical output + no manifest churn."""
    from app.db import subagents as subagents_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-sad', 'P', 'active')")
        conn.commit()
    sa = subagents_repo.create_subagent(
        name="planner",
        description="Plans work",
        content="Plan carefully.",
        project_id="proj-sad",
    )
    bindings_repo.add_binding("proj-sad", "subagent", sa["id"])

    r1 = materialize_primitives({"id": "proj-sad"}, ["subagent"], tmp_path)
    f = tmp_path / ".claude" / "agents" / "planner.md"
    text1 = f.read_text()
    manifest1 = (tmp_path / ".claude" / "agented-forge" / "manifest.json").read_text()
    r2 = materialize_primitives({"id": "proj-sad"}, ["subagent"], tmp_path)
    text2 = f.read_text()
    manifest2 = (tmp_path / ".claude" / "agented-forge" / "manifest.json").read_text()

    assert text1 == text2
    assert manifest1 == manifest2
    assert {w.rel_path for w in r1.written} == {w.rel_path for w in r2.written}
    assert r2.deleted == []


def test_mcp_json_idempotent_marker_length_and_bad_file_recovery(isolated_db, tmp_path):
    import json as _json
    from app.db import mcp_servers as mcp_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolver import _find_mcp_server_id_by_name
    from app.database import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('proj-mj', 'P', 'active')")
        conn.commit()
    # corrupt existing mcp.json — writer must recover (treat as empty), not crash
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "mcp.json").write_text("{ not valid json")
    mcp_repo.create_mcp_server(
        name="ctx",
        description="c",
        server_type="stdio",
        command="ctx",
        args=None,
        env_json=None,
        url=None,
    )
    mid = _find_mcp_server_id_by_name("ctx")
    bindings_repo.add_binding("proj-mj", "mcp_server", str(mid))
    materialize_primitives({"id": "proj-mj"}, ["mcp_server"], tmp_path)
    materialize_primitives({"id": "proj-mj"}, ["mcp_server"], tmp_path)
    data = _json.loads((tmp_path / ".claude" / "mcp.json").read_text())
    assert data["_agented_mcp_servers"] == ["ctx"]  # exactly one, no growth
    assert "ctx" in data["mcpServers"]
