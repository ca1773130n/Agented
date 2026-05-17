"""GRD CLI Service — subprocess wrapper for the GRD plugin (v0.3.24+).

Provides binary auto-detection and graceful degradation when GRD isn't
installed. The plugin ships two entry points:

* ``grd-tools.js`` — original deterministic CLI (state, verify, scaffold,
  frontmatter, tracker, ...). Agented relies on this for write operations
  that must preserve GRD's internal consistency.
* ``gd.js`` — new unified entry point (v0.3.x) that supersedes
  ``grd-tools.js`` for some subcommands and adds the Ouroboros surface
  (``think``, ``health``, ``dead-end add``, ``genome``,
  ``plan-tournament score``, ``verify mechanical``).

Both binaries are auto-detected from the same install roots. Agented
prefers ``gd.js`` when both are present because it covers the larger
command surface; ``grd-tools.js`` remains the fallback so older deploys
keep working unchanged. The ``run_*`` helpers below dispatch to the
right binary per call.
"""

import glob as glob_module
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


# Valid PLAN.md status values (subset of GRD's PlanStatus enum that the
# UI plumbs through). Kept here so callers in routes don't import the
# Pydantic enum for a simple string-set membership check.
_VALID_PLAN_STATUSES = {"pending", "in_progress", "completed", "failed", "in_review"}


class GrdCliService:
    """Service for shelling out to GRD CLI binaries (``gd`` + ``grd-tools``).

    Class-level state with ``@classmethod`` methods. Binary detection runs
    once at startup via ``detect_binaries()`` and caches both paths. The
    legacy ``detect_binary()`` shim is preserved for callers that only
    want the ``grd-tools.js`` path (most internal callers).
    """

    _binary_path: Optional[str] = None  # grd-tools.js — write ops
    _gd_path: Optional[str] = None  # gd.js — v0.3.24 Ouroboros surface
    _binary_available: bool = False
    _gd_available: bool = False

    @classmethod
    def detect_binary(cls) -> Optional[str]:
        """Back-compat alias — detects both binaries, returns ``grd-tools.js``
        path. New callers should use ``detect_binaries()`` and check
        ``gd_path()`` / ``binary_path()`` explicitly.
        """
        cls.detect_binaries()
        return cls._binary_path

    @classmethod
    def detect_binaries(cls) -> None:
        """Detect both ``grd-tools.js`` and ``gd.js`` binary paths and cache.

        Detection runs the same probe order for each binary independently:
          1. Settings table (``grd_binary_path`` / ``gd_binary_path``)
          2. ``CLAUDE_PLUGIN_ROOT`` env var + ``bin/<name>``
          3. Glob known install locations (most recently modified wins)
          4. Mark unavailable if nothing matches
        """
        cls._binary_path, cls._binary_available = cls._detect_one(
            filename="grd-tools.js",
            setting_key="grd_binary_path",
            label="grd-tools",
        )
        cls._gd_path, cls._gd_available = cls._detect_one(
            filename="gd.js",
            setting_key="gd_binary_path",
            label="gd",
        )

    @classmethod
    def _detect_one(
        cls, *, filename: str, setting_key: str, label: str
    ) -> tuple[Optional[str], bool]:
        """Locate a single GRD entry-point binary."""
        # 1. Settings table override
        try:
            from app.database import get_setting

            stored = get_setting(setting_key)
            if stored and os.path.isfile(stored):
                logger.info("GRD %s binary found via settings: %s", label, stored)
                return stored, True
        except Exception:
            # Settings table may not be available during import.
            pass

        # 2. CLAUDE_PLUGIN_ROOT env var
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            candidate = os.path.join(plugin_root, "bin", filename)
            if os.path.isfile(candidate):
                logger.info(
                    "GRD %s binary found via CLAUDE_PLUGIN_ROOT: %s", label, candidate
                )
                return candidate, True

        # 3. Glob known install locations (most recently modified first)
        patterns = [
            os.path.expanduser(f"~/.claude/plugins/*/GRD/bin/{filename}"),
            os.path.expanduser(
                f"~/.claude/plugins/marketplaces/*/plugins/GRD/bin/{filename}"
            ),
            os.path.expanduser(f"~/.claude-*/plugins/*/GRD/bin/{filename}"),
        ]
        for pattern in patterns:
            matches = glob_module.glob(pattern)
            if matches:
                matches.sort(key=os.path.getmtime, reverse=True)
                logger.info("GRD %s binary found via glob: %s", label, matches[0])
                return matches[0], True

        logger.warning(
            "GRD %s binary not found — related operations will be unavailable",
            label,
        )
        return None, False

    # -----------------------------------------------------------------
    # Status accessors used by routes / health probes
    # -----------------------------------------------------------------

    @classmethod
    def binary_path(cls) -> Optional[str]:
        """Path to ``grd-tools.js`` if detected."""
        return cls._binary_path

    @classmethod
    def gd_path(cls) -> Optional[str]:
        """Path to ``gd.js`` if detected (v0.3.24+ surface)."""
        return cls._gd_path

    @classmethod
    def available(cls) -> dict:
        """Combined availability report — handy for /health endpoints."""
        return {
            "grd_tools_path": cls._binary_path,
            "grd_tools_available": cls._binary_available,
            "gd_path": cls._gd_path,
            "gd_available": cls._gd_available,
        }

    # -----------------------------------------------------------------
    # Raw runners
    # -----------------------------------------------------------------

    @classmethod
    def run_command(cls, cwd: str, *args) -> dict:
        """Run a ``grd-tools.js`` command. Returns ``{success, output, error}``.

        Legacy entry point used by ``update_plan_status``. New callers
        targeting the v0.3.24 surface should prefer ``run_gd`` so they
        get the larger command set (think / health / dead-end / genome /
        plan-tournament / verify mechanical) without forking on binary
        detection.
        """
        return cls._run(cls._binary_path, cwd, list(args), raw=True)

    @classmethod
    def run_gd(cls, cwd: str, *args, json_output: bool = False) -> dict:
        """Run a ``gd.js`` command (v0.3.24+ Ouroboros surface).

        ``json_output=True`` appends ``--json`` so the command returns a
        machine-parseable payload that callers can parse via
        ``run_gd_json``. The dual signature keeps the door open for
        commands that legitimately want plain-text output (``gd help``,
        ``gd progress`` in human mode, etc.).
        """
        argv = list(args)
        if json_output and "--json" not in argv:
            argv.append("--json")
        return cls._run(cls._gd_path, cwd, argv, raw=False)

    @classmethod
    def run_gd_json(cls, cwd: str, *args) -> dict:
        """Run ``gd`` with ``--json`` and parse the result.

        Returns ``{success: bool, data: dict|None, error: str|None}``.
        Non-JSON output is surfaced as an error rather than a partial
        success so callers don't have to defend against ``data=None``
        when ``success=True``.
        """
        raw = cls.run_gd(cwd, *args, json_output=True)
        if not raw["success"]:
            return {"success": False, "data": None, "error": raw.get("error")}
        out = (raw.get("output") or "").strip()
        if not out:
            return {"success": True, "data": None, "error": None}
        try:
            return {"success": True, "data": json.loads(out), "error": None}
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "data": None,
                "error": f"gd returned non-JSON output: {exc}",
            }

    @classmethod
    def _run(
        cls, binary: Optional[str], cwd: str, argv: list, *, raw: bool
    ) -> dict:
        """Shared subprocess runner used by both ``run_command`` and
        ``run_gd``. ``raw=True`` appends the ``grd-tools`` ``--raw`` flag
        which suppresses prompts; ``gd`` doesn't use that flag.
        """
        if not binary:
            return {
                "success": False,
                "output": None,
                "error": "GRD binary not available",
            }
        cmd = ["node", binary] + list(argv)
        if raw:
            cmd.append("--raw")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout.strip(),
                    "error": None,
                }
            return {
                "success": False,
                "output": result.stdout.strip() or None,
                "error": result.stderr.strip() or f"Exit code {result.returncode}",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": None,
                "error": "Command timed out (30s)",
            }
        except FileNotFoundError:
            # ``node`` or the binary disappeared between detection and
            # invocation. Flip availability so future calls fail fast
            # instead of paying the subprocess startup cost.
            if binary == cls._binary_path:
                cls._binary_available = False
            if binary == cls._gd_path:
                cls._gd_available = False
            return {
                "success": False,
                "output": None,
                "error": "node or GRD binary not found",
            }
        except Exception as exc:  # pragma: no cover — defensive
            return {"success": False, "output": None, "error": str(exc)}

    # -----------------------------------------------------------------
    # Typed helpers — v0.3.24 Ouroboros surface
    # -----------------------------------------------------------------

    @classmethod
    def update_plan_status(cls, project_path: str, plan_file: str, status: str) -> dict:
        """Update a plan's frontmatter ``status`` field via ``grd-tools.js``.

        Status must be one of ``pending``, ``in_progress``, ``completed``,
        ``failed``, ``in_review``. Returns the standard
        ``{success, output, error}`` envelope.
        """
        if status not in _VALID_PLAN_STATUSES:
            return {
                "success": False,
                "output": None,
                "error": (
                    f"Invalid status: {status}. Must be one of: "
                    f"{', '.join(sorted(_VALID_PLAN_STATUSES))}"
                ),
            }
        return cls.run_command(
            project_path,
            "frontmatter",
            "set",
            plan_file,
            "--field",
            "status",
            "--value",
            f'"{status}"',
        )

    @classmethod
    def get_health(cls, project_path: str) -> dict:
        """v0.3.24 — ``gd-tools health`` weighted drift score + blockers.

        Returns parsed JSON. Falls back to ``grd-tools.js health`` when
        ``gd.js`` isn't installed, since both binaries expose the same
        command shape.
        """
        if cls._gd_available:
            return cls.run_gd_json(project_path, "health")
        # Fallback to grd-tools.js
        raw = cls.run_command(project_path, "health")
        if not raw["success"]:
            return {"success": False, "data": None, "error": raw.get("error")}
        return {"success": True, "data": {"text": raw.get("output")}, "error": None}

    @classmethod
    def think(cls, project_path: str) -> dict:
        """v0.3.24 — ``gd think`` writes a one-shot project briefing
        markdown under ``.planning/thoughts/<ts>-thinking.md`` and
        returns a JSON snapshot pointing at it.

        Falls back to ``{success: False}`` when ``gd.js`` is missing —
        ``think`` is a v0.3.24-only command, no legacy fallback exists.
        """
        if not cls._gd_available:
            return {
                "success": False,
                "data": None,
                "error": "gd binary not available (v0.3.24+ required for think)",
            }
        return cls.run_gd_json(project_path, "think")

    @classmethod
    def add_dead_end(
        cls,
        project_path: str,
        *,
        approach: str,
        reason: str,
        phase: Optional[str] = None,
    ) -> dict:
        """v0.3.24 — append an entry to ``.planning/DEAD-ENDS.md`` via
        ``gd-tools dead-end add``. ``approach`` and ``reason`` are
        required; ``phase`` (e.g. ``"42"``) scopes the entry to a
        phase if supplied.
        """
        if not approach or not reason:
            return {
                "success": False,
                "output": None,
                "error": "approach and reason are required",
            }
        argv = ["dead-end", "add", "--approach", approach, "--reason", reason]
        if phase:
            argv += ["--phase", str(phase)]
        return cls.run_command(project_path, *argv)

    @classmethod
    def promote_dead_ends_from_phase(cls, project_path: str, phase: str) -> dict:
        """v0.3.24 — promote ``verdict: falsified`` reflections from a
        phase into ``.planning/DEAD-ENDS.md`` via
        ``gd-tools dead-end promote-from-phase --phase <N>``.
        """
        if not phase:
            return {
                "success": False,
                "output": None,
                "error": "phase is required",
            }
        return cls.run_command(
            project_path, "dead-end", "promote-from-phase", "--phase", str(phase)
        )

    @classmethod
    def genome_show(cls, project_path: str) -> dict:
        """v0.3.24 — read ``.planning/GENOME.md`` strategy snapshot via
        ``gd-tools genome show``. Returns JSON with
        ``{exists: bool, content: str|null}``.
        """
        # grd-tools genome show always emits JSON regardless of --raw.
        raw = cls.run_command(project_path, "genome", "show")
        if not raw["success"]:
            return {"success": False, "data": None, "error": raw.get("error")}
        out = (raw.get("output") or "").strip()
        if not out:
            return {"success": True, "data": None, "error": None}
        try:
            return {"success": True, "data": json.loads(out), "error": None}
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "data": None,
                "error": f"genome show returned non-JSON output: {exc}",
            }

    @classmethod
    def genome_snapshot(cls, project_path: str) -> dict:
        """v0.3.24 — append a ``GENOME.md`` snapshot of the current
        strategy via ``gd-tools genome snapshot``. Idempotency and
        split-index handling live in the CLI; Agented just calls it.
        """
        return cls.run_command(project_path, "genome", "snapshot")

    @classmethod
    def verify_mechanical(cls, project_path: str, phase: str) -> dict:
        """v0.3.24 — bundle the four PLAN.md mechanical checks via
        ``gd-tools verify mechanical --phase <N>``. Cheaper to run than
        the full ``/grd:verify-phase`` agent flow; intended for the
        Ouroboros pre-verification gate.
        """
        if not phase:
            return {
                "success": False,
                "output": None,
                "error": "phase is required",
            }
        return cls.run_command(
            project_path, "verify", "mechanical", "--phase", str(phase)
        )
