"""GRD CLI Service — subprocess wrapper for the GRD plugin (v0.3.24–v0.4.x).

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
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

import re as _re

_GRD_VERSION_SEG_RE = _re.compile(r"/grd/(\d+)\.(\d+)\.(\d+)")


def _grd_path_version(path: str) -> tuple[int, int, int]:
    """Parse the ``.../grd/<major.minor.patch>/...`` segment of a cached GRD
    binary path into a comparable tuple (highest = newest). Returns (-1, -1, -1)
    for paths without a version segment (npm/legacy layouts) so they lose the
    semver comparison and fall back to the mtime tiebreak."""
    m = _GRD_VERSION_SEG_RE.search(path)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (-1, -1, -1)


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

    _binary_path: Optional[str] = None  # grd-tools(.js) — write ops
    _gd_path: Optional[str] = None  # gd(.js) — Ouroboros / harness surface
    _binary_available: bool = False
    _gd_available: bool = False
    # v0.4.x: the binary may resolve to a direct executable on PATH (npm
    # `@jokerized/getresearchdone` symlinks `gd` / `grd-tools`) rather than a
    # `.js` file. Direct executables are invoked as `gd …`; `.js` paths as
    # `node …/gd.js …`.
    _binary_is_exec: bool = False
    _gd_is_exec: bool = False

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
          2. ``CLAUDE_PLUGIN_ROOT`` env var + ``bin/<name>`` (explicit override)
          3. On PATH (npm installs symlink ``gd`` / ``grd-tools``)
          4. Glob known install locations (highest semver, then mtime)
          5. Mark unavailable if nothing matches
        """
        cls._binary_path, cls._binary_available, cls._binary_is_exec = cls._detect_one(
            filename="grd-tools.js",
            exec_name="grd-tools",
            setting_key="grd_binary_path",
            label="grd-tools",
        )
        cls._gd_path, cls._gd_available, cls._gd_is_exec = cls._detect_one(
            filename="gd.js",
            exec_name="gd",
            setting_key="gd_binary_path",
            label="gd",
        )

    @classmethod
    def _detect_one(
        cls, *, filename: str, exec_name: str, setting_key: str, label: str
    ) -> tuple[Optional[str], bool, bool]:
        """Locate a single GRD entry-point binary.

        Returns ``(path, available, is_exec)`` — ``is_exec`` True when the
        resolved path is a direct executable (invoke ``<path> …``), False for a
        ``.js`` file (invoke ``node <path> …``).
        """
        # 1. Settings table override
        try:
            from app.database import get_setting

            stored = get_setting(setting_key)
            if stored and os.path.isfile(stored):
                logger.info("GRD %s binary found via settings: %s", label, stored)
                return stored, True, not stored.endswith(".js")
        except Exception:
            # Settings table may not be available during import.
            pass

        # 2. CLAUDE_PLUGIN_ROOT env var — an EXPLICIT override, so it must beat
        # whatever happens to be on PATH. The PATH probe below was added later
        # (2026-06-14, "detect 0.4.x gd binary (npm/PATH…)") and was inserted
        # ABOVE this block, which silently demoted the override: setting
        # CLAUDE_PLUGIN_ROOT to pin a specific GRD build got you the PATH one
        # instead. The docstring above never described that order, and the three
        # tests asserting it have been red since — long enough to be filed as
        # "known baseline failures" rather than read.
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            candidate = os.path.join(plugin_root, "bin", filename)
            if os.path.isfile(candidate):
                logger.info("GRD %s binary found via CLAUDE_PLUGIN_ROOT: %s", label, candidate)
                return candidate, True, False

        # 3. On PATH (npm @jokerized/getresearchdone symlinks `gd` / `grd-tools`)
        which = shutil.which(exec_name)
        if which:
            logger.info("GRD %s binary found on PATH: %s", label, which)
            return which, True, True

        # 4. Glob known install locations (most recently modified first). The
        # v0.4.x marketplace cache is lowercase `grd/<version>/bin`; the npm
        # global lives under node_modules/@jokerized/getresearchdone; the
        # uppercase `GRD` paths are kept for legacy (v0.3.x) installs.
        patterns = [
            os.path.expanduser(f"~/.claude-*/plugins/cache/*/grd/*/bin/{filename}"),
            os.path.expanduser(f"~/.claude/plugins/cache/*/grd/*/bin/{filename}"),
            os.path.expanduser(
                f"~/.nvm/versions/node/*/lib/node_modules/@jokerized/getresearchdone/bin/{filename}"
            ),
            os.path.expanduser(f"~/.claude/plugins/*/GRD/bin/{filename}"),
            os.path.expanduser(f"~/.claude/plugins/marketplaces/*/plugins/GRD/bin/{filename}"),
            os.path.expanduser(f"~/.claude-*/plugins/*/GRD/bin/{filename}"),
        ]
        for pattern in patterns:
            matches = glob_module.glob(pattern)
            if matches:
                # Prefer the highest SEMVER (the `.../grd/<version>/bin` cache
                # segment), falling back to mtime. mtime alone was fragile —
                # touching an old version dir (or a clock skew) could regress the
                # selection to a stale binary.
                matches.sort(
                    key=lambda p: (_grd_path_version(p), os.path.getmtime(p)), reverse=True
                )
                logger.info("GRD %s binary found via glob: %s", label, matches[0])
                return matches[0], True, False

        logger.warning(
            "GRD %s binary not found — related operations will be unavailable",
            label,
        )
        return None, False, False

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
        return cls._run(cls._binary_path, cwd, list(args), raw=True, is_exec=cls._binary_is_exec)

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
        return cls._run(cls._gd_path, cwd, argv, raw=False, is_exec=cls._gd_is_exec)

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
        cls, binary: Optional[str], cwd: str, argv: list, *, raw: bool, is_exec: bool = False
    ) -> dict:
        """Shared subprocess runner used by both ``run_command`` and
        ``run_gd``. ``raw=True`` appends the ``grd-tools`` ``--raw`` flag
        which suppresses prompts; ``gd`` doesn't use that flag. ``is_exec``
        True invokes the binary directly (``gd …``); False via node (a ``.js``).
        """
        if not binary:
            return {
                "success": False,
                "output": None,
                "error": "GRD binary not available",
            }
        cmd = ([binary] if is_exec else ["node", binary]) + list(argv)
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
    def harness_conversion(cls, project_path: str) -> dict:
        """GRD 0.4.16 — ``gd harness conversion --json``: a DETERMINISTIC
        self-improvement effectiveness audit (no LLM, no re-run). Measures
        trial-to-behavior conversion (did a recorded lesson change a concrete
        file/config in a later round, and with what latency) and
        trial-to-harness-behavior conversion (did recurring failures change
        gates/prompts/scheduler policy). Parsed shape: ``rounds_total/live/
        applied``, ``lessons_total/converted``, ``conversion_rate``,
        ``median_latency_rounds``, ``harness_policy{count,recurring_count}``,
        ``events[]``, ``dead_ends{}``, ``top_unconverted[]``.

        Falls back to ``{success: False}`` when ``gd`` (0.4.16+) is missing.
        """
        if not cls._gd_available:
            return {
                "success": False,
                "data": None,
                "error": "gd binary not available (0.4.16+ required for harness conversion)",
            }
        return cls.run_gd_json(project_path, "harness", "conversion")

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
        return cls.run_command(project_path, "verify", "mechanical", "--phase", str(phase))

    # -----------------------------------------------------------------
    # Research (v0.8.0 — REQ-14, autoresearch loop browser surface)
    #
    # These are the READ-ONLY / status surfaces around ``gd research``;
    # the long loop itself runs through ``GrdResearchSessionHandler`` as
    # a streamed PSM session, NOT through these helpers. The on-disk
    # readers are deliberate: a research thread's THREAD.md / HYPOTHESES.md
    # / FINDING.md are the source of truth the loop writes, so the browser
    # reads them directly rather than paying a CLI round-trip. There is no
    # ``gd research report`` or ``gd research portfolio`` command — the
    # report IS FINDING.md on disk and the portfolio IS the thread list.
    # -----------------------------------------------------------------

    _RESEARCH_THREADS_REL = os.path.join(".planning", "research", "threads")

    @staticmethod
    def _is_safe_thread_id(thread_id: Optional[str]) -> bool:
        """Reject thread ids that could escape the threads directory.

        ``thread_id`` arrives from a URL path/query param and is joined onto
        a filesystem path (``read_thread``) and passed as a ``gd`` argv
        (``research_status``), so a value containing a path separator, a
        ``..`` segment, or a NUL byte is treated as hostile and refused —
        defense-in-depth against path traversal regardless of how the ASGI
        server decodes ``%2F``.
        """
        if not thread_id:
            return False
        if "\x00" in thread_id or "/" in thread_id or "\\" in thread_id:
            return False
        # With separators already rejected, the only traversal left is a
        # bare ``..`` segment.
        if thread_id == "..":
            return False
        return True

    @classmethod
    def research_status(cls, project_path: str, thread_id: Optional[str] = None) -> dict:
        """``gd research status [thread_id]`` — JSON snapshot of the
        active/most-recent research loop (in gd 0.5.0 the status JSON also carries
        a paused thread's ``pendingCheckpoint``). Returns ``{"error": ...}`` when
        the ``gd`` binary isn't available (no legacy fallback exists).
        """
        if not cls._gd_available:
            return {
                "success": False,
                "data": None,
                "error": "gd binary not available (gd 0.5.0+ required for research)",
            }
        args = ["research", "status"]
        if thread_id:
            if not cls._is_safe_thread_id(thread_id):
                return {"success": False, "data": None, "error": "invalid thread_id"}
            args.append(thread_id)
        return cls.run_gd_json(project_path, *args)

    @classmethod
    def list_threads(cls, project_path: str) -> list[dict]:
        """Portfolio/browser — read the frontmatter of every
        ``.planning/research/threads/<id>/THREAD.md`` on disk.

        Returns ``[]`` when the threads directory is missing (it does not
        exist until the first research run, so the absence is normal, not
        an error). Each entry carries the parsed
        ``id``/``question``/``status``/``iteration``/``max_iterations``
        frontmatter fields (missing fields are ``None``). This is an
        on-disk read, not a CLI round-trip.
        """
        threads_dir = os.path.join(project_path, cls._RESEARCH_THREADS_REL)
        if not os.path.isdir(threads_dir):
            return []

        out: list[dict] = []
        for entry in sorted(os.listdir(threads_dir)):
            thread_path = os.path.join(threads_dir, entry)
            if not os.path.isdir(thread_path):
                continue
            thread_md = os.path.join(thread_path, "THREAD.md")
            fm = cls._read_frontmatter(thread_md)
            out.append(
                {
                    "id": fm.get("id") or entry,
                    "question": fm.get("question"),
                    "status": fm.get("status"),
                    "iteration": fm.get("iteration"),
                    "max_iterations": fm.get("max_iterations"),
                }
            )
        return out

    @classmethod
    def read_thread(cls, project_path: str, thread_id: str) -> dict:
        """Bundle the three on-disk documents for one research thread:
        ``THREAD.md`` + ``HYPOTHESES.md`` + ``FINDING.md`` from
        ``.planning/research/threads/<id>/``.

        Each field is ``None`` when its file is absent (a thread mid-loop
        may not have written FINDING.md yet), so callers get a None-safe
        bundle rather than a partial dict or an exception. A hostile
        ``thread_id`` (path separators / ``..``) yields an all-``None``
        bundle rather than escaping the threads directory.
        """
        if not cls._is_safe_thread_id(thread_id):
            return {"id": thread_id, "thread": None, "hypotheses": None, "finding": None}
        thread_path = os.path.join(project_path, cls._RESEARCH_THREADS_REL, thread_id)
        return {
            "id": thread_id,
            "thread": cls._read_text(os.path.join(thread_path, "THREAD.md")),
            "hypotheses": cls._read_text(os.path.join(thread_path, "HYPOTHESES.md")),
            "finding": cls._read_text(os.path.join(thread_path, "FINDING.md")),
        }

    # -----------------------------------------------------------------
    # Deep research (GRD 0.4.14 — /grd:deep-research)
    #
    # deep-research's artifact is structurally DISTINCT from the threads
    # tree: it writes ONE standalone dated report to
    # ``.planning/milestones/<milestone>/research/deep-research/<slug>-<date>.md``
    # with no frontmatter / iteration / status and no thread dir. So these
    # readers glob across ALL milestones (avoiding any "current milestone"
    # resolution or CLI round-trip — a pure on-disk read, mirroring
    # ``list_threads``) rather than reusing the thread reader.
    # -----------------------------------------------------------------

    _RESEARCH_DEEP_GLOB = os.path.join(
        ".planning", "milestones", "*", "research", "deep-research", "*.md"
    )

    @classmethod
    def list_deep_reports(cls, project_path: str) -> list[dict]:
        """List every deep-research report on disk across ALL milestones.

        Returns ``[]`` when no report exists (the ``deep-research/`` dir does
        not exist until the first deep run — the absence is normal, mirroring
        ``list_threads``). Each entry carries ``name`` (basename),
        ``milestone`` (the milestone dir segment), ``path`` (relative to the
        project), and ``modified`` (mtime), sorted newest-first.
        """
        import glob

        pattern = os.path.join(project_path, cls._RESEARCH_DEEP_GLOB)
        out: list[dict] = []
        for match in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(match)
            except OSError:
                mtime = 0.0
            # ``.planning/milestones/<milestone>/research/deep-research/<name>``
            rel = os.path.relpath(match, project_path)
            parts = rel.split(os.sep)
            milestone = parts[2] if len(parts) > 2 else ""
            out.append(
                {
                    "name": os.path.basename(match),
                    "milestone": milestone,
                    "path": rel,
                    "modified": mtime,
                }
            )
        out.sort(key=lambda r: r["modified"], reverse=True)
        return out

    @classmethod
    def read_deep_report(cls, project_path: str, name: str) -> dict:
        """Return one deep-research report's markdown by basename.

        The ``name`` comes from a URL path param, so it is sanitized against
        path traversal: it MUST equal its own ``os.path.basename`` and carry
        no separator / ``..``, otherwise the read is refused (``markdown``
        None). The report is located by globbing the same all-milestones
        pattern and matching the sanitized basename, so no milestone or path
        input from the caller is trusted.
        """
        import glob

        safe = os.path.basename(name)
        if safe != name or os.sep in name or (os.altsep and os.altsep in name) or ".." in name:
            return {"name": name, "markdown": None}

        pattern = os.path.join(project_path, cls._RESEARCH_DEEP_GLOB)
        for match in glob.glob(pattern):
            if os.path.basename(match) == safe:
                return {"name": name, "markdown": cls._read_text(match)}
        return {"name": name, "markdown": None}

    @staticmethod
    def _read_text(path: str) -> Optional[str]:
        """Read a file, returning ``None`` when it is absent or unreadable."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except (FileNotFoundError, NotADirectoryError, OSError):
            return None

    @classmethod
    def _read_frontmatter(cls, path: str) -> dict:
        """Parse the leading ``--- ... ---`` YAML-ish frontmatter block of
        a markdown file into a flat ``{key: value}`` dict.

        Deliberately a tiny ``key: value`` line parser (not a YAML import)
        — research THREAD.md frontmatter is flat scalars. ``iteration`` /
        ``max_iterations`` are coerced to ``int`` when numeric. Returns an
        empty dict when the file is absent or has no frontmatter.
        """
        text = cls._read_text(path)
        if not text:
            return {}
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        fm: dict = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:
                continue
            if key in ("iteration", "max_iterations") and value.isdigit():
                fm[key] = int(value)
            else:
                fm[key] = value or None
        return fm
