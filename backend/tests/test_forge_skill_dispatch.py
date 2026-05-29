"""Skill create/update/delete dispatch in the evolver."""

from __future__ import annotations

import pytest

from app.database import get_connection
from app.db import skills as skills_repo
from app.services import harness_evolver as ev


@pytest.fixture()
def _proj(isolated_db, tmp_path):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES ('proj-sk', 'P', 'active', ?)",
            (str(tmp_path),),
        )
        conn.commit()
    return str(tmp_path)


def test_skill_in_writable_kinds():
    assert "skill" in ev.WRITABLE_KINDS


def test_create_skill_writes_md_and_row(_proj):
    from pathlib import Path

    asset_id = ev._create_dispatch["skill"](
        name="commit-style",
        payload={"description": "Use conventional commits", "content": "Body here"},
        project_id="proj-sk",
    )
    assert asset_id is not None
    row = skills_repo.get_user_skill_by_name("commit-style")
    assert row is not None
    skill_md = Path(_proj) / ".claude" / "skills" / "commit-style" / "SKILL.md"
    assert skill_md.exists()
    assert "Body here" in skill_md.read_text()


def test_update_then_delete_skill(_proj):
    from pathlib import Path

    aid = ev._create_dispatch["skill"](
        name="temp",
        payload={"description": "d", "content": "v1"},
        project_id="proj-sk",
    )
    ev._update_dispatch["skill"](asset_id=aid, payload={"description": "d2", "content": "v2"})
    md = Path(_proj) / ".claude" / "skills" / "temp" / "SKILL.md"
    assert "v2" in md.read_text()
    ev._delete_dispatch["skill"](asset_id=aid)
    assert skills_repo.get_user_skill(int(aid)) is None
    assert not md.exists()


def test_skill_description_with_colon_newline_is_yaml_safe(_proj):
    from pathlib import Path

    import yaml

    aid = ev._create_dispatch["skill"](
        name="tricky",
        payload={"description": "Fix: do\nthing", "content": "body"},
        project_id="proj-sk",
    )
    assert aid is not None
    md = Path(_proj) / ".claude" / "skills" / "tricky" / "SKILL.md"
    text = md.read_text()
    fm = yaml.safe_load(text.split("---")[1])
    assert fm["description"] == "Fix: do\nthing"
    assert fm["name"] == "tricky"


def test_create_skill_duplicate_name_updates_existing(_proj):
    aid1 = ev._create_dispatch["skill"](
        name="dup",
        payload={"description": "d1", "content": "v1"},
        project_id="proj-sk",
    )
    aid2 = ev._create_dispatch["skill"](
        name="dup",
        payload={"description": "d2", "content": "v2"},
        project_id="proj-sk",
    )
    # Same row id returned (updated, not orphaned), and only one row by name.
    assert int(aid2) == int(aid1)
    row = skills_repo.get_user_skill_by_name("dup")
    assert row is not None
