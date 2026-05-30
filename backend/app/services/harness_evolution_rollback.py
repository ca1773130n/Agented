"""Phase C2: reverse an applied evolution round (DB ops + git)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.db import harness_evolution as evo_repo
from app.db import project_forge_bindings as bindings_repo
from app.models.harness_evolution import RevertResult

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


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def _later_applied_conflicts(round_row: dict) -> list[dict]:
    """Return conflict entries from later applied rounds touching the same assets."""
    mine = {(e["kind"], str(e["asset_id"])) for e in (round_row.get("apply_journal") or [])}
    out: list[dict] = []
    for other in evo_repo.list_for_project(round_row["project_id"], limit=200):
        if other["id"] == round_row["id"] or other.get("status") != "applied":
            continue
        if (other.get("started_at") or "") <= (round_row.get("started_at") or ""):
            continue
        for e in other.get("apply_journal") or []:
            if (e["kind"], str(e["asset_id"])) in mine:
                out.append({"round_id": other["id"], "kind": e["kind"], "asset_id": e["asset_id"]})
    return out


# ---------------------------------------------------------------------------
# Git helper
# ---------------------------------------------------------------------------


def _git_revert(project_id: str, sha: str) -> bool:
    """Run `git revert --no-edit <sha>` in the project root. Returns True on success.

    Returns False (not an error) when there is no git repo to revert.
    Raises subprocess.CalledProcessError on git failure.
    """
    from app.db.projects import get_project

    proj = get_project(project_id)
    root = (proj or {}).get("local_path") or (proj or {}).get("clone_path")
    if not root or not (Path(root) / ".git").exists():
        return False
    subprocess.run(
        ["git", "revert", "--no-edit", sha],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def revert_round(round_id: str, *, force: bool = False, revert_git: bool = True) -> RevertResult:
    """Orchestrate a full rollback of an applied evolution round.

    Steps:
    1. Validate round exists and is applied.
    2. Check for a non-empty apply journal.
    3. Detect conflicts with later applied rounds (skip when force=True).
    4. Reverse the DB journal entries.
    5. Optionally revert the git commit.
    6. Mark the round as reverted.
    """
    row = evo_repo.get_round(round_id)
    if row is None:
        return RevertResult(status="failed", error="round not found")

    if row.get("status") != "applied":
        return RevertResult(
            status="failed",
            error=f"status is {row.get('status')}, not applied",
        )

    journal = row.get("apply_journal")
    if not journal:
        return RevertResult(
            status="failed",
            error="no apply journal (round predates rollback support)",
        )

    conflicts = _later_applied_conflicts(row)
    if conflicts and not force:
        return RevertResult(
            status="conflict",
            conflicts=conflicts,
            error="later applied round(s) touched the same assets",
        )

    n, failures = reverse_apply_journal(row["project_id"], journal)
    if failures:
        evo_repo.set_revert_error(round_id, f"partial reversal: {len(failures)} op(s) failed")
        return RevertResult(
            status="failed",
            reversed_count=n,
            error="partial DB reversal — see revert_error",
        )

    git_done = False
    sha = row.get("git_commit_sha")
    if revert_git and sha:
        try:
            git_done = _git_revert(row["project_id"], sha)
        except Exception as exc:
            evo_repo.set_revert_error(round_id, f"db reversed but git revert failed: {exc}")
            return RevertResult(
                status="failed",
                reversed_count=n,
                git_reverted=False,
                error="git revert failed (db reversed; see revert_error)",
            )

    evo_repo.mark_reverted(round_id)
    return RevertResult(status="reverted", reversed_count=n, git_reverted=git_done)
