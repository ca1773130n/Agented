# v0.5.2 — Silent-failure cleanup

Patch milestone closing the **CRITICAL** silent-failure findings from
`.planning/error-handling-audit-pr4.md`. The audit catalogued 14 issues
across `backend/app/db/agent_memory.py` and `backend/app/db/tracing.py`;
this plan ships the four highest-severity ones plus a regression guard
for the two pre-existing fixes.

## Why these four

| Audit # | File | Severity | Status before | This plan |
|---------|------|----------|---------------|-----------|
| #3 | `tracing.py:end_span` attribute merge | CRITICAL | `pass` swallows `JSONDecodeError`; previous attributes silently dropped | log warning + clobber-and-warn |
| #4 | `tracing.py:update_span` attribute merge | CRITICAL | identical to #3 | log warning + clobber-and-warn |
| #1 | `agent_memory.py:vector_recall` metadata parse | CRITICAL (audit text) → in fact safely set to None already, just no log | `metadata = None` silently | add `logger.warning` with `msg["id"]` |
| #8 | `agent_memory.py:get_working_memory` content parse | HIGH | `content_parsed = None` silently | add `logger.warning` with `entity_id` |

Two related sites (`agent_memory.py:_row_with_json_metadata` and
`tracing.py:_parse_json_field`) already had `logger.warning(...)` from
an earlier pass. Both get a regression guard test in this plan to keep
them that way.

## Source changes

### `backend/app/db/tracing.py`

`end_span` (lines ~225-228) and `update_span` (lines ~265-268) shared
the same flawed pattern:

```python
existing = {}
if row["attributes"]:
    try:
        existing = json.loads(row["attributes"])
    except (json.JSONDecodeError, TypeError):
        pass        # ← silent: previous attributes dropped, no log
existing.update(attributes)
```

Replaced both `pass` blocks with `logger.warning(...)` carrying the
function name + `span_id` + truncated raw value. The `existing = {}`
fallback stays — keeping a known-corrupt blob is worse than discarding
it, but the operator now sees the loss in logs.

### `backend/app/db/agent_memory.py`

`vector_recall` (lines ~359-370) and `get_working_memory` (lines
~485-499): both already used a safe `None` fallback, but neither logged.
Added matching `logger.warning(...)` blocks following the
`_row_with_json_metadata` template (function name + entity id + raw
truncated to 200 chars).

## Tests

### `backend/tests/test_tracing.py::TestCorruptAttributes`

Two new tests. Each:
1. Creates a span with valid attributes via `create_span(...)`.
2. Stomps the row's `attributes` column with malformed JSON via raw
   SQL `UPDATE`.
3. Calls `end_span` / `update_span` with new attributes.
4. Asserts the function returned (no raise), the new attributes were
   applied, and a `WARNING` was logged with the function name and
   span id.

### `backend/tests/test_agent_memory.py::TestCorruptJSON`

Two new tests:

- `test_get_messages_logs_corrupt_row_metadata` — regression guard for
  the pre-existing `_row_with_json_metadata` warning (since 1.5.x). The
  fix replaced a silent `pass` with `logger.warning("Failed to parse
  metadata JSON: %s", ...)`; this test ensures nothing reverts that.
- `test_get_working_memory_logs_corrupt_content` — exercises the new
  warning added in this plan. Inserts valid working memory, stomps
  the `content` column with non-JSON, asserts `content_parsed is None`
  and the warning surfaces both `entity_id` and the marker text.

## Out of scope

- Audit issues #5 (FTS5 query errors) — needs a different kind of
  fix (catch + return empty + log) and is HIGH not CRITICAL.
- Issues #9, #10 — `datetime.fromisoformat` corruption — narrow surface.
- Issues #13, #14 — semantic, not error-handling.
- Modal-interaction E2E (carried over from v0.5.0) — still blocked on
  `@ai-accounts` wizard fixtures; remains in v0.6.0.

## Verification

- `cd backend && uv run pytest` — **2192 passed** (+4)
- `cd frontend && npm run test:run` — **1069 passed** (unchanged)
- `cd frontend && npm run build` — vue-tsc + vite clean
