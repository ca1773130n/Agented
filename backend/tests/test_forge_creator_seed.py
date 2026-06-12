"""Phase 17-06: forge-creator default-bundle seed idempotence (P8)."""

from __future__ import annotations

from app.db import (
    get_all_user_skills,
    get_forge_bundle_by_name,
    list_forge_bundle_items,
)
from app.services.forge_creator_seed import (
    _CREATOR_SKILLS,
    BUNDLE_NAME,
    seed_forge_creator_bundle,
)

_EXPECTED_NAMES = {name for name, _rel, _desc in _CREATOR_SKILLS}


def test_seed_produces_five_skills_one_bundle(isolated_db):
    summary = seed_forge_creator_bundle()

    skills = get_all_user_skills()
    creator_skills = [s for s in skills if s["skill_name"] in _EXPECTED_NAMES]
    assert {s["skill_name"] for s in creator_skills} == _EXPECTED_NAMES
    assert len(creator_skills) == 5

    bundle = get_forge_bundle_by_name(BUNDLE_NAME)
    assert bundle is not None
    assert bundle["scope"] == "global"
    assert bundle["id"] == summary["bundle_id"]

    items = list_forge_bundle_items(bundle["id"])
    assert len(items) == 5
    assert all(it["kind"] == "skill" for it in items)
    assert summary["created"] is True


def test_seed_idempotent(isolated_db):
    first = seed_forge_creator_bundle()
    skills_after_first = {s["skill_name"] for s in get_all_user_skills()}
    items_after_first = list_forge_bundle_items(first["bundle_id"])

    second = seed_forge_creator_bundle()

    # Same bundle id, no new skills, no new items, created flag now False.
    assert second["bundle_id"] == first["bundle_id"]
    assert second["created"] is False
    assert {s["skill_name"] for s in get_all_user_skills()} == skills_after_first

    items_after_second = list_forge_bundle_items(second["bundle_id"])
    assert len(items_after_second) == len(items_after_first) == 5

    # Exactly one bundle named forge-creator (UNIQUE name guard held).
    bundle = get_forge_bundle_by_name(BUNDLE_NAME)
    assert bundle is not None
