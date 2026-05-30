"""Phase C2: reverse an applied evolution round (DB ops + git)."""

from __future__ import annotations

import logging

from app.db import project_forge_bindings as bindings_repo

logger = logging.getLogger(__name__)


def _unbind(project_id: str, kind: str, asset_id: str) -> None:
    for b in bindings_repo.list_bindings(project_id):
        if b.get("kind") == kind and str(b.get("asset_id")) == str(asset_id):
            bindings_repo.remove_binding(b["id"])


def _already_restored(project_id: str, kind: str, name: str) -> bool:
    """True if a same-named asset of this kind already exists for the project
    (so a delete-reversal retry doesn't create a duplicate)."""
    try:
        if kind == "rule":
            from app.db.rules import get_rules_by_project

            return any(r.get("name") == name for r in get_rules_by_project(project_id))
        if kind == "hook":
            from app.db.hooks import get_hooks_by_project

            return any(r.get("name") == name for r in get_hooks_by_project(project_id))
        if kind == "command":
            from app.db.commands import get_commands_by_project

            return any(r.get("name") == name for r in get_commands_by_project(project_id))
        if kind == "skill":
            from app.db.skills import get_user_skill_by_name

            return get_user_skill_by_name(name) is not None
    except Exception:
        return False
    return False  # mcp_server: best-effort, no idempotence guard


def reverse_apply_journal(project_id: str, journal: list[dict]) -> tuple[int, list[dict]]:
    """Reverse each journal entry in reverse order. Returns (reversed_count, failures).

    Best-effort per entry; a failure is recorded (not counted) and the loop continues.
    """
    from app.services.harness_evolver import (
        _asset_to_payload,
        _create_dispatch,
        _delete_dispatch,
        _update_dispatch,
    )

    reversed_count = 0
    failures: list[dict] = []
    for entry in reversed(journal):
        kind, op, asset_id = entry["kind"], entry["op"], entry["asset_id"]
        before = entry.get("before")
        try:
            if op == "create":
                _delete_dispatch[kind](asset_id=asset_id)
                _unbind(project_id, kind, asset_id)
            elif op == "update":
                if not before:
                    raise ValueError("update entry has no before-image")
                _update_dispatch[kind](asset_id=asset_id, payload=_asset_to_payload(kind, before))
            elif op == "delete":
                if not before:
                    raise ValueError("delete entry has no before-image")
                name = before.get("name") or before.get("skill_name") or "restored"
                if not _already_restored(project_id, kind, name):
                    new_id = _create_dispatch[kind](
                        name=name,
                        payload=_asset_to_payload(kind, before),
                        project_id=project_id,
                    )
                    if new_id is not None:
                        bindings_repo.add_binding(project_id, kind, str(new_id))
            else:
                raise ValueError(f"unknown op {op}")
            reversed_count += 1
        except Exception as exc:
            logger.warning(
                "reverse journal: failed to reverse %s %s %s: %s",
                op,
                kind,
                asset_id,
                exc,
                exc_info=True,
            )
            failures.append({"kind": kind, "op": op, "asset_id": str(asset_id), "error": str(exc)})
    return reversed_count, failures
