"""GRD life-harness round runner — wraps ``gd harness round/status/revert``.

A round gathers Tesserae Session findings, proposes ONE eval-gated patch to
GRD's primitives, and records the outcome under
``.planning/harness/rounds/<round_id>/``. It can take a while (it spawns a
proposer agent), so ``run_round`` launches it on a daemon thread and mirrors the
result into ``grd_harness_rounds`` on completion. The frontend polls the rounds
list (rounds are discrete, infrequent — no SSE session to attach to).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from typing import Optional

from app.db.grd_harness_rounds import upsert_harness_round
from app.services.grd_cli_service import GrdCliService

logger = logging.getLogger(__name__)

_ROUND_TIMEOUT_SECONDS = 1800  # a round spawns a proposer agent — allow 30 min


def _read_json_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _finalize_round(project_id: str, cwd: str, stdout: str, returncode: int) -> str:
    """Parse a ``gd harness round`` RoundRecord (stdout) + enrich from the
    on-disk round dir, then mirror to ``grd_harness_rounds``. Returns the
    mirror id. Never raises."""
    record = None
    try:
        text = (stdout or "").strip()
        record = json.loads(text) if text else None
    except json.JSONDecodeError:
        record = None

    if not isinstance(record, dict) or not record.get("round_id"):
        # Subprocess produced no parseable record — log a single error row.
        return upsert_harness_round(
            project_id=project_id,
            round_id="error",
            status="error",
            detail=((stdout or "")[-500:]) or f"exit code {returncode}",
        )

    round_id = record["round_id"]
    rounds_dir = os.path.join(cwd, ".planning", "harness", "rounds", round_id)
    patch_json = _read_json_text(os.path.join(rounds_dir, "patch.json"))
    eval_disk = _read_json_text(os.path.join(rounds_dir, "eval.json"))

    patch: dict = {}
    if patch_json:
        try:
            patch = json.loads(patch_json) or {}
        except json.JSONDecodeError:
            patch = {}

    eval_report = record.get("eval_report")
    eval_json = json.dumps(eval_report) if eval_report is not None else eval_disk

    return upsert_harness_round(
        project_id=project_id,
        round_id=round_id,
        status=record.get("status") or "unknown",
        detail=record.get("detail"),
        evidence_count=record.get("evidence_count"),
        patch_hash=record.get("patch_hash"),
        confidence=patch.get("confidence") if isinstance(patch, dict) else None,
        summary=patch.get("summary") if isinstance(patch, dict) else None,
        applied_sha=record.get("applied_sha"),
        eval_json=eval_json,
        patch_json=patch_json or (json.dumps(patch) if patch else None),
    )


def _round_argv(*, auto: bool, dry_run: bool, full_eval: bool) -> list[str]:
    argv = ["harness", "round"]
    if auto:
        argv.append("--auto")
    if dry_run:
        argv.append("--dry-run")
    if full_eval:
        argv.append("--full-eval")
    return argv


def _gd_cmd(extra: list[str]) -> Optional[list[str]]:
    """Build the argv to invoke the resolved gd binary, or None if unavailable."""
    GrdCliService.detect_binaries()
    gd = GrdCliService.gd_path()
    if not gd:
        return None
    base = [gd] if GrdCliService._gd_is_exec else ["node", gd]
    return base + extra


def run_round(
    project_id: str,
    cwd: str,
    *,
    auto: bool = False,
    dry_run: bool = False,
    full_eval: bool = False,
) -> bool:
    """Launch ``gd harness round`` on a daemon thread; mirror the result on
    completion. Returns True if the round was started (gd available)."""
    cmd = _gd_cmd(_round_argv(auto=auto, dry_run=dry_run, full_eval=full_eval))
    if cmd is None:
        return False

    def _worker() -> None:
        try:
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=_ROUND_TIMEOUT_SECONDS
            )
            _finalize_round(project_id, cwd, result.stdout, result.returncode)
        except subprocess.TimeoutExpired:
            upsert_harness_round(
                project_id=project_id, round_id="error", status="error",
                detail=f"round timed out after {_ROUND_TIMEOUT_SECONDS}s",
            )
        except Exception:
            logger.warning("harness round failed for %s", project_id, exc_info=True)
            upsert_harness_round(
                project_id=project_id, round_id="error", status="error",
                detail="round runner crashed (see logs)",
            )

    threading.Thread(target=_worker, daemon=True, name=f"grd-harness-round-{project_id}").start()
    return True


def revert_round(cwd: str, round_id: str) -> dict:
    """Run ``gd harness revert <round-id>``. Returns ``{success, output, error}``."""
    cmd = _gd_cmd(["harness", "revert", round_id])
    if cmd is None:
        return {"success": False, "output": None, "error": "GRD gd binary not available"}
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip(), "error": None}
        return {
            "success": False,
            "output": result.stdout.strip() or None,
            "error": result.stderr.strip() or f"exit code {result.returncode}",
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"success": False, "output": None, "error": str(exc)}


def harness_status(cwd: str) -> dict:
    """Run ``gd harness status`` and return parsed JSON (best-effort)."""
    cmd = _gd_cmd(["harness", "status"])
    if cmd is None:
        return {"success": False, "rounds": [], "error": "GRD gd binary not available"}
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return {"success": False, "rounds": [], "error": result.stderr.strip()}
        out = (result.stdout or "").strip()
        data = json.loads(out) if out else {}
        rounds = data.get("rounds", data) if isinstance(data, dict) else data
        return {"success": True, "rounds": rounds, "error": None}
    except Exception as exc:  # pragma: no cover - defensive
        return {"success": False, "rounds": [], "error": str(exc)}
