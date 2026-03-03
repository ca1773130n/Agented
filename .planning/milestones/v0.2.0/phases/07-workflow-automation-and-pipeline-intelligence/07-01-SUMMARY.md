---
phase: "07"
plan: "01"
subsystem: "workflow-engine"
tags: [conditional-logic, expression-evaluator, approval-gates, dag-execution, edge-routing]
dependency_graph:
  requires: []
  provides:
    - "Safe AST-based expression evaluator for condition evaluation"
    - "Edge-aware branch routing in DAG execution"
    - "Approval gate node type with threading.Event pause/resume"
    - "Approval state DB persistence and REST endpoints"
  affects:
    - "backend/app/services/workflow_execution_service.py"
    - "backend/app/models/workflow.py"
    - "backend/app/db/workflows.py"
    - "backend/app/db/schema.py"
    - "backend/app/routes/workflows.py"
tech_stack:
  added:
    - "ast module for safe expression parsing"
    - "operator module for comparison dispatch"
  patterns:
    - "AST-walking evaluator (no eval/exec)"
    - "threading.Event for approval gate pause/resume"
    - "Edge sourceHandle filtering for branch routing"
key_files:
  created: []
  modified:
    - "backend/app/services/workflow_execution_service.py"
    - "backend/app/models/workflow.py"
    - "backend/app/db/workflows.py"
    - "backend/app/db/schema.py"
    - "backend/app/db/migrations.py"
    - "backend/app/db/__init__.py"
    - "backend/app/routes/workflows.py"
decisions:
  - "Used ast.parse + recursive _eval_node walker instead of eval/exec for expression evaluation"
  - "Approval gate uses threading.Event.wait() following proven TeamExecutionService pattern"
  - "Edge-aware branching preserves backward compatibility: edges without sourceHandle always execute"
  - "Rejection implemented via separate flag dict checked after Event.set() to avoid race conditions"
metrics:
  duration: "7m 18s"
  completed: "2026-03-04"
---

# Phase 07 Plan 01: Conditional Logic, Edge-Aware Branching, and Approval Gates Summary

AST-based safe expression evaluator with edge-aware DAG branch routing and human-in-the-loop approval gate nodes, enabling conditional workflow paths and pause/resume execution.

## Completed Tasks

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Safe expression evaluator and edge-aware conditional branching | 3d19bde | Done |
| 2 | Approval gate node with DB persistence and approve/reject endpoints | bcdc070 | Done |

## Key Changes

### Task 1: Safe Expression Evaluator and Edge-Aware Branching

**Safe Expression Evaluator** (`evaluate_condition`):
- Built on Python's `ast` module -- parses expressions into AST and walks it recursively
- Supports comparison operators: `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not in`
- Supports boolean operators: `and`, `or`, `not`
- Supports dot-notation (`pr.branch`) and subscript (`pr["branch"]`) access on nested dicts
- Raises `ValueError` for any unsupported AST node type -- no code injection possible

**Enhanced Conditional Node**:
- Added `expression` condition type alongside existing `has_text`, `exit_code_zero`, `contains`
- Expression evaluation uses input message data as context dict
- Full backward compatibility with existing condition types

**Edge-Aware Branch Routing**:
- After a conditional node succeeds, checks if output has a `branch` label
- Filters edges by `sourceHandle`: only edges matching the branch label execute
- Non-matching edges have their targets added to `skipped_nodes` with recursive downstream propagation
- Edges without `sourceHandle` (None) are treated as unconditional for backward compatibility

**Model Updates**:
- `WorkflowNodeType.APPROVAL_GATE` enum value
- `WorkflowExecutionStatus.PENDING_APPROVAL` and `NodeExecutionStatus.PENDING_APPROVAL`
- `WorkflowEdge.sourceHandle: Optional[str]` field

### Task 2: Approval Gate Node with DB Persistence

**DB Schema** (`workflow_approval_states` table):
- Fields: id, execution_id, node_id, status, timeout_seconds, requested_at, resolved_at, resolved_by
- Unique constraint on (execution_id, node_id)
- Migration v56 creates the table

**CRUD Functions**:
- `add_workflow_approval_state` -- insert pending record
- `update_workflow_approval_state` -- transition to approved/rejected/timed_out
- `get_workflow_approval_state` -- fetch single record
- `get_pending_approval_states` -- fetch all pending (for UI)
- `cleanup_stale_approval_states` -- mark all pending as timed_out (startup cleanup)

**Approval Gate Node Executor**:
- Creates `threading.Event` and registers in class-level `_approval_events` dict
- Reads `execution_id` from `input_msg.metadata["_execution_id"]` (injected by `_run_workflow`)
- Persists approval state to DB
- Updates node and execution status to `pending_approval` (triggers SSE broadcast)
- Calls `event.wait(timeout=timeout)` -- blocks until approved, rejected, or timeout
- On timeout: marks DB as `timed_out`, raises RuntimeError
- On rejection: checks `_rejection_flags`, raises RuntimeError
- On approval: returns input message as pass-through

**Approve/Reject Methods**:
- `approve_node()` -- sets Event, updates DB to approved
- `reject_node()` -- sets rejection flag, sets Event, updates DB to rejected

**REST Endpoints**:
- `POST /admin/workflows/executions/<execution_id>/nodes/<node_id>/approve`
- `POST /admin/workflows/executions/<execution_id>/nodes/<node_id>/reject`
- `GET /admin/workflows/pending-approvals`

**Startup Cleanup**:
- Extended `cleanup_stale_executions()` to call `cleanup_stale_approval_states()` on startup
- Marks all pending approval states as timed_out since in-memory Events are lost

## Verification Results

- 6 distinct expression evaluation tests: PASS
- Model enum assertions: PASS
- Approval state DB CRUD cycle: PASS
- NODE_DISPATCHERS contains approval_gate: PASS
- All 3 REST endpoints registered and routable (not 405): PASS
- 911 existing backend tests: PASS (no regressions)

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

All key files exist and all commits verified.
