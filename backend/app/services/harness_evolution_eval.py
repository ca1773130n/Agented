"""Phase C1 eval gate: test a proposed patch before it is applied.

static checks (mechanical) + regression-replay (LLM judge, provider-kind) ->
EvalVerdict. See docs/superpowers/specs/2026-05-29-life-harness-phaseC-trust-design.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.harness_evolution import CheckResult
from app.services.forge_materialization_service import MaterializationResult


def _static_checks(workspace: Path, result: MaterializationResult) -> list[CheckResult]:
    """Mechanical validity checks over the materialized .claude files."""
    checks: list[CheckResult] = []
    for w in result.written:
        target = workspace / w.rel_path
        if not target.exists():
            checks.append(
                CheckResult(
                    name=f"exists:{w.rel_path}",
                    passed=False,
                    detail="expected materialized file is missing",
                )
            )
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
            lines = [ln.strip() for ln in text.splitlines()]
            non_empty = [ln for ln in lines if ln]
            opens = bool(non_empty) and non_empty[0] == "---"
            closes = opens and any(ln == "---" for ln in lines[lines.index("---") + 1 :])
            ok = opens and closes
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
