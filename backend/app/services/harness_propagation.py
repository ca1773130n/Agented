"""Phase E1: cross-project propagation (evidence → promote → shared layer)."""

from __future__ import annotations

import logging

from app.db import forge_promotion as fp
from app.services.forge_fingerprint import fingerprint

logger = logging.getLogger(__name__)

# Decayed-evidence score required to promote (≈ several high-confidence applies).
PROMOTION_THRESHOLD = 3.0
# mcp_server and skill propagation deferred (junction-table scoping / project_root differ).
_PROPAGATABLE = ("rule", "hook", "command")


def record_promotion_evidence(project_id: str, applied: list[dict], *, eval_score: float) -> None:
    """For each applied create/update primitive, log eval evidence under its fingerprint."""
    from app.services.harness_evolver import _fetch_primitive

    for entry in applied:
        if entry.get("op") not in ("create", "update"):
            continue
        kind = entry["kind"]
        if kind not in _PROPAGATABLE:
            continue
        asset = _fetch_primitive(kind, entry["asset_id"])
        if not asset:
            continue
        try:
            fp.record_evidence(
                fingerprint=fingerprint(kind, asset),
                kind=kind,
                asset_id=str(entry["asset_id"]),
                project_id=project_id,
                eval_score=float(eval_score),
            )
        except Exception:
            logger.warning(
                "propagation: record_evidence failed for %s %s",
                kind,
                entry["asset_id"],
                exc_info=True,
            )


def promote_if_qualified(kind: str, fp_value: str, asset: dict) -> bool:
    """If the fingerprint's decayed evidence score >= threshold and not already shared,
    create a global-scope copy of the asset + a shared_forge_binding.
    Returns True if promoted."""
    if kind not in _PROPAGATABLE:
        return False
    # already shared?
    if any(
        s["fingerprint"] == fp_value and s["kind"] == kind
        for s in fp.list_shared_bindings(enabled_only=True)
    ):
        return False
    if fp.promotion_score(fp_value) < PROMOTION_THRESHOLD:
        return False
    from app.services.harness_evolver import _asset_to_payload, _create_dispatch

    try:
        global_id = _create_dispatch[kind](
            name=asset.get("name") or asset.get("skill_name") or "promoted",
            payload=_asset_to_payload(kind, asset),
            project_id=None,
        )
        if global_id is None:
            return False
        fp.create_shared_binding(
            scope="global", kind=kind, asset_id=str(global_id), fingerprint=fp_value
        )
        logger.info(
            "propagation: promoted %s fingerprint %s to global scope %s",
            kind,
            fp_value[:12],
            global_id,
        )
        return True
    except Exception:
        logger.warning("propagation: promote failed for %s %s", kind, fp_value[:12], exc_info=True)
        return False


def adopt_shared_binding(project_id: str, shared_binding_id: int) -> dict:
    """Adopt a shared (promoted) binding into a project.

    Returns:
        {"adopted": True, "binding_id": <id>}          — newly adopted
        {"adopted": True, "reason": "already"}          — already adopted (idempotent)
        {"adopted": False, "reason": "local_wins"}      — project has own local binding
        {"adopted": False, "reason": "not_found"}       — shared binding doesn't exist
    """
    sb = fp.get_shared_binding(shared_binding_id)
    if sb is None:
        return {"adopted": False, "reason": "not_found"}

    from app.db import project_forge_bindings as bindings_repo

    for row in bindings_repo.list_bindings(project_id):
        if (
            row.get("kind") == sb["kind"]
            and str(row.get("fingerprint")) == str(sb["fingerprint"])
            and row.get("source_scope") != "shared"
        ):
            return {"adopted": False, "reason": "local_wins"}

    binding = bindings_repo.add_binding(
        project_id,
        sb["kind"],
        sb["asset_id"],
        source_scope="shared",
        source_shared_binding_id=shared_binding_id,
        fingerprint=sb["fingerprint"],
    )
    fp.record_adoption(project_id=project_id, shared_binding_id=shared_binding_id)
    bid = binding.get("id") if isinstance(binding, dict) else binding
    return {"adopted": True, "binding_id": bid}
