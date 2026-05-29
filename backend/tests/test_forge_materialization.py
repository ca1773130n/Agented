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
