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
