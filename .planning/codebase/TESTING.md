# Testing Strategy and Patterns

**Analysis Date:** 2026-02-25

---

## Overview

The project has two test tiers: a Python backend test suite using pytest and a TypeScript frontend test suite using Vitest. There is additionally a Playwright E2E suite in `frontend/e2e/`. All three must pass before declaring any task complete (see CLAUDE.md verification steps).

---

## How to Run Tests

```bash
# Backend — run all tests
cd backend && uv run pytest

# Backend — run single file
cd backend && uv run pytest tests/test_github_webhook.py

# Backend — run single test
cd backend && uv run pytest tests/test_github_webhook.py::TestGitHubWebhookSignature::test_ping_event -v

# Frontend — run all tests once
cd frontend && npm run test:run

# Frontend — watch mode
cd frontend && npm test

# Frontend — with coverage
cd frontend && npm run test:coverage

# Full verification (both builds and tests — ALWAYS run before declaring complete)
just build          # frontend type check + vite build
cd backend && uv run pytest
cd frontend && npm run test:run
```

---

## Backend Test Framework

**Framework:** pytest `>=9.0.2` with `pytest-cov >=7.0.0`

**Configuration:** `backend/pyproject.toml` — no `pytest.ini` or `setup.cfg`; pytest discovers tests automatically from `backend/tests/`

**Test files:** `backend/tests/test_*.py` (40+ test files covering all domains)

**Integration tests:** `backend/tests/integration/` (4 files with stricter API contract checks)

---

## Backend Core Fixtures (`backend/tests/conftest.py`)

### `isolated_db` (autouse=True)

Every test automatically gets a fresh SQLite database. The fixture:
1. Creates a temp file via `tmp_path`
2. Patches `app.config.DB_PATH` using `monkeypatch.setattr`
3. Calls `init_db()` then `seed_predefined_triggers()` to create the schema and insert the two predefined triggers (`bot-security`, `bot-pr-review`)
4. Suppresses harmless `no such table` warnings from daemon threads during teardown
5. Yields the temp DB path

```python
@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("app.config.SYMLINK_DIR", str(tmp_path / "project_links"))
    from app.database import init_db, seed_predefined_triggers
    init_db()
    seed_predefined_triggers()
    yield db_file
```

Because `get_connection()` reads `config.DB_PATH` dynamically at call time, patching the config is sufficient to redirect all DB access.

### `app` (session-scoped)

Creates a single Flask test application once per session with `TESTING = True`. In testing mode, `create_app()` skips all background service initialization (scheduler, monitoring, session cleanup, etc.) and DB seeding — those are handled by `isolated_db`.

```python
@pytest.fixture(scope="session")
def app():
    from app import create_app
    return create_app(config={"TESTING": True})
```

### `client`

Returns a Flask test client from the session-scoped app. Combined with `isolated_db` (which patches the DB path before each test), each test gets a fresh database while reusing the same app object.

```python
@pytest.fixture()
def client(app):
    return app.test_client()
```

### `reset_github_webhook_rate_limit` (autouse=True)

Clears the `_repo_last_event` dict in `app.routes.github_webhook` before and after each test to prevent rate-limit state from leaking between tests.

---

## Backend Test Patterns

### DB-Only Tests (no HTTP)

Tests that exercise DB functions directly use `isolated_db` (which is `autouse`) and import functions directly:

```python
def test_add_trigger_with_trigger_source(isolated_db):
    from app.database import add_trigger, get_trigger
    trigger_id = add_trigger(
        name="Manual Trigger",
        prompt_template="/test",
        trigger_source="manual",
    )
    assert trigger_id is not None
    trigger = get_trigger(trigger_id)
    assert trigger["trigger_source"] == "manual"
```

### HTTP API Tests (Flask Test Client)

Tests that hit routes use `client`:

```python
def test_ping_event(self, client, monkeypatch):
    payload = json.dumps({"zen": "test"}).encode()
    response = client.post(
        "/api/webhooks/github/",
        data=payload,
        content_type="application/json",
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": signature},
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == "pong"
```

### Monkeypatching Module-Level Constants

For patching module-level constants (like webhook secrets), use `monkeypatch.setattr` on the module object:

```python
from app.routes import github_webhook
monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", "test-secret")
```

### Class-Based Test Organization

Related tests are grouped into classes. The class can define shared constants and a class-level `autouse` fixture:

```python
class TestGitHubWebhookPREvents:
    SECRET = "test-secret"

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, monkeypatch):
        from app.routes import github_webhook
        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", self.SECRET)

    def test_pr_opened_creates_review_record(self, client):
        ...
```

### Helper Function Conventions

Test files use module-level helper functions prefixed with `_` to create test data:

```python
def _create_agent_in_db(isolated_db, agent_id, name="Test Agent"):
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute("INSERT INTO agents (id, name, backend_type, enabled) VALUES (?, ?, ?, 1)", ...)
        conn.commit()
```

### Mocking Subprocess for Execution Tests

Tests that exercise execution flow mock `subprocess.Popen` using `MagicMock` with `io.StringIO` for stdout pipes:

```python
def _make_mock_process(stdout_lines, exit_code=0):
    proc = MagicMock()
    proc.pid = 12345
    stdout_text = "".join(line + "\n" for line in stdout_lines)
    proc.stdout = io.StringIO(stdout_text)
    proc.stderr = io.StringIO("")
    proc.wait.return_value = exit_code
    proc.returncode = exit_code
    return proc
```

### Polling Helpers for Async Operations

Tests that involve background thread execution use polling helpers with a timeout:

```python
def _wait_for_execution(client, execution_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/admin/workflows/executions/{execution_id}")
        status = resp.get_json()["execution"]["status"]
        if status not in ("running", "pending"):
            return resp.get_json()
        time.sleep(0.1)
    return client.get(f"/admin/workflows/executions/{execution_id}").get_json()
```

---

## Backend Integration Tests (`backend/tests/integration/`)

Integration tests in `backend/tests/integration/` use the real Flask test client and real DB with zero mocks. They validate API contracts between the backend and the frontend TypeScript types.

### Contract Assertion Helper

`backend/tests/integration/conftest.py` provides `assert_response_contract()`:

```python
def assert_response_contract(response_dict, expected_fields, entity_name="entity"):
    actual = set(response_dict.keys())
    missing = expected_fields - actual
    assert not missing, (
        f"{entity_name} response missing fields expected by frontend: {missing}. "
        f"Actual fields: {sorted(actual)}"
    )
```

### Contract Test Pattern

```python
# Expected fields derived from frontend/src/services/api/types.ts
AGENT_REQUIRED_FIELDS = {"id", "name", "backend_type", "enabled", "creation_status"}

def test_agent_list_response_contract(client):
    resp = client.get("/admin/agents")
    data = resp.get_json()
    for agent in data["agents"]:
        assert_response_contract(agent, AGENT_REQUIRED_FIELDS, "Agent")
```

### Integration Test Fixtures

`backend/tests/integration/conftest.py` extends the parent conftest with:
- `seed_test_execution` — inserts a test execution log record, yields the `execution_id`

---

## Frontend Test Framework

**Framework:** Vitest `+ happy-dom + @vue/test-utils`

**Configuration:** `frontend/vitest.config.ts`

```typescript
export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/main.ts', 'src/**/*.d.ts', 'src/test/**']
    },
    setupFiles: ['./src/test/setup.ts']
  }
})
```

**Global setup** (`frontend/src/test/setup.ts`):
- Provides mock `showToast` and `refreshTriggers` globally via `config.global.provide`
- Clears all mocks via `beforeEach(() => { vi.clearAllMocks() })`
- Exports `mockShowToast` and `mockRefreshTriggers` for test assertions

---

## Frontend Test Patterns

### Component Tests (Base Components)

Tests for base components (`frontend/src/components/base/__tests__/`) use `mount` directly with props. Tests use CSS class selectors to assert behavior:

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '../StatusBadge.vue'

describe('StatusBadge', () => {
  it('applies correct CSS class for success variant', () => {
    const wrapper = mount(StatusBadge, {
      props: { label: 'Active', variant: 'success' },
    })
    expect(wrapper.find('span').classes()).toContain('ds-status-success')
  })
})
```

Use `it.each` for parameterized variant tests:

```typescript
it.each([
  ['success', 'ds-status-success'],
  ['warning', 'ds-status-warning'],
] as const)('applies correct CSS class for %s variant', (variant, expectedClass) => {
  const wrapper = mount(StatusBadge, { props: { label: 'Test', variant } })
  expect(wrapper.find('span').classes()).toContain(expectedClass)
})
```

### Mount Helper Pattern

Use a local `mountComponent()` or `mountTable()` factory function to avoid repetition and allow easy override:

```typescript
function mountTable(overrides: Record<string, unknown> = {}) {
  return mount(DataTable, {
    props: { columns, items, ...overrides },
  });
}
```

### View Tests (API Mocking)

View tests mock the entire API module with `vi.mock`:

```typescript
vi.mock('../../services/api', () => ({
  triggerApi: {
    list: vi.fn(),
    create: vi.fn(),
    // ...
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
}))
```

View tests provide `showToast` and other injectables in the mount call:

```typescript
function mountComponent() {
  return mount(TriggerManagement, {
    global: {
      provide: {
        showToast: mockShowToast,
        refreshTriggers: mockRefreshTriggers
      },
      stubs: { AddTriggerModal: true }
    }
  })
}
```

Use `flushPromises()` to wait for all async operations to complete before asserting:

```typescript
it('displays trigger names after loading', async () => {
  const wrapper = mountComponent()
  await flushPromises()
  expect(wrapper.text()).toContain('Test Trigger')
})
```

### Composable Tests

Composables are tested by wrapping them in a minimal `defineComponent`:

```typescript
function createTestComponent(options: UseDataPageOptions<TestItem>) {
  return defineComponent({
    setup() { return useDataPage<TestItem>(options); },
    template: '<div />',
  });
}

it('sets items after successful load', async () => {
  const opts = defaultOptions();
  const wrapper = mount(createTestComponent(opts));
  await flushPromises();
  expect(wrapper.vm.items).toEqual(mockItems);
});
```

### API Service Tests

API service tests stub `globalThis.fetch` using `vi.stubGlobal` and create mock responses:

```typescript
function mockResponse(data: unknown, ok = true, status = 200) {
  return {
    ok, status,
    text: () => Promise.resolve(JSON.stringify(data)),
    json: () => Promise.resolve(data)
  } as Response
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  globalThis.fetch = originalFetch
})

it('should fetch triggers list', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ triggers: mockTriggers }))
  const result = await triggerApi.list()
  expect(result.triggers).toEqual(mockTriggers)
})
```

### WebMCP Tests

`frontend/src/webmcp/__tests__/` contains tests for the WebMCP tool system. These tests use mock tool maps (not real API calls) and a test harness in `frontend/src/webmcp/test-harness/`:
- `random-runner.ts` — `invokeTool()` and `generateRandomInputs()`
- `state-verifier.ts` — `getStateToolForAction()` mapping
- `tool-weights.ts` — random walk test weights

WebMCP tests verify that tool execution and state verification patterns work correctly for each domain.

---

## Test Fixtures

### Backend

Fixtures are defined in `backend/tests/conftest.py` (shared) and `backend/tests/integration/conftest.py` (integration-only). No separate fixtures directory.

### Frontend

Typed fixture data lives in `frontend/src/test/fixtures/`:
- `frontend/src/test/fixtures/triggers.ts` — `mockTrigger`, `mockTriggers`, `mockProjectPaths`, `mockTriggerWithGitHub`, `mockTriggerWithWebhook`
- `frontend/src/test/fixtures/audits.ts` — `mockAuditRecords`, `mockAuditStats`

---

## Test File Organization

### Backend

```
backend/tests/
  conftest.py                    — shared fixtures (isolated_db, app, client)
  test_database_crud.py          — comprehensive CRUD for all 10+ entity types (2041 lines)
  test_github_webhook.py         — webhook signature + PR event handling
  test_monitoring.py             — MonitoringService window/ETA calculations
  test_workflow_execution.py     — DAG execution engine
  test_budget_integration.py     — execution flow with token tracking
  test_rotation_service.py       — rotation evaluator
  test_team_topology.py          — team topology + edges
  test_chat_streaming.py         — SSE streaming
  ... (40+ additional files per service/domain)
  integration/
    conftest.py                  — contract assertion helper + seed fixtures
    test_entity_crud_contracts.py — API response shape against frontend TS types
    test_cross_entity_references.py
    test_execution_history_path.py
    test_trigger_execution_flow.py
```

### Frontend

```
frontend/src/
  test/
    setup.ts                     — global mock setup
    fixtures/
      triggers.ts                — trigger fixture data
      audits.ts                  — audit fixture data
  components/base/__tests__/     — DataTable, EmptyState, ErrorState, PageHeader, StatusBadge
  components/canvas/__tests__/   — team-topology
  components/monitoring/__tests__/ — RotationTimelineChart
  components/security/__tests__/ — FindingsChart, PrHistoryChart, RunScanModal
  components/super-agents/__tests__/ — MessageInbox
  components/triggers/__tests__/ — AddTriggerModal, ExecutionLogViewer
  composables/__tests__/         — useDataPage
  services/__tests__/            — api (full API service tests)
  views/__tests__/               — SketchChatPage, SuperAgentPlayground, SuperAgentsPage, TriggerManagement, WorkflowsPage
  webmcp/__tests__/              — crud-cycle, full-sweep, generic-tools, page-specific-tools,
                                    random-walk, search-sort-cycle, tool-registry,
                                    useWebMcpPageTools, useWebMcpTool
```

---

## Coverage and Gaps

### What Is Well-Covered

- **DB CRUD** — `test_database_crud.py` covers all 10+ entity types comprehensively
- **API contract validation** — integration tests check that every list/detail endpoint returns the fields expected by the frontend TypeScript types
- **Service logic** — dedicated test files for `MonitoringService`, `WorkflowExecutionService`, `BudgetService`, `RotationEvaluator`, and `AgentScheduler`
- **Base Vue components** — all shared UI primitives in `components/base/` have unit tests
- **API client** — `services/__tests__/api.test.ts` covers `triggerApi`, `auditApi`, retry, and error classes
- **Composables** — `useDataPage` is fully tested including error states and retry

### Known Gaps

- Many view pages in `frontend/src/views/` have no unit tests (only 5 of ~50 views are tested)
- Domain-specific components in `components/teams/`, `components/grd/`, `components/ai/` have no unit tests
- Backend routes themselves lack direct HTTP integration tests for most domains (only GitHub webhook, workflows, and a few others have route-level tests; most tests operate at the service/DB layer)
- No test coverage for `frontend/src/composables/` composables other than `useDataPage`

---

## E2E Tests (Playwright)

**Location:** `frontend/e2e/`
**Config:** `frontend/playwright.config.ts`

E2E tests are organized as:
```
frontend/e2e/
  fixtures/
    base.ts                — base test fixtures
    live-backend.ts        — live backend fixtures
    mock-data.ts           — mock data
  pages/
    sidebar.page.ts        — page object for sidebar
  tests/
    agents-crud.spec.ts
    ai-backends.spec.ts
    commands.spec.ts
    navigation.spec.ts
    ...
    integration/
      dashboard-data.spec.ts
      entity-crud-flow.spec.ts
      trigger-execution.spec.ts
```

E2E tests use the Page Object pattern. They are not part of the standard `just build` + unit test verification cycle described in CLAUDE.md.

---

*Testing analysis: 2026-02-25*
