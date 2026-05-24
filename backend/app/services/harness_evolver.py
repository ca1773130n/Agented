"""Codex-driven, project-scoped harness evolution (post-pivot).

Replaces the previous parallel-IR design. The evolution loop now reads the
project's bound Forge primitives (rules / hooks / commands / mcp_servers),
gives Codex a workspace mirroring those primitives, parses Codex's edits
back into Forge CRUD operations, and applies them via the existing Forge
repos.

Scope of automatic evolution:
    - rules        — H3 Environment Contract suggestions
    - hooks        — H2 Action Realization (PreToolUse) +
                     H4 Trajectory Regulation (PostToolUse / Stop)
    - commands     — H5-shaped operator shortcuts
    - mcp_servers  — tool-registry additions

Skills create/update is deferred — the ``.claude/skills/<name>/SKILL.md``
filesystem layout needs more than a single repo call. Codex can still
*propose* skill changes; validate_patch flags them as unsupported and the
operator handles them manually.

Reference: arXiv 2605.22166 §5.2 Evolution Dynamics.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.db import harness_annotations as annotations_repo
from app.db import harness_evolution as evolution_repo
from app.db import harness_snapshots as snapshots_repo
from app.db import project_forge_bindings as bindings_repo
from app.db.commands import (
    create_command,
    delete_command,
    get_command,
    update_command,
)
from app.db.hooks import create_hook, delete_hook, get_hook, update_hook
from app.db.mcp_servers import (
    create_mcp_server,
    delete_mcp_server,
    get_mcp_server,
    update_mcp_server,
)
from app.db.rules import create_rule, delete_rule, get_rule, update_rule

logger = logging.getLogger(__name__)


# Forge "kinds" the evolver can read + write today. Skills are deferred
# because they need filesystem materialization in ``.claude/skills/``.
WRITABLE_KINDS = ("rule", "hook", "command", "mcp_server")
READABLE_KINDS = ("rule", "skill", "hook", "command", "mcp_server")

_HOOK_EVENTS = {
    "PreToolUse", "PostToolUse", "Stop", "Notification",
    "SubagentStop", "PreCompact",
}


# --------------------------------------------------------------------------
# Rate limit (unchanged from pre-pivot, except keyed on project_id)
# --------------------------------------------------------------------------

def _default_min_interval_hours() -> int:
    raw = os.environ.get("AGENTED_EVOLUTION_MIN_INTERVAL_HOURS", "24")
    try:
        return max(0, int(raw))
    except ValueError:
        return 24


def _check_rate_limit(
    project_id: str, min_interval_hours: int,
) -> Optional[str]:
    if min_interval_hours <= 0:
        return None
    recent = evolution_repo.list_for_project(project_id, limit=1)
    if not recent:
        return None
    last = recent[0]
    started = last.get("started_at")
    if not started:
        return None
    parsed = _parse_sqlite_dt(started)
    if parsed is None:
        return None
    elapsed = datetime.now(timezone.utc) - parsed
    if elapsed < timedelta(hours=min_interval_hours):
        remaining = timedelta(hours=min_interval_hours) - elapsed
        return (
            f"rate-limited: last round at {started} "
            f"(<{min_interval_hours}h ago, "
            f"~{int(remaining.total_seconds() // 60)}m remaining); "
            f"pass force=True or AGENTED_EVOLUTION_MIN_INTERVAL_HOURS=0 to override"
        )
    return None


def _parse_sqlite_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.replace("T", " ").replace("Z", "")
    try:
        return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Result + patch dataclasses
# --------------------------------------------------------------------------

@dataclass
class PatchEntry:
    """One change Codex proposed against a Forge primitive."""
    op: str                          # 'create' | 'update' | 'delete'
    kind: str                        # rule / hook / command / mcp_server / skill
    name: str
    existing_asset_id: Optional[Any] = None  # INTEGER for most kinds, TEXT for mcp_server
    payload: Optional[dict] = None


@dataclass
class EvolutionPatch:
    entries: list[PatchEntry] = field(default_factory=list)
    notes: str = ""


@dataclass
class EvolutionResult:
    round_id: str
    status: str                              # 'applied' | 'awaiting_approval' | 'failed' | 'aborted'
    applied_asset_ids: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    notes: str = ""


# --------------------------------------------------------------------------
# Embedded design guide + prompt
# --------------------------------------------------------------------------

_DESIGN_GUIDE = """# Life-Harness Design Guide (Forge edition)

Reference: arXiv 2605.22166 (CC BY 4.0). Forge is Agented's harness-primitive
registry; this guide names the per-primitive intent so Codex can map the
paper's four layers to concrete Forge tables.

## Forge primitives Codex can edit

- **rules**       — H3 Environment Contract. Stable, system-prompt-overlay
                    text injected before every turn. Use for "the API uses
                    snake_case", "PRs need test coverage", etc.
- **hooks**       — H2 (PreToolUse) and H4 (PostToolUse / Stop). Each hook
                    has a shell-command ``content`` and an ``event`` from
                    {PreToolUse, PostToolUse, Stop, Notification,
                    SubagentStop, PreCompact}.
- **commands**    — Slash-command shortcuts. Useful when a recurring
                    procedural skill should be invocable explicitly.
- **mcp_servers** — Tool registry. Add a new MCP server when the agent
                    keeps failing because it lacks a tool it needs.

Skills (``.claude/skills/<name>/SKILL.md``) need filesystem materialization
and are *not* auto-evolved by this loop — propose them in NOTES.md but
don't add files for them.

## Workspace layout

    forge/
      rules/<name>.json
      hooks/<name>.json
      commands/<name>.json
      mcp_servers/<name>.json
      skills/<name>.json      (read-only — do not edit)
    trajectories/<exec_id>.json
    DESIGN_GUIDE.md            (this file — read-only)
    PROMPT.md                  (your task)
    NOTES.md                   (write your rationale here)

## Editing rules

- **Add** a new primitive: create a fresh ``forge/<kind>/<name>.json`` file
  with the payload. Leave ``id: null``.
- **Modify** an existing primitive: edit its ``payload`` in place; keep
  ``id`` and the filename the same.
- **Remove**: delete the file.

## Priority of failure annotation (Appendix A.1)

    h2 (interface) → h3 (contract) → h4 (degeneration) → general (reasoning)

Higher priority blocks classification at lower priority. Map each cluster
to the right Forge primitive type before proposing edits.
"""


_PROMPT_TEMPLATE = """# Task
Improve the Life-Harness for **project `{project_id}`** by analysing recent
failed trajectories and editing the Forge primitives under ``forge/``.

# Inputs
- ``forge/rules/*.json``, ``forge/hooks/*.json``, ``forge/commands/*.json``,
  ``forge/mcp_servers/*.json``: the current Forge primitives bound to this
  project. Each file is one primitive; the filename is its name.
- ``forge/skills/*.json``: read-only view of bound skills. Skill changes
  are not auto-applied — propose them in NOTES.md only.
- ``trajectories/*.json``: per-execution outcome + ``primary_layer`` +
  incidents + ``active_bindings``.
- ``DESIGN_GUIDE.md``: four-layer principles + editing rules.

# Your task
1. Group failed trajectories by ``primary_layer``.
2. For each cluster, decide which Forge primitive type addresses it (h2/h4
   → hooks; h3 → rules; tool gaps → mcp_servers; recurring procedures →
   commands).
3. Edit ``forge/<kind>/<name>.json`` files following the rules in
   ``DESIGN_GUIDE.md``.
4. Write your rationale to ``NOTES.md`` (what changed, why, and any skill
   suggestions for the operator to apply manually).

Do NOT edit ``DESIGN_GUIDE.md``, ``PROMPT.md``, or anything in
``trajectories/`` / ``forge/skills/``.
"""


# --------------------------------------------------------------------------
# Step 1 — gather inputs
# --------------------------------------------------------------------------

def gather_inputs(
    project_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Read the project's bound Forge primitives + recent trajectories."""
    bindings = bindings_repo.list_bindings(project_id, enabled_only=True)

    # Resolve every binding to its underlying Forge row so the workspace
    # contains the actual payload (not just the asset id).
    primitives: dict[str, list[dict]] = {k: [] for k in READABLE_KINDS}
    for b in bindings:
        kind = b["kind"]
        if kind not in primitives:
            continue
        asset = _fetch_primitive(kind, b["asset_id"])
        if asset is None:
            continue
        primitives[kind].append({
            "binding_id": b["id"],
            "position": b["position"],
            "role": b.get("role"),
            "asset": asset,
        })

    snapshots = snapshots_repo.list_for_project(project_id, limit=limit * 2)
    if since:
        snapshots = [s for s in snapshots if s["created_at"] >= since]
    if until:
        snapshots = [s for s in snapshots if s["created_at"] <= until]
    snapshots = snapshots[:limit]

    trajectories = []
    for snap in snapshots:
        exec_id = snap["execution_id"]
        annotation = annotations_repo.get_annotation(exec_id)
        incidents = annotations_repo.list_incidents(exec_id)
        trajectories.append({
            "execution_id": exec_id,
            "bundle_hash": snap.get("bundle_hash"),
            "active_bindings": snap.get("resolved_bindings") or [],
            "outcome": (annotation or {}).get("outcome"),
            "primary_layer": (annotation or {}).get("primary_layer"),
            "incident_count": (annotation or {}).get("incident_count", 0),
            "incidents": incidents,
            "snapshot_taken_at": snap.get("created_at"),
        })

    return {
        "project_id": project_id,
        "primitives": primitives,
        "trajectories": trajectories,
    }


def _fetch_primitive(kind: str, asset_id: Any) -> Optional[dict]:
    try:
        if kind == "rule":
            return get_rule(int(asset_id))
        if kind == "hook":
            return get_hook(int(asset_id))
        if kind == "command":
            return get_command(int(asset_id))
        if kind == "mcp_server":
            return get_mcp_server(str(asset_id))
        if kind == "skill":
            # skills are read-only here; defer the import so a missing
            # repo function (older deployments) doesn't break workspace
            # build.
            from app.db.skills import get_user_skill
            return get_user_skill(int(asset_id))
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# Step 2 — workspace builder
# --------------------------------------------------------------------------

def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)


def _payload_for_kind(kind: str, asset: dict) -> dict:
    """Project the Forge row into the JSON shape Codex sees in the workspace.

    We deliberately exclude DB-internal fields (timestamps, source_path)
    so a diff of the workspace cleanly maps to user-meaningful changes.
    """
    common = {"id": asset.get("id"), "name": asset.get("name")}
    if kind == "rule":
        return {**common, "payload": {
            "description": asset.get("description"),
            "rule_type": asset.get("rule_type"),
            "condition": asset.get("condition"),
            "action": asset.get("action"),
            "enabled": bool(asset.get("enabled", 1)),
        }}
    if kind == "hook":
        return {**common, "payload": {
            "event": asset.get("event"),
            "description": asset.get("description"),
            "content": asset.get("content"),
            "enabled": bool(asset.get("enabled", 1)),
        }}
    if kind == "command":
        return {**common, "payload": {
            "description": asset.get("description"),
            "content": asset.get("content"),
            "arguments": asset.get("arguments"),
            "enabled": bool(asset.get("enabled", 1)),
        }}
    if kind == "mcp_server":
        return {**common, "payload": {
            "description": asset.get("description"),
            "server_type": asset.get("server_type"),
            "command": asset.get("command"),
            "args": asset.get("args"),
            "env_json": asset.get("env_json"),
            "url": asset.get("url"),
            "enabled": bool(asset.get("enabled", 1)),
        }}
    if kind == "skill":
        return {**common, "payload": {
            "description": asset.get("description"),
            "content": asset.get("content"),
        }, "_read_only": True}
    return {**common, "payload": asset}


def build_workspace(inputs: dict[str, Any], scratch_dir: Path) -> Path:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    (scratch_dir / "forge").mkdir(exist_ok=True)
    (scratch_dir / "trajectories").mkdir(exist_ok=True)
    for kind in READABLE_KINDS:
        (scratch_dir / "forge" / f"{kind}s").mkdir(exist_ok=True)

    for kind in READABLE_KINDS:
        target_dir = scratch_dir / "forge" / f"{kind}s"
        for entry in inputs["primitives"][kind]:
            asset = entry["asset"]
            payload = _payload_for_kind(kind, asset)
            fname = _safe_filename(str(asset.get("name") or asset.get("id") or "unnamed"))
            (target_dir / f"{fname}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    for traj in inputs["trajectories"]:
        safe = _safe_filename(traj["execution_id"])
        (scratch_dir / "trajectories" / f"{safe}.json").write_text(
            json.dumps(traj, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    (scratch_dir / "DESIGN_GUIDE.md").write_text(_DESIGN_GUIDE, encoding="utf-8")
    (scratch_dir / "PROMPT.md").write_text(
        _PROMPT_TEMPLATE.format(project_id=inputs["project_id"]),
        encoding="utf-8",
    )
    (scratch_dir / "NOTES.md").write_text("", encoding="utf-8")

    return scratch_dir


# --------------------------------------------------------------------------
# Step 3 — Codex invocation (mockable)
# --------------------------------------------------------------------------

def _default_codex_cmd() -> list[str]:
    raw = os.environ.get("AGENTED_CODEX_CMD")
    if raw:
        try:
            return shlex.split(raw)
        except ValueError:
            logger.warning("AGENTED_CODEX_CMD malformed; using default")
    return ["codex", "exec", "--auto", "--prompt-file", "PROMPT.md"]


def _run_codex_in_workspace(scratch_dir: Path, *, timeout: int = 600) -> None:
    cmd = _default_codex_cmd()
    logger.info("harness_evolver: invoking codex in %s: %s", scratch_dir, cmd)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(scratch_dir),
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"codex CLI not found ({cmd[0]}); set AGENTED_CODEX_CMD"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"codex CLI timed out after {timeout}s"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"codex CLI exited {result.returncode}: "
            f"{(result.stderr or '')[:500]}"
        )


# --------------------------------------------------------------------------
# Step 4 — patch parser
# --------------------------------------------------------------------------

def parse_patch(
    scratch_dir: Path,
    inputs: dict[str, Any],
    *,
    notes: str = "",
) -> EvolutionPatch:
    """Diff before/after by scanning the workspace's ``forge/<kind>s/`` dirs.

    Skills are intentionally NOT diffed for create/update — they're
    read-only in the workspace. Only delete-by-removal would be detectable
    but we skip skill deletes too (operators manage them via the existing
    skill UI).
    """
    patch = EvolutionPatch(notes=notes)

    # Build "before" lookups keyed by filename so the diff is filesystem-
    # native rather than name-mangled.
    before_by_kind: dict[str, dict[str, dict]] = {
        k: {} for k in READABLE_KINDS
    }
    for kind in READABLE_KINDS:
        for entry in inputs["primitives"][kind]:
            asset = entry["asset"]
            fname = _safe_filename(str(asset.get("name") or asset.get("id") or "unnamed"))
            before_by_kind[kind][fname] = _payload_for_kind(kind, asset)

    for kind in WRITABLE_KINDS:
        kind_dir = scratch_dir / "forge" / f"{kind}s"
        if not kind_dir.exists():
            continue

        after_files: dict[str, dict] = {}
        for child in kind_dir.iterdir():
            if not child.is_file() or child.suffix != ".json":
                continue
            try:
                after_files[child.stem] = json.loads(child.read_text())
            except (OSError, json.JSONDecodeError):
                continue

        # Create / update
        for fname, after in after_files.items():
            payload = after.get("payload") or {}
            name = str(after.get("name") or fname)
            ent_id = after.get("id")
            before = before_by_kind[kind].get(fname)

            if before is None or ent_id in (None, "null"):
                patch.entries.append(PatchEntry(
                    op="create", kind=kind, name=name, payload=payload,
                ))
                continue
            if (before.get("payload") or {}) == payload:
                continue
            patch.entries.append(PatchEntry(
                op="update", kind=kind, name=name,
                existing_asset_id=before.get("id"),
                payload=payload,
            ))

        # Delete: files in before but missing in after.
        for fname, before in before_by_kind[kind].items():
            if fname in after_files:
                continue
            patch.entries.append(PatchEntry(
                op="delete", kind=kind, name=str(before.get("name") or fname),
                existing_asset_id=before.get("id"),
            ))

    return patch


# --------------------------------------------------------------------------
# Step 5 — validation
# --------------------------------------------------------------------------

def validate_patch(patch: EvolutionPatch) -> list[str]:
    problems: list[str] = []
    for i, entry in enumerate(patch.entries):
        prefix = f"entry[{i}] ({entry.op}, {entry.kind}, {entry.name!r})"
        if entry.kind not in WRITABLE_KINDS:
            problems.append(
                f"{prefix}: {entry.kind!r} is not an auto-evolvable Forge kind "
                f"(allowed: {list(WRITABLE_KINDS)})"
            )
            continue
        if entry.op in ("create", "update"):
            if not isinstance(entry.payload, dict):
                problems.append(f"{prefix}: payload must be an object")
                continue
            problems.extend(_validate_payload(entry.kind, entry.payload, prefix))
        if entry.op in ("update", "delete") and entry.existing_asset_id is None:
            problems.append(f"{prefix}: missing existing_asset_id")
    return problems


def _validate_payload(kind: str, payload: dict, prefix: str) -> list[str]:
    problems: list[str] = []
    if kind == "hook":
        event = payload.get("event")
        if not event:
            problems.append(f"{prefix}: hook.event is required")
        elif event not in _HOOK_EVENTS:
            problems.append(
                f"{prefix}: unknown hook event {event!r}; "
                f"allowed: {sorted(_HOOK_EVENTS)}"
            )
        if not payload.get("content"):
            problems.append(f"{prefix}: hook.content is required")
    elif kind == "rule":
        if not payload.get("description") and not payload.get("action"):
            problems.append(
                f"{prefix}: rule needs at least description or action"
            )
    elif kind == "command":
        if not payload.get("content"):
            problems.append(f"{prefix}: command.content is required")
    elif kind == "mcp_server":
        if not (payload.get("command") or payload.get("url")):
            problems.append(
                f"{prefix}: mcp_server needs command (stdio) or url (http)"
            )
    return problems


# --------------------------------------------------------------------------
# Step 6 — applier
# --------------------------------------------------------------------------

def apply_patch(patch: EvolutionPatch, project_id: str) -> list[dict]:
    """Apply each patch entry against the appropriate Forge repo, and bind
    new primitives to the project. Returns ``[{kind, asset_id, op}, ...]``."""
    applied: list[dict] = []
    for entry in patch.entries:
        kind = entry.kind
        payload = entry.payload or {}

        if entry.op == "create":
            asset_id = _create_dispatch[kind](
                name=entry.name, payload=payload, project_id=project_id,
            )
            if asset_id is None:
                continue
            try:
                bindings_repo.add_binding(
                    project_id, kind, str(asset_id),
                )
            except Exception:
                logger.warning(
                    "apply_patch: bind failed for %s %s",
                    kind, asset_id, exc_info=True,
                )
            applied.append({"kind": kind, "op": "create", "asset_id": asset_id})

        elif entry.op == "update":
            _update_dispatch[kind](
                asset_id=entry.existing_asset_id, payload=payload,
            )
            applied.append({
                "kind": kind, "op": "update",
                "asset_id": entry.existing_asset_id,
            })

        elif entry.op == "delete":
            _delete_dispatch[kind](asset_id=entry.existing_asset_id)
            applied.append({
                "kind": kind, "op": "delete",
                "asset_id": entry.existing_asset_id,
            })

    return applied


def _create_rule(*, name, payload, project_id):
    return create_rule(
        name=name,
        rule_type=payload.get("rule_type", "validation"),
        description=payload.get("description"),
        condition=payload.get("condition"),
        action=payload.get("action"),
        enabled=bool(payload.get("enabled", True)),
        project_id=project_id,
    )


def _create_hook(*, name, payload, project_id):
    return create_hook(
        name=name,
        event=payload["event"],
        description=payload.get("description"),
        content=payload.get("content"),
        enabled=bool(payload.get("enabled", True)),
        project_id=project_id,
    )


def _create_command(*, name, payload, project_id):
    return create_command(
        name=name,
        description=payload.get("description"),
        content=payload.get("content"),
        arguments=payload.get("arguments"),
        enabled=bool(payload.get("enabled", True)),
        project_id=project_id,
    )


def _create_mcp_server(*, name, payload, project_id):
    # MCP servers are global; the binding is what scopes them to a project.
    from app.db.ids import generate_id
    server_id = generate_id("mcp")
    create_mcp_server(
        name=name,
        description=payload.get("description"),
        server_type=payload.get("server_type", "stdio"),
        command=payload.get("command"),
        args=payload.get("args"),
        env_json=payload.get("env_json"),
        url=payload.get("url"),
    )
    # ``create_mcp_server`` doesn't return the id; we have to look it up.
    return _find_mcp_server_id_by_name(name) or server_id


def _find_mcp_server_id_by_name(name: str) -> Optional[str]:
    try:
        from app.db.mcp_servers import get_all_mcp_servers
        for row in get_all_mcp_servers():
            if row.get("name") == name:
                return row["id"]
    except Exception:
        pass
    return None


def _update_rule(*, asset_id, payload):
    update_rule(rule_id=int(asset_id), **{
        k: v for k, v in payload.items()
        if k in ("name", "description", "rule_type", "condition", "action", "enabled")
    })


def _update_hook(*, asset_id, payload):
    update_hook(hook_id=int(asset_id), **{
        k: v for k, v in payload.items()
        if k in ("name", "event", "description", "content", "enabled")
    })


def _update_command(*, asset_id, payload):
    update_command(command_id=int(asset_id), **{
        k: v for k, v in payload.items()
        if k in ("name", "description", "content", "arguments", "enabled")
    })


def _update_mcp_server(*, asset_id, payload):
    update_mcp_server(str(asset_id), **{
        k: v for k, v in payload.items()
        if k in ("name", "description", "server_type", "command", "args",
                 "env_json", "url", "enabled")
    })


_create_dispatch = {
    "rule": _create_rule,
    "hook": _create_hook,
    "command": _create_command,
    "mcp_server": _create_mcp_server,
}

_update_dispatch = {
    "rule": _update_rule,
    "hook": _update_hook,
    "command": _update_command,
    "mcp_server": _update_mcp_server,
}

_delete_dispatch = {
    "rule": lambda *, asset_id: delete_rule(int(asset_id)),
    "hook": lambda *, asset_id: delete_hook(int(asset_id)),
    "command": lambda *, asset_id: delete_command(int(asset_id)),
    "mcp_server": lambda *, asset_id: delete_mcp_server(str(asset_id)),
}


# --------------------------------------------------------------------------
# Step 7 — orchestrators
# --------------------------------------------------------------------------

def run_evolution_round(
    project_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
    keep_scratch_on_failure: bool = True,
    dry_run: bool = False,
    min_interval_hours: Optional[int] = None,
    force: bool = False,
) -> EvolutionResult:
    if not force:
        interval = (
            min_interval_hours
            if min_interval_hours is not None
            else _default_min_interval_hours()
        )
        reason = _check_rate_limit(project_id, interval)
        if reason:
            return EvolutionResult(
                round_id="", status="aborted", error=reason,
            )

    inputs = gather_inputs(project_id, since=since, until=until, limit=limit)

    _tmp_root = "/tmp" if os.path.isdir("/tmp") else tempfile.gettempdir()
    scratch = Path(tempfile.mkdtemp(
        prefix="agented-harness-evolution-", dir=_tmp_root,
    ))

    round_id = evolution_repo.start_round(
        project_id=project_id,
        input_window_since=since,
        input_window_until=until,
        input_execution_count=len(inputs["trajectories"]),
        input_forge=_summarize_primitives(inputs["primitives"]),
        scratch_dir=str(scratch),
    )

    try:
        evolution_repo.mark_running(round_id)
        build_workspace(inputs, scratch)
        _run_codex_in_workspace(scratch)

        notes_path = scratch / "NOTES.md"
        notes = notes_path.read_text() if notes_path.exists() else ""

        patch = parse_patch(scratch, inputs, notes=notes)
        problems = validate_patch(patch)
        if problems:
            joined = "; ".join(problems[:5])
            evolution_repo.mark_failed(
                round_id,
                error_message=f"patch validation failed: {joined}",
                output_patch=_patch_to_dict(patch),
            )
            return EvolutionResult(
                round_id=round_id, status="failed",
                error=f"patch validation failed: {joined}",
                notes=notes,
            )

        if dry_run:
            evolution_repo.mark_awaiting_approval(
                round_id,
                output_patch=_patch_to_dict(patch),
                notes=notes,
            )
            return EvolutionResult(
                round_id=round_id, status="awaiting_approval",
                notes=notes,
            )

        applied = apply_patch(patch, project_id)
        evolution_repo.mark_applied(
            round_id,
            output_patch=_patch_to_dict(patch),
            applied_asset_ids=applied,
            notes=notes,
        )

        if not keep_scratch_on_failure:
            shutil.rmtree(scratch, ignore_errors=True)
        return EvolutionResult(
            round_id=round_id, status="applied",
            applied_asset_ids=applied,
            notes=notes,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("harness_evolver: round %s failed", round_id)
        evolution_repo.mark_failed(round_id, error_message=str(exc))
        return EvolutionResult(
            round_id=round_id, status="failed", error=str(exc),
        )


def apply_dry_run_round(round_id: str) -> EvolutionResult:
    row = evolution_repo.get_round(round_id)
    if row is None:
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"round not found: {round_id}",
        )
    if row["status"] != "awaiting_approval":
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"round is not awaiting approval (status={row['status']!r})",
        )

    patch_data = row.get("output_patch") or {}
    try:
        patch = _patch_from_dict(patch_data)
    except (KeyError, TypeError, ValueError) as exc:
        evolution_repo.mark_failed(
            round_id, error_message=f"stored patch unreadable: {exc}",
        )
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"stored patch unreadable: {exc}",
        )

    try:
        applied = apply_patch(patch, row["project_id"])
    except Exception as exc:  # noqa: BLE001
        evolution_repo.mark_failed(
            round_id, error_message=f"apply failed: {exc}",
        )
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"apply failed: {exc}",
        )

    evolution_repo.mark_applied(
        round_id,
        output_patch=patch_data,
        applied_asset_ids=applied,
        notes=row.get("notes"),
    )
    return EvolutionResult(
        round_id=round_id, status="applied",
        applied_asset_ids=applied,
        notes=row.get("notes") or "",
    )


def abort_dry_run_round(
    round_id: str, *, reason: Optional[str] = None,
) -> EvolutionResult:
    row = evolution_repo.get_round(round_id)
    if row is None:
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"round not found: {round_id}",
        )
    if row["status"] != "awaiting_approval":
        return EvolutionResult(
            round_id=round_id, status="failed",
            error=f"round is not awaiting approval (status={row['status']!r})",
        )
    evolution_repo.mark_aborted(round_id, reason=reason)
    return EvolutionResult(
        round_id=round_id, status="aborted",
        notes=row.get("notes") or "",
    )


def _summarize_primitives(primitives: dict[str, list[dict]]) -> dict[str, Any]:
    return {
        kind: [
            {"binding_id": e["binding_id"], "asset_id": e["asset"].get("id"),
             "name": e["asset"].get("name")}
            for e in entries
        ]
        for kind, entries in primitives.items()
    }


def _patch_to_dict(patch: EvolutionPatch) -> dict[str, Any]:
    return {
        "notes": patch.notes,
        "entries": [
            {
                "op": e.op, "kind": e.kind, "name": e.name,
                "existing_asset_id": e.existing_asset_id,
                "payload": e.payload,
            }
            for e in patch.entries
        ],
    }


def _patch_from_dict(data: dict[str, Any]) -> EvolutionPatch:
    entries = []
    for raw in (data.get("entries") or []):
        entries.append(PatchEntry(
            op=raw["op"],
            kind=raw["kind"],
            name=raw.get("name") or "untitled",
            existing_asset_id=raw.get("existing_asset_id"),
            payload=raw.get("payload"),
        ))
    return EvolutionPatch(entries=entries, notes=data.get("notes") or "")
