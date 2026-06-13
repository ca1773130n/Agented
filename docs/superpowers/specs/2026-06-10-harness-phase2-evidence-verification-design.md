# Harness-1 Phase 2 — Structured Evidence + Verification (Design)

**Date:** 2026-06-10
**Status:** Approved (design); pending spec review
**Depends on:** Phase 1 (PR #208, `harness_runs`/`harness_checkpoints`) — merged
**Source:** [`harness-1-integration.md`](../../harness-1-integration.md) (P3 + P5); arXiv:2606.02373

## Motivation

Phase 1 made trigger runs *recoverable*. Phase 2 makes runs *auditable*:
turn ephemeral `tool_use` events into a queryable evidence ledger, and add
durable verification records with a post-hoc gate on side-effects.

The two halves land on **different substrates**, because that is how the
codebase actually works:

- **Chat / super-agent session substrate** — `run_streaming_response`
  (`streaming_helper.py:47`) emits **typed `ToolUseEvent`s**
  (`conversation_streaming.py:63`). Keyed by `session_id` (super-agent
  sessions). This is where structured evidence (P3) is buildable.
- **Trigger-execution substrate** — `ExecutionService` drives an opaque
  `subprocess.Popen`; only flattened stdout is available. Keyed by
  `execution_logs(execution_id)`. Verification records (P5) attach here,
  next to Phase 1's `harness_runs`.

In-loop gating of an opaque subprocess is impossible (only mid-run lever is
SIGKILL), so P5 is a **record store + one post-hoc side-effect gate**, not a
workflow engine.

---

## Unit A — P3: Evidence ledger (chat/session substrate)

### Data model
New table `harness_evidence`, in a new `schema/_harness_evidence.py`
(`create_harness_evidence_tables`), mirroring the Phase-1 `harness_*`
keyed-table pattern:

```sql
CREATE TABLE IF NOT EXISTS harness_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    super_agent_id  TEXT,
    seq             INTEGER NOT NULL,           -- per-session monotonic ordinal
    tool_name       TEXT    NOT NULL,
    tool_input_json TEXT    NOT NULL DEFAULT '{}',
    tool_use_id     TEXT,                       -- provider tool_use id (ToolUseEvent.id)
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, seq),                   -- backstop; seq assigned atomically in INSERT
    FOREIGN KEY (session_id)
        REFERENCES super_agent_sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_harness_evidence_session
    ON harness_evidence(session_id, seq);
```

`seq` is a per-session ordinal (current `MAX(seq)+1` for the session), so the
ledger preserves tool-call order and is queryable without grepping the
transcript.

### Repository module — `app/db/harness_evidence.py`
- `record_tool_use(session_id, *, super_agent_id, tool_name, tool_input, tool_use_id=None) -> int`
  — assigns the next `seq` and inserts one row in a single transaction;
  returns the assigned `seq`. `tool_input` is JSON-serialized (`default=str`).
- `list_evidence(session_id) -> list[dict]` — ordered by `seq`, `tool_input`
  deserialized.
- `count_evidence(session_id) -> int`.

### Tap point — `streaming_helper.run_streaming_response`
Two existing dispatch sites handle the typed event:
`streaming_helper.py:177-178` and `:275-276`:

```python
if isinstance(chunk, ToolUseEvent):
    ChatStateService.push_delta(_session_id, "tool_use", chunk.to_dict())
```

Add a **best-effort** ledger write immediately after each `push_delta`:

```python
try:
    harness_evidence.record_tool_use(
        _session_id,
        super_agent_id=_super_agent_id,
        tool_name=chunk.name,
        tool_input=chunk.input,
        tool_use_id=chunk.id,
    )
except Exception as e:  # never disrupt streaming
    logger.debug("evidence ledger write failed for %s: %s", _session_id, e)
```

`ToolUseEvent` = `{name: str, input: Any, id: Optional[str]}`
(`conversation_streaming.py:63`).

### Registration
`create_harness_evidence_tables` added to `schema/__init__.py:create_fresh_schema`
(after `_super_agents`, the FK target) **and** a `V07_MIGRATIONS` entry
**149** in `v07_features.py` (idempotent `CREATE TABLE IF NOT EXISTS`).

### Scope cuts (YAGNI — from the report's corrections)
- **`tool_use` only.** No `tool_result` pairing — no extractor exists in
  `conversation_streaming.py` today; deferred.
- **No "kept/seen" flag.** Agented has no `returned_chunk_ids`/`output_chunk_ids`
  concept; the report's borrowed RAG vocabulary is dropped.

---

## Unit B — P5: Verification records (execution substrate)

### Data model
New table `verification_records`, in a new `schema/_verification_records.py`
(`create_verification_records_tables`):

```sql
CREATE TABLE IF NOT EXISTS verification_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id  TEXT    NOT NULL,
    claim         TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'passed', 'failed')),
    evidence_ref  TEXT,                          -- file path / PR url / span id
    checked_at    TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (execution_id)
        REFERENCES execution_logs(execution_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_verification_records_exec
    ON verification_records(execution_id);
```

### Repository module — `app/db/verification_records.py`
- `record_verification(execution_id, claim, status='pending', evidence_ref=None) -> int`
  — inserts; sets `checked_at = datetime('now')` when `status != 'pending'`.
- `list_verifications(execution_id) -> list[dict]`.
- `has_failed(execution_id) -> bool` — `EXISTS(... status='failed')`; the gate
  predicate.

### Write surface — `VerificationService`
`app/services/verification_service.py` thin facade:
`VerificationService.record(execution_id, claim, status, evidence_ref=None)`
→ `verification_records.record_verification(...)`. The deliverable is the
**write API**; auto-wiring a specific bot (bot-security/bot-pr-review) to
populate records is a later integration, not this phase.

### Read surface — Litestar router
`app_litestar/routes/verification.py`, mounted like `quality_ratings_router`
(`Router(...)` of `@get`/`@post` handlers):
- `GET  /api/executions/{execution_id}/verifications` → `list_verifications`.
- `POST /api/executions/{execution_id}/verifications` → `record` (body:
  `claim`, `status`, `evidence_ref`).

### Gate seam — post-hoc, advisory by default
At the side-effect call site `execution_service.py:672`
(`auto_resolve_and_pr(trigger, github_repo_map, scan_output)`), guard it:

```python
if verification_records.has_failed(execution_id):
    logger.warning("Skipping auto-PR for %s: a verification claim failed", execution_id)
else:
    auto_resolve_and_pr(trigger, github_repo_map, scan_output)
```

**Advisory by default:** with no records, `has_failed` is `False` and behavior
is unchanged. It only blocks the *downstream side-effect* (PR creation) when a
claim is explicitly `failed` — never pauses or kills the run. This is the
report-endorsed "gate side-effects post-hoc," avoiding the stall/deadlock risk
of an in-loop gate.

### Registration
`create_verification_records_tables` in `create_fresh_schema` (after `_core`,
the `execution_logs` FK target) **and** `V07_MIGRATIONS` entry **150**.

---

## Testing (TDD throughout)

**P3 — `tests/test_harness_evidence_repo.py` + `tests/test_evidence_ledger_tap.py`**
- `record_tool_use` assigns monotonic `seq` (1, 2, 3…) per session; returns it.
- `list_evidence` ordered, `tool_input` round-trips; `count_evidence`.
- FK cascade: deleting the `super_agent_sessions` row removes evidence.
- Idempotent `create_harness_evidence_tables`; migration **149** registered.
- Tap: feeding a `ToolUseEvent` through the dispatch path records a row;
  a ledger-write exception does **not** break streaming.

**P5 — `tests/test_verification_records_repo.py` + `tests/test_verification_gate.py` + route test**
- `record_verification` (status transitions set `checked_at`); `list_verifications`.
- `has_failed` true only when a `failed` row exists.
- FK cascade on `execution_logs` delete.
- Gate: `auto_resolve_and_pr` is **skipped** when `has_failed` is true, **runs**
  otherwise (patch/spy the side-effect).
- `GET`/`POST` route returns/writes records (Litestar `TestClient`).
- Idempotent schema; migration **150** registered.

Verification gates: `cd backend && uv run pytest` (targeted files — the full
serial suite is known to hang), `ruff format` + `ruff check`. Backend-only;
no frontend changes.

---

## Out of scope (later phases)
`tool_result` capture / evidence curation; in-loop blocking or SIGKILL-on-
critical gate; auto-wiring a bot as the verifier (ship the write API + gate,
not the bot integration); P4 resume, P6 budget, P7 operator surface, P8 PTY.

## File manifest
**New:** `app/db/schema/_harness_evidence.py`, `app/db/harness_evidence.py`,
`app/db/schema/_verification_records.py`, `app/db/verification_records.py`,
`app/services/verification_service.py`, `app_litestar/routes/verification.py`,
4 test files.
**Modified:** `app/db/schema/__init__.py` (register 2 tables),
`app/db/migrations/v07_features.py` (migrations 149, 150),
`app/services/streaming_helper.py` (P3 tap, 2 sites),
`app/services/execution_service.py` (P5 gate at :672),
router registration in the Litestar app.
