"""Idempotent seed for the ``forge-creator`` default bundle.

Ships five global-scope creator skills (skill/rule/hook/command/subagent-
creator) — each an agentskills.io-compatible ``SKILL.md`` under
``app/forge_seeds/forge-creator/<name>/`` — composed into a single
``forge-creator`` bundle (``scope='global'``).

Global-scope decision (RESEARCH.md Open Q2): ``user_skills`` has no
``project_id`` column, so a user skill is *inherently* global — there is no
per-project skill row. We therefore express "global" with no sentinel
project_id at all on the skill side, and tag the bundle itself
``scope='global'`` (the same enum ``forge_bundles.scope`` already supports
alongside ``'project'``). This keeps the seed reusing existing primitives with
no schema change.

Idempotence: every step is guarded on existence (skill name, bundle name,
bundle item) so re-running ``seed_forge_creator_bundle`` is a pure no-op —
mirroring the predefined-bot seeding pattern. Safe to call on every startup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.db.forge_bundles import (
    add_bundle_item,
    create_forge_bundle,
    get_forge_bundle_by_name,
    list_forge_bundle_items,
)
from app.db.skills import add_user_skill, get_user_skill_by_name

logger = logging.getLogger(__name__)

BUNDLE_NAME = "forge-creator"
BUNDLE_DESCRIPTION = (
    "Default creator skills: scaffold skills, rules, hooks, commands, and "
    "subagents under .claude/ from within an Agented-driven session."
)

# Directory holding the five SKILL.md seeds (one subdir per creator skill).
_SEEDS_DIR = Path(__file__).resolve().parent.parent / "forge_seeds" / "forge-creator"

# (skill_name, relative SKILL.md path, one-line description). Order is stable so
# bundle item positions are deterministic.
_CREATOR_SKILLS: list[tuple[str, str, str]] = [
    (
        "skill-creator",
        "skill-creator/SKILL.md",
        "Scaffold a new agentskills.io-compatible skill under .claude/skills/.",
    ),
    (
        "rule-creator",
        "rule-creator/SKILL.md",
        "Scaffold a new always-on rule under .claude/rules/.",
    ),
    (
        "hook-creator",
        "hook-creator/SKILL.md",
        "Scaffold a new lifecycle hook under .claude/hooks/.",
    ),
    (
        "command-creator",
        "command-creator/SKILL.md",
        "Scaffold a new slash command under .claude/commands/.",
    ),
    (
        "subagent-creator",
        "subagent-creator/SKILL.md",
        "Scaffold a new subagent under .claude/agents/.",
    ),
]


def _ensure_skill(skill_name: str, rel_path: str, description: str) -> int | None:
    """Register one creator skill at global scope iff it does not already exist.

    Returns the skill id (existing or newly created), or None if creation
    failed (e.g. a race lost the UNIQUE insert — re-resolved by name).
    """
    existing = get_user_skill_by_name(skill_name)
    if existing is not None:
        return existing["id"]

    skill_path = str(_SEEDS_DIR / rel_path)
    new_id = add_user_skill(
        skill_name=skill_name,
        skill_path=skill_path,
        description=description,
        enabled=1,
        selected_for_harness=0,
    )
    if new_id is not None:
        return new_id

    # add_user_skill returns None on IntegrityError (concurrent insert) —
    # re-resolve so the bundle item still gets the right id.
    again = get_user_skill_by_name(skill_name)
    return again["id"] if again else None


def seed_forge_creator_bundle() -> dict:
    """Idempotently seed the five creator skills + the forge-creator bundle.

    Returns a small summary dict: ``{"bundle_id", "skill_ids", "created"}``
    where ``created`` is False when everything already existed (pure no-op).
    Never raises on already-seeded state.
    """
    # 1. Ensure each global-scope creator skill exists.
    skill_ids: dict[str, int] = {}
    for skill_name, rel_path, description in _CREATOR_SKILLS:
        sid = _ensure_skill(skill_name, rel_path, description)
        if sid is not None:
            skill_ids[skill_name] = sid

    # 2. Ensure the global-scope bundle exists (UNIQUE name guard).
    bundle = get_forge_bundle_by_name(BUNDLE_NAME)
    created = False
    if bundle is None:
        bundle = create_forge_bundle(
            name=BUNDLE_NAME,
            description=BUNDLE_DESCRIPTION,
            scope="global",
        )
        created = True
    bundle_id = bundle["id"]

    # 3. Ensure each skill is an item of the bundle. add_bundle_item is
    #    idempotent on (bundle_id, kind, asset_id), so guarding here just
    #    avoids redundant writes and keeps positions stable.
    existing_items = {
        (it["kind"], str(it["asset_id"])) for it in list_forge_bundle_items(bundle_id)
    }
    for position, (skill_name, _rel, _desc) in enumerate(_CREATOR_SKILLS):
        sid = skill_ids.get(skill_name)
        if sid is None:
            continue
        if ("skill", str(sid)) in existing_items:
            continue
        add_bundle_item(bundle_id, "skill", str(sid), position=position)

    logger.info(
        "forge-creator seed: bundle=%s skills=%d (created=%s)",
        bundle_id,
        len(skill_ids),
        created,
    )
    return {"bundle_id": bundle_id, "skill_ids": skill_ids, "created": created}
