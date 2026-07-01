"""Phase C1 eval gate: test a proposed patch before it is applied.

static checks (mechanical) + regression-replay (LLM judge, provider-kind) ->
EvalVerdict. See docs/superpowers/specs/2026-05-29-life-harness-phaseC-trust-design.md.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from app.models.harness_evolution import CheckResult, EvalVerdict, ReplaySample
from app.services.forge_materialization_service import MaterializationResult, materialize_round
from app.services.provider_cli_map import resolve_llm_cmd

logger = logging.getLogger(__name__)

_REPLAY_CONFIDENCE_FLOOR = 0.5

_JUDGE_PROMPT = (
    "You are a strict reviewer. A harness failure incident occurred:\n"
    "kind={kind} layer={layer} evidence={evidence}\n\n"
    "A proposed patch changed the harness primitives as follows:\n{patched}\n\n"
    "Question: does the patch plausibly ADDRESS this failure WITHOUT introducing a "
    "new one? Reply ONLY with a JSON object: "
    '{{"name": "replay", "passed": <bool>, "detail": "<short>", "confidence": <0..1>}}'
)


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


def _run_judge(prompt: str, provider_kind: str) -> str:
    """Invoke the provider CLI judge; return stdout. Mockable (tests patch this)."""
    template = resolve_llm_cmd(provider_kind)
    if "{PROMPT}" in template:
        cmd = [prompt if p == "{PROMPT}" else p for p in template]
        stdin = None
    else:
        cmd = list(template)
        stdin = prompt
    # SECURITY (23): gate the autonomous provider-CLI judge spawn (an unattended
    # LLM eval incurring AI cost) through the shared non-interactive policy layer
    # BEFORE launching. A DENY (or ASK, a refusal here) fails the eval closed.
    from app.services.policy_service import PolicyDenied, PolicyService

    try:
        PolicyService.enforce_launch_noninteractive(
            session_id="", cmd=list(cmd), backend=provider_kind
        )
    except PolicyDenied as exc:
        raise RuntimeError(f"harness eval judge blocked by policy: {exc}") from exc
    try:
        r = subprocess.run(
            cmd,
            cwd=tempfile.gettempdir(),
            input=stdin,
            timeout=60,
            capture_output=True,
            text=True,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    if r.returncode != 0:
        raise RuntimeError(f"judge exited {r.returncode}: {(r.stderr or '')[:200]}")
    return r.stdout or ""


def _parse_check(raw: str, name: str) -> CheckResult:
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return CheckResult(
                name=name,
                passed=bool(obj.get("passed")),
                detail=str(obj.get("detail", ""))[:300],
                confidence=float(obj.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return CheckResult(name=name, passed=False, detail="unparseable judge output", confidence=0.2)


def _replay_checks(
    samples: list[ReplaySample],
    *,
    patched_summary: str,
    provider_kind: str,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for s in samples:
        prompt = _JUDGE_PROMPT.format(
            kind=s.incident_kind,
            layer=s.layer,
            evidence=json.dumps(s.evidence)[:500],
            patched=patched_summary[:2000],
        )
        try:
            raw = _run_judge(prompt, provider_kind)
        except RuntimeError as exc:
            checks.append(
                CheckResult(
                    name=f"replay:{s.incident_kind}",
                    passed=False,
                    detail=f"judge error: {exc}",
                    confidence=0.2,
                )
            )
            continue
        checks.append(_parse_check(raw, f"replay:{s.incident_kind}"))
    return checks


def _verdict(checks: list[CheckResult]) -> EvalVerdict:
    if not checks:
        logger.warning("eval verdict: no checks ran (empty patch/sample set) — passing by default")
        return EvalVerdict(passed=True, score=1.0, per_check=[], notes="no checks")
    failed = [c for c in checks if not c.passed]
    blocking = [
        c
        for c in failed
        if c.name.startswith("replay") and c.confidence >= _REPLAY_CONFIDENCE_FLOOR
    ]
    blocking += [c for c in failed if not c.name.startswith("replay")]
    passed = not blocking
    raw = sum(c.confidence if c.passed else 0.0 for c in checks) / len(checks)
    # Keep score consistent with `passed`: a failed verdict must not report a
    # score at/above the trust floor (Phase D gates on score).
    score = raw if passed else min(raw, _REPLAY_CONFIDENCE_FLOOR - 0.01)
    return EvalVerdict(passed=passed, score=round(score, 3), per_check=checks)


def evaluate_patch(
    *,
    round_id: str,
    workspace_dir: Path,
    samples: list[ReplaySample],
    patched_summary: str,
    provider_kind: str = "anthropic",
) -> EvalVerdict:
    """Materialize the round into the sandbox, run static + replay checks, return a verdict."""
    mat = materialize_round(round_id, workspace_dir)
    static = _static_checks(workspace_dir, mat)
    if any(not c.passed for c in static):
        return _verdict(static)  # don't judge a structurally broken patch
    replay = _replay_checks(samples, patched_summary=patched_summary, provider_kind=provider_kind)
    return _verdict(static + replay)
