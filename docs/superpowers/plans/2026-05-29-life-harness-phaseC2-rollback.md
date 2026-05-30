# Phase C2 — Rollback (Revert an Applied Round) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an applied evolution round reversible — capture an apply-journal (before-images) at apply time, then `revert_round(round_id)` reverses the DB CRUD ops, git-reverts the Phase B commit, and marks the round `reverted`, with conflict detection so a later round's changes aren't silently clobbered.

**Architecture:** At apply, `apply_patch` records a per-entry journal: for `create` the new asset id (reverse = delete + unbind); for `update`/`delete` the **before-image** (`_fetch_primitive` snapshot taken *before* the mutation) so reverse can restore/recreate. The journal is stored in a new `apply_journal_json` column on the round (alongside the existing `applied_asset_ids_json`). `revert_round` (new `harness_evolution_rollback.py` service) refuses unless `status == 'applied'` and a journal exists, runs conflict detection (a later `applied` round touching the same `{kind, asset_id}` ⇒ refuse unless `force`), reverses the journal in reverse order inside a DB transaction, then — only if DB reversal succeeded — `git revert`s the Phase B `git_commit_sha`. On success → `status='reverted'`. The `reverted` state is already in the CHECK constraint (added in C1). DB reversal happens before git; if git fails, the round is left `applied` with a `revert_error` recorded for manual recovery.

**Tech Stack:** Python 3.10, raw SQLite, Pydantic v2, `subprocess` for git, pytest with `isolated_db` + `tmp_path`, ruff line-length=100.

**Consumes (merged to main):** `harness_evolver._fetch_primitive(kind, asset_id)`, `_create_dispatch`/`_update_dispatch`/`_delete_dispatch`, `bindings_repo.{add_binding,remove_binding,list_bindings}`; round columns `git_commit_sha` (Phase B), `apply_journal_json` (this phase); `harness_evolution.get_round`/`mark_*`.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/models/harness_evolution.py` | **Modify** | Add `ApplyJournalEntry`, `RevertResult` |
| `backend/app/db/schema/_harness_evolution.py` | **Modify** | Add `apply_journal_json`, `reverted_at`, `revert_error` columns to CREATE TABLE |
| `backend/app/db/harness_evolution.py` | **Modify** | `_ensure_revert_columns` migration; `mark_applied` stores `apply_journal_json`; `mark_reverted`/`set_revert_error`; `_row_to_dict` decodes `apply_journal_json` |
| `backend/app/services/harness_evolver.py` | **Modify** | `apply_patch` builds + returns the journal (before-images); `run_evolution_round`/`apply_dry_run_round` pass it to `mark_applied`; `_asset_to_payload` helper |
| `backend/app/services/harness_evolution_rollback.py` | **Create** | `reverse_apply_journal`, `revert_round`, conflict detection |
| `backend/app_litestar/routes/harness_evolution.py` | **Modify** | `POST /evolution/rounds/{id}/revert` |
| `backend/tests/test_harness_apply_journal.py` | **Create** | journal capture |
| `backend/tests/test_harness_rollback.py` | **Create** | reverse ops + revert_round + conflicts |

---

## Task 1: `ApplyJournalEntry` + `RevertResult` models

**Files:**
- Modify: `backend/app/models/harness_evolution.py`
- Test: `backend/tests/test_harness_apply_journal.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_apply_journal.py
from app.models.harness_evolution import ApplyJournalEntry, RevertResult


def test_apply_journal_entry_create():
    e = ApplyJournalEntry(kind="rule", op="create", asset_id="5", before=None)
    assert e.op == "create" and e.before is None


def test_apply_journal_entry_update_carries_before():
    e = ApplyJournalEntry(kind="rule", op="update", asset_id="5",
                          before={"name": "r", "action": "old"})
    assert e.before["action"] == "old"


def test_revert_result_shape():
    r = RevertResult(status="reverted", reversed_count=3, git_reverted=True)
    assert r.status == "reverted"
    assert r.reversed_count == 3
    assert RevertResult.model_validate_json(r.model_dump_json()).git_reverted is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_apply_journal.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/models/harness_evolution.py`:

```python
from typing import Literal, Optional


class ApplyJournalEntry(BaseModel):
    kind: str
    op: Literal["create", "update", "delete"]
    asset_id: str
    # before-image of the asset (for update/delete reversal); None for create.
    before: Optional[dict] = None
    # binding row info captured at apply time, if any (for rebind on delete-reverse).
    binding: Optional[dict] = None


class RevertResult(BaseModel):
    status: Literal["reverted", "conflict", "failed"]
    reversed_count: int = 0
    git_reverted: bool = False
    error: str = ""
    conflicts: list[dict] = Field(default_factory=list)
```

(`Field` and `BaseModel` are already imported at the top of the file from C1.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_apply_journal.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/harness_evolution.py backend/tests/test_harness_apply_journal.py
git commit -m "feat(rollback): ApplyJournalEntry + RevertResult models"
```

---

## Task 2: Schema columns + DB functions for the journal & revert metadata

**Files:**
- Modify: `backend/app/db/schema/_harness_evolution.py` (add 3 columns)
- Modify: `backend/app/db/harness_evolution.py` (`_ensure_revert_columns`; `mark_applied` gains `apply_journal_json`; `mark_reverted`/`set_revert_error`; `_row_to_dict` decode)
- Test: `backend/tests/test_harness_rollback.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_rollback.py
from app.database import get_connection
from app.db import harness_evolution as evo


def _applied_round(project_id="pr", journal=None, sha="sha1"):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES (?, 'P', 'active')", (project_id,))
        conn.commit()
    rid = evo.start_round(project_id=project_id, input_window_since=None, input_window_until=None,
                          input_execution_count=0, input_forge={}, scratch_dir="/tmp/x")
    evo.mark_running(rid)
    evo.mark_applied(rid, output_patch={"entries": []},
                     applied_asset_ids=[{"kind": "rule", "op": "create", "asset_id": "1"}],
                     notes="", git_commit_sha=sha,
                     apply_journal_json=__import__("json").dumps(journal or []))
    return rid


def test_apply_journal_persisted_and_decoded(isolated_db):
    journal = [{"kind": "rule", "op": "create", "asset_id": "1", "before": None}]
    rid = _applied_round(journal=journal)
    row = evo.get_round(rid)
    assert row["apply_journal"] == journal
    assert row["git_commit_sha"] == "sha1"


def test_mark_reverted_sets_state(isolated_db):
    rid = _applied_round()
    evo.mark_reverted(rid)
    assert evo.get_round(rid)["status"] == "reverted"


def test_set_revert_error_leaves_applied(isolated_db):
    rid = _applied_round()
    evo.set_revert_error(rid, "git revert failed")
    row = evo.get_round(rid)
    assert row["status"] == "applied"        # not reverted — left for manual recovery
    assert "git revert failed" in (row["revert_error"] or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -v`
Expected: FAIL — `mark_applied` has no `apply_journal_json` param; `mark_reverted`/`set_revert_error` undefined.

- [ ] **Step 3: Write minimal implementation**

(a) In `_harness_evolution.py` CREATE TABLE, add after `eval_verdict_json`:
```
            apply_journal_json       TEXT,
            reverted_at              TEXT,
            revert_error             TEXT
```

(b) In `harness_evolution.py`, add the migration (mirror `_ensure_eval_columns`; these are pure ALTERs — no CHECK change since `reverted` is already allowed):
```python
def _ensure_revert_columns(conn) -> None:
    _ensure_eval_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    for col in ("apply_journal_json", "reverted_at", "revert_error"):
        if col not in cols:
            conn.execute(f"ALTER TABLE harness_evolution_rounds ADD COLUMN {col} TEXT")
```
Also add `"apply_journal_json"` to `_ROUND_COLUMNS_IN_ORDER` (so the C1 table-recreate migration preserves it), and `reverted_at`/`revert_error` too.

(c) Extend `mark_applied` to accept + persist `apply_journal_json` (call `_ensure_revert_columns` at the top instead of `_ensure_materialization_columns`):
```python
def mark_applied(round_id, *, output_patch, applied_asset_ids, notes=None,
                 materialization_result_json=None, git_commit_sha=None,
                 apply_journal_json=None):
    with get_connection() as conn:
        _ensure_revert_columns(conn)
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status='applied', finished_at=datetime('now'),
                   output_patch_json=?, applied_asset_ids_json=?, notes=?,
                   materialization_result_json=?, git_commit_sha=?, apply_journal_json=?
               WHERE id=?""",
            (json.dumps(output_patch, default=str), json.dumps(applied_asset_ids, default=str),
             notes, materialization_result_json, git_commit_sha, apply_journal_json, round_id),
        )
        conn.commit()
```
(Read the REAL current `mark_applied` and preserve its exact columns; only ADD `apply_journal_json` + swap the ensure call.)

(d) Add the two revert-state functions:
```python
def mark_reverted(round_id: str) -> None:
    with get_connection() as conn:
        _ensure_revert_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET status='reverted', reverted_at=datetime('now') "
            "WHERE id=? AND status='applied'",
            (round_id,),
        )
        conn.commit()


def set_revert_error(round_id: str, error: str) -> None:
    with get_connection() as conn:
        _ensure_revert_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET revert_error=? WHERE id=?",
            ((error or "")[:2000], round_id),
        )
        conn.commit()
```

(e) In `_row_to_dict`, add `("apply_journal_json", "null")` to the decode loop (so `apply_journal` is decoded). `reverted_at`/`revert_error` are plain text columns (no decode needed — they come through via `dict(row)`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -v`
Expected: the 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/schema/_harness_evolution.py backend/app/db/harness_evolution.py backend/tests/test_harness_rollback.py
git commit -m "feat(rollback): apply_journal_json + revert metadata columns + mark_reverted/set_revert_error"
```

---

## Task 3: Capture the apply-journal in `apply_patch`

**Files:**
- Modify: `backend/app/services/harness_evolver.py` (`apply_patch` builds the journal; `_asset_to_payload`; callers pass journal to `mark_applied`)
- Test: `backend/tests/test_harness_apply_journal.py`

**Context:** `apply_patch(patch, project_id)` currently returns `applied = [{kind, op, asset_id}]`. Change it to ALSO build a journal of `ApplyJournalEntry`-shaped dicts capturing before-images. For `update`/`delete`, snapshot `_fetch_primitive(kind, existing_asset_id)` BEFORE the mutation. For `create`, before=None (asset_id = the new id). Return `(applied, journal)`. Update both callers (`run_evolution_round` and `apply_dry_run_round`) to capture the journal and pass `apply_journal_json=json.dumps(journal)` to `mark_applied`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_apply_journal.py
import json
from app.database import get_connection
from app.db import rules as rules_repo
from app.db import project_forge_bindings as bindings_repo
from app.services.harness_evolver import apply_patch, EvolutionPatch, PatchEntry  # adjust import to real types


def test_apply_patch_journal_captures_update_before_image(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pj', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(name="r", rule_type="validation", description="OLD",
                                 action="old-action", project_id="pj")
    bindings_repo.add_binding("pj", "rule", str(rid))
    patch = EvolutionPatch(entries=[PatchEntry(op="update", kind="rule", name="r",
                                               existing_asset_id=rid,
                                               payload={"description": "NEW", "action": "new-action"})])
    applied, journal = apply_patch(patch, "pj")
    # journal entry for the update carries the BEFORE image
    upd = [j for j in journal if j["op"] == "update"][0]
    assert upd["before"]["description"] == "OLD"
    assert upd["before"]["action"] == "old-action"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_apply_journal.py::test_apply_patch_journal_captures_update_before_image -v`
Expected: FAIL — `apply_patch` returns a single value (not a tuple). (Read the real `EvolutionPatch`/`PatchEntry` dataclasses and fix the import/construction; `PatchEntry` fields are `op, kind, name, existing_asset_id, payload` per Phase B's verified read.)

- [ ] **Step 3: Write minimal implementation**

In `apply_patch`, build a `journal: list[dict]` alongside `applied`. Read the real loop (~lines 960-1010) and adapt:
```python
def apply_patch(patch, project_id):
    applied: list[dict] = []
    journal: list[dict] = []
    for entry in patch.entries:
        kind = entry.kind
        if entry.op == "create":
            asset_id = _create_dispatch[kind](name=entry.name, payload=entry.payload or {}, project_id=project_id)
            if asset_id is None:
                continue
            try:
                bindings_repo.add_binding(project_id, kind, str(asset_id))
            except Exception:
                logger.warning("apply_patch: bind failed for %s %s", kind, asset_id, exc_info=True)
            applied.append({"kind": kind, "op": "create", "asset_id": asset_id})
            journal.append({"kind": kind, "op": "create", "asset_id": str(asset_id), "before": None})
        elif entry.op == "update":
            before = _fetch_primitive(kind, entry.existing_asset_id)   # snapshot BEFORE mutating
            _update_dispatch[kind](asset_id=entry.existing_asset_id, payload=entry.payload or {})
            applied.append({"kind": kind, "op": "update", "asset_id": entry.existing_asset_id})
            journal.append({"kind": kind, "op": "update", "asset_id": str(entry.existing_asset_id), "before": before})
        elif entry.op == "delete":
            before = _fetch_primitive(kind, entry.existing_asset_id)   # snapshot BEFORE deleting
            _delete_dispatch[kind](asset_id=entry.existing_asset_id)
            # (Phase B already unbinds here — keep that logic)
            <preserve the existing unbind loop from Phase B>
            applied.append({"kind": kind, "op": "delete", "asset_id": entry.existing_asset_id})
            journal.append({"kind": kind, "op": "delete", "asset_id": str(entry.existing_asset_id), "before": before})
    return applied, journal
```
**IMPORTANT:** preserve the existing Phase B delete-unbind loop inside the delete branch. The ONLY structural change is (a) building `journal` and (b) returning `(applied, journal)`.

Update the two callers:
- In `run_evolution_round`, change `applied = apply_patch(patch, project_id)` to `applied, journal = apply_patch(patch, project_id)`, and pass `apply_journal_json=json.dumps(journal, default=str)` to `mark_applied`.
- In `apply_dry_run_round` (read it — it also calls `apply_patch`), do the same.

Add `_asset_to_payload` (used by Task 4 reversal; define here so it lives with the dispatch):
```python
_PAYLOAD_KEYS = {
    "rule": ("rule_type", "description", "condition", "action", "enabled"),
    "hook": ("event", "description", "content", "enabled"),
    "command": ("description", "content", "arguments", "enabled"),
    "mcp_server": ("description", "server_type", "command", "args", "env_json", "url"),
    "skill": ("description", "content"),
}


def _asset_to_payload(kind: str, asset: dict) -> dict:
    """Project a before-image asset row into the payload shape the create/update
    dispatch functions expect (content fields only — not id/timestamps)."""
    keys = _PAYLOAD_KEYS.get(kind, ())
    return {k: asset[k] for k in keys if k in asset and asset[k] is not None}
```
(Confirm the real column names per kind by reading `_create_rule`/`_create_hook`/etc. and the repo getters; adjust `_PAYLOAD_KEYS` to match.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_apply_journal.py -v` then `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or forge" -q 2>&1 | tail -8`
Expected: new test passes; regression green (the `apply_patch` return-shape change must be reflected in ALL callers + any test that calls `apply_patch` directly — update those to unpack the tuple).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolver.py backend/tests/test_harness_apply_journal.py [updated caller tests]
git commit -m "feat(rollback): apply_patch captures before-image journal; callers persist apply_journal_json"
```

---

## Task 4: `reverse_apply_journal` — reverse the CRUD ops

**Files:**
- Create: `backend/app/services/harness_evolution_rollback.py`
- Test: `backend/tests/test_harness_rollback.py`

**Context:** Given a journal (list of entries), reverse each entry IN REVERSE ORDER: `create`→delete the asset + unbind; `update`→restore the before-image via `_update_dispatch` with `_asset_to_payload(kind, before)`; `delete`→recreate via `_create_dispatch` from the before-image + rebind. Returns the count reversed. Runs each reversal best-effort but reports failures.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_rollback.py
def test_reverse_journal_update_restores_before(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prj', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(name="r", rule_type="validation", description="NEW",
                                 action="new", project_id="prj")
    bindings_repo.add_binding("prj", "rule", str(rid))
    journal = [{"kind": "rule", "op": "update", "asset_id": str(rid),
                "before": {"name": "r", "rule_type": "validation", "description": "OLD", "action": "old", "enabled": 1}}]
    n = reverse_apply_journal("prj", journal)
    assert n == 1
    assert rules_repo.get_rule(int(rid))["description"] == "OLD"   # restored


def test_reverse_journal_create_deletes(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import reverse_apply_journal
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prc', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(name="created", rule_type="validation", description="x", project_id="prc")
    bindings_repo.add_binding("prc", "rule", str(rid))
    journal = [{"kind": "rule", "op": "create", "asset_id": str(rid), "before": None}]
    reverse_apply_journal("prc", journal)
    assert rules_repo.get_rule(int(rid)) is None   # deleted
    assert not any(b["kind"] == "rule" and str(b["asset_id"]) == str(rid)
                   for b in bindings_repo.list_bindings("prc"))   # unbound
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -k "reverse_journal" -v`
Expected: FAIL — module/function undefined.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/harness_evolution_rollback.py
"""Phase C2: reverse an applied evolution round (DB ops + git)."""
from __future__ import annotations

import logging

from app.db import project_forge_bindings as bindings_repo

logger = logging.getLogger(__name__)


def _unbind(project_id: str, kind: str, asset_id: str) -> None:
    for b in bindings_repo.list_bindings(project_id):
        if b.get("kind") == kind and str(b.get("asset_id")) == str(asset_id):
            bindings_repo.remove_binding(b["id"])


def reverse_apply_journal(project_id: str, journal: list[dict]) -> int:
    """Reverse each journal entry in reverse order. Returns count reversed."""
    from app.services.harness_evolver import (
        _create_dispatch, _update_dispatch, _delete_dispatch, _asset_to_payload,
    )
    reversed_count = 0
    for entry in reversed(journal):
        kind = entry["kind"]
        op = entry["op"]
        asset_id = entry["asset_id"]
        before = entry.get("before")
        try:
            if op == "create":
                _delete_dispatch[kind](asset_id=asset_id)
                _unbind(project_id, kind, asset_id)
            elif op == "update":
                if before:
                    _update_dispatch[kind](asset_id=asset_id, payload=_asset_to_payload(kind, before))
            elif op == "delete":
                if before:
                    new_id = _create_dispatch[kind](
                        name=before.get("name") or before.get("skill_name") or "restored",
                        payload=_asset_to_payload(kind, before), project_id=project_id,
                    )
                    if new_id is not None:
                        bindings_repo.add_binding(project_id, kind, str(new_id))
            reversed_count += 1
        except Exception:
            logger.warning("reverse journal: failed to reverse %s %s %s", op, kind, asset_id, exc_info=True)
    return reversed_count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -k "reverse_journal" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolution_rollback.py backend/tests/test_harness_rollback.py
git commit -m "feat(rollback): reverse_apply_journal — reverse create/update/delete from before-images"
```

---

## Task 5: `revert_round` — orchestrate (state checks, conflicts, DB + git)

**Files:**
- Modify: `backend/app/services/harness_evolution_rollback.py`
- Test: `backend/tests/test_harness_rollback.py`

**Context:** `revert_round(round_id, *, force=False, revert_git=True) -> RevertResult`: refuse if `status != 'applied'` (→ `RevertResult(status="failed")`); refuse if no `apply_journal` (old round → failed); run conflict detection (later `applied` rounds whose journal touches the same `{kind, asset_id}` → `RevertResult(status="conflict", conflicts=[...])` unless `force`); else `reverse_apply_journal`, then (if `revert_git` and `git_commit_sha`) `git revert --no-edit <sha>` in the project repo — if git fails, `set_revert_error` and leave `status='applied'` (return failed); on full success `mark_reverted` → `RevertResult(status="reverted", ...)`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_rollback.py
def test_revert_round_refuses_non_applied(isolated_db):
    from app.services.harness_evolution_rollback import revert_round
    rid = _applied_round("prr")
    evo.mark_reverted(rid)                       # now 'reverted', not 'applied'
    result = revert_round(rid, revert_git=False)
    assert result.status == "failed"


def test_revert_round_reverts_applied(isolated_db):
    from app.database import get_connection
    from app.db import rules as rules_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.services.harness_evolution_rollback import revert_round
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('prv', 'P', 'active')")
        conn.commit()
    rid_asset = rules_repo.create_rule(name="c", rule_type="validation", description="x", project_id="prv")
    bindings_repo.add_binding("prv", "rule", str(rid_asset))
    round_id = evo.start_round(project_id="prv", input_window_since=None, input_window_until=None,
                               input_execution_count=0, input_forge={}, scratch_dir="/tmp/x")
    evo.mark_running(round_id)
    journal = [{"kind": "rule", "op": "create", "asset_id": str(rid_asset), "before": None}]
    evo.mark_applied(round_id, output_patch={"entries": []},
                     applied_asset_ids=[{"kind": "rule", "op": "create", "asset_id": str(rid_asset)}],
                     notes="", git_commit_sha=None,
                     apply_journal_json=__import__("json").dumps(journal))
    result = revert_round(round_id, revert_git=False)   # no git (project has no repo here)
    assert result.status == "reverted"
    assert rules_repo.get_rule(int(rid_asset)) is None
    assert evo.get_round(round_id)["status"] == "reverted"


def test_revert_round_conflict_with_later_round(isolated_db):
    from app.services.harness_evolution_rollback import revert_round
    # round A (older) created asset 7; round B (newer, applied) also touched asset 7
    a = _applied_round("prx", journal=[{"kind": "rule", "op": "update", "asset_id": "7", "before": {"description": "o"}}])
    b = _applied_round("prx", journal=[{"kind": "rule", "op": "update", "asset_id": "7", "before": {"description": "p"}}])
    # reverting A must detect B as a conflict (B is a later applied round touching asset 7)
    result = revert_round(a, revert_git=False)
    assert result.status == "conflict"
    assert any(str(c.get("asset_id")) == "7" for c in result.conflicts)
    # force overrides
    forced = revert_round(a, revert_git=False, force=True)
    assert forced.status == "reverted"
```

(Note: `_applied_round` inserts into the SAME project per call — adjust the conflict test so both rounds share a project and `started_at` ordering makes B "later" than A. If `_applied_round` needs a distinct started_at, set it explicitly. Read how `list_for_project` orders rounds and ensure B sorts after A.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -k "revert_round" -v`
Expected: FAIL — `revert_round` undefined.

- [ ] **Step 3: Write minimal implementation**

Add to `harness_evolution_rollback.py`:

```python
import subprocess
from pathlib import Path

from app.db import harness_evolution as evo_repo
from app.models.harness_evolution import RevertResult


def _later_applied_conflicts(round_row: dict) -> list[dict]:
    """Later applied rounds whose journal touches the same {kind, asset_id}."""
    mine = {(e["kind"], str(e["asset_id"])) for e in (round_row.get("apply_journal") or [])}
    conflicts: list[dict] = []
    for other in evo_repo.list_for_project(round_row["project_id"], limit=200):
        if other["id"] == round_row["id"]:
            continue
        if other.get("status") != "applied":
            continue
        if (other.get("started_at") or "") <= (round_row.get("started_at") or ""):
            continue   # only LATER rounds conflict
        for e in (other.get("apply_journal") or []):
            if (e["kind"], str(e["asset_id"])) in mine:
                conflicts.append({"round_id": other["id"], "kind": e["kind"], "asset_id": e["asset_id"]})
    return conflicts


def _git_revert(project_id: str, sha: str) -> bool:
    from app.db.projects import get_project
    proj = get_project(project_id)
    root = (proj or {}).get("local_path") or (proj or {}).get("clone_path")
    if not root or not (Path(root) / ".git").exists():
        return False
    try:
        subprocess.run(["git", "revert", "--no-edit", sha], cwd=root,
                       check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning("git revert failed for %s: %s", sha, exc)
        raise


def revert_round(round_id: str, *, force: bool = False, revert_git: bool = True) -> RevertResult:
    row = evo_repo.get_round(round_id)
    if row is None:
        return RevertResult(status="failed", error="round not found")
    if row.get("status") != "applied":
        return RevertResult(status="failed", error=f"round status is {row.get('status')}, not applied")
    journal = row.get("apply_journal")
    if not journal:
        return RevertResult(status="failed", error="no apply journal (round predates rollback support)")

    conflicts = _later_applied_conflicts(row)
    if conflicts and not force:
        return RevertResult(status="conflict", conflicts=conflicts,
                            error="later applied round(s) touched the same assets")

    n = reverse_apply_journal(row["project_id"], journal)

    git_done = False
    sha = row.get("git_commit_sha")
    if revert_git and sha:
        try:
            git_done = _git_revert(row["project_id"], sha)
        except Exception as exc:
            # DB reversal already happened; leave status applied + record error for manual recovery.
            evo_repo.set_revert_error(round_id, f"db reversed but git revert failed: {exc}")
            return RevertResult(status="failed", reversed_count=n, git_reverted=False,
                                error="git revert failed (db changes reversed; see revert_error)")

    evo_repo.mark_reverted(round_id)
    return RevertResult(status="reverted", reversed_count=n, git_reverted=git_done)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_rollback.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolution_rollback.py backend/tests/test_harness_rollback.py
git commit -m "feat(rollback): revert_round — state checks, conflict detection, db reverse + git revert"
```

---

## Task 6: Route + verification gate

**Files:**
- Modify: `backend/app_litestar/routes/harness_evolution.py` (add revert endpoint)
- Test: route smoke (optional, in an existing route test file)

- [ ] **Step 1: Add the route**

Read `backend/app_litestar/routes/harness_evolution.py` (it has `approve_round`/`abort_round` post handlers). Add:
```python
@post("/evolution/rounds/{round_id:str}/revert", sync_to_thread=True)
def revert_round_route(round_id: str, data: Optional[dict] = None) -> dict[str, Any]:
    from app.services.harness_evolution_rollback import revert_round
    force = bool((data or {}).get("force"))
    result = revert_round(round_id, force=force)
    return {"round_id": round_id, **result.model_dump()}
```
Register it in the router's `route_handlers` list (mirror how `approve_round`/`abort_round` are registered).

- [ ] **Step 2: Verification gate**

Run, in order:
- `cd backend && uv run pytest tests/test_harness_apply_journal.py tests/test_harness_rollback.py tests/test_harness_evolver.py -q`
- `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or forge" -q` (no regressions — esp. the `apply_patch` tuple-return change reflected everywhere)
- `cd backend && uv run ruff format --check` + `ruff check` on the touched files
- `cd frontend && npm run test:run`
- `just build`

All must pass.

- [ ] **Step 3: Commit + tag**

```bash
git add backend/app_litestar/routes/harness_evolution.py [any test]
git commit -m "feat(rollback): POST /evolution/rounds/{id}/revert route"
git tag life-harness-phaseC2-rollback-complete
```
