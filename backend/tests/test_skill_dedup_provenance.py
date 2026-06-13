"""P3 — dedup + provenance tests for skill_safety_scanner.

The autouse ``isolated_db`` fixture (conftest.py) routes through ``init_db()``,
so the migration-only ``forge_origin`` table exists. Provenance MUST be tested
this way — a bare ``create_fresh_schema`` connection lacks ``forge_origin``
(22-RESEARCH.md, migration #157).
"""

from app.db.forge_origin import record_origin
from app.db.skills import add_user_skill
from app.services.skill_safety_scanner import (
    find_duplicate_binding,
    provenance_allows_overwrite,
)
from app.utils.plugin_format import content_hash


# --- dedup: patch-over-create -----------------------------------------------
def test_exact_name_returns_existing_binding():
    add_user_skill("format-json", "/skills/format-json/SKILL.md")
    found = find_duplicate_binding("format-json")
    assert found is not None
    assert found["skill_name"] == "format-json"


def test_near_duplicate_name_returns_existing_binding():
    # ~90%+ name-cosine: underscores vs hyphens, same tokens.
    add_user_skill("format-json-output", "/skills/format-json-output/SKILL.md")
    found = find_duplicate_binding("format_json_output")
    assert found is not None
    assert found["skill_name"] == "format-json-output"


def test_distinct_name_returns_none():
    add_user_skill("format-json", "/skills/format-json/SKILL.md")
    assert find_duplicate_binding("deploy-kubernetes-cluster") is None


def test_no_skills_returns_none():
    assert find_duplicate_binding("anything") is None


# --- provenance: never overwrite operator-modified --------------------------
def test_no_origin_row_allows_overwrite(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("body", encoding="utf-8")
    # nothing recorded -> nothing to protect -> allow
    assert provenance_allows_overwrite("unbound-skill", "skill", skill_md) is True


def test_matching_hash_allows_overwrite(tmp_path):
    content = "# My Skill\n\nDo the thing.\n"
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    record_origin(
        "my-skill", "skill", origin_hash=content_hash(content), source_session_id="sess-1"
    )
    assert provenance_allows_overwrite("my-skill", "skill", skill_md) is True


def test_diverged_hash_refuses_overwrite(tmp_path):
    original = "# My Skill\n\nDo the thing.\n"
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(original, encoding="utf-8")
    record_origin(
        "my-skill", "skill", origin_hash=content_hash(original), source_session_id="sess-1"
    )
    # operator edits the on-disk file
    skill_md.write_text(original + "\nOperator added a line.\n", encoding="utf-8")
    assert provenance_allows_overwrite("my-skill", "skill", skill_md) is False


def test_missing_file_refuses_overwrite(tmp_path):
    record_origin("my-skill", "skill", origin_hash=content_hash("x"), source_session_id="sess-1")
    # file gone -> can't verify -> fail closed
    assert provenance_allows_overwrite("my-skill", "skill", tmp_path / "absent.md") is False
