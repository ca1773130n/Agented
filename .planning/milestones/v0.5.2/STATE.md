# v0.5.2 State

Patch release closing the CRITICAL silent-failure findings from
`.planning/error-handling-audit-pr4.md`.

**Status:** COMPLETE — ready for tag/release.

## Shipped

### tracing.py — end_span + update_span attribute merge

Audit #3 + #4 (both CRITICAL). Replaced silent `pass` on
`JSONDecodeError` with `logger.warning(...)` carrying the function
name, span id, and truncated raw value. The `{}` fallback stays
because keeping a known-corrupt JSON blob is worse than discarding
it — but the operator now sees the loss in logs.

### agent_memory.py — vector_recall + get_working_memory

Audit #1 + #8. Both sites already had a safe `None` fallback; neither
logged. Added matching `logger.warning(...)` carrying the message id
or entity id and the raw value truncated to 200 chars.

### Regression guards

The pre-existing fixes in `_row_with_json_metadata` and
`_parse_json_field` (which already had `logger.warning`) get a
`test_get_messages_logs_corrupt_row_metadata` test to make sure
the warning doesn't get reverted to `pass` again.

## Test additions

- `tests/test_tracing.py::TestCorruptAttributes` — 2 tests
- `tests/test_agent_memory.py::TestCorruptJSON` — 2 tests

Pattern: insert a valid row → stomp the JSON column with raw SQL →
call the function → assert (a) no raise, (b) safe fallback shape,
(c) WARNING with the right context.

## Out of scope

- Audit issues #5, #6, #7 (FTS5 errors, agent_memory routes) and
  #9, #10 (datetime parsing). Lower severity; deferred.
- Modal-interaction E2E from v0.5.0. Still blocked on
  `@ai-accounts` wizard fixtures; remains in v0.6.0.

## Verification

- `cd backend && uv run pytest` — **2192 passed** (+4)
- `cd frontend && npm run test:run` — 1069 passed (unchanged)
- `cd frontend && npm run build` — vue-tsc + vite clean
