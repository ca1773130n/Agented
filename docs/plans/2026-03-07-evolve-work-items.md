# Evolve Work Items Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement all 18 pending evolve work items — 5 refactoring tasks and 13 test coverage tasks.

**Architecture:** Split oversized files into focused modules while preserving public APIs via re-exports. Add test coverage for untested services, routes, composables, and components using existing project patterns (pytest + isolated_db for backend, vitest + vue-test-utils for frontend).

**Tech Stack:** Python/Flask/flask-openapi3/Pydantic (backend), Vue 3/TypeScript/Vitest (frontend)

---

## Wave 1: Route Refactoring (lower risk — routes aren't imported by other modules)

### Task 1: Split super_agents.py route (721 lines -> 5 files)

**Files:**
- Create: `backend/app/routes/super_agent_documents.py` — document CRUD (5 handlers)
- Create: `backend/app/routes/super_agent_sessions.py` — session lifecycle (6 handlers)
- Create: `backend/app/routes/super_agent_chat.py` — chat SSE + send message (2 handlers + 4 helpers)
- Create: `backend/app/routes/super_agent_messages.py` — messaging (4 handlers)
- Modify: `backend/app/routes/super_agents.py` — keep only SuperAgent CRUD (5 handlers)
- Modify: `backend/app/routes/__init__.py` — register 4 new blueprints

**Approach:**
- Each new file gets its own `APIBlueprint` with shared `url_prefix="/admin/super-agents"` (following integrations.py pattern)
- Move Pydantic path/body models used only by one sub-file into that file
- Shared models (SuperAgentPath) stay in super_agents.py or move to models/
- Private helpers (_generate_message_id, _resolve_session, _dispatch_by_mode, _launch_background_thread) move with the routes that use them

### Task 2: Split teams.py route (872 lines -> 6 files)

**Files:**
- Create: `backend/app/routes/team_members.py` — member CRUD (4 handlers)
- Create: `backend/app/routes/team_connections.py` — connection CRUD (3 handlers)
- Create: `backend/app/routes/team_assignments.py` — assignment CRUD (5 handlers)
- Create: `backend/app/routes/team_edges.py` — edge CRUD (4 handlers)
- Create: `backend/app/routes/team_generation.py` — generation + job tracking (3 handlers + job store)
- Modify: `backend/app/routes/teams.py` — keep CRUD + topology + trigger + manual run (8 handlers)
- Modify: `backend/app/routes/__init__.py` — register 5 new blueprints

**Approach:**
- `_generation_jobs`, `_jobs_lock`, `_MAX_JOBS` move to team_generation.py
- `_auto_generate_topology_edges` stays in teams.py (used by create/update)
- Each new file gets `url_prefix="/admin/teams"` with appropriate Tag

## Wave 2: Service Refactoring (higher risk — services are imported by other modules)

### Task 3: Split team_execution_service.py (763 lines -> 3 files)

**Files:**
- Create: `backend/app/services/topology_strategies.py` — 7 strategy methods as standalone functions
- Create: `backend/app/services/team_execution_tracker.py` — in-memory state + lock + cleanup
- Modify: `backend/app/services/team_execution_service.py` — thin orchestrator importing from above

**Approach:**
- TeamExecutionService remains the public API (preserve all imports)
- Strategy methods become module-level functions accepting tracker + helpers as args
- Tracker class owns `_executions` dict and `_lock`

### Task 4: Split workflow_execution_service.py (1,459 lines -> 3 files)

**Files:**
- Create: `backend/app/services/workflow_expression_evaluator.py` — AST-based expression evaluation (~100 lines)
- Create: `backend/app/services/workflow_node_executor.py` — node dispatch methods (trigger, skill, command, agent, script, conditional, transform, approval)
- Modify: `backend/app/services/workflow_execution_service.py` — orchestration + DAG utils

**Approach:**
- WorkflowExecutionService remains the public API
- Node executor methods become a NodeExecutor class, called by the orchestrator
- Expression evaluator becomes standalone utility functions

### Task 5: Split execution_service.py (1,476 lines -> 4 files)

**Files:**
- Create: `backend/app/services/trigger_dispatcher.py` — dispatch_github_event, dispatch_webhook_event, _match_payload
- Create: `backend/app/services/execution_runner.py` — _run_execution core logic, _stream_pipe, _budget_monitor, _clone_repos
- Create: `backend/app/services/execution_retry.py` — retry scheduling, rate limit detection, transient failure detection
- Modify: `backend/app/services/execution_service.py` — thin facade importing from above, keeps build_command + run_trigger as entry points

**Approach:**
- ExecutionService class remains with all public method signatures (backward compat)
- Methods delegate to extracted modules
- ExecutionState stays in main file

## Wave 3: Backend Test Coverage

### Task 6: ExecutionService error path tests

**File:** `backend/tests/test_execution_error_paths.py`
- Subprocess timeout handling
- Log streaming pipe failures
- Partial output / truncated responses
- Rate limit retry logic with real timer behavior
- Budget exceeded mid-execution

### Task 7: Concurrent/threaded operation tests

**File:** `backend/tests/test_concurrent_operations.py`
- Concurrent execution queue handling
- Thread-safe state access in ExecutionService
- Team execution parallel strategy with real threads
- Workflow parallel node execution

### Task 8: Untested route coverage (batch)

**Files:** Create test files for highest-priority untested routes:
- `backend/tests/test_agents_routes.py`
- `backend/tests/test_plugins_routes.py`
- `backend/tests/test_commands_routes.py`
- `backend/tests/test_hooks_routes.py`
- `backend/tests/test_rules_routes.py`
- `backend/tests/test_products_routes.py`
- `backend/tests/test_projects_routes.py`
- `backend/tests/test_executions_routes.py`
- `backend/tests/test_health_routes.py`
- `backend/tests/test_audit_routes.py`

Each file: CRUD operations (list, create, get, update, delete) + error cases (not found, validation)

### Task 9: Core service tests (pty_service, cliproxy_manager)

**Files:**
- `backend/tests/test_pty_service.py`
- `backend/tests/test_cliproxy_manager.py`

### Task 10: Conversation service tests

**Files:**
- `backend/tests/test_base_conversation_service.py`
- `backend/tests/test_conversation_services.py` (agent, command, skill, plugin, hook, rule variants)

### Task 11: Integration tests for multi-service workflows

**File:** `backend/tests/test_integration_pipeline.py`
- Trigger -> dispatch -> execution -> log streaming -> status update
- Workflow trigger -> node execution -> result collection
- Team trigger -> topology strategy -> agent execution

### Task 12: MonitoringSection.vue tests

**File:** `frontend/src/components/monitoring/__tests__/MonitoringSection.test.ts`

## Wave 4: Frontend Test Coverage

### Task 13: Missing route test coverage (remaining)

Additional backend route tests for:
- `backend/tests/test_budgets_routes.py`
- `backend/tests/test_bulk_routes.py`
- `backend/tests/test_orchestration_routes.py`
- `backend/tests/test_rotation_routes.py`
- `backend/tests/test_secrets_extra_routes.py`

### Task 14: Frontend composable tests (priority)

**Files:**
- `frontend/src/composables/__tests__/useConversation.test.ts`
- `frontend/src/composables/__tests__/useStreamingParser.test.ts`
- `frontend/src/composables/__tests__/useToast.test.ts`
- `frontend/src/composables/__tests__/useListFilter.test.ts`
- `frontend/src/composables/__tests__/usePagination.test.ts`
- `frontend/src/composables/__tests__/useTokenFormatting.test.ts`
- `frontend/src/composables/__tests__/useTopologyValidation.test.ts`
- `frontend/src/composables/__tests__/useUnsavedGuard.test.ts`
- `frontend/src/composables/__tests__/useMarkdown.test.ts`
- `frontend/src/composables/__tests__/useAutoScroll.test.ts`
- `frontend/src/composables/__tests__/useFocusTrap.test.ts`
- `frontend/src/composables/__tests__/useHealthPolling.test.ts`
- `frontend/src/composables/__tests__/useAsyncState.test.ts`
- `frontend/src/composables/__tests__/useSidebarCollapse.test.ts`

### Task 15: Frontend component tests

**Files:** Tests for critical untested components:
- `frontend/src/components/monitoring/__tests__/BudgetLimitForm.test.ts`
- `frontend/src/components/monitoring/__tests__/ServiceHealthGrid.test.ts`
- `frontend/src/components/monitoring/__tests__/TokenUsageChart.test.ts`
- `frontend/src/components/monitoring/__tests__/RateLimitGauge.test.ts`

### Task 16: Composable error path tests

**Files:**
- `frontend/src/composables/__tests__/useSketchChat.test.ts`
- `frontend/src/composables/__tests__/useProjectSession.test.ts`
- `frontend/src/composables/__tests__/useStreamingGeneration.test.ts`
- `frontend/src/composables/__tests__/useWorkflowExecution.test.ts`

---

## Verification

After each wave:
```bash
cd backend && uv run pytest
cd frontend && npm run test:run
just build
```

All three must pass with zero errors.
