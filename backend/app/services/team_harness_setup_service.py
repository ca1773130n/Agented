"""TeamHarnessSetupService — sequential 6-step harness-setup orchestrator.

This module is the wave-1 *skeleton* half of Phase 21. It owns the
orchestration / idempotency / failure-handling machinery; the four wave-2
step-group plans (21-03..06) replace the placeholder ``_step_*`` bodies with
the real work, and the wave-3 route plan (21-07) calls :meth:`setup`.

Contract (what 21-03..06 implement against):

- ``HARNESS_SETUP_STEP_KEYS`` — exactly 6 ordered keys (a→f). Do not reorder.
- Each step is a function ``_step_<name>(project_id, existing_row) -> StepResult``.
  ``existing_row`` is the persisted ``harness_setup_steps`` row (a dict) or
  ``None`` when the step has never run. A step:
    1. inspects ``existing_row`` (+ its own fingerprint logic) to decide
       skip-vs-run,
    2. calls existing DB/service helpers to do the work,
    3. returns ``StepResult(step_key, status, detail, fingerprint)`` —
       it does NOT persist the row itself (the orchestrator does).
  A step raising an exception is treated as a hard failure for that step.
- The orchestrator persists the row, drives the overall status state machine
  (none→running→ready/failed), and on the FIRST failure stops iterating and
  leaves later steps un-recorded (so they stay retryable). It never rolls back
  prior steps (no destructive deletes — SC4).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from app.models.autonomy_policy import AutonomyPolicy

from app.db.projects import (
    get_harness_setup_steps,
    get_project,
    set_harness_setup_status,
    upsert_harness_setup_step,
)

logger = logging.getLogger(__name__)

# Exactly 6 steps, ordered a→f. Wave-2 plans plug bodies into _STEP_FUNCS.
HARNESS_SETUP_STEP_KEYS: list[str] = [
    "grd_init",
    "team_topology",
    "bundle_binding",
    "tesserae_enable",
    "default_policies",
    "materialize_compile",
]


@dataclass
class StepResult:
    """Outcome of a single setup step.

    ``status`` is one of "ok" | "skipped" | "failed". ``fingerprint`` (when a
    step computes one) lets a later re-run detect unchanged inputs and skip.
    """

    step_key: str
    status: str  # "ok" | "skipped" | "failed"
    detail: str = ""
    fingerprint: Optional[str] = None


class TeamHarnessSetupService:
    """Sequential orchestrator over the six harness-setup steps."""

    @classmethod
    def setup(cls, project_id: str) -> str:
        """Run all six steps in order; return the final overall status.

        State machine: status is set "running" up front, then "ready" if every
        step is ok/skipped, or "failed" on the first step that raises. Never
        raises out of ``setup()`` itself — a catch-all guard converts any
        unexpected error into a "failed" status.
        """
        set_harness_setup_status(project_id, "running")
        overall_failed = False

        try:
            existing_rows = {row["step_key"]: row for row in get_harness_setup_steps(project_id)}

            for key in HARNESS_SETUP_STEP_KEYS:
                existing_row = existing_rows.get(key)

                # Skip steps already 'ok' (idempotency / retry-skip). A step's
                # own fingerprint logic in _step_* may still re-run on changed
                # inputs; here we honour an already-ok row as the skip floor.
                if existing_row is not None and existing_row.get("status") == "ok":
                    logger.debug(
                        "harness-setup step %s already ok for %s — skipping",
                        key,
                        project_id,
                    )
                    continue

                step_func = cls._STEP_FUNCS[key]
                try:
                    result = step_func(project_id, existing_row)
                except Exception as exc:  # noqa: BLE001 — per-step isolation
                    logger.warning(
                        "harness-setup step %s failed for %s: %s",
                        key,
                        project_id,
                        exc,
                    )
                    upsert_harness_setup_step(project_id, key, "failed", detail=str(exc))
                    overall_failed = True
                    # Stop iterating: leave later steps un-recorded (retryable).
                    break

                upsert_harness_setup_step(
                    project_id,
                    key,
                    result.status,
                    detail=result.detail,
                    fingerprint=result.fingerprint,
                )
        except Exception as exc:  # noqa: BLE001 — setup() must never raise
            logger.exception("harness-setup orchestration crashed for %s: %s", project_id, exc)
            overall_failed = True

        final_status = "failed" if overall_failed else "ready"
        set_harness_setup_status(project_id, final_status)
        return final_status


# ---------------------------------------------------------------------------
# Placeholder step bodies. Wave-2 plans (21-03..06) replace these with the
# real work. They are intentionally side-effect-free so the import smoke (S3)
# and the skeleton state-machine tests pass immediately.
# ---------------------------------------------------------------------------


def _planning_fingerprint(planning_dir: str) -> Optional[str]:
    """Hash presence + mtime of ``.planning/`` so a re-run after init skips.

    Returns ``None`` when the directory is absent (init has not happened),
    else a short hash of ``(path, mtime)`` — stable while .planning/ is
    untouched, so the orchestrator's already-ok floor + this fingerprint both
    converge on skip.
    """
    if not os.path.isdir(planning_dir):
        return None
    try:
        mtime = os.path.getmtime(planning_dir)
    except OSError:
        mtime = 0.0
    digest = hashlib.sha256(f"{planning_dir}:{mtime}".encode()).hexdigest()
    return digest[:16]


def _step_grd_init(project_id: str, existing_row: Optional[dict]) -> StepResult:
    """Step a — reconcile GRD initialization (never re-init a populated repo).

    If the project's ``<local_path>/.planning/`` already exists we are done:
    return ``skipped`` (reconcile — no destructive re-init, SC4). Otherwise
    trigger the GRD-init path via :meth:`GrdPlanningService.auto_init_project`
    (fire-and-forget background work); we record ``ok`` ("init triggered") and
    let the deferred dogfood (D1) validate real completion.
    """
    project = get_project(project_id)
    if not project:
        raise ValueError(f"grd_init: project {project_id} not found")

    local_path = project.get("local_path")
    if not local_path:
        raise ValueError(f"grd_init: project {project_id} has no local_path")

    planning_dir = os.path.join(local_path, ".planning")
    fingerprint = _planning_fingerprint(planning_dir)

    # Reconcile: .planning/ already present → never re-init (no destructive deletes).
    if fingerprint is not None:
        return StepResult(
            "grd_init", "skipped", "planning already present", fingerprint=fingerprint
        )

    # No .planning/ yet → trigger the (background) GRD-init path. Imported lazily
    # so tests can monkeypatch GrdPlanningService.auto_init_project cheaply.
    from app.services.grd_planning_service import GrdPlanningService

    GrdPlanningService.auto_init_project(project_id, local_path)
    return StepResult("grd_init", "ok", "init triggered")


def _step_team_topology(project_id: str, existing_row: Optional[dict]) -> StepResult:
    """Step b — team topology + SA instances tagged ``driver='grd'`` (Phase 19).

    Two phase-sharp pitfalls handled here:

    1. SA-instance creation is NOT constraint-deduped at this layer, so we
       EXISTENCE-CHECK first: if instances already exist for the project we do
       not call ``create_team_instances`` again (P1 — no duplicate rows on
       re-run). We still reconcile ``driver`` below so a skip converges too.
    2. ``InstanceService.create_team_instances`` takes no ``driver`` kwarg, so
       we post-update each SA instance's ``driver`` column to ``"grd"`` via
       ``update_project_sa_instance(..., driver="grd")`` (Open Question 2:
       change kept local to this phase) and verify with ``get_instance_driver``.
    """
    from app.db.project_sa_instances import (
        get_instance_driver,
        get_project_sa_instances_for_project,
        update_project_sa_instance,
    )
    from app.services.instance_service import InstanceService

    project = get_project(project_id)
    if not project:
        raise ValueError(f"team_topology: project {project_id} not found")

    team_id = project.get("owner_team_id")
    if not team_id:
        raise ValueError(f"team_topology: project {project_id} has no owner_team_id")

    # PITFALL 1 — existence check FIRST (SA creation is not constraint-deduped).
    existing_instances = get_project_sa_instances_for_project(project_id)
    if existing_instances:
        status = "skipped"
        detail_prefix = "instances already present"
        instances = existing_instances
    else:
        created = InstanceService.create_team_instances(project_id, team_id)
        if not created:
            raise RuntimeError(
                f"team_topology: create_team_instances returned no result for "
                f"project={project_id} team={team_id}"
            )
        status = "ok"
        detail_prefix = "instances created"
        instances = get_project_sa_instances_for_project(project_id)

    # PITFALL 2 — reconcile driver='grd' on EVERY SA instance (runs on both
    # the create and the skip path so re-runs converge to driver=grd).
    for inst in instances:
        if get_instance_driver(inst["id"]) != "grd":
            update_project_sa_instance(inst["id"], driver="grd")

    return StepResult("team_topology", status, f"{detail_prefix}: {len(instances)} SA instances")


# forge-creator (forge_creator_seed.BUNDLE_NAME) is the guaranteed floor —
# always bound. Language-specific bundles are bound only when actually seeded.
_FORGE_CREATOR_BUNDLE = "forge-creator"
_LANGUAGE_BUNDLE_MAP: dict[str, str] = {
    "python": "forge-python",
    "typescript": "forge-typescript",
}


def _select_bundles_for_stack(stack_md_text: Optional[str]) -> list[str]:
    """Pure STACK.md → ordered bundle-name list (P3 tailoring surface).

    Always emits the ``forge-creator`` floor first. Parses the ``## Languages``
    section of STACK.md; for each recognized language (case-insensitive
    substring match against the section lines) appends its language-keyed
    bundle name from a small static map. Dedups while preserving order.
    ``None``/missing STACK.md → ``["forge-creator"]`` only.
    """
    names: list[str] = [_FORGE_CREATOR_BUNDLE]
    if not stack_md_text:
        return names

    # Slice the "## Languages" section: from its heading to the next "## ".
    lines = stack_md_text.splitlines()
    in_languages = False
    section: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_languages = stripped[3:].strip().lower() == "languages"
            continue
        if in_languages:
            section.append(line)
    section_text = "\n".join(section).lower()

    for language, bundle_name in _LANGUAGE_BUNDLE_MAP.items():
        if language in section_text and bundle_name not in names:
            names.append(bundle_name)
    return names


def _read_stack_md(local_path: Optional[str]) -> Optional[str]:
    """Read ``<local_path>/.planning/codebase/STACK.md`` (None when absent)."""
    if not local_path:
        return None
    stack_path = os.path.join(local_path, ".planning", "codebase", "STACK.md")
    try:
        with open(stack_path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _step_bundle_binding(project_id: str, existing_row: Optional[dict]) -> StepResult:
    """Step c — project-tailored forge-bundle binding (REQ-21 tailoring).

    Parses STACK.md ``## Languages`` to a bundle-name list via the pure
    :func:`_select_bundles_for_stack`. Always binds the ``forge-creator``
    floor; binds a language-specific bundle ONLY when it is actually seeded
    (``get_forge_bundle_by_name`` returns a row). Binding goes exclusively
    through ``bind_bundle_to_project`` (delegating to the idempotent
    ``upsert_binding``) — DELETE/unbind paths are NEVER called (SC4). Re-runs
    upsert the same rows, so no duplicate bindings.
    """
    from app.db.forge_bundles import bind_bundle_to_project, get_forge_bundle_by_name

    project = get_project(project_id)
    if not project:
        raise ValueError(f"bundle_binding: project {project_id} not found")

    stack_text = _read_stack_md(project.get("local_path"))
    names = _select_bundles_for_stack(stack_text)

    bound: list[str] = []
    for name in names:
        bundle = get_forge_bundle_by_name(name)
        if bundle is None:
            # Language-specific bundle not seeded → skip silently. forge-creator
            # is guaranteed by the seed, so a missing floor is a hard failure.
            if name == _FORGE_CREATOR_BUNDLE:
                raise RuntimeError("bundle_binding: forge-creator bundle is not seeded")
            continue
        bind_bundle_to_project(project_id, bundle["id"])  # idempotent upsert
        bound.append(name)

    return StepResult("bundle_binding", "ok", f"bound: {', '.join(bound)}")


def _step_tesserae_enable(project_id: str, existing_row: Optional[dict]) -> StepResult:
    """Step d — enable per-project Tesserae via the idempotent set path.

    Resolves the Tesserae root to the project's ``local_path`` and calls
    ``set_tesserae_root`` (tesserae_integration:103) — explicitly idempotent
    and also best-effort binds the per-project Tesserae MCP server. Reconcile:
    if ``get_tesserae_root`` already returns the same resolved root, return
    ``skipped``; otherwise ``ok``. ``unset_tesserae_root_bindings`` is NEVER
    called (SC4 / P2).
    """
    from pathlib import Path

    from app.services.tesserae_integration import get_tesserae_root, set_tesserae_root

    project = get_project(project_id)
    if not project:
        raise ValueError(f"tesserae_enable: project {project_id} not found")

    local_path = project.get("local_path")
    if not local_path:
        raise ValueError(f"tesserae_enable: project {project_id} has no local_path")

    root = Path(local_path)
    existing_root = get_tesserae_root(project_id)
    already_set = existing_root is not None and existing_root == root.resolve()

    set_tesserae_root(project_id, root)  # idempotent

    if already_set:
        return StepResult("tesserae_enable", "skipped", f"tesserae root already {root.resolve()}")
    return StepResult("tesserae_enable", "ok", f"tesserae root set to {root.resolve()}")


def _default_autonomy_policy() -> "AutonomyPolicy":
    """The dual-consumer default policy row (RESEARCH Seam 5 / Open Question 1).

    A SINGLE ``project_autonomy_config`` row is read by two consumers:

    1. ``repeated_request_gate._auto_apply_policy`` — needs ``enabled=True`` to
       turn takeaway auto-apply ON (skill-from-repetition / ``discovered_procedure``).
    2. ``harness_autonomy.autonomous_apply_eligible`` — must stay conservative.

    Resolved with one row: ``enabled=True`` arms auto-apply, while
    ``allowed_kinds=["discovered_procedure"]`` (excluding ``rule``/``hook``),
    ``block_deletes=True`` and ``max_ops_per_round=1`` keep evolution autonomy
    cautious — rule/hook evolution patches are gate-blocked, deletes are
    blocked, and blast radius is capped at one op per round.
    ``confidence_threshold`` and ``rate_limit_per_day`` keep their conservative
    model defaults (0.85 / 10).
    """
    from app.models.autonomy_policy import AutonomyPolicy

    return AutonomyPolicy(
        enabled=True,
        allowed_kinds=["discovered_procedure"],
        block_deletes=True,
        max_ops_per_round=1,
    )


def _step_default_policies(project_id: str, existing_row: Optional[dict]) -> StepResult:
    """Step e — write the dual-consumer default autonomy policy (P7 / Seam 5).

    Upserts the single ``project_autonomy_config`` row via the idempotent
    ``upsert_policy`` (ON CONFLICT(project_id) DO UPDATE — one row on re-run,
    never a DELETE; SC4). Reconcile: if ``get_policy`` already equals the target
    return ``skipped``, else ``ok``. The row satisfies BOTH gate readers:
    ``_auto_apply_policy`` returns True (takeaway auto-apply ON), while
    ``autonomous_apply_eligible`` stays conservative (allowed_kinds excludes
    rule/hook, block_deletes on, max_ops_per_round=1).
    """
    from app.db.project_autonomy_config import get_policy, upsert_policy

    target = _default_autonomy_policy()
    current = get_policy(project_id)
    if current is not None and current == target:
        return StepResult(
            "default_policies",
            "skipped",
            "autonomy policy already at dual-consumer default",
        )

    upsert_policy(project_id, target)
    return StepResult(
        "default_policies",
        "ok",
        "autonomy policy set: enabled, allowed_kinds=['discovered_procedure'], "
        "block_deletes, max_ops_per_round=1",
    )


def _step_materialize_compile(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("materialize_compile", "ok")


# Dispatch table — the seam wave-2 plans rebind per step.
TeamHarnessSetupService._STEP_FUNCS: dict[str, Callable[[str, Optional[dict]], StepResult]] = {
    "grd_init": _step_grd_init,
    "team_topology": _step_team_topology,
    "bundle_binding": _step_bundle_binding,
    "tesserae_enable": _step_tesserae_enable,
    "default_policies": _step_default_policies,
    "materialize_compile": _step_materialize_compile,
}
