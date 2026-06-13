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

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from app.db.projects import (
    get_harness_setup_steps,
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


def _step_grd_init(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("grd_init", "ok")


def _step_team_topology(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("team_topology", "ok")


def _step_bundle_binding(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("bundle_binding", "ok")


def _step_tesserae_enable(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("tesserae_enable", "ok")


def _step_default_policies(project_id: str, existing_row: Optional[dict]) -> StepResult:
    return StepResult("default_policies", "ok")


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
