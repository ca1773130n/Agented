"""Codex-driven harness evolution loop (T3).

Translates the Life-Harness paper's offline evolution procedure into an
Agented-native workflow::

    1. Gather a recent window of executions for the bot, along with their
       snapshots (which layer versions were active) and annotations (which
       interface layer the failure landed in).
    2. Build a scratch workspace: ``harness.json`` (current layers grouped
       by H2/H3/H4/H5), one ``trajectories/<exec_id>.json`` per execution,
       a ``DESIGN_GUIDE.md``, a ``PROMPT.md``, and an empty ``NOTES.md``.
    3. Invoke Codex CLI on the workspace with auto-edit on. Codex reads
       the design guide + trajectories, edits ``harness.json``, and
       writes its rationale to ``NOTES.md``.
    4. Diff ``harness.json`` before / after to produce a patch
       (create / supersede / disable instructions).
    5. Validate the patch (regex compile, action-kind allowlist).
    6. Apply via the layers repo. Each surviving change comes back with
       its new layer id; we record the round.

Codex invocation is one method (``_run_codex_in_workspace``) so tests can
mock it without spinning up a real CLI. The default argv is configurable
via ``AGENTED_CODEX_CMD``; operators verify it works in their env before
relying on this in production.
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
from app.db import harness_layers as layers_repo
from app.db import harness_snapshots as snapshots_repo

logger = logging.getLogger(__name__)


def _default_min_interval_hours() -> int:
    """Default rate-limit window. Overridable per call via the ``force`` /
    ``min_interval_hours`` kwargs to ``run_evolution_round``."""
    raw = os.environ.get("AGENTED_EVOLUTION_MIN_INTERVAL_HOURS", "24")
    try:
        return max(0, int(raw))
    except ValueError:
        return 24


def _check_rate_limit(
    bot_id: str, min_interval_hours: int,
) -> Optional[str]:
    """Return ``None`` if a new round is allowed, or a human-readable
    blocking reason. Looks at the most recent round regardless of
    outcome — failed and aborted rounds still consumed Codex resources
    and we don't want a runaway retry loop.
    """
    if min_interval_hours <= 0:
        return None
    recent = evolution_repo.list_for_bot(bot_id, limit=1)
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
            f"(<{min_interval_hours}h ago, ~{int(remaining.total_seconds() // 60)}m remaining); "
            f"pass force=True or AGENTED_EVOLUTION_MIN_INTERVAL_HOURS=0 to override"
        )
    return None


def _parse_sqlite_dt(value: str) -> Optional[datetime]:
    """SQLite's ``datetime('now')`` emits ``YYYY-MM-DD HH:MM:SS`` (UTC).
    Tolerate ISO variants and a trailing ``Z``."""
    if not value:
        return None
    cleaned = value.replace("T", " ").replace("Z", "")
    try:
        return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_VALID_LAYERS = ("h2", "h3", "h4", "h5")
_H2_ACTION_KINDS = {"block", "canonicalize", "rescue"}
_H4_DETECTOR_KINDS = {"repeat_action", "stagnation", "budget", "regex_count"}
_H4_RESPONSE_KINDS = {"inject_hint", "abort", "suppress_dup"}


# --------------------------------------------------------------------------
# Result + patch dataclasses
# --------------------------------------------------------------------------

@dataclass
class PatchEntry:
    """One change Codex proposed. ``op`` is computed from before/after."""
    op: str                          # "create" | "supersede" | "disable"
    layer: str                       # h2 | h3 | h4 | h5
    name: str
    existing_layer_id: Optional[str] = None  # for supersede / disable
    payload: Optional[dict] = None           # for create / supersede


@dataclass
class EvolutionPatch:
    entries: list[PatchEntry] = field(default_factory=list)
    notes: str = ""


@dataclass
class EvolutionResult:
    round_id: str
    status: str                              # "applied" | "failed"
    applied_layer_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None
    notes: str = ""


# --------------------------------------------------------------------------
# Design guide — embedded so the round is self-contained
# --------------------------------------------------------------------------

_DESIGN_GUIDE = """# Life-Harness Design Guide

Reference: arXiv 2605.22166 (CC BY 4.0).

The harness adapts the *runtime interface* around a frozen LLM — without
retraining the model or modifying the environment. Four layers, each
addressing a distinct failure mode in deterministic agent loops:

## 1. Environment Contract Layer (h3)
Clarify stable tool, action, policy, and answer-format constraints BEFORE
interaction. Injected as system-prompt overlay text and tool-description
overrides. Fixes "the agent's calling protocol is wrong from turn 1".

## 2. Procedural Skill Layer (h5)
Retrieve compact procedural skills distilled from past successful
trajectories. Injected into the initial system prompt. Each skill is a
short recipe: "when X happens, do Y then Z".

## 3. Action Realization Layer (h2)
Validate model-generated actions BEFORE execution. Either ``block`` actions
that would deterministically fail, ``canonicalize`` malformed inputs into a
valid form, or ``rescue`` an in-content action into a real tool call.
Implemented as PreToolUse hooks.

## 4. Trajectory Regulation Layer (h4)
Monitor post-execution trajectories. Detect non-progressing patterns
(``repeat_action``, ``stagnation``, ``budget``, ``regex_count``) and
respond with ``inject_hint``, ``abort``, or ``suppress_dup``. Implemented
as PostToolUse hooks.

## Priority of failure annotation
When classifying a failed trajectory, check in this order:
  h2 (interface) → h3 (contract) → h4 (degeneration) → general (reasoning).
This prevents later symptoms from hiding earlier interface failures.

## Editing rules
- Adding a new layer rule: append a JSON object WITHOUT an ``id`` field.
- Modifying an existing rule: edit its ``payload`` IN PLACE, keeping its
  ``id`` and ``name`` unchanged.
- Removing a stale rule: delete its entry. The system records this as a
  ``disable`` (the old row stays in the audit log).
"""


_PROMPT_TEMPLATE = """# Task
Improve the harness for bot `{bot_id}` by analysing recent failed
trajectories and editing `harness.json`.

# Inputs
- `harness.json`: current harness, grouped by layer (h2, h3, h4, h5).
- `trajectories/*.json`: one file per recent execution. Each has
  `outcome`, `primary_layer`, `incidents`, `active_layers`, and a stdout
  snippet.
- `DESIGN_GUIDE.md`: the four-layer design principles + edit rules.

# Your task
1. Read every trajectory. Group failures by `primary_layer`.
2. For each cluster, decide: add a new rule, modify an existing rule, or
   remove an obsolete one.
3. Write your edits back to `harness.json`. Follow the edit rules in
   `DESIGN_GUIDE.md`.
4. Add a brief rationale to `NOTES.md` describing what changed and why.

Do NOT edit `DESIGN_GUIDE.md`, `PROMPT.md`, or anything in `trajectories/`.
"""


# --------------------------------------------------------------------------
# Step 1 — gather inputs
# --------------------------------------------------------------------------

def gather_inputs(
    bot_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Return the data we'll lay into the workspace. Pure read; no writes."""
    enabled_layers = layers_repo.list_enabled_for_bot(bot_id)

    # snapshots → narrow set, then enrich with annotation + incidents.
    snapshots = snapshots_repo.list_for_bot(bot_id)
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
            "active_layers": snap.get("layer_versions") or {},
            "outcome": (annotation or {}).get("outcome"),
            "primary_layer": (annotation or {}).get("primary_layer"),
            "incident_count": (annotation or {}).get("incident_count", 0),
            "incidents": incidents,
            "snapshot_taken_at": snap.get("created_at"),
        })

    return {
        "bot_id": bot_id,
        "enabled_layers": enabled_layers,
        "trajectories": trajectories,
    }


# --------------------------------------------------------------------------
# Step 2 — workspace builder
# --------------------------------------------------------------------------

def _group_layers_by_kind(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {k: [] for k in _VALID_LAYERS}
    for r in rows:
        if r["layer"] in out:
            out[r["layer"]].append({
                "id": r["id"],
                "name": r["name"],
                "version": r.get("version", 1),
                "payload": r.get("payload") or {},
            })
    return out


def build_workspace(inputs: dict[str, Any], scratch_dir: Path) -> Path:
    """Materialize the round's inputs into ``scratch_dir``. Returns the dir.

    Caller owns lifecycle: the dir lives until ``apply_patch`` reads from
    it; the round record stores the path so failed rounds are debuggable.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    (scratch_dir / "trajectories").mkdir(exist_ok=True)

    harness = _group_layers_by_kind(inputs["enabled_layers"])
    (scratch_dir / "harness.json").write_text(
        json.dumps(harness, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (scratch_dir / "DESIGN_GUIDE.md").write_text(_DESIGN_GUIDE, encoding="utf-8")
    (scratch_dir / "PROMPT.md").write_text(
        _PROMPT_TEMPLATE.format(bot_id=inputs["bot_id"]),
        encoding="utf-8",
    )
    (scratch_dir / "NOTES.md").write_text("", encoding="utf-8")

    for traj in inputs["trajectories"]:
        exec_id = traj["execution_id"]
        # Sanitize for filesystem; execution ids are already prefixed-random
        # but defence-in-depth never hurts.
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", exec_id)
        (scratch_dir / "trajectories" / f"{safe}.json").write_text(
            json.dumps(traj, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

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
    # Default tries the most conservative form. Operators override via env.
    return ["codex", "exec", "--auto", "--prompt-file", "PROMPT.md"]


def _run_codex_in_workspace(scratch_dir: Path, *, timeout: int = 600) -> None:
    """Spawn Codex CLI inside ``scratch_dir``. Raises ``RuntimeError`` on
    non-zero exit or timeout. Tests monkeypatch this entire function."""
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
    before_harness: dict[str, list[dict]],
    after_harness: dict[str, list[dict]],
    *,
    notes: str = "",
) -> EvolutionPatch:
    """Diff before vs after, classify each entry as create/supersede/disable."""
    patch = EvolutionPatch(notes=notes)

    for layer in _VALID_LAYERS:
        before_entries = before_harness.get(layer) or []
        after_entries = after_harness.get(layer) or []

        before_by_id = {e["id"]: e for e in before_entries if e.get("id")}
        seen_ids: set[str] = set()

        for entry in after_entries:
            ent_id = entry.get("id")
            payload = entry.get("payload") or {}
            name = entry.get("name") or (payload.get("title") or "untitled")

            if not ent_id:
                patch.entries.append(PatchEntry(
                    op="create", layer=layer, name=name, payload=payload,
                ))
                continue

            seen_ids.add(ent_id)
            prior = before_by_id.get(ent_id)
            if prior is None:
                # Codex invented an id that doesn't exist. Treat as create.
                patch.entries.append(PatchEntry(
                    op="create", layer=layer, name=name, payload=payload,
                ))
                continue
            if (prior.get("payload") or {}) == payload:
                continue  # unchanged
            patch.entries.append(PatchEntry(
                op="supersede",
                layer=layer,
                name=name,
                existing_layer_id=ent_id,
                payload=payload,
            ))

        # Anything in before but missing from after → disable.
        for ent_id, prior in before_by_id.items():
            if ent_id in seen_ids:
                continue
            patch.entries.append(PatchEntry(
                op="disable",
                layer=layer,
                name=prior.get("name", "unknown"),
                existing_layer_id=ent_id,
            ))

    return patch


# --------------------------------------------------------------------------
# Step 5 — validation
# --------------------------------------------------------------------------

def validate_patch(patch: EvolutionPatch) -> list[str]:
    """Return a list of human-readable problems. Empty list = patch ok."""
    problems: list[str] = []
    for i, entry in enumerate(patch.entries):
        prefix = f"entry[{i}] ({entry.op}, {entry.layer}, {entry.name!r})"

        if entry.layer not in _VALID_LAYERS:
            problems.append(f"{prefix}: unknown layer")
            continue
        if entry.op in ("create", "supersede"):
            if not isinstance(entry.payload, dict):
                problems.append(f"{prefix}: payload must be an object")
                continue
            problems.extend(_validate_payload(entry.layer, entry.payload, prefix))
        if entry.op in ("supersede", "disable") and not entry.existing_layer_id:
            problems.append(f"{prefix}: missing existing_layer_id")
    return problems


def _validate_payload(layer: str, payload: dict, prefix: str) -> list[str]:
    problems: list[str] = []
    if not payload.get("title"):
        problems.append(f"{prefix}: payload.title is required")

    if layer == "h2":
        for arg, pat in ((payload.get("match") or {}).get("arg_regex") or {}).items():
            try:
                re.compile(pat)
            except re.error as exc:
                problems.append(
                    f"{prefix}: invalid arg_regex[{arg!r}]: {exc}"
                )
        cr = (payload.get("match") or {}).get("content_regex")
        if cr:
            try:
                re.compile(cr)
            except re.error as exc:
                problems.append(f"{prefix}: invalid content_regex: {exc}")
        kind = (payload.get("action") or {}).get("kind")
        if kind and kind not in _H2_ACTION_KINDS:
            problems.append(
                f"{prefix}: unknown action.kind={kind!r}; "
                f"allowed: {sorted(_H2_ACTION_KINDS)}"
            )

    elif layer == "h4":
        dk = (payload.get("detector") or {}).get("kind")
        if dk and dk not in _H4_DETECTOR_KINDS:
            problems.append(
                f"{prefix}: unknown detector.kind={dk!r}; "
                f"allowed: {sorted(_H4_DETECTOR_KINDS)}"
            )
        rk = (payload.get("response") or {}).get("kind")
        if rk and rk not in _H4_RESPONSE_KINDS:
            problems.append(
                f"{prefix}: unknown response.kind={rk!r}; "
                f"allowed: {sorted(_H4_RESPONSE_KINDS)}"
            )
    return problems


# --------------------------------------------------------------------------
# Step 6 — applier
# --------------------------------------------------------------------------

def apply_patch(patch: EvolutionPatch, bot_id: str) -> list[str]:
    """Apply each patch entry via the layers repo. Returns the new layer ids
    that were created or superseded into existence."""
    new_ids: list[str] = []
    for entry in patch.entries:
        if entry.op == "create":
            new_id = layers_repo.create_layer(
                bot_id=bot_id,
                layer=entry.layer,
                name=entry.name,
                payload=entry.payload or {},
                source_kind="evolved",
            )
            new_ids.append(new_id)
        elif entry.op == "supersede":
            assert entry.existing_layer_id is not None
            new_id = layers_repo.supersede_layer(
                entry.existing_layer_id,
                new_payload=entry.payload or {},
                source_kind="evolved",
            )
            new_ids.append(new_id)
        elif entry.op == "disable":
            assert entry.existing_layer_id is not None
            layers_repo.set_enabled(entry.existing_layer_id, False)
    return new_ids


# --------------------------------------------------------------------------
# Step 7 — full orchestrator
# --------------------------------------------------------------------------

def run_evolution_round(
    bot_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
    keep_scratch_on_failure: bool = True,
    dry_run: bool = False,
    min_interval_hours: Optional[int] = None,
    force: bool = False,
) -> EvolutionResult:
    """Run one full evolution round end-to-end. Never raises.

    When ``dry_run=True``, the round stops after patch validation. The row
    transitions ``pending`` → ``running`` → ``awaiting_approval`` with the
    parsed patch in ``output_patch_json``. The operator then calls
    ``apply_dry_run_round(round_id)`` or ``abort_dry_run_round(round_id)``.

    Rate-limited by ``min_interval_hours`` (default
    ``AGENTED_EVOLUTION_MIN_INTERVAL_HOURS`` / 24h). Pass ``force=True`` to
    override; the rate-limit guard is meant as protection against accidental
    burst-triggers, not a hard policy.
    """
    if not force:
        interval = (
            min_interval_hours
            if min_interval_hours is not None
            else _default_min_interval_hours()
        )
        reason = _check_rate_limit(bot_id, interval)
        if reason:
            return EvolutionResult(
                round_id="",  # nothing was started — no row to point at
                status="aborted",
                error=reason,
            )

    inputs = gather_inputs(bot_id, since=since, until=until, limit=limit)

    # Pin to /tmp so we don't accidentally land scratch dirs in the
    # process CWD when ``$TMPDIR`` is unset (some sandbox runtimes).
    # Fall back to the system default if /tmp doesn't exist.
    _tmp_root = "/tmp" if os.path.isdir("/tmp") else tempfile.gettempdir()
    scratch = Path(tempfile.mkdtemp(
        prefix="agented-harness-evolution-", dir=_tmp_root,
    ))
    round_id = evolution_repo.start_round(
        bot_id=bot_id,
        input_window_since=since,
        input_window_until=until,
        input_execution_count=len(inputs["trajectories"]),
        input_layers=_group_layers_by_kind(inputs["enabled_layers"]),
        scratch_dir=str(scratch),
    )

    try:
        evolution_repo.mark_running(round_id)
        build_workspace(inputs, scratch)
        _run_codex_in_workspace(scratch)

        after = json.loads((scratch / "harness.json").read_text())
        before = _group_layers_by_kind(inputs["enabled_layers"])
        notes_path = scratch / "NOTES.md"
        notes = notes_path.read_text() if notes_path.exists() else ""

        patch = parse_patch(before, after, notes=notes)
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
                round_id=round_id,
                status="awaiting_approval",
                applied_layer_ids=[],
                notes=notes,
            )

        applied_ids = apply_patch(patch, bot_id)
        evolution_repo.mark_applied(
            round_id,
            output_patch=_patch_to_dict(patch),
            applied_layer_ids=applied_ids,
            notes=notes,
        )

        if not keep_scratch_on_failure:
            shutil.rmtree(scratch, ignore_errors=True)
        return EvolutionResult(
            round_id=round_id,
            status="applied",
            applied_layer_ids=applied_ids,
            notes=notes,
        )

    except Exception as exc:  # noqa: BLE001 — orchestrator must not raise
        logger.exception("harness_evolver: round %s failed", round_id)
        evolution_repo.mark_failed(round_id, error_message=str(exc))
        return EvolutionResult(
            round_id=round_id, status="failed", error=str(exc),
        )


def apply_dry_run_round(round_id: str) -> EvolutionResult:
    """Apply the patch stored on a dry-run round.

    Reads the patch from ``output_patch_json``, replays it through
    ``apply_patch``, and transitions the round ``awaiting_approval`` →
    ``applied``. No-op (returns a ``failed`` result) when the round isn't
    in ``awaiting_approval``.
    """
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
        applied_ids = apply_patch(patch, row["bot_id"])
    except Exception as exc:  # noqa: BLE001 — repo errors are reported, not raised
        evolution_repo.mark_failed(
            round_id, error_message=f"apply failed: {exc}",
        )
        return EvolutionResult(
            round_id=round_id, status="failed", error=f"apply failed: {exc}",
        )

    evolution_repo.mark_applied(
        round_id,
        output_patch=patch_data,
        applied_layer_ids=applied_ids,
        notes=row.get("notes"),
    )
    return EvolutionResult(
        round_id=round_id, status="applied",
        applied_layer_ids=applied_ids,
        notes=row.get("notes") or "",
    )


def abort_dry_run_round(round_id: str, *, reason: Optional[str] = None) -> EvolutionResult:
    """Operator rejects a dry-run patch; transitions
    ``awaiting_approval`` → ``aborted``. No layer changes are applied."""
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


def _patch_from_dict(data: dict[str, Any]) -> EvolutionPatch:
    """Inverse of ``_patch_to_dict``. Used by ``apply_dry_run_round`` to
    replay the persisted patch."""
    entries = []
    for raw in (data.get("entries") or []):
        entries.append(PatchEntry(
            op=raw["op"],
            layer=raw["layer"],
            name=raw.get("name") or "untitled",
            existing_layer_id=raw.get("existing_layer_id"),
            payload=raw.get("payload"),
        ))
    return EvolutionPatch(entries=entries, notes=data.get("notes") or "")


def _patch_to_dict(patch: EvolutionPatch) -> dict[str, Any]:
    return {
        "notes": patch.notes,
        "entries": [
            {
                "op": e.op, "layer": e.layer, "name": e.name,
                "existing_layer_id": e.existing_layer_id,
                "payload": e.payload,
            }
            for e in patch.entries
        ],
    }
