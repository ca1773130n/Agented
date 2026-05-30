"""Phase C2: reverse an applied evolution round (DB ops + git)."""

from __future__ import annotations

import logging

from app.db import project_forge_bindings as bindings_repo

logger = logging.getLogger(__name__)


def _unbind(project_id: str, kind: str, asset_id: str) -> None:
    for b in bindings_repo.list_bindings(project_id):
        if b.get("kind") == kind and str(b.get("asset_id")) == str(asset_id):
            bindings_repo.remove_binding(b["id"])


def reverse_apply_journal(project_id: str, journal: list[dict]) -> int:
    """Reverse each journal entry in reverse order. Returns count reversed.

    Best-effort per entry (failures logged, loop continues).
    """
    from app.services.harness_evolver import (
        _asset_to_payload,
        _create_dispatch,
        _delete_dispatch,
        _update_dispatch,
    )

    reversed_count = 0
    for entry in reversed(journal):
        kind = entry["kind"]
        op = entry["op"]
        asset_id = entry["asset_id"]
        before = entry.get("before")
        try:
            if op == "create":
                _delete_dispatch[kind](asset_id=asset_id)
                _unbind(project_id, kind, asset_id)
            elif op == "update":
                if before:
                    _update_dispatch[kind](
                        asset_id=asset_id, payload=_asset_to_payload(kind, before)
                    )
            elif op == "delete":
                if before:
                    name = before.get("name") or before.get("skill_name") or "restored"
                    new_id = _create_dispatch[kind](
                        name=name,
                        payload=_asset_to_payload(kind, before),
                        project_id=project_id,
                    )
                    if new_id is not None:
                        bindings_repo.add_binding(project_id, kind, str(new_id))
            reversed_count += 1
        except Exception:
            logger.warning(
                "reverse journal: failed to reverse %s %s %s",
                op,
                kind,
                asset_id,
                exc_info=True,
            )
    return reversed_count
