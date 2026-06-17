"""GRD 0.4.5 multi-candidate plan selection — wraps the deterministic
``gd select-candidate`` / ``gd plan-tournament`` subcommands.

Selection is pure file scoring (no LLM, no agent) so these run SYNCHRONOUSLY
via ``GrdCliService.run_gd_json`` and return inline. A non-dry-run selection
promotes the winner ``PLAN-N.md → PLAN.md`` and is mirrored into
``grd_plan_selections``; dry-run is a preview (no promote, no mirror).
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.db.grd_plan_selections import upsert_plan_selection
from app.services.grd_cli_service import GrdCliService

logger = logging.getLogger(__name__)


def _mirror_selection(project_id: str, phase: str, data: dict) -> Optional[str]:
    """Mirror a SelectionResult dict into grd_plan_selections. Never raises."""
    try:
        candidates = data.get("candidates")
        return upsert_plan_selection(
            project_id=project_id,
            phase=str(phase),
            milestone=data.get("milestone"),
            winner_rel=(data.get("winner") or {}).get("relPath")
            if isinstance(data.get("winner"), dict)
            else data.get("winner"),
            promoted_to=data.get("promoted_to"),
            candidates_json=json.dumps(candidates) if candidates is not None else None,
            audit_json=json.dumps(data),
        )
    except Exception:
        logger.warning("plan-selection mirror failed for %s phase %s", project_id, phase,
                       exc_info=True)
        return None


def select_candidate(
    project_id: str,
    cwd: str,
    phase: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    run_verification_commands: bool = False,
) -> dict:
    """Run ``gd select-candidate <phase>`` (deterministic scorer + promoter).

    Returns ``{success, data, error, mirrored}``. On a real (non-dry-run)
    success the SelectionResult is mirrored to ``grd_plan_selections`` and
    ``mirrored`` is the ``psel-`` id; dry-run never mirrors.
    """
    argv = ["select-candidate", str(phase)]
    if dry_run:
        argv.append("--dry-run")
    if force:
        argv.append("--force")
    if run_verification_commands:
        argv.append("--run-verification-commands")
    result = GrdCliService.run_gd_json(cwd, *argv)
    mirrored: Optional[str] = None
    if result.get("success") and isinstance(result.get("data"), dict) and not dry_run:
        mirrored = _mirror_selection(project_id, phase, result["data"])
    return {
        "success": result.get("success", False),
        "data": result.get("data"),
        "error": result.get("error"),
        "mirrored": mirrored,
    }


def plan_tournament(cwd: str, phase: str, candidate_paths: List[str]) -> dict:
    """Run ``gd plan-tournament --phase <N> --candidates <paths…>`` (ad-hoc
    ranked scoring; no promotion, no mirror). Returns ``{success, data, error}``.
    """
    argv = ["plan-tournament", "--phase", str(phase), "--candidates", *candidate_paths]
    result = GrdCliService.run_gd_json(cwd, *argv)
    return {
        "success": result.get("success", False),
        "data": result.get("data"),
        "error": result.get("error"),
    }
