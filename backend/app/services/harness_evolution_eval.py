"""Phase C1 eval gate: test a proposed patch before it is applied.

static checks (mechanical) + regression-replay (LLM judge, provider-kind) ->
EvalVerdict. See docs/superpowers/specs/2026-05-29-life-harness-phaseC-trust-design.md.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models.harness_evolution import CheckResult
from app.services.forge_materialization_service import MaterializationResult

logger = logging.getLogger(__name__)


def _static_checks(workspace: Path, result: MaterializationResult) -> list[CheckResult]:
    """Mechanical validity checks over the materialized .claude files."""
    checks: list[CheckResult] = []
    for w in result.written:
        target = workspace / w.rel_path
        if not target.exists():
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        if w.rel_path.endswith(".json"):
            try:
                json.loads(text)
                checks.append(CheckResult(name=f"json:{w.rel_path}", passed=True))
            except json.JSONDecodeError as exc:
                checks.append(
                    CheckResult(
                        name=f"json:{w.rel_path}", passed=False, detail=f"invalid json: {exc}"
                    )
                )
        elif w.rel_path.endswith(".md"):
            ok = text.lstrip().startswith("---") and text.count("---") >= 2
            checks.append(
                CheckResult(
                    name=f"frontmatter:{w.rel_path}",
                    passed=ok,
                    detail="" if ok else "missing/unclosed frontmatter",
                )
            )
        elif w.rel_path.endswith(".sh"):
            ok = bool(text.strip())
            checks.append(
                CheckResult(
                    name=f"hook:{w.rel_path}",
                    passed=ok,
                    detail="" if ok else "empty hook script",
                )
            )
    return checks
