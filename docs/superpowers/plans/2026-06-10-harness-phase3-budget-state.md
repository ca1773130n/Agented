# Harness-1 Phase 3 — Live Budget Discipline + Operator State Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-run incremental budget accounting with a soft-warn/hard-kill ceiling, plus a `GET /executions/{id}/state` snapshot endpoint and a minimal Vue operator panel.

**Architecture:** All live accounting runs inside the **existing** per-execution `budget_monitor` thread (`execution_runner.py:111`) via a new testable module-level helper `_per_run_budget_tick` — nothing on the `append_log` hot path, no new threads. Cost flows: live stdout buffer → `extract_token_usage` (partial-log capable) → new `BudgetService.cost_from_usage` (native cost or `MODEL_PRICING` estimate) → `harness_runs.budget_used` (Phase-1 table) → warn at ≥80% / SIGKILL at ≥100% of a new nullable `budget_limits.per_run_limit_usd` (migration 151; NULL = off). The `/state` endpoint composes Phase-1/2 state read-only; the Vue panel polls it inside ExecutionHistory's log modal.

**Tech Stack:** Python 3.10+/raw SQLite/Litestar/pytest (backend); Vue 3 + TS + vue-i18n + Vitest/@vue/test-utils (frontend); ruff line-length 100.

**Per-backend honesty (carries into code comments + tests):** codex JSONL accumulates → genuine incremental accounting; claude/gemini emit usage only in terminal JSON → extraction returns `None` mid-run and every per-run check **no-ops** (documented limitation, not hidden).

**Conventions:**
- Migrations: `_migrate_NNN_<name>(conn)` + `(NNN, "<name>", fn)` in `V07_MIGRATIONS` (`v07_features.py`; current max **150** → this phase uses **151**). PRAGMA-guarded ALTER pattern: see `_migrate_144_token_usage_immutable_date`.
- Targeted pytest only (`uv run pytest tests/<file>.py -q`) — the full serial suite hangs.
- Frontend component tests are colocated: `src/components/<area>/__tests__/<Name>.test.ts` (see `components/monitoring/__tests__/BudgetLimitForm.test.ts`).
- i18n: every new key goes into ALL FOUR catalogs (`src/locales/{en,ko,ja,zh}.json`), key-identical.

---

## Task 1: `per_run_limit_usd` column — migration 151 + budgets get/set

**Files:**
- Modify: `backend/app/db/schema/_misc.py` (budget_limits DDL at ~:59 — add column)
- Modify: `backend/app/db/budgets.py` (`set_budget_limit` at ~:379, `get_budget_limit` needs no change — `SELECT *`)
- Modify: `backend/app/db/migrations/v07_features.py` (add `_migrate_151_per_run_budget_limit` + registry tuple)
- Test: `backend/tests/test_migration_151_per_run_limit.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_151_per_run_limit.py
"""Migration 151: nullable per-run budget ceiling (Harness-1 Phase 3, P6)."""

from app.db.budgets import get_budget_limit, set_budget_limit
from app.db.connection import get_connection


def test_migration_151_registered():
    from app.db.migrations import VERSIONED_MIGRATIONS

    versions = {v for (v, _n, _f) in VERSIONED_MIGRATIONS}
    names = {n for (_v, n, _f) in VERSIONED_MIGRATIONS}
    assert 151 in versions
    assert "per_run_budget_limit" in names


def test_fresh_schema_has_column():
    """Call create_fresh_schema DIRECTLY — the isolated_db fixture runs all
    migrations too, so checking the fixture DB would pass even if only the
    migration (not the fresh DDL) added the column (false positive)."""
    import sqlite3

    from app.db.schema import create_fresh_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_fresh_schema(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    assert "per_run_limit_usd" in cols


def test_migration_151_alter_is_idempotent():
    import sqlite3

    from app.db.migrations.v07_features import _migrate_151_per_run_budget_limit

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE budget_limits (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id TEXT)"
    )
    _migrate_151_per_run_budget_limit(conn)
    _migrate_151_per_run_budget_limit(conn)  # second run must not raise
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    assert "per_run_limit_usd" in cols


def test_set_and_get_round_trips_per_run_limit():
    assert set_budget_limit("trigger", "t-1", per_run_limit_usd=2.5) is True
    row = get_budget_limit("trigger", "t-1")
    assert row["per_run_limit_usd"] == 2.5
    # Upsert keeps it updatable
    assert set_budget_limit("trigger", "t-1", per_run_limit_usd=3.0) is True
    assert get_budget_limit("trigger", "t-1")["per_run_limit_usd"] == 3.0


def test_set_rejects_nonpositive_per_run_limit():
    """<= 0 is rejected: NULL is the only 'off' state, so the tick's
    `if not limit` check is unambiguous (0.0 can never be stored)."""
    assert set_budget_limit("trigger", "t-2", per_run_limit_usd=-1.0) is False
    assert set_budget_limit("trigger", "t-2", per_run_limit_usd=0.0) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_migration_151_per_run_limit.py -q`
Expected: FAIL — `_migrate_151_per_run_budget_limit` missing; `set_budget_limit() got an unexpected keyword argument`.

- [ ] **Step 3: Add the column to the fresh DDL**

In `backend/app/db/schema/_misc.py`, inside the `budget_limits` CREATE TABLE (~:59), add after `max_monthly_runs INTEGER,`:

```sql
            per_run_limit_usd REAL,
```

- [ ] **Step 4: Add migration 151**

In `backend/app/db/migrations/v07_features.py`, before `V07_MIGRATIONS`:

```python
def _migrate_151_per_run_budget_limit(conn):
    """Harness-1 Phase 3 (P6): nullable per-run cost ceiling on budget_limits.
    NULL = feature off (default), so existing installs are unchanged.
    PRAGMA-guarded ALTER — idempotent (pattern: _migrate_144)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    if "per_run_limit_usd" not in cols:
        conn.execute("ALTER TABLE budget_limits ADD COLUMN per_run_limit_usd REAL")
```

And append to `V07_MIGRATIONS` (after the `150, "verification_records"` tuple):

```python
    # Harness-1 Phase 3: per-run budget ceiling (soft warn 80% / hard kill 100%).
    (151, "per_run_budget_limit", _migrate_151_per_run_budget_limit),
```

- [ ] **Step 5: Extend `set_budget_limit`**

In `backend/app/db/budgets.py` — four changes, mirroring how `max_monthly_runs` flows through:

1. Signature: add `per_run_limit_usd: Optional[float] = None,` after `max_monthly_runs`.
2. The "at least one limit provided" guard (~:389): add `or per_run_limit_usd is not None`.
3. Validation (next to the existing `hard < soft` check) — reject `<= 0` so
   NULL is the only "off" state and the monitor's `if not limit` is unambiguous:
```python
    if per_run_limit_usd is not None and per_run_limit_usd <= 0:
        logger.warning("per_run_limit_usd must be positive")
        return False
```
4. The INSERT: add `per_run_limit_usd` to the column list, a `?` to VALUES, `per_run_limit_usd = excluded.per_run_limit_usd,` to the UPSERT SET, and `per_run_limit_usd,` to the params tuple (keep tuple order matching the column order).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_migration_151_per_run_limit.py -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/schema/_misc.py backend/app/db/budgets.py backend/app/db/migrations/v07_features.py backend/tests/test_migration_151_per_run_limit.py
git commit -m "feat(harness): per_run_limit_usd on budget_limits + migration 151 (Phase 3 P6)"
```

---

## Task 2: `cost_from_usage` + `update_budget_used` + `count_checkpoints`

**Files:**
- Modify: `backend/app/services/budget_service.py` (new classmethod near `estimate_cost` ~:265)
- Modify: `backend/app/db/harness_state.py` (two new fns)
- Test: `backend/tests/test_cost_from_usage.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cost_from_usage.py
"""Token->USD conversion + live budget_used upsert (Harness-1 Phase 3, P6)."""

import pytest

from app.db import harness_state
from app.services.budget_service import BudgetService


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="codex",
        command="echo hi",
    )


def test_native_cost_passthrough():
    usage = {"input_tokens": 100, "output_tokens": 50, "total_cost_usd": 0.42}
    assert BudgetService.cost_from_usage(usage, "claude") == pytest.approx(0.42)


def test_zero_native_cost_estimates_with_codex_pricing():
    """codex extraction reports total_cost_usd=0.0 — must estimate using CODEX
    pricing (session_cost_service), NOT the claude fallback rate."""
    from app.services.session_cost_service import _PRICING

    usage = {"input_tokens": 1_000_000, "output_tokens": 0, "total_cost_usd": 0.0}
    cost = BudgetService.cost_from_usage(usage, "codex")
    assert cost == pytest.approx(_PRICING["gpt-5.3-codex"]["input"])
    # And claude-backend estimates use claude rates (when no native cost).
    cost_claude = BudgetService.cost_from_usage(usage, "claude")
    assert cost_claude == pytest.approx(_PRICING["claude-sonnet-4"]["input"])


def test_none_usage_is_zero():
    assert BudgetService.cost_from_usage(None, "codex") == 0.0
    assert BudgetService.cost_from_usage({}, "codex") == 0.0


def test_update_budget_used_upserts_run_row():
    _make_execution()
    harness_state.update_budget_used("exec-1", 0.10)  # creates the run row
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.10)
    harness_state.update_budget_used("exec-1", 0.25)  # updates in place
    run = harness_state.get_run("exec-1")
    assert run["budget_used"] == pytest.approx(0.25)
    assert run["step_cursor"] == 0  # accounting must not advance the checkpoint cursor


def test_update_budget_used_is_monotonic():
    """Live cost only grows; a stale lower write (e.g. racing a checkpoint)
    must not regress the recorded value."""
    _make_execution()
    harness_state.update_budget_used("exec-1", 0.25)
    harness_state.update_budget_used("exec-1", 0.10)  # stale — ignored by MAX
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.25)


def test_count_checkpoints():
    _make_execution()
    assert harness_state.count_checkpoints("exec-1") == 0
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    assert harness_state.count_checkpoints("exec-1") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_cost_from_usage.py -q`
Expected: FAIL — `cost_from_usage`/`update_budget_used`/`count_checkpoints` don't exist.

- [ ] **Step 3: Implement `BudgetService.cost_from_usage`**

In `backend/app/services/budget_service.py`, add as a `@classmethod` near `estimate_cost`:

```python
    # Backend-family default model for live cost estimation when the
    # extractor reports tokens but no cost (codex/opencode report cost 0.0).
    _ESTIMATE_MODEL_FOR_BACKEND = {
        "codex": "gpt-5.3-codex",
        "opencode": "gpt-5.3-codex",
    }

    @classmethod
    def cost_from_usage(cls, usage: Optional[dict], backend_type: str) -> float:
        """USD cost of a usage dict (Harness-1 Phase 3 live accounting).

        Uses the extractor's native ``total_cost_usd`` when present (claude
        reports it); otherwise estimates via session_cost_service's canonical
        pricing/_compute_cost, selecting the model family by backend (codex
        reports tokens but cost 0.0 — it must NOT be priced at claude rates).
        An ESTIMATE for live discipline — the authoritative record stays
        ``record_usage`` at finish."""
        if not usage:
            return 0.0
        native = usage.get("total_cost_usd") or 0.0
        if native > 0:
            return float(native)
        from .session_cost_service import _compute_cost

        model = cls._ESTIMATE_MODEL_FOR_BACKEND.get(backend_type, "claude-sonnet-4")
        return _compute_cost(
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("cache_read_tokens", 0),
            usage.get("cache_creation_tokens", 0),
            model,
        )
```

(Reuses `session_cost_service._compute_cost` / `_resolve_model_pricing` —
the repo's canonical token→USD computation, which already knows codex/gpt-5
family pricing — instead of duplicating rates in `MODEL_PRICING`.)

- [ ] **Step 4: Implement the two `harness_state` fns**

In `backend/app/db/harness_state.py`:

```python
def update_budget_used(execution_id: str, budget_used: float) -> None:
    """Live-accounting write (Harness-1 P6): upsert the run row's budget_used
    WITHOUT advancing the checkpoint cursor. MAX keeps the value monotonic —
    a stale lower write (racing a concurrent checkpoint upsert) can't regress
    the live total."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO harness_runs (execution_id, status, step_cursor, budget_used, updated_at)
                VALUES (?, 'running', 0, ?, datetime('now'))
            ON CONFLICT(execution_id) DO UPDATE SET
                budget_used = MAX(COALESCE(harness_runs.budget_used, 0), excluded.budget_used),
                updated_at  = datetime('now')
            """,
            (execution_id, budget_used),
        )
        conn.commit()


def count_checkpoints(execution_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM harness_checkpoints WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
    return int(row[0])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_cost_from_usage.py -q`
Expected: PASS (6 passed). Also run `uv run pytest tests/test_harness_state_repo.py -q` (regression, 8 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/budget_service.py backend/app/db/harness_state.py backend/tests/test_cost_from_usage.py
git commit -m "feat(harness): cost_from_usage + live budget_used upsert (Phase 3 P6)"
```

---

## Task 3: `_per_run_budget_tick` wired into `budget_monitor`

**Files:**
- Modify: `backend/app/services/execution_runner.py` (`budget_monitor` at ~:111; new module-level helper above it)
- Modify: `backend/app/services/execution_service.py` (`_budget_monitor` ~:298; thread-spawn site ~:581)
- Test: `backend/tests/test_budget_monitor_per_run.py`

The tick is a **module-level helper** so it is unit-testable without driving the
30s polling loop (same seam pattern as Phase 2's `_maybe_auto_resolve_and_pr`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_budget_monitor_per_run.py
"""Per-run budget tick: accounting, one-shot warn, hard kill (Phase 3 P6)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.db import harness_state
from app.db.budgets import set_budget_limit
from app.services.budget_service import BudgetService
from app.services.execution_runner import _per_run_budget_tick, budget_monitor


def _make_execution(execution_id: str = "exec-1", trigger_id: str = "bot-pr-review") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id=trigger_id,
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="codex",
        command="echo hi",
    )


def _fake_process() -> SimpleNamespace:
    return SimpleNamespace(pid=99999)


def _usage(cost: float) -> dict:
    return {"input_tokens": 10, "output_tokens": 5, "total_cost_usd": cost}


def _tick(execution_id: str, state: dict, cost: float) -> None:
    with patch.object(BudgetService, "extract_token_usage", return_value=_usage(cost)):
        _per_run_budget_tick(
            execution_id, "bot-pr-review", "trigger", "bot-pr-review",
            "codex", _fake_process(), state,
        )


def test_tick_updates_budget_used_without_limit():
    _make_execution()
    state = {}
    _tick("exec-1", state, 0.10)
    assert harness_state.get_run("exec-1")["budget_used"] == pytest.approx(0.10)
    assert not state.get("warned") and not state.get("killed")


def test_tick_noop_when_extraction_returns_none():
    """claude/gemini mid-run: extraction yields None -> documented no-op."""
    _make_execution()
    with patch.object(BudgetService, "extract_token_usage", return_value=None):
        _per_run_budget_tick(
            "exec-1", "bot-pr-review", "trigger", "bot-pr-review",
            "claude", _fake_process(), {},
        )
    assert harness_state.get_run("exec-1") is None  # nothing written


def test_tick_warns_once_at_80_percent():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=1.0)
    state = {}
    with patch(
        "app.services.execution_log_service.ExecutionLogService.append_log"
    ) as append:
        _tick("exec-1", state, 0.85)
        _tick("exec-1", state, 0.90)  # second tick must NOT warn again
    warn_calls = [c for c in append.call_args_list if "[BUDGET]" in str(c)]
    assert len(warn_calls) == 1
    assert state.get("warned") is True
    assert not state.get("killed")


def test_tick_kills_at_limit():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=1.0)
    state = {}
    with patch("os.killpg") as killpg, patch("os.getpgid", return_value=4242):
        _tick("exec-1", state, 1.2)
    killpg.assert_called_once()
    assert state.get("killed") is True


def test_tick_no_enforcement_when_limit_null():
    _make_execution()
    set_budget_limit("trigger", "bot-pr-review", hard_limit_usd=100.0)  # per_run stays NULL
    state = {}
    with patch("os.killpg") as killpg:
        _tick("exec-1", state, 50.0)
    killpg.assert_not_called()
    assert not state.get("warned") and not state.get("killed")


def test_tick_fails_open_on_parser_error():
    _make_execution()
    with patch.object(BudgetService, "extract_token_usage", side_effect=RuntimeError("boom")):
        # Must not raise — the monitor's period check must never be disrupted.
        _per_run_budget_tick(
            "exec-1", "bot-pr-review", "trigger", "bot-pr-review",
            "codex", _fake_process(), {},
        )


def test_budget_monitor_invokes_tick():
    """Wiring: the polling loop calls the tick with the threaded backend_type."""
    _make_execution()
    process = MagicMock()
    # Loop order is poll -> sleep -> poll-again -> tick, so one live tick
    # needs TWO None polls before the terminal 0.
    process.poll.side_effect = [None, None, 0]
    with (
        patch("app.services.execution_runner._per_run_budget_tick") as tick,
        patch.object(BudgetService, "check_budget", return_value={"allowed": True}),
        patch.object(BudgetService, "check_execution_time_limit", return_value=False),
    ):
        budget_monitor(
            "exec-1", "bot-pr-review", "trigger", "bot-pr-review", process,
            interval_seconds=0, backend_type="codex",
        )
    assert tick.call_count == 1
    assert tick.call_args[0][4] == "codex"  # backend_type positional
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_budget_monitor_per_run.py -q`
Expected: FAIL — `cannot import name '_per_run_budget_tick'`.

- [ ] **Step 3: Implement the tick helper**

In `backend/app/services/execution_runner.py`, add ABOVE `budget_monitor` (module level). Match the module's existing import style (it already imports `ExecutionLogService`, `AuditLogService`, `BudgetService`, `logger`, `signal` — verify with `grep -n "^from\|^import" app/services/execution_runner.py` and add only what's missing):

```python
def _per_run_budget_tick(
    execution_id: str,
    trigger_id: str,
    entity_type: str,
    entity_id: str,
    backend_type: Optional[str],
    process: "subprocess.Popen",
    tick_state: dict,
) -> None:
    """One per-run live-accounting step (Harness-1 Phase 3, P6). Fail-open:
    any error is swallowed so the monitor's period check is never disrupted.

    claude/gemini emit usage only in their terminal JSON, so extraction
    returns None mid-run and this whole tick no-ops for them (documented
    limitation); codex JSONL accumulates and works incrementally.

    Each tick re-parses the full buffered log (every 30s). Accepted for now:
    cumulative cost on very long logs — revisit with a parsed-line offset in
    tick_state if it shows up in profiles."""
    if not backend_type:
        return
    try:
        from ..db import harness_state
        from ..db.budgets import get_budget_limit
        from ..db.health_alerts import create_health_alert

        partial_log = ExecutionLogService.get_stdout_log(execution_id)
        usage = BudgetService.extract_token_usage(partial_log, backend_type)
        if not usage:
            return
        cost = BudgetService.cost_from_usage(usage, backend_type)
        harness_state.update_budget_used(execution_id, cost)
        if cost <= 0:
            return

        limit_row = get_budget_limit(entity_type, entity_id) or {}
        limit = limit_row.get("per_run_limit_usd")
        if not limit:  # NULL = off; set_budget_limit rejects <= 0, so 0.0 can't be stored
            return

        if cost >= limit:
            reason = f"per-run limit exceeded: ${cost:.2f} >= ${limit:.2f}"
            logger.warning(
                "Per-run budget limit exceeded during execution %s — terminating. %s",
                execution_id,
                reason,
            )
            try:
                import os as _os

                _os.killpg(_os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass  # already terminated
            except Exception as kill_err:
                logger.error(
                    "Failed to kill over-budget process for execution %s: %s",
                    execution_id,
                    kill_err,
                    exc_info=True,
                )
            ExecutionLogService.append_log(
                execution_id, "stderr", f"[BUDGET] Execution terminated: {reason}"
            )
            create_health_alert(
                "budget_exceeded", trigger_id, reason,
                details={"execution_id": execution_id, "per_run": True},
                severity="critical",
            )
            AuditLogService.log(
                action="execution.budget_exceeded",
                entity_type=entity_type,
                entity_id=entity_id,
                outcome="killed",
                details={"execution_id": execution_id, "reason": reason, "per_run": True},
            )
            tick_state["killed"] = True
        elif cost >= 0.8 * limit and not tick_state.get("warned"):
            tick_state["warned"] = True
            message = f"[BUDGET] approaching per-run limit: ${cost:.2f} of ${limit:.2f}"
            ExecutionLogService.append_log(execution_id, "stderr", message)
            create_health_alert(
                "budget_warning", trigger_id, message,
                details={"execution_id": execution_id, "cost": cost, "limit": limit},
                severity="warning",
            )
            AuditLogService.log(
                action="execution.budget_warning",
                entity_type=entity_type,
                entity_id=entity_id,
                outcome="warned",
                details={"execution_id": execution_id, "cost": cost, "limit": limit},
            )
    except Exception as e:  # pragma: no cover - defensive fail-open
        logger.debug("per-run budget tick failed for %s: %s", execution_id, e)
```

(`Optional` — confirm it's imported in the module; add `from typing import Optional` if not.)

- [ ] **Step 4: Wire into `budget_monitor`**

In `budget_monitor` (~:111):
1. Signature: add `backend_type: Optional[str] = None,` as the LAST parameter (after `interval_seconds`), so existing positional callers are unaffected.
2. Before the `while` loop: `tick_state: dict = {"warned": False, "killed": False}`.
3. Inside the loop, AFTER the existing period-budget and time-limit checks, add:

```python
        # Per-run incremental accounting + ceiling (Harness-1 Phase 3, P6).
        _per_run_budget_tick(
            execution_id, trigger_id, entity_type, entity_id,
            backend_type, process, tick_state,
        )
        if tick_state.get("killed"):
            break
```

- [ ] **Step 5: Thread `backend_type` from the spawn site**

In `backend/app/services/execution_service.py`:
1. `_budget_monitor` (~:298): add `backend_type: Optional[str] = None,` as the last parameter and pass it through: `return budget_monitor(execution_id, trigger_id, entity_type, entity_id, process, interval_seconds, backend_type=backend_type)`.
2. The thread spawn (~:581): find the backend local in `run_trigger` scope with `grep -n "backend_type" app/services/execution_service.py | sed -n '1,20p'` (the variable used to build the command / create the execution log). Pass it via kwargs:

```python
            budget_monitor_thread = threading.Thread(
                target=cls._budget_monitor,
                args=(execution_id, trigger_id, entity_type, entity_id, process),
                kwargs={"backend_type": backend_type},
                daemon=True,
            )
```

(If the in-scope local has a different name, e.g. `backend`, use that name in the kwargs value — keep the kwarg key `backend_type`.)

- [ ] **Step 6: Run tests**

Run: `cd backend && uv run pytest tests/test_budget_monitor_per_run.py -q`
Expected: PASS (7 passed).
Then regression: `uv run pytest tests/test_execution_service.py tests/test_execution_log_checkpoint.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/execution_runner.py backend/app/services/execution_service.py backend/tests/test_budget_monitor_per_run.py
git commit -m "feat(harness): per-run budget tick — live accounting, soft warn, hard kill (Phase 3 P6)"
```

---

## Task 4: `GET /executions/{execution_id}/state`

**Files:**
- Modify: `backend/app_litestar/routes/executions.py` (new handler beside `GET /executions/{execution_id}` at ~:125; register in the `executions_router` handler list at the bottom of the file)
- Test: `backend/tests/test_execution_state_route.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_execution_state_route.py
"""GET /executions/{id}/state — composed Phase 1-3 snapshot (Phase 3 P7)."""

from litestar.testing import create_test_client

from app.db import harness_state
from app.db import verification_records as vr
from app.db.budgets import set_budget_limit
from app_litestar.auth import provide_caller
from app_litestar.routes.executions import executions_router


def _client():
    return create_test_client(
        route_handlers=[executions_router],
        dependencies={"caller": provide_caller},
    )


def _make_execution(execution_id: str = "exec-1") -> None:
    from app.db.execution_logs import create_execution_log

    create_execution_log(
        execution_id=execution_id,
        trigger_id="bot-pr-review",
        trigger_type="manual",
        started_at="2026-06-10T00:00:00",
        prompt="p",
        backend_type="codex",
        command="echo hi",
    )


def test_state_full_snapshot():
    _make_execution()
    harness_state.record_checkpoint("exec-1", ledger={"lines": []})
    harness_state.update_budget_used("exec-1", 0.42)
    vr.record_verification("exec-1", "no secrets", status="passed")
    set_budget_limit("trigger", "bot-pr-review", per_run_limit_usd=2.0)

    with _client() as client:
        # executions_router mounts at path="/admin" (executions.py ~:562)
        resp = client.get("/admin/executions/exec-1/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution"]["status"] == "running"
    assert body["execution"]["backend_type"] == "codex"
    assert body["run"]["budget_used"] == 0.42
    assert body["run"]["step_cursor"] == 1
    assert body["latest_checkpoint"]["step"] == 1
    assert body["checkpoint_count"] == 1
    assert body["verifications"][0]["claim"] == "no secrets"
    assert body["per_run_limit_usd"] == 2.0


def test_state_nulls_for_bare_execution():
    """Pre-Phase-1 rows (no run/checkpoints/verifications) must not 500."""
    _make_execution("exec-bare")
    with _client() as client:
        resp = client.get("/admin/executions/exec-bare/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"] is None
    assert body["latest_checkpoint"] is None
    assert body["checkpoint_count"] == 0
    assert body["verifications"] == []
    assert body["per_run_limit_usd"] is None


def test_state_404_for_unknown_execution():
    with _client() as client:
        resp = client.get("/admin/executions/nope/state")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_execution_state_route.py -q`
Expected: FAIL — 404 on all three (route not defined yet), so the first two fail.

- [ ] **Step 3: Implement the handler**

In `backend/app_litestar/routes/executions.py` — first check the file's existing imports (`NotFoundException` may already be imported; the module already imports execution-log accessors). Add the handler near the `GET /executions/{execution_id}` sibling, mirroring its decorator style (`sync_to_thread=False`):

```python
@get("/executions/{execution_id:str}/state", sync_to_thread=False)
def get_execution_state(execution_id: str) -> dict[str, Any]:
    """Composed harness-state snapshot (Harness-1 Phase 3, P7): execution
    summary + Phase-1 run/checkpoints + Phase-2 verifications + live budget."""
    from app.db import harness_state
    from app.db import verification_records
    from app.db.budgets import get_budget_limit
    from app.db.execution_logs import get_execution_log

    execution = get_execution_log(execution_id)
    if not execution:
        raise NotFoundException(detail=f"Execution {execution_id} not found")

    run = harness_state.get_run(execution_id)
    latest = harness_state.get_latest_checkpoint(execution_id)
    # Per-run limit is trigger-scoped here; team-dispatched runs may use a
    # different entity — acceptable for a display-only operator panel.
    limit_row = get_budget_limit("trigger", execution.get("trigger_id") or "") or {}

    return {
        "execution": {
            k: execution.get(k)
            for k in (
                "execution_id", "status", "exit_code", "started_at",
                "finished_at", "duration_ms", "backend_type",
            )
        },
        "run": (
            {k: run.get(k) for k in ("status", "step_cursor", "budget_used", "updated_at")}
            if run
            else None
        ),
        "latest_checkpoint": (
            {"step": latest["step"], "created_at": latest["created_at"]} if latest else None
        ),
        "checkpoint_count": harness_state.count_checkpoints(execution_id),
        "verifications": verification_records.list_verifications(execution_id),
        "per_run_limit_usd": limit_row.get("per_run_limit_usd"),
    }
```

Add `get_execution_state` to the `executions_router` `route_handlers` list at the bottom of the file. If `NotFoundException` isn't imported, add `from litestar.exceptions import NotFoundException`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_execution_state_route.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app_litestar/routes/executions.py backend/tests/test_execution_state_route.py
git commit -m "feat(harness): GET /executions/{id}/state snapshot endpoint (Phase 3 P7)"
```

---

## Task 5: Vue `HarnessStatePanel` + api client + i18n + mount

**Files:**
- Modify: `frontend/src/services/api/types/triggers.ts` (add `ExecutionStateSnapshot`)
- Modify: `frontend/src/services/api/triggers.ts` (add `getState` to `executionApi`, ~:237, using `apiFetch`)
- Modify: `frontend/src/services/api/index.ts` (export the new type, following its existing re-export style)
- Create: `frontend/src/components/executions/HarnessStatePanel.vue`
- Create: `frontend/src/components/executions/__tests__/HarnessStatePanel.test.ts`
- Modify: `frontend/src/views/ExecutionHistory.vue` (mount in the Log Viewer Modal, ~:420)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json` (new `harnessState.*` namespace, key-identical)

NOTE: `frontend/src/services/api` is a **directory** (barrel `index.ts` + per-domain
modules + `types/`), NOT a single `api.ts` file — the root CLAUDE.md description is
stale. `executionApi` lives in `services/api/triggers.ts` and its methods use the
`apiFetch` helper from `services/api/client.ts`.

- [ ] **Step 1: Study the conventions (read, don't guess)**

1. Open `frontend/src/services/api/triggers.ts` ~:237, find `executionApi`, and note exactly how its existing methods call `apiFetch` and build their `/admin/executions/...` paths — mirror that for `getState`.
2. Open `frontend/src/components/monitoring/__tests__/BudgetLimitForm.test.ts` and note the mount/i18n/mock setup — mirror it for the panel test.
3. Open `frontend/src/views/ExecutionHistory.vue` ~:420-440 (the Log Viewer Modal) to choose the exact mount point (directly under the modal header block).

- [ ] **Step 2: Add the api client method + type**

In `frontend/src/services/api/types/triggers.ts`, next to the `Execution` type:

```typescript
export interface ExecutionStateSnapshot {
  execution: {
    execution_id: string;
    status: string;
    exit_code: number | null;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number | null;
    backend_type: string | null;
  };
  run: {
    status: string;
    step_cursor: number;
    budget_used: number;
    updated_at: string;
  } | null;
  latest_checkpoint: { step: number; created_at: string } | null;
  checkpoint_count: number;
  verifications: Array<{
    id: number;
    claim: string;
    status: string;
    evidence_ref: string | null;
    checked_at: string | null;
  }>;
  per_run_limit_usd: number | null;
}
```

And inside `executionApi` in `frontend/src/services/api/triggers.ts`, a method
mirroring the sibling methods' `apiFetch` style (the backend route mounts under
`/admin` — match the exact prefix the adjacent execution methods use):

```typescript
  getState: (executionId: string) =>
    apiFetch<ExecutionStateSnapshot>(`/admin/executions/${executionId}/state`),
```

Then export `ExecutionStateSnapshot` from `frontend/src/services/api/index.ts`
following its existing type re-export style.

- [ ] **Step 3: Write the failing component test**

```typescript
// frontend/src/components/executions/__tests__/HarnessStatePanel.test.ts
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import HarnessStatePanel from '../HarnessStatePanel.vue';
import { executionApi } from '../../../services/api';
// i18n setup: mirror BudgetLimitForm.test.ts (global plugins / t-mock) exactly.

vi.mock('../../../services/api', () => ({
  executionApi: { getState: vi.fn() },
}));

const SNAPSHOT = {
  execution: {
    execution_id: 'exec-1', status: 'running', exit_code: null,
    started_at: '2026-06-10T00:00:00', finished_at: null,
    duration_ms: null, backend_type: 'codex',
  },
  run: { status: 'running', step_cursor: 3, budget_used: 0.9, updated_at: '2026-06-10T00:01:00' },
  latest_checkpoint: { step: 3, created_at: '2026-06-10T00:01:00' },
  checkpoint_count: 3,
  verifications: [
    { id: 1, claim: 'no secrets', status: 'passed', evidence_ref: null, checked_at: '2026-06-10T00:02:00' },
  ],
  per_run_limit_usd: 1.0,
};

describe('HarnessStatePanel', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(executionApi.getState).mockResolvedValue(SNAPSHOT as never);
  });
  afterEach(() => {
    // Unmount every wrapper so no poll interval leaks across tests
    // (no global auto-unmount in this project's Vitest setup).
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  function mountPanel(status = 'running') {
    const wrapper = mount(HarnessStatePanel, {
      props: { executionId: 'exec-1', executionStatus: status },
      // global: { plugins: [i18n] }  — per the BudgetLimitForm.test.ts convention
    });
    wrappers.push(wrapper);
    return wrapper;
  }

  it('renders run state, budget, and verifications', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledWith('exec-1');
    expect(wrapper.text()).toContain('3');           // step cursor
    expect(wrapper.text()).toContain('no secrets');  // verification claim
    expect(wrapper.text()).toContain('0.9');         // budget used
  });

  it('applies warning styling past 80% of the per-run limit', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.find('.budget-warning').exists()).toBe(true); // 0.9 of 1.0
  });

  it('polls every 5s while running and stops when terminal', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(5000);
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledTimes(2);

    // Terminal snapshot stops the poller.
    vi.mocked(executionApi.getState).mockResolvedValue({
      ...SNAPSHOT,
      execution: { ...SNAPSHOT.execution, status: 'success' },
    } as never);
    vi.advanceTimersByTime(5000);
    await flushPromises();
    const after = vi.mocked(executionApi.getState).mock.calls.length;
    vi.advanceTimersByTime(15000);
    await flushPromises();
    expect(vi.mocked(executionApi.getState).mock.calls.length).toBe(after);

    wrapper.unmount(); // must not throw; interval cleared
  });

  it('shows the empty-state when no run row exists', async () => {
    vi.mocked(executionApi.getState).mockResolvedValue({
      ...SNAPSHOT, run: null, latest_checkpoint: null, checkpoint_count: 0, verifications: [],
    } as never);
    const wrapper = mountPanel('success');
    await flushPromises();
    expect(wrapper.find('.harness-state-empty').exists()).toBe(true);
  });
});
```

Run: `cd frontend && npm run test:run -- HarnessStatePanel`
Expected: FAIL — component doesn't exist.

- [ ] **Step 4: Implement the panel**

```vue
<!-- frontend/src/components/executions/HarnessStatePanel.vue -->
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ExecutionStateSnapshot } from '../../services/api';
import { executionApi } from '../../services/api';

const props = defineProps<{
  executionId: string;
  executionStatus?: string;
}>();

const { t } = useI18n();
const snapshot = ref<ExecutionStateSnapshot | null>(null);
const error = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const isRunning = computed(() => snapshot.value?.execution.status === 'running');
const budgetRatio = computed(() => {
  const used = snapshot.value?.run?.budget_used ?? 0;
  const limit = snapshot.value?.per_run_limit_usd;
  return limit ? used / limit : null;
});
const budgetWarning = computed(() => budgetRatio.value !== null && budgetRatio.value >= 0.8);

async function fetchState() {
  try {
    snapshot.value = await executionApi.getState(props.executionId);
    error.value = false;
    if (!isRunning.value) stopPolling();
  } catch {
    error.value = true;
    stopPolling();
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(fetchState, 5000);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(async () => {
  await fetchState();
  if (isRunning.value) startPolling();
});
onBeforeUnmount(stopPolling);
watch(() => props.executionId, async () => {
  stopPolling();
  await fetchState();
  if (isRunning.value) startPolling();
});
</script>

<template>
  <div class="harness-state-panel">
    <h4>{{ t('harnessState.title') }}</h4>
    <div v-if="error" class="harness-state-error">{{ t('harnessState.error') }}</div>
    <div v-else-if="!snapshot" class="harness-state-loading">{{ t('harnessState.loading') }}</div>
    <div v-else-if="!snapshot.run" class="harness-state-empty">{{ t('harnessState.noState') }}</div>
    <template v-else>
      <dl class="state-grid">
        <dt>{{ t('harnessState.runStatus') }}</dt>
        <dd>{{ snapshot.run.status }}</dd>
        <dt>{{ t('harnessState.stepCursor') }}</dt>
        <dd>{{ snapshot.run.step_cursor }}</dd>
        <dt>{{ t('harnessState.budget') }}</dt>
        <dd :class="{ 'budget-warning': budgetWarning }">
          ${{ snapshot.run.budget_used.toFixed(2) }}
          <span v-if="snapshot.per_run_limit_usd !== null">
            {{ t('harnessState.budgetOf', { limit: snapshot.per_run_limit_usd.toFixed(2) }) }}
          </span>
        </dd>
        <dt>{{ t('harnessState.lastCheckpoint') }}</dt>
        <dd>
          <template v-if="snapshot.latest_checkpoint">
            {{ t('harnessState.step', { step: snapshot.latest_checkpoint.step }) }}
            · {{ snapshot.latest_checkpoint.created_at }}
            ({{ snapshot.checkpoint_count }})
          </template>
          <template v-else>—</template>
        </dd>
      </dl>
      <div v-if="snapshot.verifications.length" class="verifications">
        <h5>{{ t('harnessState.verifications') }}</h5>
        <ul>
          <li v-for="v in snapshot.verifications" :key="v.id" :data-status="v.status">
            <span class="claim">{{ v.claim }}</span>
            <span class="status">{{ t(`harnessState.status_${v.status}`) }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.harness-state-panel {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}
.state-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}
.state-grid dt { opacity: 0.7; }
.state-grid dd { margin: 0; }
.budget-warning { color: var(--warning-color, #e6a700); font-weight: 600; }
.verifications ul { list-style: none; padding: 0; margin: 0.25rem 0 0; }
.verifications li { display: flex; justify-content: space-between; gap: 1rem; }
.verifications li[data-status='failed'] .status { color: var(--error-color, #e05555); }
.verifications li[data-status='passed'] .status { color: var(--success-color, #4caf78); }
</style>
```

(Adjust CSS custom-property names to the ones actually defined in `App.vue` — check `grep -n "^  --" frontend/src/App.vue | head -20` and use existing tokens.)

- [ ] **Step 5: i18n — all four catalogs**

Add a top-level `harnessState` namespace to `en.json`, `ko.json`, `ja.json`, `zh.json` (translate values; keys identical):

```json
"harnessState": {
  "title": "Harness state",
  "runStatus": "Run status",
  "stepCursor": "Step cursor",
  "budget": "Live budget",
  "budgetOf": "of ${limit}",
  "lastCheckpoint": "Last checkpoint",
  "step": "step {step}",
  "verifications": "Verifications",
  "status_pending": "pending",
  "status_passed": "passed",
  "status_failed": "failed",
  "noState": "No harness state recorded for this execution.",
  "loading": "Loading…",
  "error": "Could not load harness state."
}
```

- [ ] **Step 6: Mount in ExecutionHistory's Log Viewer Modal**

In `frontend/src/views/ExecutionHistory.vue`: import the component, then inside the modal (the `div` whose header is `modal-title-execution-log`, ~:420-430), directly after the modal header block, add:

```vue
          <HarnessStatePanel
            :execution-id="selectedExecution.execution_id"
            :execution-status="selectedExecution.status"
          />
```

- [ ] **Step 7: Run frontend tests + build**

Run: `cd frontend && npm run test:run -- HarnessStatePanel`
Expected: PASS (4 passed).
Run: `cd frontend && npm run test:run`
Expected: full frontend suite PASS (no locale-parity or existing-test regressions).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/executions/ frontend/src/services/api/ frontend/src/views/ExecutionHistory.vue frontend/src/locales/
git commit -m "feat(harness): HarnessStatePanel + /state api client + i18n (Phase 3 P7)"
```

---

## Task 6: `per_run_limit_usd` through the budget-limits form chain

**Files:**
- Modify: `frontend/src/components/monitoring/BudgetLimitForm.vue` (field + the at-least-one guard at ~:80)
- Modify: `frontend/src/components/monitoring/__tests__/BudgetLimitForm.test.ts`
- Modify: `frontend/src/components/triggers/TriggerDetailPanel.vue` (the SECOND budget editor — load at ~:239, save payload at ~:262)
- Modify: `frontend/src/services/api/budgets.ts` (`budgetApi.setLimit` at ~:28 — accept the new field)
- Modify: `frontend/src/services/api/types/budgets.ts` (`BudgetLimit` at ~:5 — add `per_run_limit_usd: number | null`)
- Modify: `backend/app_litestar/routes/budgets.py` (`set_limit` handler at ~:67 — parse/validate/pass)
- Modify: `backend/app/models/budget.py` (de-stale `BudgetLimitRequest`/`BudgetLimitResponse`)
- Modify: `frontend/src/locales/{en,ko,ja,zh}.json` (field labels for BOTH surfaces' namespaces)
- Test (backend): extend `backend/tests/test_migration_151_per_run_limit.py`

- [ ] **Step 1: Trace the existing chain (read, don't guess)**

Trace how `soft_limit_usd` flows end-to-end and mirror it for `per_run_limit_usd`:
1. `frontend/src/components/monitoring/BudgetLimitForm.vue` — form field + payload.
2. `budgetApi.setLimit()` in `frontend/src/services/api/budgets.ts` (~:28) and the `BudgetLimit` type in `frontend/src/services/api/types/budgets.ts` (~:5).
3. The **`PUT /admin/budgets/limits`** handler (`set_limit`, `backend/app_litestar/routes/budgets.py` ~:67) — it reads the body and calls `set_budget_limit` (which already accepts `per_run_limit_usd` from Task 1).

- [ ] **Step 2: Backend route — failing test first**

Append to `backend/tests/test_migration_151_per_run_limit.py`:

```python
def test_budget_route_accepts_per_run_limit():
    from litestar.testing import create_test_client

    from app.db.budgets import get_budget_limit
    from app_litestar.auth import provide_caller
    from app_litestar.routes.budgets import budgets_router  # confirm exact symbol via grep

    with create_test_client(
        route_handlers=[budgets_router], dependencies={"caller": provide_caller}
    ) as client:
        resp = client.put(
            "/admin/budgets/limits",
            json={
                "entity_type": "trigger",
                "entity_id": "bot-pr-review",
                "per_run_limit_usd": 1.5,
            },
        )
    assert resp.status_code in (200, 201)
    assert get_budget_limit("trigger", "bot-pr-review")["per_run_limit_usd"] == 1.5
```

Run it, watch it fail (the handler ignores the field → stored limit is None), then
extend the `set_limit` handler (~:67): add `per_run_limit_usd` to its body
model/param parsing, include it in the handler's "at least one limit provided"
guard if it has one, and pass it through to `set_budget_limit`. Re-run → PASS.

- [ ] **Step 3: De-stale the backend Pydantic models**

In `backend/app/models/budget.py`: add `per_run_limit_usd: Optional[float] = None`
to BOTH `BudgetLimitRequest` and `BudgetLimitResponse`; widen
`BudgetLimitRequest.entity_type` to `Literal["agent", "team", "trigger"]`; and
update `validate_limits` so `per_run_limit_usd` counts toward the
"at least one limit" check and rejects `<= 0`. (These models aren't on the live
`PUT /admin/budgets/limits` path, but they're part of the model surface — keep
them consistent rather than stale.)

- [ ] **Step 4: Frontend api + BOTH budget editors**

1. `frontend/src/services/api/types/budgets.ts` (~:5): add `per_run_limit_usd: number | null;` to `BudgetLimit`.
2. `frontend/src/services/api/budgets.ts` (~:28): add `per_run_limit_usd?: number;` to `setLimit()`'s input shape and include it in the request body exactly like `soft_limit_usd`.
3. `BudgetLimitForm.vue`: add a number input mirroring the `soft_limit_usd` field's exact markup/binding/validation pattern, bound to `per_run_limit_usd`, labeled with a new i18n key in the form's existing namespace (all four catalogs), included in the submit payload — **and update the at-least-one guard (~:80) so a per-run-only submission is valid** (it currently checks only soft/hard).
4. `TriggerDetailPanel.vue` — the second, independent budget editor: add per-run state where the panel loads limits (~:239), display + input mirroring its soft/hard fields, include it in the save payload (~:262), update its own at-least-one guard the same way, and add the label key to its locale namespace in all four catalogs.

- [ ] **Step 5: Extend the component tests — including the per-run-only path**

In `BudgetLimitForm.test.ts` (mirroring its style):
1. Extend the existing submit test to set the new field and assert the API payload includes `per_run_limit_usd`.
2. Add a dedicated case: fill ONLY `per_run_limit_usd` (soft/hard empty) → the form submits successfully and the payload carries just the per-run value. This pins the guard fix; without it an implementation could reject per-run-only submissions while all tests pass.

If `TriggerDetailPanel` has a test file (check `frontend/src/components/triggers/__tests__/`), extend it the same way; if not, the form tests + manual smoke cover it.

Run: `cd frontend && npm run test:run -- BudgetLimitForm`
Expected: PASS (including the new per-run-only case).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/monitoring/ frontend/src/components/triggers/ backend/app_litestar/routes/budgets.py backend/app/models/budget.py backend/tests/test_migration_151_per_run_limit.py frontend/src/locales/ frontend/src/services/api/
git commit -m "feat(harness): per-run limit settable from budget form (Phase 3 P6)"
```

---

## Task 7: Full Phase-3 verification sweep

- [ ] **Step 1: Backend — all Phase-3 tests + regressions**

```bash
cd backend && uv run pytest \
  tests/test_migration_151_per_run_limit.py tests/test_cost_from_usage.py \
  tests/test_budget_monitor_per_run.py tests/test_execution_state_route.py \
  tests/test_execution_service.py tests/test_harness_state_repo.py \
  tests/test_execution_log_checkpoint.py tests/test_litestar_streams.py -q
```
Expected: ALL PASS.

- [ ] **Step 2: Lint**

```bash
cd backend && uv run ruff format app/db/budgets.py app/db/harness_state.py app/db/schema/_misc.py app/db/migrations/v07_features.py app/services/budget_service.py app/services/execution_runner.py app/services/execution_service.py app_litestar/routes/executions.py app_litestar/routes/budgets.py
cd backend && uv run ruff check app/services/execution_runner.py app/db/budgets.py app/db/harness_state.py app_litestar/routes/executions.py
```
Expected: clean / `All checks passed!`.

- [ ] **Step 3: Frontend — full suite + production build**

```bash
cd frontend && npm run test:run
just build
```
Expected: frontend suite PASS; `vue-tsc` + vite build succeed.

- [ ] **Step 4: Final commit (if lint changed anything)**

```bash
git add -A backend/ frontend/
git commit -m "chore(harness): ruff/format pass for Phase 3"
```

---

## Self-Review notes (author)
- **Spec coverage:** migration+get/set (T1), cost helper + budget_used + checkpoint count (T2), monitor tick + threading backend_type (T3), /state (T4), panel+api+i18n+mount (T5), budget-form field chain (T6), gates (T7). All spec units covered; spec's `checkpoint_count` adjustment included (T4).
- **Type consistency:** `cost_from_usage(usage, backend_type) -> float`; `update_budget_used(execution_id, budget_used)`; `count_checkpoints(execution_id) -> int`; `_per_run_budget_tick(execution_id, trigger_id, entity_type, entity_id, backend_type, process, tick_state)`; `budget_monitor(..., interval_seconds=30, backend_type=None)`; `getState(executionId) -> ExecutionStateSnapshot` — consistent across tasks.
- **Confirm-at-execution points (each task says how to confirm):** the backend local name at the monitor spawn site (T3 S5); the fetch helper + `/api` prefix in api.ts (T5 S2); BudgetLimitForm i18n namespace + form markup (T6); budgets router symbol/path/body (T6 S2); CSS custom-property tokens (T5 S4).
