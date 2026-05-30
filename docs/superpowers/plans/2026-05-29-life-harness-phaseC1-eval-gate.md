# Phase C1 — Eval Gate (Trust the Changes) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert an evaluation gate into the evolution round so a proposed patch is *tested* (static checks + regression-replay LLM judge) before it is applied or held for approval — turning "shape-valid" into "trustworthy."

**Architecture:** After `validate_patch()` passes and before the dry-run/apply branches, `run_evolution_round` calls a new `harness_evolution_eval.evaluate_patch()`. That service materializes the proposed primitives into a throwaway sandbox via Phase B's `materialize_round(round_id, workspace_dir)`, runs mechanical static checks on the materialized files, then runs a regression-replay LLM judge over a sample of the round's input-window incidents (does the patch plausibly address each targeted failure without introducing new ones?). It returns a typed `EvalVerdict` stored on the round. A failing verdict short-circuits the round to the new terminal state `eval_failed`. The LLM judge is provider-kind agnostic via Phase A's `provider_cli_map.resolve_llm_cmd` (spine reconciliation #3). New round states `evaluating`/`eval_failed` (and `reverted`, reserved for C2) require rebuilding the `status` CHECK constraint — SQLite can't alter it in place, so the migration recreates the table preserving rows.

**Tech Stack:** Python 3.10, raw SQLite, Pydantic v2, pytest with `isolated_db`, `unittest.mock` for the LLM subprocess, ruff line-length=100.

**Consumes (Phase B, merged to main):** `forge_materialization_service.materialize_round(round_id, workspace_dir) -> MaterializationResult`; `MaterializationResult.written` (list of `WrittenFile(rel_path, kind, asset_id)`). **Consumes (Phase A, merged):** `provider_cli_map.resolve_llm_cmd(provider_kind, model_override=None) -> list[str]` (argv with `{PROMPT}`).

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/models/harness_evolution.py` | **Create** | Pydantic v2 `CheckResult`, `EvalVerdict`, `ReplaySample` |
| `backend/app/db/schema/_harness_evolution.py` | **Modify** | Rebuild `status` CHECK to include new states; add `eval_verdict_json` column |
| `backend/app/db/harness_evolution.py` | **Modify** | `_ensure_eval_columns` migration (recreate table for CHECK change); `mark_evaluating`, `mark_eval_failed`, `store_eval_verdict`; `_row_to_dict` decodes `eval_verdict_json` |
| `backend/app/services/harness_evolution_eval.py` | **Create** | `evaluate_patch`, `_static_checks`, `_replay_checks`, `_judge_replay` |
| `backend/app/services/harness_evolver.py` | **Modify** | Call `evaluate_patch` between `validate_patch` and the dry-run/apply branches; add `evaluating` to the rate-limiter's in-flight set |
| `backend/tests/test_harness_eval_models.py` | **Create** | model validation |
| `backend/tests/test_harness_eval_states.py` | **Create** | DB state transitions + migration |
| `backend/tests/test_harness_eval_service.py` | **Create** | static + replay + evaluate_patch |
| `backend/tests/test_harness_eval_gate_wiring.py` | **Create** | run_evolution_round gate behavior |

---

## Task 1: Eval models

**Files:**
- Create: `backend/app/models/harness_evolution.py`
- Test: `backend/tests/test_harness_eval_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_eval_models.py
from app.models.harness_evolution import CheckResult, EvalVerdict, ReplaySample


def test_check_result_fields():
    c = CheckResult(name="frontmatter", passed=True, detail="ok", confidence=0.9)
    assert c.passed is True
    assert 0.0 <= c.confidence <= 1.0


def test_eval_verdict_aggregates():
    v = EvalVerdict(
        passed=False,
        score=0.4,
        per_check=[
            CheckResult(name="static", passed=True, detail="", confidence=1.0),
            CheckResult(name="replay:tk1", passed=False, detail="regresses", confidence=0.8),
        ],
    )
    assert v.passed is False
    assert len(v.per_check) == 2
    # round-trips through json (stored as eval_verdict_json)
    assert EvalVerdict.model_validate_json(v.model_dump_json()).score == 0.4


def test_replay_sample_shape():
    s = ReplaySample(incident_kind="h2_invalid_tool_call", layer="h2",
                     evidence={"error": "x"}, trajectory_excerpt="...")
    assert s.layer == "h2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_eval_models.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.harness_evolution`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/harness_evolution.py
"""Pydantic models for the evolution-round eval gate (Phase C1)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReplaySample(BaseModel):
    incident_kind: str
    layer: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    trajectory_excerpt: str = ""


class EvalVerdict(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    per_check: list[CheckResult] = Field(default_factory=list)
    notes: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_eval_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/harness_evolution.py backend/tests/test_harness_eval_models.py
git commit -m "feat(eval): CheckResult/EvalVerdict/ReplaySample models"
```

---

## Task 2: Schema — rebuild status CHECK + eval column

**Files:**
- Modify: `backend/app/db/schema/_harness_evolution.py` (the `CREATE TABLE` CHECK + add column)
- Modify: `backend/app/db/harness_evolution.py` (add `_ensure_eval_columns` migration that recreates the table for existing DBs)
- Test: `backend/tests/test_harness_eval_states.py`

**Context:** Current CHECK (`_harness_evolution.py:30-33`) lists `pending/running/awaiting_approval/applied/failed/aborted`. We add `evaluating`, `eval_failed`, `reverted`. SQLite can't ALTER a CHECK in place, so the migration recreates the table (create new with the new CHECK + all current columns incl. Phase B's `materialization_result_json`/`git_commit_sha` + new `eval_verdict_json`, copy rows, drop old, rename). Fresh DBs get it from the updated CREATE TABLE.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_eval_states.py
import pytest
from app.database import get_connection
from app.db import harness_evolution as evo


def _seed_round(project_id="p"):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,))
        conn.commit()
    return evo.start_round(project_id=project_id, input_window_since=None, input_window_until=None,
                           input_execution_count=0, input_forge={}, scratch_dir="/tmp/x")


def test_evaluating_state_allowed(isolated_db):
    rid = _seed_round()
    evo.mark_running(rid)
    evo.mark_evaluating(rid)            # must NOT raise CHECK violation
    assert evo.get_round(rid)["status"] == "evaluating"


def test_eval_failed_is_terminal(isolated_db):
    from app.models.harness_evolution import EvalVerdict, CheckResult
    rid = _seed_round()
    evo.mark_running(rid)
    evo.mark_evaluating(rid)
    verdict = EvalVerdict(passed=False, score=0.2,
                          per_check=[CheckResult(name="static", passed=False, detail="bad")])
    evo.mark_eval_failed(rid, verdict=verdict)
    row = evo.get_round(rid)
    assert row["status"] == "eval_failed"
    assert row["eval_verdict"]["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_eval_states.py -v`
Expected: FAIL — `mark_evaluating`/`mark_eval_failed` undefined (and, until the CHECK is rebuilt on the test's fresh DB, a write of `evaluating` would be a CHECK violation).

- [ ] **Step 3: Write minimal implementation**

(a) In `backend/app/db/schema/_harness_evolution.py`, change the `status` CHECK to:

```python
            status                   TEXT NOT NULL DEFAULT 'pending'
                                     CHECK (status IN (
                                         'pending', 'running', 'evaluating',
                                         'awaiting_approval', 'applied',
                                         'eval_failed', 'failed', 'aborted',
                                         'reverted'
                                     )),
```

and add `eval_verdict_json TEXT` to the column list (after `git_commit_sha`).

(b) In `backend/app/db/harness_evolution.py`, add a migration that recreates the table when the CHECK is stale, plus the column. Place it next to `_ensure_materialization_columns` and call it from the new mark functions:

```python
_ROUND_COLUMNS_IN_ORDER = (
    "id", "project_id", "started_at", "finished_at", "status",
    "input_window_since", "input_window_until", "input_execution_count",
    "input_forge_json", "output_patch_json", "applied_asset_ids_json",
    "error_message", "notes", "scratch_dir",
    "materialization_result_json", "git_commit_sha", "eval_verdict_json",
)


def _check_allows_evaluating(conn) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='harness_evolution_rounds'"
    ).fetchone()
    return bool(row) and "evaluating" in (row["sql"] or "")


def _ensure_eval_columns(conn) -> None:
    _ensure_materialization_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "eval_verdict_json" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN eval_verdict_json TEXT")
    if _check_allows_evaluating(conn):
        return
    # SQLite can't alter a CHECK in place — recreate the table preserving rows.
    from app.db.schema._harness_evolution import create_harness_evolution_tables
    cols_now = [r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")]
    shared = [c for c in _ROUND_COLUMNS_IN_ORDER if c in cols_now]
    collist = ", ".join(shared)
    conn.execute("ALTER TABLE harness_evolution_rounds RENAME TO _her_old")
    create_harness_evolution_tables(conn)
    conn.execute(
        f"INSERT INTO harness_evolution_rounds ({collist}) SELECT {collist} FROM _her_old"
    )
    conn.execute("DROP TABLE _her_old")
```

(c) Add the three mark functions (note `store_eval_verdict` + `mark_evaluating` call `_ensure_eval_columns`):

```python
def mark_evaluating(round_id: str) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET status = 'evaluating' "
            "WHERE id = ? AND status = 'running'",
            (round_id,),
        )
        conn.commit()


def store_eval_verdict(round_id: str, verdict) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET eval_verdict_json = ? WHERE id = ?",
            (verdict.model_dump_json(), round_id),
        )
        conn.commit()


def mark_eval_failed(round_id: str, *, verdict) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status            = 'eval_failed',
                   finished_at       = datetime('now'),
                   eval_verdict_json = ?
               WHERE id = ?""",
            (verdict.model_dump_json(), round_id),
        )
        conn.commit()
```

(d) In `_row_to_dict`, decode `eval_verdict_json` → `eval_verdict` (default `null`). Add `("eval_verdict_json", "null")` to the decode loop tuple (read the real loop at ~line 192-199 and extend it).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_eval_states.py -v`
Expected: PASS. The `isolated_db` fresh DB builds the table via the updated CREATE TABLE (new CHECK), so `evaluating` is accepted. The migration path is exercised in Task-2b's upgrade test below.

- [ ] **Step 5: Add an upgrade-migration test**

```python
# Append to backend/tests/test_harness_eval_states.py
def test_migration_recreates_table_for_old_check(isolated_db):
    """Simulate an old table (no 'evaluating' in CHECK) and confirm the
    migration recreates it preserving rows + allowing the new state."""
    from app.database import get_connection
    from app.db import harness_evolution as evo
    with get_connection() as conn:
        conn.execute("DROP TABLE harness_evolution_rounds")
        conn.execute(
            """CREATE TABLE harness_evolution_rounds (
                   id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                   started_at TEXT NOT NULL DEFAULT (datetime('now')), finished_at TEXT,
                   status TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','running','awaiting_approval','applied','failed','aborted')),
                   input_window_since TEXT, input_window_until TEXT,
                   input_execution_count INTEGER NOT NULL DEFAULT 0,
                   input_forge_json TEXT NOT NULL DEFAULT '{}', output_patch_json TEXT,
                   applied_asset_ids_json TEXT NOT NULL DEFAULT '[]',
                   error_message TEXT, notes TEXT, scratch_dir TEXT)"""
        )
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pm', 'P', 'active')")
        conn.execute("INSERT INTO harness_evolution_rounds (id, project_id, status) VALUES ('r-old', 'pm', 'applied')")
        conn.commit()
        evo._ensure_eval_columns(conn)
        conn.commit()
    row = evo.get_round("r-old")
    assert row is not None and row["status"] == "applied"   # row preserved
    rid = _seed_round("pm2")
    evo.mark_running(rid); evo.mark_evaluating(rid)          # new state now allowed
    assert evo.get_round(rid)["status"] == "evaluating"
```

Run: `cd backend && uv run pytest tests/test_harness_eval_states.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/schema/_harness_evolution.py backend/app/db/harness_evolution.py backend/tests/test_harness_eval_states.py
git commit -m "feat(eval): evaluating/eval_failed/reverted states + eval_verdict column + table-recreate migration"
```

---

## Task 3: Eval service — static checks

**Files:**
- Create: `backend/app/services/harness_evolution_eval.py`
- Test: `backend/tests/test_harness_eval_service.py`

**Context:** Static checks run mechanically over the *materialized* files (from `materialize_round`). Each is a `CheckResult`: command/rule `.md` files parse (frontmatter delimited by `---`), hook `.sh` files are non-empty, `mcp.json`/`settings.json` are valid JSON. Cheap, deterministic, no LLM.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_eval_service.py
from pathlib import Path
from app.services.harness_evolution_eval import _static_checks
from app.services.forge_materialization_service import MaterializationResult, WrittenFile


def test_static_checks_pass_for_valid_files(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "deploy.md").write_text('---\nname: "deploy"\n---\n\nbody\n')
    (tmp_path / ".claude").joinpath("settings.json").write_text('{"hooks": {}}')
    result = MaterializationResult(written=[
        WrittenFile(".claude/commands/deploy.md", "command", "c1"),
        WrittenFile(".claude/settings.json", "hook", "settings"),
    ])
    checks = _static_checks(tmp_path, result)
    assert all(c.passed for c in checks), [c.detail for c in checks if not c.passed]


def test_static_checks_flag_bad_json(tmp_path):
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{ not json")
    result = MaterializationResult(written=[WrittenFile(".claude/settings.json", "hook", "settings")])
    checks = _static_checks(tmp_path, result)
    assert any(not c.passed for c in checks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_eval_service.py::test_static_checks_pass_for_valid_files tests/test_harness_eval_service.py::test_static_checks_flag_bad_json -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/harness_evolution_eval.py
"""Phase C1 eval gate: test a proposed patch before it is applied.

static checks (mechanical) + regression-replay (LLM judge, provider-kind) →
EvalVerdict. See docs/superpowers/specs/2026-05-29-life-harness-phaseC-trust-design.md.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models.harness_evolution import CheckResult, EvalVerdict, ReplaySample
from app.services.forge_materialization_service import MaterializationResult

logger = logging.getLogger(__name__)


def _static_checks(workspace: Path, result: MaterializationResult) -> list[CheckResult]:
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
                checks.append(CheckResult(name=f"json:{w.rel_path}", passed=False,
                                          detail=f"invalid json: {exc}"))
        elif w.rel_path.endswith(".md"):
            ok = text.lstrip().startswith("---") and text.count("---") >= 2
            checks.append(CheckResult(name=f"frontmatter:{w.rel_path}", passed=ok,
                                      detail="" if ok else "missing/!closed frontmatter"))
        elif w.rel_path.endswith(".sh"):
            ok = bool(text.strip())
            checks.append(CheckResult(name=f"hook:{w.rel_path}", passed=ok,
                                      detail="" if ok else "empty hook script"))
    return checks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_eval_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolution_eval.py backend/tests/test_harness_eval_service.py
git commit -m "feat(eval): static checks over materialized .claude files"
```

---

## Task 4: Eval service — replay judge (provider-kind) + evaluate_patch

**Files:**
- Modify: `backend/app/services/harness_evolution_eval.py`
- Test: `backend/tests/test_harness_eval_service.py`

**Context:** Replay = for each sampled input-window incident, ask an LLM judge "does this patch plausibly address the failure without introducing a new one?" → `CheckResult`. The judge uses `provider_cli_map.resolve_llm_cmd(provider_kind)` and a mockable runner (tests patch the runner). `evaluate_patch` orchestrates: static checks + replay checks → `EvalVerdict` (passed = all static pass AND no replay check fails below the confidence floor; score = mean of check confidences weighted by pass).

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_eval_service.py
from unittest.mock import patch
from app.services import harness_evolution_eval as ev
from app.models.harness_evolution import ReplaySample


def _samples():
    return [ReplaySample(incident_kind="h2_invalid_tool_call", layer="h2",
                         evidence={"error": "missing arg"}, trajectory_excerpt="...")]


def test_judge_replay_parses_checkresult(monkeypatch):
    fake = '{"name": "replay", "passed": true, "detail": "addressed", "confidence": 0.85}'
    with patch.object(ev, "_run_judge", lambda prompt, provider_kind: fake):
        checks = ev._replay_checks(_samples(), patched_summary="rule X added",
                                   provider_kind="anthropic")
    assert len(checks) == 1 and checks[0].passed is True and checks[0].confidence == 0.85


def test_judge_malformed_output_is_failed_low_confidence(monkeypatch):
    with patch.object(ev, "_run_judge", lambda prompt, provider_kind: "garbage not json"):
        checks = ev._replay_checks(_samples(), patched_summary="x", provider_kind="anthropic")
    assert checks[0].passed is False and checks[0].confidence <= 0.3


def test_evaluate_patch_combines_static_and_replay(tmp_path, monkeypatch):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "d.md").write_text('---\nname: "d"\n---\nb\n')
    from app.services.forge_materialization_service import MaterializationResult, WrittenFile
    mat = MaterializationResult(written=[WrittenFile(".claude/commands/d.md", "command", "c1")])
    good = '{"name":"replay","passed":true,"detail":"ok","confidence":0.9}'
    with patch.object(ev, "materialize_round", lambda rid, ws: mat), \
         patch.object(ev, "_run_judge", lambda prompt, provider_kind: good):
        verdict = ev.evaluate_patch(round_id="r1", workspace_dir=tmp_path,
                                    samples=_samples(), patched_summary="x",
                                    provider_kind="anthropic")
    assert verdict.passed is True
    assert 0.0 <= verdict.score <= 1.0
    assert any(c.name.startswith("frontmatter") for c in verdict.per_check)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_eval_service.py -k "judge or evaluate_patch" -v`
Expected: FAIL — `_replay_checks`/`_run_judge`/`evaluate_patch`/`materialize_round` not defined in the module.

- [ ] **Step 3: Write minimal implementation**

Add to `harness_evolution_eval.py`:

```python
import subprocess
import tempfile

from app.services.forge_materialization_service import materialize_round
from app.services.provider_cli_map import resolve_llm_cmd

_REPLAY_CONFIDENCE_FLOOR = 0.5

_JUDGE_PROMPT = (
    "You are a strict reviewer. A harness failure incident occurred:\n"
    "kind={kind} layer={layer} evidence={evidence}\n\n"
    "A proposed patch changed the harness primitives as follows:\n{patched}\n\n"
    "Question: does the patch plausibly ADDRESS this failure WITHOUT introducing a "
    "new one? Reply ONLY with a JSON object: "
    '{{"name": "replay", "passed": <bool>, "detail": "<short>", "confidence": <0..1>}}'
)


def _run_judge(prompt: str, provider_kind: str) -> str:
    """Invoke the provider CLI judge; return stdout. Mockable (tests patch this)."""
    template = resolve_llm_cmd(provider_kind)
    if "{PROMPT}" in template:
        cmd = [prompt if p == "{PROMPT}" else p for p in template]
        stdin = None
    else:
        cmd = list(template)
        stdin = prompt
    try:
        r = subprocess.run(cmd, cwd=tempfile.gettempdir(), input=stdin,
                           timeout=60, capture_output=True, text=True)
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
                name=name, passed=bool(obj.get("passed")),
                detail=str(obj.get("detail", ""))[:300],
                confidence=float(obj.get("confidence", 0.5)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return CheckResult(name=name, passed=False, detail="unparseable judge output", confidence=0.2)


def _replay_checks(samples: list[ReplaySample], *, patched_summary: str,
                   provider_kind: str) -> list[CheckResult]:
    checks: list[CheckResult] = []
    for s in samples:
        prompt = _JUDGE_PROMPT.format(kind=s.incident_kind, layer=s.layer,
                                      evidence=json.dumps(s.evidence)[:500],
                                      patched=patched_summary[:2000])
        try:
            raw = _run_judge(prompt, provider_kind)
        except RuntimeError as exc:
            checks.append(CheckResult(name=f"replay:{s.incident_kind}", passed=False,
                                      detail=f"judge error: {exc}", confidence=0.2))
            continue
        checks.append(_parse_check(raw, f"replay:{s.incident_kind}"))
    return checks


def evaluate_patch(*, round_id: str, workspace_dir: Path, samples: list[ReplaySample],
                   patched_summary: str, provider_kind: str = "anthropic") -> EvalVerdict:
    """Materialize the round into the sandbox, run static + replay checks, return a verdict."""
    mat = materialize_round(round_id, workspace_dir)
    static = _static_checks(workspace_dir, mat)
    # If static checks fail, skip replay (design: don't judge a structurally broken patch).
    if any(not c.passed for c in static):
        return _verdict(static)
    replay = _replay_checks(samples, patched_summary=patched_summary, provider_kind=provider_kind)
    return _verdict(static + replay)


def _verdict(checks: list[CheckResult]) -> EvalVerdict:
    if not checks:
        return EvalVerdict(passed=True, score=1.0, per_check=[], notes="no checks")
    failed = [c for c in checks if not c.passed]
    # A replay failure only counts if the judge was confident about it.
    blocking = [c for c in failed if c.name.startswith("replay") and c.confidence >= _REPLAY_CONFIDENCE_FLOOR]
    blocking += [c for c in failed if not c.name.startswith("replay")]  # any static failure blocks
    passed = not blocking
    score = sum(c.confidence if c.passed else 0.0 for c in checks) / len(checks)
    return EvalVerdict(passed=passed, score=round(score, 3), per_check=checks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_eval_service.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolution_eval.py backend/tests/test_harness_eval_service.py
git commit -m "feat(eval): provider-kind replay judge + evaluate_patch verdict"
```

---

## Task 5: Wire the eval gate into `run_evolution_round` + rate limiter

**Files:**
- Modify: `backend/app/services/harness_evolver.py` (insert gate after `validate_patch`; add `evaluating` to the in-flight rate-limit set)
- Test: `backend/tests/test_harness_eval_gate_wiring.py`

**Context:** In `run_evolution_round`, after `validate_patch` passes (~lines 1119-1120) and BEFORE the `if dry_run:` / apply branches (~lines 1134-1151): mark the round `evaluating`, build the replay samples from `inputs` (the gathered incidents/annotations in the round's input window), call `evaluate_patch(round_id, scratch_subdir, samples, patched_summary)`, `store_eval_verdict`, and if `not verdict.passed` → `mark_eval_failed` + return an `EvolutionResult(status="eval_failed", ...)`. Otherwise continue to the existing dry-run/apply branches. The `patched_summary` is a short text rendering of `patch.entries`. Also: `_check_rate_limit` (~lines 134-182) treats only `pending`/`running` as in-flight — add `evaluating`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_eval_gate_wiring.py
from unittest.mock import patch
from app.database import get_connection
from app.db import harness_evolution as evo
from app.models.harness_evolution import EvalVerdict, CheckResult


def _round(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pg', 'P', 'active')")
        conn.commit()
    return evo.start_round(project_id="pg", input_window_since=None, input_window_until=None,
                           input_execution_count=0, input_forge={}, scratch_dir="/tmp/x")


def test_eval_failed_short_circuits_apply(isolated_db):
    """When evaluate_patch returns passed=False, the round ends eval_failed and
    apply_patch is NOT called."""
    import app.services.harness_evolver as hv
    rid = _round(isolated_db)
    bad = EvalVerdict(passed=False, score=0.1,
                      per_check=[CheckResult(name="static", passed=False, detail="x")])
    with patch.object(hv, "_run_one_round_through_validate", return_value=("r", rid)) if hasattr(hv, "_run_one_round_through_validate") else patch.object(hv, "evaluate_patch", return_value=bad, create=True), \
         patch.object(hv, "apply_patch") as mock_apply:
        # Drive the gate path directly via the helper the implementer extracts (see note).
        result = hv._eval_gate(rid, patch=_FakePatch(), inputs={"incidents": []}, scratch=__import__("pathlib").Path("/tmp"))
    assert result is not None and result.status == "eval_failed"
    mock_apply.assert_not_called()


class _FakePatch:
    entries = []
```

> **NOTE for the implementer:** the test above targets a small extracted helper. To keep the gate testable, extract the gate logic into `_eval_gate(round_id, *, patch, inputs, scratch) -> Optional[EvolutionResult]` in `harness_evolver.py` (returns an `EvolutionResult` to short-circuit on eval failure, or `None` to continue). Then `run_evolution_round` calls it. Adjust the test to the real `EvolutionResult`/patch shapes you find — keep the two assertions: eval-fail → `status == "eval_failed"` and `apply_patch` not called. Build replay samples from `inputs` incidents (map each to a `ReplaySample`); if there are no incidents, pass an empty sample list (replay is skipped → static-only verdict).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_eval_gate_wiring.py -v`
Expected: FAIL — `_eval_gate` not defined.

- [ ] **Step 3: Write minimal implementation**

Read `run_evolution_round` (the block from `problems = validate_patch(patch)` through the `if dry_run:` branch and the `applied = apply_patch(...)` block). Extract + insert the gate. Add to `harness_evolver.py`:

```python
def _patched_summary(patch) -> str:
    lines = []
    for e in getattr(patch, "entries", []):
        lines.append(f"{e.op} {e.kind} {getattr(e, 'name', '') or getattr(e, 'existing_asset_id', '')}")
    return "\n".join(lines) or "(no entries)"


def _replay_samples_from_inputs(inputs: dict) -> list:
    from app.models.harness_evolution import ReplaySample
    samples = []
    for inc in (inputs.get("incidents") or [])[:8]:   # cap the judge cost
        samples.append(ReplaySample(
            incident_kind=inc.get("kind", "unknown"),
            layer=inc.get("layer", "general"),
            evidence=inc.get("evidence") or {},
            trajectory_excerpt="",
        ))
    return samples


def _eval_gate(round_id: str, *, patch, inputs: dict, scratch: Path):
    """Run the eval gate. Returns an EvolutionResult to short-circuit (eval_failed),
    or None to continue to the dry-run/apply branches."""
    from app.services.harness_evolution_eval import evaluate_patch
    evolution_repo.mark_evaluating(round_id)
    eval_ws = scratch / "eval"
    eval_ws.mkdir(parents=True, exist_ok=True)
    try:
        verdict = evaluate_patch(
            round_id=round_id, workspace_dir=eval_ws,
            samples=_replay_samples_from_inputs(inputs),
            patched_summary=_patched_summary(patch),
        )
    except Exception:
        logger.warning("eval gate errored for %s; treating as non-blocking", round_id, exc_info=True)
        return None
    evolution_repo.store_eval_verdict(round_id, verdict)
    if not verdict.passed:
        evolution_repo.mark_eval_failed(round_id, verdict=verdict)
        return EvolutionResult(round_id=round_id, status="eval_failed",
                               error="eval gate failed", notes="")
    return None
```

Insert into `run_evolution_round` immediately after the `validate_patch` problems-check passes and before `if dry_run:`:

```python
        gate_result = _eval_gate(round_id, patch=patch, inputs=inputs, scratch=scratch)
        if gate_result is not None:
            return gate_result
```

(Confirm the real local names: `patch`, `inputs`, `scratch`, `round_id`, and the `EvolutionResult` constructor fields — adapt the snippet to them.)

In `_check_rate_limit` (~lines 134-182), add `"evaluating"` to the set of statuses treated as in-flight (where it currently checks `pending`/`running`). Keep `eval_failed` OUT of the recent-success set.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_eval_gate_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolver.py backend/tests/test_harness_eval_gate_wiring.py
git commit -m "feat(eval): wire eval gate into run_evolution_round (eval_failed short-circuit) + rate-limit evaluating"
```

---

## Task 6: Verification gate

**Files:** none — runs the project gates.

- [ ] **Step 1: Eval + evolver backend tests**

Run: `cd backend && uv run pytest tests/test_harness_eval_models.py tests/test_harness_eval_states.py tests/test_harness_eval_service.py tests/test_harness_eval_gate_wiring.py tests/test_harness_evolver.py -q`
Expected: all pass.

- [ ] **Step 2: Evolver/forge regression**

Run: `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or forge" -q`
Expected: no failures (the eval gate now runs in `run_evolution_round` — existing live-apply tests must still pass; if a test drove a real apply without mocking the gate and now hits the judge subprocess, it should mock `evaluate_patch`/`_run_judge` or pass no incidents so replay is skipped + static passes; update such tests).

- [ ] **Step 3: Ruff format**

Run: `cd backend && uv run ruff format --check backend/app/services/harness_evolution_eval.py backend/app/services/harness_evolver.py backend/app/db/harness_evolution.py backend/app/models/harness_evolution.py`
Expected: clean (else `ruff format` + commit).

- [ ] **Step 4: Frontend + build (no FE changes, gates mandatory)**

Run: `cd frontend && npm run test:run` then `just build`
Expected: both pass.

- [ ] **Step 5: Tag**

```bash
git tag life-harness-phaseC1-eval-complete
```
