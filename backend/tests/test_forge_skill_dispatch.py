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
