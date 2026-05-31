# Phase E1 — Cross-Project Propagation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a forged primitive that proves effective in one project propagate to others — accumulate eval evidence per primitive, promote to a shared layer when a decayed score crosses a threshold, and let projects adopt shared primitives (local always wins on conflict).

**Architecture:** A primitive is identified across projects by a content **fingerprint** (hash of its payload). On each applied round with a passing C1 eval, `record_promotion_evidence` logs `(fingerprint, kind, asset_id, project_id, eval_score)`; `promote_if_qualified` computes a time-decayed score `sum(eval_score · exp(-ln2/half_life · age_days))` and, when it crosses `PROMOTION_THRESHOLD`, creates a **global-scope copy** of the asset (`project_id=NULL` — already supported by rules/hooks/commands) and catalogues it in `shared_forge_bindings`. A project **adopts** a shared binding via `adopt_shared_binding` → a real `project_forge_binding` with `source_scope='shared'`, which the existing compile/gather read path picks up automatically. Conflict: if the project already has a local binding for the same `kind+fingerprint`, `local_wins` skips adoption. The promote step doesn't re-judge — it reuses Phase C's `eval_verdict.score`.

**Scope note (deferred within E1):** HarnessSync export of shared primitives and auto-adoption-on-qualification are deferred to follow-ups; this plan delivers the core promote→adopt mechanism + an explicit-adoption API. mcp_server propagation is deferred (junction-table scoping differs); E1 propagates `rule`/`hook`/`command`/`skill`.

**Consumes (merged to main):** round `eval_verdict` (C1), `bindings_repo.{list_bindings,add_binding}`, the C2 `_PAYLOAD_KEYS`/`_fetch_primitive` (for fingerprinting), `run_evolution_round`'s post-apply hook point, `create_rule/create_hook/create_command` (accept `project_id=None` for global scope).

**Tech Stack:** Python 3.10, raw SQLite, Pydantic v2, pytest with `isolated_db`, ruff line-length=100.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/services/forge_fingerprint.py` | **Create** | `fingerprint(kind, asset)` content hash |
| `backend/app/db/schema/_forge_promotion.py` | **Create** | `forge_promotion_evidence` + `shared_forge_bindings` + `project_shared_forge_adoptions` tables; register |
| `backend/app/db/forge_promotion.py` | **Create** | evidence record/score; shared-binding + adoption repo |
| `backend/app/db/project_forge_bindings.py` | **Modify** | `source_scope`/`source_shared_binding_id`/`conflict_policy`/`fingerprint` columns + `_ensure` migration; `add_binding` accepts them |
| `backend/app/services/harness_propagation.py` | **Create** | `record_promotion_evidence`, `promote_if_qualified`, `adopt_shared_binding` |
| `backend/app/services/harness_evolver.py` | **Modify** | After apply, call `record_promotion_evidence` for applied primitives + `promote_if_qualified` |
| `backend/app_litestar/routes/harness_evolution.py` | **Modify** | `GET /shared-forge` + `POST /projects/{id}/adopt-shared/{sbid}` |
| tests | **Create** | `backend/tests/test_harness_propagation.py` |

---

## Task 1: Fingerprint helper

**Files:** Create `backend/app/services/forge_fingerprint.py`; Test `backend/tests/test_harness_propagation.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_propagation.py
from app.services.forge_fingerprint import fingerprint


def test_fingerprint_stable_for_same_content():
    a = {"name": "r", "rule_type": "validation", "description": "d", "action": "x", "enabled": 1}
    b = {"name": "r", "rule_type": "validation", "description": "d", "action": "x", "enabled": 1, "id": 9}
    # id/timestamps don't change the fingerprint; only content fields matter
    assert fingerprint("rule", a) == fingerprint("rule", b)


def test_fingerprint_differs_on_content_change():
    a = {"name": "r", "rule_type": "validation", "action": "x"}
    b = {"name": "r", "rule_type": "validation", "action": "y"}
    assert fingerprint("rule", a) != fingerprint("rule", b)


def test_fingerprint_includes_kind():
    payload = {"name": "x", "description": "d", "content": "c"}
    assert fingerprint("hook", payload) != fingerprint("command", payload)
```

- [ ] **Step 2: Run test to verify it fails** — `cd backend && uv run pytest tests/test_harness_propagation.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/forge_fingerprint.py
"""Content fingerprint for forge primitives (Phase E propagation).

Two primitives of the same kind with identical *content* fields share a
fingerprint regardless of project / id / timestamps."""
from __future__ import annotations

import hashlib
import json

# Content fields per kind (mirrors the create/update payload shape).
_FP_KEYS = {
    "rule": ("rule_type", "description", "condition", "action", "enabled"),
    "hook": ("event", "description", "content", "enabled"),
    "command": ("description", "content", "arguments", "enabled"),
    "skill": ("description", "content"),
}


def fingerprint(kind: str, asset: dict) -> str:
    keys = _FP_KEYS.get(kind, ())
    payload = {k: asset.get(k) for k in keys}
    payload["__kind"] = kind
    payload["__name"] = asset.get("name") or asset.get("skill_name")
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/services/forge_fingerprint.py backend/tests/test_harness_propagation.py
git commit -m "feat(propagation): content fingerprint for forge primitives"
```

---

## Task 2: Promotion-evidence + shared-binding tables + repo

**Files:** Create `backend/app/db/schema/_forge_promotion.py`; Create `backend/app/db/forge_promotion.py`; register schema; Test.

**Context:** Read how `create_project_autonomy_tables`/`create_project_forge_bindings` get registered in `schema/__init__.py` and register the new tables identically.

- [ ] **Step 1: Write the failing test**

```python
# Append to test_harness_propagation.py
from app.db import forge_promotion as fp


def test_record_evidence_and_score(isolated_db):
    fp.record_evidence(fingerprint="fp1", kind="rule", asset_id="1", project_id="p1", eval_score=0.9)
    fp.record_evidence(fingerprint="fp1", kind="rule", asset_id="2", project_id="p2", eval_score=0.8)
    # decayed score with age 0 ≈ 0.9 + 0.8 = 1.7
    score = fp.promotion_score("fp1", half_life_days=30)
    assert 1.6 <= score <= 1.8


def test_create_and_list_shared_binding(isolated_db):
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fp1")
    assert sbid is not None
    rows = fp.list_shared_bindings(enabled_only=True)
    assert any(r["id"] == sbid and r["fingerprint"] == "fp1" for r in rows)
    # UNIQUE(scope, kind, fingerprint): re-create returns the existing id (idempotent)
    assert fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fp1") == sbid


def test_record_adoption(isolated_db):
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="9", fingerprint="fpA")
    fp.record_adoption(project_id="padopt", shared_binding_id=sbid, state="adopted")
    assert fp.is_adopted("padopt", sbid) is True
    assert fp.is_adopted("other", sbid) is False
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Write implementation**

(a) `schema/_forge_promotion.py`:
```python
"""Phase E propagation tables."""
from __future__ import annotations


def create_forge_promotion_tables(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS forge_promotion_evidence (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL,
            kind        TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            project_id  TEXT NOT NULL,
            eval_score  REAL NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fpe_fingerprint ON forge_promotion_evidence(fingerprint)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS shared_forge_bindings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            scope       TEXT NOT NULL DEFAULT 'global',
            kind        TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(scope, kind, fingerprint)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sfb_enabled ON shared_forge_bindings(enabled)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS project_shared_forge_adoptions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id        TEXT NOT NULL,
            shared_binding_id INTEGER NOT NULL,
            state             TEXT NOT NULL DEFAULT 'adopted',
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project_id, shared_binding_id)
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_psfa_project ON project_shared_forge_adoptions(project_id, state)")
```
Register `create_forge_promotion_tables(conn)` in `schema/__init__.py`'s `create_fresh_schema` (mirror the autonomy registration).

(b) `db/forge_promotion.py` — `record_evidence`, `promotion_score` (decayed sum), `create_shared_binding` (idempotent on UNIQUE → return existing id on conflict), `list_shared_bindings`, `record_adoption` (idempotent on UNIQUE), `is_adopted`. Use `datetime` for the decay age (compute `age_days` from `created_at` vs now). Decay: `eval_score * math.exp(-math.log(2)/half_life_days * age_days)`.

(Write the full repo following the table shapes; parameterized SQL; `create_shared_binding` does `INSERT ... ON CONFLICT(scope,kind,fingerprint) DO NOTHING` then `SELECT id`.)

- [ ] **Step 4: Run** → PASS (if "no such table", fix the schema registration).
- [ ] **Step 5: Commit**
```bash
git add backend/app/db/schema/_forge_promotion.py backend/app/db/forge_promotion.py backend/app/db/schema/__init__.py backend/tests/test_harness_propagation.py
git commit -m "feat(propagation): promotion-evidence + shared-binding + adoption tables + repo"
```

---

## Task 3: project_forge_bindings propagation columns

**Files:** Modify `backend/app/db/project_forge_bindings.py`; Test.

**Context:** Add `source_scope` ('project'/'shared'), `source_shared_binding_id`, `conflict_policy` ('local_wins'/'shared_wins'/'manual'), `fingerprint`. Use an `_ensure_propagation_columns` runtime migration (PRAGMA-guarded ALTER — the table predates this, so no fresh-schema CHECK rebuild needed; add the columns to the CREATE TABLE in its schema module AND the ensure migration). `add_binding` gains optional `source_scope='project', source_shared_binding_id=None, fingerprint=None`. `_row_to_dict` returns the new fields.

- [ ] **Step 1: failing test**
```python
# Append to test_harness_propagation.py
from app.db import project_forge_bindings as bindings_repo
from app.database import get_connection


def test_add_binding_records_source_scope(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('ps', 'P', 'active')")
        conn.commit()
    bid = bindings_repo.add_binding("ps", "rule", "9", source_scope="shared",
                                    source_shared_binding_id=3, fingerprint="fpX")
    b = bindings_repo.get_binding(bid)
    assert b["source_scope"] == "shared"
    assert b["source_shared_binding_id"] == 3
    assert b["fingerprint"] == "fpX"


def test_default_source_scope_is_project(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pp', 'P', 'active')")
        conn.commit()
    bid = bindings_repo.add_binding("pp", "rule", "1")
    assert bindings_repo.get_binding(bid)["source_scope"] == "project"
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add the 4 columns to the bindings schema module + an `_ensure_propagation_columns(conn)` (PRAGMA-guarded ALTERs with the CHECK-free defaults: `source_scope TEXT NOT NULL DEFAULT 'project'`, `source_shared_binding_id INTEGER`, `conflict_policy TEXT NOT NULL DEFAULT 'local_wins'`, `fingerprint TEXT`); call it at the top of `add_binding`/`list_bindings`/`get_binding`. Extend `add_binding` signature + INSERT + `_row_to_dict`. READ the real `add_binding`/`_row_to_dict` first; preserve the idempotent UNIQUE(project_id,kind,asset_id) behavior.
- [ ] **Step 4: Run** → PASS + `cd backend && uv run pytest tests/ -k "forge or binding" -q 2>&1 | tail -4` (no regressions).
- [ ] **Step 5: Commit**
```bash
git add backend/app/db/project_forge_bindings.py backend/app/db/schema/*.py backend/tests/test_harness_propagation.py
git commit -m "feat(propagation): project_forge_bindings source_scope/shared/conflict/fingerprint columns"
```

---

## Task 4: Promotion — record evidence + promote to shared layer

**Files:** Create `backend/app/services/harness_propagation.py`; Modify `harness_evolver.py` (post-apply hook); Test.

**Context:** `record_promotion_evidence(project_id, applied, eval_score)` — for each applied create/update entry, fetch the asset (`_fetch_primitive`), compute `fingerprint`, `fp.record_evidence(...)`. `promote_if_qualified(kind, fingerprint, asset)` — if `fp.promotion_score(fingerprint) >= PROMOTION_THRESHOLD` and not already shared, create a **global-scope copy** (`create_rule/hook/command(..., project_id=None)` from the asset's payload) + `fp.create_shared_binding(scope='global', kind, asset_id=<global id>, fingerprint)`. Hook both into `run_evolution_round` right AFTER `mark_applied` (best-effort; failure must not unwind the apply). The eval score is the round's `eval_verdict.score` (or 1.0 if no verdict, e.g. operator-applied).

- [ ] **Step 1: failing test**
```python
# Append to test_harness_propagation.py
from app.services.harness_propagation import record_promotion_evidence, promote_if_qualified, PROMOTION_THRESHOLD
from app.db import forge_promotion as fp
from app.db import rules as rules_repo


def test_promotion_creates_global_copy_and_shared_binding(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pq', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(name="great", rule_type="validation", description="d",
                                 action="a", project_id="pq")
    asset = rules_repo.get_rule(int(rid))
    fpv = __import__("app.services.forge_fingerprint", fromlist=["fingerprint"]).fingerprint("rule", asset)
    # pump enough high-score evidence to cross the threshold
    for i in range(10):
        fp.record_evidence(fingerprint=fpv, kind="rule", asset_id=str(rid), project_id="pq", eval_score=0.95)
    promote_if_qualified("rule", fpv, asset)
    shared = [s for s in fp.list_shared_bindings(enabled_only=True) if s["fingerprint"] == fpv]
    assert len(shared) == 1
    # a global-scope rule copy now exists (project_id IS NULL)
    glob = [r for r in rules_repo.get_rules_by_type("validation") if r.get("project_id") is None and r["name"] == "great"]
    assert glob


def test_record_evidence_from_applied(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pr2', 'P', 'active')")
        conn.commit()
    rid = rules_repo.create_rule(name="r2", rule_type="validation", description="d", action="a", project_id="pr2")
    applied = [{"kind": "rule", "op": "create", "asset_id": rid}]
    record_promotion_evidence("pr2", applied, eval_score=0.9)
    asset = rules_repo.get_rule(int(rid))
    fpv = __import__("app.services.forge_fingerprint", fromlist=["fingerprint"]).fingerprint("rule", asset)
    assert fp.promotion_score(fpv) > 0
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `harness_propagation.py` — `PROMOTION_THRESHOLD = 3.0` (≈ several high-confidence applies); `record_promotion_evidence`, `promote_if_qualified` (per the context above; for the global copy reuse `harness_evolver._asset_to_payload` + the per-kind `create_*` with `project_id=None`; READ `create_rule` etc. to confirm they accept `project_id=None`). Then in `run_evolution_round`, after the apply+mark_applied block, add a best-effort:
```python
        try:
            from app.services.harness_propagation import record_promotion_evidence, promote_if_qualified
            verdict = (evolution_repo.get_round(round_id) or {}).get("eval_verdict") or {}
            score = float(verdict.get("score", 1.0))
            record_promotion_evidence(project_id, applied, eval_score=score)
            from app.services.forge_fingerprint import fingerprint as _fp
            for entry in applied:
                if entry["op"] in ("create", "update"):
                    asset = _fetch_primitive(entry["kind"], entry["asset_id"])
                    if asset:
                        promote_if_qualified(entry["kind"], _fp(entry["kind"], asset), asset)
        except Exception:
            logger.warning("propagation: evidence/promote failed for %s", round_id, exc_info=True)
```
(Place it after `mark_applied` in the non-dry-run apply path; confirm `applied`/`project_id`/`round_id` locals.)
- [ ] **Step 4: Run** → PASS + `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or propagation or forge" -q 2>&1 | tail -6` (no regressions).
- [ ] **Step 5: Commit**
```bash
git add backend/app/services/harness_propagation.py backend/app/services/harness_evolver.py backend/tests/test_harness_propagation.py
git commit -m "feat(propagation): record eval evidence + promote qualified primitives to global shared layer"
```

---

## Task 5: Adoption + conflict (local_wins)

**Files:** Modify `harness_propagation.py` (`adopt_shared_binding`); Test.

**Context:** `adopt_shared_binding(project_id, shared_binding_id) -> dict` — load the shared binding; if the project already has a LOCAL binding with the same `kind` + matching `fingerprint` → `local_wins`: skip (return `{"adopted": False, "reason": "local_wins"}`). Else create a `project_forge_binding(project_id, kind, asset_id=<shared asset>, source_scope='shared', source_shared_binding_id, fingerprint)` + `fp.record_adoption(...)`. Idempotent (re-adopt is a no-op).

- [ ] **Step 1: failing test**
```python
# Append to test_harness_propagation.py
from app.services.harness_propagation import adopt_shared_binding


def test_adopt_creates_shared_binding(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('pad', 'P', 'active')")
        conn.commit()
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="77", fingerprint="fpZ")
    res = adopt_shared_binding("pad", sbid)
    assert res["adopted"] is True
    bound = [b for b in bindings_repo.list_bindings("pad")
             if b["kind"] == "rule" and str(b["asset_id"]) == "77"]
    assert bound and bound[0]["source_scope"] == "shared"
    # idempotent
    assert adopt_shared_binding("pad", sbid)["adopted"] in (True, False)  # no duplicate
    assert len([b for b in bindings_repo.list_bindings("pad") if str(b["asset_id"]) == "77"]) == 1


def test_local_wins_skips_adoption(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('plw', 'P', 'active')")
        conn.commit()
    # project already has a LOCAL binding with the same fingerprint
    bindings_repo.add_binding("plw", "rule", "5", fingerprint="fpL")
    sbid = fp.create_shared_binding(scope="global", kind="rule", asset_id="88", fingerprint="fpL")
    res = adopt_shared_binding("plw", sbid)
    assert res["adopted"] is False and res["reason"] == "local_wins"
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `adopt_shared_binding` per the context.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**
```bash
git add backend/app/services/harness_propagation.py backend/tests/test_harness_propagation.py
git commit -m "feat(propagation): adopt_shared_binding + local_wins conflict resolution"
```

---

## Task 6: Routes + verification gate

**Files:** Modify `backend/app_litestar/routes/harness_evolution.py`.

- [ ] **Step 1:** Add (match the file's handler style + `/admin` prefix + route_handlers registration):
```python
@get("/shared-forge", sync_to_thread=False)
def list_shared_forge() -> dict[str, Any]:
    from app.db.forge_promotion import list_shared_bindings
    return {"shared": list_shared_bindings(enabled_only=True)}


@post("/projects/{project_id:str}/adopt-shared/{shared_binding_id:int}", sync_to_thread=True)
def adopt_shared_route(project_id: str, shared_binding_id: int) -> dict[str, Any]:
    from app.services.harness_propagation import adopt_shared_binding
    return {"project_id": project_id, **adopt_shared_binding(project_id, shared_binding_id)}
```
Register both in `route_handlers`.

- [ ] **Step 2: Verification gate** — run in order:
  - `cd backend && uv run pytest tests/test_harness_propagation.py -q`
  - `cd backend && uv run pytest tests/ -k "evolv or harness_evolution or propagation or forge or binding" -q` (no regressions)
  - `cd backend && uv run ruff format --check` + `ruff check` on the touched backend files
  - `cd frontend && npm run test:run` + `just build`
- [ ] **Step 3: Commit + tag**
```bash
git add backend/app_litestar/routes/harness_evolution.py
git commit -m "feat(propagation): GET /shared-forge + POST adopt-shared route"
git tag life-harness-phaseE1-propagation-complete
```
