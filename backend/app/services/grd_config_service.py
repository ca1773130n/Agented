"""Read/write the two GRD 0.5.0 research-steering settings in a project's
``.planning/config.json``.

GRD 0.5.0's headline feature is interactive research steering. Two settings
decide what actually happens at the four checkpoint stations (SEED / HYPOTHESIZE
/ DESIGN / DECIDE), and they are the pair an operator needs to reach:

- ``autonomous_mode`` — GRD's ``resolveInteractive`` returns ``active:false``
  under ANY unattended condition (``autonomous_mode``, autopilot/
  ``GRD_AUTOPILOT``, ``--no-gates``, portfolio concurrency > 1). So while this is
  ``true``, the human checkpoints NEVER fire no matter how the per-station flags
  are set. Turning it off is the single switch that turns on real
  human-in-the-loop steering.
- ``research_gates.interactive.fallback`` — who answers when no human is present.
  ``"recommended"`` takes each question's recommended default; ``"panel"`` runs a
  multi-backend AI discussion (roster ``claude/codex/gemini/opencode`` minus the
  loop's own backend). Degrade-safe: empty synthesis, a rate-limited or
  logged-out panelist, or any error resolves to the recommended defaults.

Because ``autonomous_mode`` gates the other one's relevance, the two are only
meaningful together — which is why they are surfaced as one pair.

**This file is GRD's, not ours.** Every write is read-modify-write and preserves
all other keys byte-for-byte in value; unknown keys are never dropped. GRD's own
loader tolerates unknown keys, but *our* writing must not be what removes them.
Written with ``indent=2`` + a trailing newline to match GRD's own formatting so
the file doesn't churn in git.
"""

import json
from pathlib import Path
from typing import Any, Optional

from app.db.connection import get_connection

logger = __import__("logging").getLogger(__name__)

# The only two values ``fallback`` may take (checkpoints.ts readInteractiveConfig
# warns and reverts to 'recommended' on anything else).
FALLBACK_VALUES = ("recommended", "panel")


def _config_path(local_path: Optional[str]) -> Optional[Path]:
    """``<local_path>/.planning/config.json``, or None when the project has no
    local path. Mirrors ``grd_sync_service``'s planning-dir resolution."""
    if not local_path:
        return None
    return Path(local_path).expanduser() / ".planning" / "config.json"


def _read_raw(path: Path) -> Optional[dict[str, Any]]:
    """Parsed config, or None when absent/unreadable/not an object. A corrupt
    config must not 500 the settings page — it reads as 'no config here'."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _steering_of(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The two settings as the UI needs them, with GRD's own defaults applied.

    ``interactive.enabled`` is reported too — not editable here, but without it
    the UI would show a ``fallback`` that does nothing, since GRD only consults
    the fallback for a checkpoint it was going to raise.
    """
    gates = (raw or {}).get("research_gates")
    interactive = gates.get("interactive") if isinstance(gates, dict) else None
    if not isinstance(interactive, dict):
        interactive = {}
    fallback = interactive.get("fallback")
    return {
        # GRD treats a missing autonomous_mode as falsy.
        "autonomous_mode": bool((raw or {}).get("autonomous_mode")),
        # defaultInteractive() in checkpoints.ts: enabled false, fallback 'recommended'.
        "interactive_enabled": bool(interactive.get("enabled")),
        "interactive_fallback": fallback if fallback in FALLBACK_VALUES else "recommended",
    }


def get_steering(project_id: str) -> dict[str, Any]:
    """Steering settings for one project. ``configured`` is False when the
    project has no local path or no ``.planning/config.json`` — the UI must
    disable the controls rather than write a config file into a directory GRD
    was never initialised in."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, local_path FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if row is None:
        return {}
    return _project_entry(row)


def _project_entry(row: Any) -> dict[str, Any]:
    path = _config_path(row["local_path"])
    raw = _read_raw(path) if path else None
    entry: dict[str, Any] = {
        "project_id": row["id"],
        "project_name": row["name"],
        "local_path": row["local_path"],
        "config_path": str(path) if path else None,
        "configured": raw is not None,
    }
    entry.update(_steering_of(raw))
    return entry


def list_steering() -> list[dict[str, Any]]:
    """One entry per project, ordered like the other settings tables."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, local_path FROM projects ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [_project_entry(r) for r in rows]


def set_steering(
    project_id: str,
    *,
    autonomous_mode: Optional[bool] = None,
    interactive_fallback: Optional[str] = None,
) -> dict[str, Any]:
    """Patch either or both settings, preserving every other key.

    Raises ``ValueError`` for an unknown fallback value, a project without a
    local path, or a missing/corrupt config — writing a fresh config.json would
    silently strip a GRD setup we merely failed to parse, so it fails closed.
    """
    if interactive_fallback is not None and interactive_fallback not in FALLBACK_VALUES:
        raise ValueError(
            f"interactive_fallback must be one of {FALLBACK_VALUES}, got {interactive_fallback!r}"
        )
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, local_path FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"project not found: {project_id}")

    path = _config_path(row["local_path"])
    if path is None:
        raise ValueError("project has no local_path; GRD config lives at <local_path>/.planning/")
    raw = _read_raw(path)
    if raw is None:
        raise ValueError(f"no readable GRD config at {path}; run GRD init for this project first")

    if autonomous_mode is not None:
        raw["autonomous_mode"] = bool(autonomous_mode)
    if interactive_fallback is not None:
        # Build the nesting only as far as it is missing — never replace a
        # research_gates block that carries the other (pre-0.5.0) gates.
        gates = raw.get("research_gates")
        if not isinstance(gates, dict):
            gates = {}
            raw["research_gates"] = gates
        interactive = gates.get("interactive")
        if not isinstance(interactive, dict):
            interactive = {}
            gates["interactive"] = interactive
        interactive["fallback"] = interactive_fallback

    # Write via a temp file in the same directory + os.replace: a crash mid-write
    # must not leave GRD with a truncated config it then silently reads as empty.
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(raw, indent=2) + "\n")
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"could not write {path}: {exc}") from exc
    logger.info(
        "grd: steering updated for %s (autonomous_mode=%s, fallback=%s)",
        project_id,
        autonomous_mode,
        interactive_fallback,
    )
    return _project_entry(row)
