"""GRD 0.4.1 pattern mining — wraps ``gd patterns`` / ``gd genome
promote-suggestion`` (deterministic, no LLM).

CLI gotcha (verified): grd-tools' output convention is INVERTED — these
commands emit JSON with NO flag, but human text with ``--json``/``--raw``, and
they EXIT 0 even on error. So we invoke with no output flag, parse stdout JSON,
and treat an ``Error:``-prefixed or unparseable body as failure (the exit code
can't be trusted). Mining the latest run is mirrored into
``grd_genome_suggestions``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional

from app.db.grd_genome_suggestions import upsert_genome_suggestions
from app.services.grd_cli_service import GrdCliService

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120  # patterns scans REFLECTION.md history; fast but bounded


def _gd_cmd(extra: list[str]) -> Optional[list[str]]:
    """argv for the resolved gd binary, or None if unavailable."""
    GrdCliService.detect_binaries()
    gd = GrdCliService.gd_path()
    if not gd:
        return None
    base = [gd] if GrdCliService._gd_is_exec else ["node", gd]
    return base + extra


def _run_gd_plain(cwd: str, args: list[str]) -> dict:
    """Run ``gd <args>`` with NO output flag (grd-tools emits JSON by default)
    and parse stdout. Returns ``{success, data, error}``. An ``Error:`` prefix
    or a non-JSON body is a failure (these commands exit 0 even on error)."""
    cmd = _gd_cmd(args)
    if cmd is None:
        return {"success": False, "data": None, "error": "GRD gd binary not available"}
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "data": None, "error": f"timed out after {_TIMEOUT_SECONDS}s"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"success": False, "data": None, "error": str(exc)}
    out = (result.stdout or "").strip()
    if result.returncode != 0:
        return {"success": False, "data": None,
                "error": (result.stderr or out or f"exit {result.returncode}").strip()[:300]}
    # grd-tools prints "Error: ..." to stdout and still exits 0 — detect it.
    if not out or out.lower().startswith("error:"):
        return {"success": False, "data": None, "error": (out or "no output")[:300]}
    try:
        return {"success": True, "data": json.loads(out), "error": None}
    except json.JSONDecodeError:
        return {"success": False, "data": None,
                "error": f"gd returned non-JSON output: {out[:200]}"}


def _mirror(project_id: str, data: dict) -> Optional[str]:
    try:
        sugg = data.get("suggestions")
        return upsert_genome_suggestions(
            project_id=project_id,
            reflections_scanned=data.get("reflections_scanned"),
            baseline_confirmed_rate=data.get("baseline_confirmed_rate"),
            tokens_tested=data.get("tokens_tested"),
            suggestions_json=json.dumps(sugg) if sugg is not None else None,
            applied=bool(data.get("applied")),
            suggestions_path=data.get("suggestions_path"),
        )
    except Exception:
        logger.warning("genome-suggestions mirror failed for %s", project_id, exc_info=True)
        return None


def mine_patterns(
    project_id: str,
    cwd: str,
    *,
    apply: bool = False,
    min_occurrences: Optional[int] = None,
    effect_size: Optional[float] = None,
    fdr_q: Optional[float] = None,
) -> dict:
    """Run ``gd patterns`` (deterministic statistical miner). ``apply`` writes
    ``.planning/GENOME-SUGGESTIONS.md`` (requires GRD's ``--yes``). On success
    the result is mirrored into ``grd_genome_suggestions``. Returns
    ``{success, data, error, mirrored}``."""
    args = ["patterns"]
    if apply:
        args += ["--apply", "--yes"]
    if min_occurrences is not None:
        args += ["--min-occurrences", str(min_occurrences)]
    if effect_size is not None:
        args += ["--effect-size", str(effect_size)]
    if fdr_q is not None:
        args += ["--fdr-q", str(fdr_q)]
    result = _run_gd_plain(cwd, args)
    mirrored: Optional[str] = None
    if result["success"] and isinstance(result.get("data"), dict):
        mirrored = _mirror(project_id, result["data"])
    return {**result, "mirrored": mirrored}


def promote_suggestion(cwd: str, slug: str) -> dict:
    """Run ``gd genome promote-suggestion <slug>`` — copy the suggestion's
    heuristic into GENOME.md. Returns ``{success, data, error}`` (no mirror —
    GENOME.md is the durable record)."""
    if not slug:
        return {"success": False, "data": None, "error": "slug required"}
    return _run_gd_plain(cwd, ["genome", "promote-suggestion", slug])
