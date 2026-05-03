# v0.5.3 — Audit cleanup, second pass + modal E2E

Closes the **remaining** silent-failure findings from
`.planning/error-handling-audit-pr4.md` and the
**modal-interaction E2E** carryover from v0.5.0.

## What this ships

### Silent-failure findings

| Audit # | Site | Severity | Status before | This plan |
|---------|------|----------|---------------|-----------|
| #6 | `app_litestar/routes/leaf_crud_f.py:get_memory_config` | HIGH | `pass` swallows JSON parse error → returns defaults | log warning + return defaults |
| #7 | `app_litestar/routes/leaf_crud_f.py:update_memory_config` | HIGH | `pass` swallows → corrupt config dropped silently | log warning + drop |
| #9 | `app/db/tracing.py:end_trace` `started_at` parse | MEDIUM | unhandled `ValueError` bubbles up as 500 | try/except + log + duration_ms = NULL |
| #10 | `app/db/tracing.py:end_span` `started_at` parse | MEDIUM | identical to #9 | identical fix |

### Modal-interaction E2E (OB-44 / OB-47)

The v0.5.0 carryover. Originally re-deferred to v0.6.0 for
`@ai-accounts` fixture engineering. Turns out the integration is
much simpler than the deferral note implied: the AccountWizard
exposes `data-tour="account-wizard"` on its container and the
existing test fixture already mocks the backend detail endpoint,
so a focused "modal opens and is interactive" E2E doesn't need
OAuth mocks or wizard XState stubs.

New test in `e2e/tests/tour-flow.spec.ts`:

1. Start tour, advance to backends step (STEP 3).
2. Click `[data-tour="add-account-btn"]`.
3. Assert AccountWizard renders (`[data-tour="account-wizard"]`).
4. Assert wizard's close button has `pointer-events != none` —
   proves the tour overlay isn't intercepting clicks.
5. Assert `tour-spotlight--reduced` OR `tour-dim-fallback.modal-open`
   appears — proves `modalOpenDuringTour` propagated through
   `provide('setTourModalOpen', ...)`.

## Stale audit findings

| Audit # | Site | Why stale |
|---------|------|-----------|
| #5 | `agent_memory.py:recall_messages` FTS5 errors | Already wrapped: `try/except Exception: logger.warning(...)` at line ~198-204. Predates the audit but the audit wasn't refreshed. |
| #11 | `routes/agent_memory.py` no DB try/except | Routes moved to Litestar; Litestar's `Exception` handler at `exception_handlers.py:155` catches uncaught DB exceptions, logs them, and emits 500/503. Framework-level coverage. |
| #12 | `routes/tracing.py` no DB try/except | Same as #11. |
| #13 | `save_messages` no thread-existence check | Semantic, not silent-failure. Out of scope. |
| #14 | `recall_messages` empty-query returns empty | Semantic. Out of scope. |

## Source changes

### `backend/app_litestar/routes/leaf_crud_f.py`

Added `import logging` + `logger = logging.getLogger(__name__)`.
Two silent `pass` blocks in `get_memory_config` and
`update_memory_config` replaced with `logger.warning(...)` carrying
the agent_id + truncated raw blob.

### `backend/app/db/tracing.py`

Wrapped `datetime.fromisoformat(row["started_at"])` calls in
`end_trace` and `end_span` with try/except (TypeError, ValueError),
logging the trace/span id + raw value and leaving `duration_ms = None`
so the API contract holds.

## Tests

- `tests/test_tracing.py::TestCorruptStartedAt` — 2 new tests
  (end_trace + end_span)
- `tests/test_litestar_leaf_crud_f.py` — 2 new tests
  (get_memory_config + update_memory_config), using a logger
  monkeypatch spy because Litestar's TestClient logger plumbing
  doesn't propagate to pytest's caplog reliably
- `frontend/e2e/tests/tour-flow.spec.ts` — 1 new E2E for OB-44

## Verification

- `cd backend && uv run pytest` — **2196 passed** (+4)
- `cd frontend && npm run test:run` — 1069 passed (unchanged)
- `cd frontend && npm run build` — vue-tsc + vite clean
- `npx playwright test --list` — 7 tour E2E tests (was 6)
