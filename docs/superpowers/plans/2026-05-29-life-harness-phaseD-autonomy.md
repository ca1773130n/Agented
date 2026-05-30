# Phase D — Autonomy (Confidence-Gated Auto-Apply) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the harness apply its own high-confidence, low-blast-radius evolution rounds without a human in every loop — review-mode stays the default, autonomous-mode is per-project opt-in, with a global kill switch.

**Architecture:** Autonomy is a **poller**, NOT a change to the apply branch (cleaner + decoupled). Rounds run as today and land in `awaiting_approval` with a C1 `EvalVerdict` stored. A scheduled job (`autonomous_apply_job`) polls projects with an enabled `AutonomyPolicy`, and for each `awaiting_approval` round with a verdict and no prior autonomy decision, evaluates hard safety gates (eval passed + `score >= confidence_threshold`, blast radius ≤ `max_ops_per_round`, all patch kinds in `allowed_kinds`, no deletes if `block_deletes`, cooldown + daily rate-limit). Eligible → apply via the existing `apply_dry_run_round` (marking `auto_applied=1` + `auto_apply_reason`); ineligible → record `auto_apply_blocked_reason`. The global env `AGENTED_AUTONOMY=0` disables all autonomous applies (mirrors the existing `AGENTED_HARNESS_INJECT=0` kill switch).

**Key reconciliations (vs the design doc):** (1) the gate compares against `EvalVerdict.score` — C1's verdict has `score`, NOT `confidence`; a fail-open bypass verdict is `score=0.0` so it can never auto-apply. (2) `EvalVerdict` is imported from `app/models/harness_evolution.py` (single source of truth — spine reconciliation #2). (3) round audit columns use the C1/C2 schema-file + `_ensure_*_columns` pattern, not the `migrations/` module. (4) `never_delete_operator` is folded into `block_deletes` for v1 (the forge doesn't track per-primitive authorship; revisit when it does).

**Tech Stack:** Python 3.10, raw SQLite, Pydantic v2, pytest with `isolated_db`, ruff line-length=100; Vue 3 + TS (one badge + type extension).

**Consumes (merged to main):** round `eval_verdict` (C1, decoded by `get_round`), `apply_dry_run_round` (C2-era apply path), `evolution_repo.mark_applied`/`list_for_project`/`get_round`, scheduler `_setup_scheduler` `periodic_jobs` pattern.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/models/autonomy_policy.py` | **Create** | `AutonomyPolicy`, `AutonomyDecision`, `GateResult` (imports `EvalVerdict`) |
| `backend/app/db/schema/_project_autonomy.py` | **Create** | `project_autonomy_config` CREATE TABLE + register in schema init |
| `backend/app/db/project_autonomy_config.py` | **Create** | get_policy / upsert_policy / list_enabled |
| `backend/app/db/schema/_harness_evolution.py` | **Modify** | Add `auto_applied`/`auto_apply_reason`/`auto_apply_blocked_reason` columns |
| `backend/app/db/harness_evolution.py` | **Modify** | `_ensure_autonomy_columns`; `mark_applied` gains auto fields; `mark_auto_apply_blocked`; `count_recent_auto_applies`; `_row_to_dict` decode |
| `backend/app/services/harness_evolver.py` | **Modify** | `apply_dry_run_round` gains optional `auto_applied`/`auto_apply_reason` (default off) |
| `backend/app/services/harness_autonomy.py` | **Create** | `autonomous_apply_eligible` (gates) + `process_project_autonomy` (poller) |
| `backend/app_litestar/lifecycle.py` | **Modify** | `autonomous_apply_job` + register in `periodic_jobs` |
| `backend/app_litestar/routes/harness_evolution.py` | **Modify** | GET/PUT `/projects/{id}/autonomy` config |
| `frontend/src/services/api/harness-evolution.ts` | **Modify** | Extend `EvolutionRound` with auto fields |
| `frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue` | **Modify** | "Auto-applied" badge |
| tests | **Create** | `backend/tests/test_harness_autonomy.py` |

---

## Task 1: AutonomyPolicy + decision models

**Files:** Create `backend/app/models/autonomy_policy.py`; Test `backend/tests/test_harness_autonomy.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_autonomy.py
from app.models.autonomy_policy import AutonomyPolicy, AutonomyDecision, GateResult


def test_policy_defaults_are_safe():
    p = AutonomyPolicy()
    assert p.enabled is False                 # review-mode default
    assert 0.0 <= p.confidence_threshold <= 1.0
    assert p.confidence_threshold == 0.85
    assert p.max_ops_per_round == 5
    assert p.block_deletes is True            # safe default
    assert p.cooldown_seconds == 3600


def test_policy_bounds_enforced():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AutonomyPolicy(confidence_threshold=1.5)


def test_decision_shape():
    d = AutonomyDecision(eligible=False, gates=[GateResult(name="confidence", passed=False, detail="0.4 < 0.85")])
    assert d.eligible is False
    assert d.gates[0].name == "confidence"
    assert AutonomyDecision.model_validate_json(d.model_dump_json()).eligible is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/autonomy_policy.py
"""Phase D autonomy policy + decision models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AutonomyPolicy(BaseModel):
    enabled: bool = False                                    # review-mode is the default
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    max_ops_per_round: int = Field(default=5, ge=1)
    allowed_kinds: list[str] = Field(default_factory=lambda: ["rule", "memory"])
    block_deletes: bool = True
    cooldown_seconds: int = Field(default=3600, ge=0)
    rate_limit_per_day: int = Field(default=10, ge=0)


class GateResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class AutonomyDecision(BaseModel):
    eligible: bool
    gates: list[GateResult] = Field(default_factory=list)
    reason: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/autonomy_policy.py backend/tests/test_harness_autonomy.py
git commit -m "feat(autonomy): AutonomyPolicy + AutonomyDecision models (review-mode default)"
```

---

## Task 2: `project_autonomy_config` table + repo

**Files:** Create `backend/app/db/schema/_project_autonomy.py`; Create `backend/app/db/project_autonomy_config.py`; register the schema; Test in `test_harness_autonomy.py`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_autonomy.py
from app.db import project_autonomy_config as cfg
from app.models.autonomy_policy import AutonomyPolicy


def test_upsert_and_get_policy(isolated_db):
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa', 'P', 'active')")
        conn.commit()
    assert cfg.get_policy("pa") is None
    cfg.upsert_policy("pa", AutonomyPolicy(enabled=True, confidence_threshold=0.9))
    p = cfg.get_policy("pa")
    assert p.enabled is True and p.confidence_threshold == 0.9


def test_list_enabled(isolated_db):
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa1', 'P', 'active')")
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pa2', 'P', 'active')")
        conn.commit()
    cfg.upsert_policy("pa1", AutonomyPolicy(enabled=True))
    cfg.upsert_policy("pa2", AutonomyPolicy(enabled=False))
    ids = {row["project_id"] for row in cfg.list_enabled()}
    assert "pa1" in ids and "pa2" not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -k "policy or list_enabled" -v`
Expected: FAIL — module/table missing.

- [ ] **Step 3: Write minimal implementation**

(a) `backend/app/db/schema/_project_autonomy.py`:
```python
"""project_autonomy_config — per-project autonomous-apply policy (Phase D)."""
from __future__ import annotations


def create_project_autonomy_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_autonomy_config (
            project_id  TEXT PRIMARY KEY,
            enabled     INTEGER NOT NULL DEFAULT 0,
            policy_json TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_autonomy_enabled "
        "ON project_autonomy_config(enabled)"
    )
```
Register `create_project_autonomy_tables` wherever the schema modules are wired (read `backend/app/db/schema/__init__.py` — find how e.g. `create_harness_evolution_tables` is called in the schema-build sequence and add this alongside it).

(b) `backend/app/db/project_autonomy_config.py`:
```python
"""Repository for per-project autonomy policy."""
from __future__ import annotations

import json
from typing import Optional

from app.database import get_connection
from app.models.autonomy_policy import AutonomyPolicy


def get_policy(project_id: str) -> Optional[AutonomyPolicy]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT policy_json FROM project_autonomy_config WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        return AutonomyPolicy.model_validate_json(row["policy_json"])
    except Exception:
        return AutonomyPolicy()


def upsert_policy(project_id: str, policy: AutonomyPolicy) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO project_autonomy_config (project_id, enabled, policy_json, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(project_id) DO UPDATE SET
                   enabled=excluded.enabled, policy_json=excluded.policy_json,
                   updated_at=datetime('now')""",
            (project_id, 1 if policy.enabled else 0, policy.model_dump_json()),
        )
        conn.commit()


def list_enabled() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT project_id, policy_json FROM project_autonomy_config WHERE enabled = 1"
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v`
Expected: PASS. (If the schema isn't auto-created in `isolated_db`, ensure the registration in step (a) is reached by the test DB build — read how other new tables like `project_forge_bindings` get created.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/schema/_project_autonomy.py backend/app/db/project_autonomy_config.py backend/app/db/schema/__init__.py backend/tests/test_harness_autonomy.py
git commit -m "feat(autonomy): project_autonomy_config table + repo"
```

---

## Task 3: Round audit columns + DB functions

**Files:** Modify `_harness_evolution.py` (schema), `harness_evolution.py` (db fns); Test in `test_harness_autonomy.py`.

**Context:** Round audit columns follow the C1/C2 pattern (schema CREATE TABLE + `_ensure_*_columns` runtime ALTER + `_ROUND_COLUMNS_IN_ORDER` so the C1 table-recreate preserves them).

- [ ] **Step 1: Write the failing test**

```python
# Append to test_harness_autonomy.py
import json
from app.db import harness_evolution as evo


def _awaiting_round(project_id="pr", verdict=None, entries=1):
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,))
        conn.commit()
    rid = evo.start_round(project_id=project_id, input_window_since=None, input_window_until=None,
                          input_execution_count=0, input_forge={}, scratch_dir="/tmp/x")
    evo.mark_running(rid)
    evo.mark_awaiting_approval(rid, output_patch={"entries": [{"op": "create", "kind": "rule"}] * entries})
    if verdict is not None:
        evo.store_eval_verdict(rid, verdict)
    return rid


def test_mark_applied_records_auto_fields(isolated_db):
    rid = _awaiting_round()
    evo.mark_applied(rid, output_patch={"entries": []}, applied_asset_ids=[], notes="",
                     auto_applied=True, auto_apply_reason={"eligible": True, "score": 0.9})
    row = evo.get_round(rid)
    assert row["auto_applied"] == 1
    assert row["auto_apply_reason"]["score"] == 0.9


def test_mark_auto_apply_blocked(isolated_db):
    rid = _awaiting_round()
    evo.mark_auto_apply_blocked(rid, {"eligible": False, "gate": "confidence"})
    row = evo.get_round(rid)
    assert row["status"] == "awaiting_approval"          # blocked != applied
    assert row["auto_apply_blocked_reason"]["gate"] == "confidence"


def test_count_recent_auto_applies(isolated_db):
    rid = _awaiting_round("prc")
    evo.mark_applied(rid, output_patch={"entries": []}, applied_asset_ids=[], notes="",
                     auto_applied=True, auto_apply_reason={"eligible": True})
    assert evo.count_recent_auto_applies("prc", since="2000-01-01T00:00:00") >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -k "auto" -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

(a) `_harness_evolution.py` CREATE TABLE — add after `revert_error`:
```
            auto_applied             INTEGER NOT NULL DEFAULT 0,
            auto_apply_reason        TEXT,
            auto_apply_blocked_reason TEXT
```

(b) `harness_evolution.py` — add the 3 to `_ROUND_COLUMNS_IN_ORDER`; add:
```python
def _ensure_autonomy_columns(conn) -> None:
    _ensure_revert_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "auto_applied" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN auto_applied INTEGER NOT NULL DEFAULT 0")
    for col in ("auto_apply_reason", "auto_apply_blocked_reason"):
        if col not in cols:
            conn.execute(f"ALTER TABLE harness_evolution_rounds ADD COLUMN {col} TEXT")
```

Extend `mark_applied` with `auto_applied: bool = False, auto_apply_reason: Optional[dict] = None`; call `_ensure_autonomy_columns(conn)`; add `auto_applied = ?, auto_apply_reason = ?` to the SET + params (`1 if auto_applied else 0`, `json.dumps(auto_apply_reason) if auto_apply_reason else None`). Preserve ALL existing columns.

Add:
```python
def mark_auto_apply_blocked(round_id: str, reason: dict) -> None:
    with get_connection() as conn:
        _ensure_autonomy_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET auto_apply_blocked_reason = ? "
            "WHERE id = ? AND status = 'awaiting_approval'",
            (json.dumps(reason), round_id),
        )
        conn.commit()


def count_recent_auto_applies(project_id: str, *, since: str) -> int:
    with get_connection() as conn:
        _ensure_autonomy_columns(conn)
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM harness_evolution_rounds "
            "WHERE project_id = ? AND auto_applied = 1 AND finished_at >= ?",
            (project_id, since),
        ).fetchone()
    return int(row["c"]) if row else 0
```

(c) `_row_to_dict` decode: add `("auto_apply_reason", "null")` and `("auto_apply_blocked_reason", "null")` to the decode loop. `auto_applied` passes through as int via `dict(row)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/schema/_harness_evolution.py backend/app/db/harness_evolution.py backend/tests/test_harness_autonomy.py
git commit -m "feat(autonomy): round audit columns + mark auto_applied/blocked + recent-auto-apply count"
```

---

## Task 4: Decision logic — `autonomous_apply_eligible`

**Files:** Create `backend/app/services/harness_autonomy.py`; Test in `test_harness_autonomy.py`.

**Context:** Pure decision function over a round row + policy + verdict + recent count. Gates (ALL must pass): global kill switch (`AGENTED_AUTONOMY != "0"`), `policy.enabled`, eval present + `verdict.passed`, `verdict.score >= confidence_threshold`, blast radius (`len(entries) <= max_ops_per_round`), allowed_kinds (every entry's kind in `allowed_kinds`), no deletes if `block_deletes`, cooldown + daily rate-limit (caller passes `recent_auto_applies` count + a cooldown check). Returns `AutonomyDecision` with a `GateResult` per gate.

- [ ] **Step 1: Write the failing test**

```python
# Append to test_harness_autonomy.py
from app.services.harness_autonomy import autonomous_apply_eligible
from app.models.autonomy_policy import AutonomyPolicy


def _round(entries, score=0.9, passed=True):
    return {
        "id": "r", "project_id": "p", "status": "awaiting_approval",
        "output_patch": {"entries": entries},
        "eval_verdict": {"passed": passed, "score": score, "per_check": []},
    }


def test_eligible_when_all_gates_pass(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"], confidence_threshold=0.85)
    rnd = _round([{"op": "create", "kind": "rule"}])
    d = autonomous_apply_eligible(rnd, policy, recent_auto_applies=0, recent_within_cooldown=False)
    assert d.eligible is True


def test_low_score_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"])
    d = autonomous_apply_eligible(_round([{"op": "create", "kind": "rule"}], score=0.4),
                                  policy, recent_auto_applies=0, recent_within_cooldown=False)
    assert d.eligible is False
    assert any(g.name == "confidence" and not g.passed for g in d.gates)


def test_kill_switch_blocks(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "0")
    policy = AutonomyPolicy(enabled=True)
    d = autonomous_apply_eligible(_round([{"op": "create", "kind": "rule"}]),
                                  policy, recent_auto_applies=0, recent_within_cooldown=False)
    assert d.eligible is False and any(g.name == "kill_switch" for g in d.gates)


def test_delete_blocked_by_default(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"], block_deletes=True)
    d = autonomous_apply_eligible(_round([{"op": "delete", "kind": "rule"}]),
                                  policy, recent_auto_applies=0, recent_within_cooldown=False)
    assert d.eligible is False and any(g.name == "block_deletes" and not g.passed for g in d.gates)


def test_blast_radius_and_rate_limit(monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule"], max_ops_per_round=2, rate_limit_per_day=3)
    big = _round([{"op": "create", "kind": "rule"}] * 5)
    assert autonomous_apply_eligible(big, policy, recent_auto_applies=0, recent_within_cooldown=False).eligible is False
    ok = _round([{"op": "create", "kind": "rule"}])
    assert autonomous_apply_eligible(ok, policy, recent_auto_applies=3, recent_within_cooldown=False).eligible is False  # rate limit hit
    assert autonomous_apply_eligible(ok, policy, recent_auto_applies=0, recent_within_cooldown=True).eligible is False  # cooldown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -k "eligible or blocks or kill or delete or blast" -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/harness_autonomy.py
"""Phase D: confidence-gated autonomous apply (decision + poller)."""
from __future__ import annotations

import logging
import os

from app.models.autonomy_policy import AutonomyDecision, AutonomyPolicy, GateResult

logger = logging.getLogger(__name__)


def _kill_switch_on() -> bool:
    return os.environ.get("AGENTED_AUTONOMY", "1") == "0"


def autonomous_apply_eligible(
    round_row: dict, policy: AutonomyPolicy, *,
    recent_auto_applies: int, recent_within_cooldown: bool,
) -> AutonomyDecision:
    gates: list[GateResult] = []
    entries = ((round_row.get("output_patch") or {}).get("entries")) or []
    verdict = round_row.get("eval_verdict") or {}
    kinds = {e.get("kind") for e in entries}
    has_delete = any(e.get("op") == "delete" for e in entries)
    score = float(verdict.get("score", 0.0))

    gates.append(GateResult(name="kill_switch", passed=not _kill_switch_on(),
                            detail="AGENTED_AUTONOMY=0" if _kill_switch_on() else ""))
    gates.append(GateResult(name="enabled", passed=bool(policy.enabled)))
    gates.append(GateResult(name="eval_present", passed=bool(verdict) and bool(verdict.get("passed")),
                            detail="" if verdict else "no eval verdict"))
    gates.append(GateResult(name="confidence", passed=score >= policy.confidence_threshold,
                            detail=f"{score} < {policy.confidence_threshold}" if score < policy.confidence_threshold else ""))
    gates.append(GateResult(name="blast_radius", passed=len(entries) <= policy.max_ops_per_round,
                            detail=f"{len(entries)} > {policy.max_ops_per_round}" if len(entries) > policy.max_ops_per_round else ""))
    bad_kinds = [k for k in kinds if k not in policy.allowed_kinds]
    gates.append(GateResult(name="allowed_kinds", passed=not bad_kinds,
                            detail=f"disallowed: {bad_kinds}" if bad_kinds else ""))
    gates.append(GateResult(name="block_deletes", passed=not (policy.block_deletes and has_delete),
                            detail="patch contains a delete" if (policy.block_deletes and has_delete) else ""))
    gates.append(GateResult(name="cooldown", passed=not recent_within_cooldown,
                            detail="within cooldown" if recent_within_cooldown else ""))
    gates.append(GateResult(name="rate_limit", passed=recent_auto_applies < policy.rate_limit_per_day,
                            detail=f"{recent_auto_applies} >= {policy.rate_limit_per_day}" if recent_auto_applies >= policy.rate_limit_per_day else ""))

    eligible = all(g.passed for g in gates)
    reason = "" if eligible else "; ".join(f"{g.name}:{g.detail or 'fail'}" for g in gates if not g.passed)
    return AutonomyDecision(eligible=eligible, gates=gates, reason=reason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_autonomy.py backend/tests/test_harness_autonomy.py
git commit -m "feat(autonomy): autonomous_apply_eligible hard gates (kill switch, score, blast, kinds, deletes, cooldown, rate-limit)"
```

---

## Task 5: Poller + auto-apply path

**Files:** Modify `backend/app/services/harness_autonomy.py` (add `process_project_autonomy`); Modify `harness_evolver.py` (`apply_dry_run_round` gains optional auto fields); Test in `test_harness_autonomy.py`.

**Context:** `process_project_autonomy(project_id)` loads the policy (skip if None/disabled), lists `awaiting_approval` rounds with an `eval_verdict` and NO prior autonomy decision (`auto_applied != 1` and `auto_apply_blocked_reason` is None), and for each: compute cooldown/recent counts, call `autonomous_apply_eligible`, then either auto-apply or record the blocked reason. The auto-apply reuses `apply_dry_run_round(round_id, auto_applied=True, auto_apply_reason=...)`.

- [ ] **Step 1: Write the failing test**

```python
# Append to test_harness_autonomy.py
from unittest.mock import patch
from app.models.harness_evolution import EvalVerdict, CheckResult


def test_poller_auto_applies_eligible(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy
    rid = _awaiting_round("ppa", verdict=EvalVerdict(passed=True, score=0.95,
                          per_check=[CheckResult(name="s", passed=True)]), entries=1)
    cfg.upsert_policy("ppa", AutonomyPolicy(enabled=True, allowed_kinds=["rule"]))
    # mock the actual apply so we don't drive the whole apply machinery
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        results = process_project_autonomy("ppa")
    assert mock_apply.called
    # the round was passed auto_applied=True
    _, kwargs = mock_apply.call_args
    assert kwargs.get("auto_applied") is True


def test_poller_blocks_low_score(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.db import harness_evolution as evo
    from app.services.harness_autonomy import process_project_autonomy
    rid = _awaiting_round("ppb", verdict=EvalVerdict(passed=True, score=0.4,
                          per_check=[CheckResult(name="s", passed=True)]), entries=1)
    cfg.upsert_policy("ppb", AutonomyPolicy(enabled=True, allowed_kinds=["rule"]))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppb")
    assert not mock_apply.called
    assert evo.get_round(rid)["auto_apply_blocked_reason"] is not None


def test_poller_skips_disabled(isolated_db, monkeypatch):
    monkeypatch.setenv("AGENTED_AUTONOMY", "1")
    from app.db import project_autonomy_config as cfg
    from app.services.harness_autonomy import process_project_autonomy
    _awaiting_round("ppd", verdict=EvalVerdict(passed=True, score=0.95), entries=1)
    cfg.upsert_policy("ppd", AutonomyPolicy(enabled=False))
    with patch("app.services.harness_autonomy.apply_dry_run_round") as mock_apply:
        process_project_autonomy("ppd")
    assert not mock_apply.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -k "poller" -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

(a) In `harness_evolver.py`, extend `apply_dry_run_round` (read its real body first — it applies the awaiting round then mark_applied) to accept `*, auto_applied: bool = False, auto_apply_reason: Optional[dict] = None` and pass them through to its `mark_applied(...)` call. Manual callers (operator approve route) don't pass them → behavior unchanged.

(b) In `harness_autonomy.py`, add the poller (import `apply_dry_run_round` at module top for the test's patch target — confirm no circular import; if circular, import locally and patch `app.services.harness_evolver.apply_dry_run_round` in the test instead):
```python
import datetime as _dt

from app.db import harness_evolution as evo_repo
from app.db import project_autonomy_config as autonomy_cfg
from app.services.harness_evolver import apply_dry_run_round


def _cooldown_cutoff(seconds: int) -> str:
    return (_dt.datetime.utcnow() - _dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S")


def process_project_autonomy(project_id: str) -> list[dict]:
    """Evaluate + auto-apply eligible awaiting_approval rounds for one project."""
    policy = autonomy_cfg.get_policy(project_id)
    if policy is None or not policy.enabled:
        return []
    results: list[dict] = []
    day_cut = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    cooldown_cut = _cooldown_cutoff(policy.cooldown_seconds)
    for rnd in evo_repo.list_for_project(project_id, limit=50):
        if rnd.get("status") != "awaiting_approval":
            continue
        if rnd.get("auto_applied") == 1 or rnd.get("auto_apply_blocked_reason"):
            continue
        if not rnd.get("eval_verdict"):
            continue
        recent = evo_repo.count_recent_auto_applies(project_id, since=day_cut)
        within_cooldown = evo_repo.count_recent_auto_applies(project_id, since=cooldown_cut) > 0
        decision = autonomous_apply_eligible(
            rnd, policy, recent_auto_applies=recent, recent_within_cooldown=within_cooldown,
        )
        reason = {"eligible": decision.eligible,
                  "gates": [g.model_dump() for g in decision.gates],
                  "reason": decision.reason,
                  "score": float((rnd.get("eval_verdict") or {}).get("score", 0.0))}
        if decision.eligible:
            try:
                apply_dry_run_round(rnd["id"], auto_applied=True, auto_apply_reason=reason)
                results.append({"round_id": rnd["id"], "action": "auto_applied"})
            except Exception:
                logger.warning("autonomy: auto-apply failed for %s", rnd["id"], exc_info=True)
                evo_repo.mark_auto_apply_blocked(rnd["id"], {**reason, "error": "apply failed"})
        else:
            evo_repo.mark_auto_apply_blocked(rnd["id"], reason)
            results.append({"round_id": rnd["id"], "action": "blocked", "reason": decision.reason})
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_autonomy.py -v` then `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or autonomy" -q 2>&1 | tail -6`
Expected: pass; no regression (the `apply_dry_run_round` signature change must not break the operator-approve route — it doesn't pass the new kwargs).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_autonomy.py backend/app/services/harness_evolver.py backend/tests/test_harness_autonomy.py
git commit -m "feat(autonomy): process_project_autonomy poller + auto-apply path (apply_dry_run_round auto fields)"
```

---

## Task 6: Scheduler job + config routes + frontend badge

**Files:** Modify `lifecycle.py` (job), `routes/harness_evolution.py` (config routes), `harness-evolution.ts` (type), `HarnessEvolutionCard.vue` (badge).

- [ ] **Step 1 (backend job):** In `lifecycle.py`, add a top-level job (mirror `purge_trigger_events_job`):
```python
def autonomous_apply_job() -> None:
    """Periodic: evaluate + auto-apply eligible rounds for autonomy-enabled projects."""
    try:
        from app.db import project_autonomy_config as cfg
        from app.services.harness_autonomy import process_project_autonomy
        for row in cfg.list_enabled():
            try:
                process_project_autonomy(row["project_id"])
            except Exception:
                logger.warning("autonomy job: project %s failed", row.get("project_id"), exc_info=True)
    except Exception:
        logger.warning("autonomous_apply_job failed", exc_info=True)
```
Register it in the `periodic_jobs` list in `_setup_scheduler` (read the list + match the `(func, interval_kwargs, job_id)` shape; use e.g. a 5-minute interval).

- [ ] **Step 2 (config routes):** In `routes/harness_evolution.py`, add (match the file's handler style):
```python
@get("/projects/{project_id:str}/autonomy", sync_to_thread=False)
def get_autonomy_config(project_id: str) -> dict[str, Any]:
    from app.db.project_autonomy_config import get_policy
    p = get_policy(project_id)
    from app.models.autonomy_policy import AutonomyPolicy
    return {"project_id": project_id, "policy": (p or AutonomyPolicy()).model_dump(),
            "configured": p is not None}


@put("/projects/{project_id:str}/autonomy", sync_to_thread=True)
def set_autonomy_config(project_id: str, data: dict) -> dict[str, Any]:
    from app.db.project_autonomy_config import upsert_policy
    from app.models.autonomy_policy import AutonomyPolicy
    policy = AutonomyPolicy.model_validate(data.get("policy") or {})
    upsert_policy(project_id, policy)
    return {"project_id": project_id, "policy": policy.model_dump()}
```
Import `get`/`put` as needed; register both in the router's `route_handlers`.

- [ ] **Step 3 (frontend):** Extend `EvolutionRound` in `harness-evolution.ts` with `auto_applied?: number; auto_apply_reason?: Record<string, unknown> | null; auto_apply_blocked_reason?: Record<string, unknown> | null;`. In `HarnessEvolutionCard.vue`, when `round.status === 'applied' && round.auto_applied`, render an `Auto-applied` badge next to the status pill (show `score` from `auto_apply_reason` if present). Add a frontend test if the card has an existing test file (`HarnessEvolutionCard.test.ts` / detail-modal test); else note skipped.

- [ ] **Step 4:** Run `cd backend && uv run pytest tests/test_harness_autonomy.py -q` + `cd frontend && npm run test:run`.

- [ ] **Step 5: Commit**

```bash
git add backend/app_litestar/lifecycle.py backend/app_litestar/routes/harness_evolution.py frontend/src/services/api/harness-evolution.ts frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue [tests]
git commit -m "feat(autonomy): scheduler job + config routes + auto-applied badge"
```

---

## Task 7: Verification gate

- [ ] **Step 1:** `cd backend && uv run pytest tests/test_harness_autonomy.py tests/test_harness_evolver.py -q`
- [ ] **Step 2:** `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or autonomy or forge" -q` (no regressions — esp. apply_dry_run_round signature change + the C1 table-recreate migration now preserving the new auto columns)
- [ ] **Step 3:** `cd backend && uv run ruff format --check` + `ruff check` on the touched backend files
- [ ] **Step 4:** `cd frontend && npm run test:run` + `just build`
- [ ] **Step 5:** `git tag life-harness-phaseD-autonomy-complete`

All gates must pass.
