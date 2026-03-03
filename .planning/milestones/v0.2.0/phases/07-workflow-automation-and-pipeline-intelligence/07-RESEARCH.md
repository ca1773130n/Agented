# Phase 7: Workflow Automation & Pipeline Intelligence - Research

**Researched:** 2026-03-04
**Domain:** DAG-based workflow execution, visual graph editing, conditional routing, approval gates, multi-model fallback, per-node retry
**Confidence:** HIGH

## Summary

Phase 7 extends an already-functional DAG workflow engine and VueFlow-based canvas. The codebase has `WorkflowExecutionService` (989 lines) implementing topological sort via `graphlib.TopologicalSorter`, per-node retry with exponential backoff, error mode handling (stop/continue/continue_with_error), and 7 node types (trigger, skill, command, agent, script, conditional, transform). The frontend has a full drag-and-drop canvas (`WorkflowCanvas.vue`) using `@vue-flow/core` 1.48 with custom node components, a `NodeConfigPanel` with per-type config forms, and composables for canvas state (`useWorkflowCanvas`), execution SSE monitoring (`useWorkflowExecution`), and graph validation (`useWorkflowValidation`).

The six requirements (WF-01 through WF-06) build incrementally on this foundation. WF-01 (visual DAG builder) is already 80% complete -- the canvas supports drag-and-drop, node config, save/load, and auto-layout. WF-02 (conditional trigger rules) requires extending the existing conditional node to evaluate PR attributes. WF-03 (approval gates) has a proven pattern in `TeamExecutionService._execute_human_in_loop` using `threading.Event` for pause/resume. WF-04 (multi-model fallback) has `OrchestrationService.execute_with_fallback` already implementing account rotation and rate-limit detection. WF-05 (conditional branch nodes) partially exists in the conditional node type but needs proper edge-aware branching. WF-06 (per-node retry) is already implemented in the workflow engine's retry loop.

**Primary recommendation:** Extend the existing `WorkflowExecutionService` and VueFlow canvas rather than building new systems. The codebase already has 70-80% of the required infrastructure -- the work is primarily about enhancing existing node types, adding a new `approval` node type, wiring the existing `OrchestrationService` fallback logic into workflow agent nodes, and enriching the conditional node's expression evaluation.

## Paper-Backed Recommendations

Every recommendation below cites specific evidence.

### Recommendation 1: Use graphlib.TopologicalSorter.get_ready() for Parallel-Ready Execution

**Recommendation:** Replace `static_order()` with the iterative `get_ready()`/`done()` protocol for future parallel node execution within levels.
**Evidence:**
- [Python graphlib docs](https://docs.python.org/3/library/graphlib.html) -- `get_ready()` returns nodes at the current level that have all predecessors completed. `done()` marks them as processed, unlocking the next level. This enables level-parallel execution.
- [Geeks for Geeks: Topological Sorting using graphlib](https://www.geeksforgeeks.org/python/topological-sorting-using-graphlib-python-module/) -- Demonstrates the iterative protocol for parallel processing.
- The current codebase uses `list(ts.static_order())` which serializes everything. For Phase 7, keep `static_order()` for simplicity but structure the code so the `get_ready()`/`done()` protocol can be adopted later.

**Confidence:** HIGH -- Python stdlib documentation, well-established API since Python 3.9.
**Expected improvement:** Enables future parallel execution of independent nodes at the same DAG level.
**Caveats:** Not needed for Phase 7 requirements but worth structuring for. Conditional branches already serialize correctly with `static_order()`.

### Recommendation 2: Use threading.Event for Approval Gate Pause/Resume (Proven Pattern)

**Recommendation:** Implement workflow approval gates using `threading.Event`, following the exact pattern already proven in `TeamExecutionService._execute_human_in_loop`.
**Evidence:**
- `backend/app/services/team_execution_service.py` lines 589-661 -- Working implementation: creates `threading.Event`, sets status to `pending_approval`, calls `event.wait(timeout=approval_timeout)`, handles both approval and timeout paths.
- `TeamExecutionService.approve_execution()` (line 673) -- External approval endpoint that calls `event.set()` from outside the execution thread.
- [Temporal workflow patterns](https://temporal.io/) -- Industry standard for human-in-the-loop: pause execution, emit notification, wait for external signal. The threading.Event pattern is the single-process equivalent.

**Confidence:** HIGH -- Working code in the same codebase, proven pattern.
**Expected improvement:** Approval gates work immediately with minimal new code.
**Caveats:** In-memory Event objects are lost on server restart. Need to persist pending approval state to DB and handle recovery.

### Recommendation 3: Extend OrchestrationService Fallback Chain into Workflow Agent Nodes

**Recommendation:** Wire `OrchestrationService.execute_with_fallback()` into `_execute_agent_node` (currently a stub) to get multi-model fallback for free.
**Evidence:**
- `backend/app/services/orchestration_service.py` lines 44-247 -- Full implementation: iterates fallback chain entries, checks rate limits via `RateLimitService`, picks best account via `pick_best_account()`, handles budget pre-checks, schedules retries after rate-limit cooldown.
- `backend/app/db/backends.py` lines 45-91 -- `get_fallback_chain()` and `set_fallback_chain()` already handle per-entity fallback chain persistence.
- `backend/app/services/rate_limit_service.py` -- Existing rate limit detection and cooldown tracking.

**Confidence:** HIGH -- Working code, already handles all the edge cases.
**Expected improvement:** Multi-model fallback (WF-04) becomes configuration-only, not new logic.
**Caveats:** The stub `_execute_agent_node` needs to be replaced with real agent/trigger execution via OrchestrationService.

### Recommendation 4: Use Safe Expression Evaluation for Conditional Branching

**Recommendation:** Use a restricted Python expression evaluator (using `ast.literal_eval` for simple cases, or a safe subset evaluator) for condition expressions on PR attributes. Do NOT use `eval()`.
**Evidence:**
- [OWASP Code Injection Prevention](https://owasp.org/) -- `eval()` is a well-known code injection vector. The codebase already has security concerns noted in CONCERNS.md around arbitrary code execution.
- The existing conditional node supports only `has_text`, `exit_code_zero`, `contains` -- these are too limited for WF-02's PR attribute conditions (line count > 500, branch matches pattern, draft status).
- A safe expression evaluator can support operators (==, !=, >, <, >=, <=, in, not in, and, or) on a sandboxed context dict without security risk.

**Confidence:** HIGH -- Standard security practice.
**Expected improvement:** Rich conditional expressions without security exposure.
**Caveats:** Avoid pulling in heavy dependencies like `simpleeval` if a lightweight custom evaluator suffices.

## Standard Stack

### Core (Already Installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@vue-flow/core` | ^1.48.2 | Interactive DAG canvas | Already in use; VueFlow is the de facto Vue 3 flowchart library |
| `@vue-flow/background` | ^1.3.2 | Grid background for canvas | Already installed |
| `@vue-flow/controls` | ^1.1.3 | Zoom/pan controls | Already installed |
| `@vue-flow/minimap` | ^1.5.4 | Minimap navigation | Already installed |
| `@dagrejs/dagre` | ^2.x | Auto-layout for DAG graphs | Already in use via `useCanvasLayout` |
| `graphlib` | stdlib | Topological sort, cycle detection | Python 3.9+ stdlib; already in use |
| `threading` | stdlib | Approval gate pause/resume | Already used for execution threads |
| `APScheduler` | 3.10 | Cron/polling workflow triggers | Already in use via `SchedulerService` |

### Supporting (No New Dependencies Needed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` | 2.x | Request/response models for new node types | Already used for all API models |
| `sqlite3` | stdlib | Approval state persistence, workflow config | Already the sole DB layer |

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| Custom expression evaluator | `simpleeval` PyPI package | Adds a dependency for a feature that can be built in ~50 lines | Build custom; keep deps minimal |
| In-memory approval Events | Redis pub/sub | Survives restarts, enables horizontal scaling | Overkill for single-process; use DB persistence + Event recovery on startup |
| Custom fallback logic | New FallbackNode type | Cleaner separation | Reuse OrchestrationService; it already handles all edge cases |

**Installation:**
```bash
# No new packages needed. All required libraries are already installed.
```

## Architecture Patterns

### Recommended Project Structure

New files (additions to existing structure):

```
backend/app/
├── services/
│   └── workflow_execution_service.py  # EXTEND: add approval_gate, enhanced conditional, fallback agent nodes
│   └── workflow_trigger_service.py    # EXTEND: add PR attribute condition evaluation
├── models/
│   └── workflow.py                    # EXTEND: add ApprovalGateConfig, ConditionExpression, FallbackChainConfig models
├── routes/
│   └── workflows.py                   # EXTEND: add approve/reject endpoints
├── db/
│   └── workflows.py                   # EXTEND: add approval state persistence functions
│   └── schema.py                      # EXTEND: add workflow_approval_states table
│   └── migrations.py                  # EXTEND: add migration for new tables/columns

frontend/src/
├── components/workflow/nodes/
│   └── ApprovalGateNode.vue           # NEW: approval gate node component
│   └── FallbackChainNode.vue          # NEW: fallback chain node component (optional visual)
│   └── ConditionalNode.vue            # EXTEND: richer condition expression UI
├── composables/
│   └── useWorkflowCanvas.ts           # EXTEND: register new node types
│   └── useWorkflowExecution.ts        # EXTEND: handle approval_pending SSE events
│   └── useWorkflowValidation.ts       # EXTEND: validate new node types
├── components/workflow/
│   └── NodeConfigPanel.vue            # EXTEND: config forms for new node types
│   └── ApprovalModal.vue              # NEW: approve/reject dialog
│   └── WorkflowCanvas.vue            # EXTEND: register new node types
```

### Pattern 1: New Node Type Registration

**What:** Adding a new node type follows a consistent 5-step pattern established by the existing 7 types.
**When to use:** For every new node type (approval_gate, condition_branch, fallback_chain).
**Example:**

1. **Backend model** (`models/workflow.py`): Add to `WorkflowNodeType` enum
2. **Backend dispatcher** (`workflow_execution_service.py`): Add entry to `NODE_DISPATCHERS` dict and `_execute_*` classmethod
3. **Frontend node component** (`components/workflow/nodes/`): Create Vue component with Handle ports
4. **Frontend canvas registration** (`WorkflowCanvas.vue`): Add to `nodeTypes` object with `markRaw()`
5. **Frontend config panel** (`NodeConfigPanel.vue`): Add type-specific config form fields

```python
# Source: backend/app/services/workflow_execution_service.py (existing pattern)
NODE_DISPATCHERS = {
    "trigger": "_execute_trigger_node",
    # ... existing types ...
    "approval_gate": "_execute_approval_gate_node",  # NEW
}
```

### Pattern 2: Approval Gate via threading.Event

**What:** Pause DAG execution at a node, wait for external approve/reject API call.
**When to use:** For WF-03 approval gate nodes.
**Example:**

```python
# Source: Adapted from backend/app/services/team_execution_service.py lines 589-661
@classmethod
def _execute_approval_gate_node(cls, node_id, node_config, input_msg):
    approval_event = threading.Event()
    timeout = node_config.get("timeout", 1800)  # 30 min default

    # Register approval state in memory and DB
    cls._register_pending_approval(execution_id, node_id, approval_event, timeout)

    # Wait for external approval or timeout
    approved = approval_event.wait(timeout=timeout)

    if not approved:
        raise RuntimeError(f"Approval gate timed out after {timeout}s")

    # Check if rejected
    if cls._was_rejected(execution_id, node_id):
        raise RuntimeError("Approval gate rejected by reviewer")

    return input_msg  # Pass through on approval
```

### Pattern 3: Conditional Branch via Edge-Aware Execution

**What:** Conditional nodes output a branch label ("true"/"false"/"skip") and the execution engine selects downstream edges based on source handle matching.
**When to use:** For WF-05 condition branch nodes.
**Source:** The frontend already has `sourceHandle` on conditional edges (see `ConditionalNode.vue` with `id="true"` and `id="false"` handles).

**Backend change needed:** The current execution engine does not filter edges by `sourceHandle`. It must be modified to respect `sourceHandle` when a conditional node outputs a branch decision.

```python
# Current: all successors of a node are executed
# Needed: only successors connected via the matching sourceHandle

# In _run_workflow, after a conditional node returns its branch result:
if node_type == "conditional" and output_msg.data.get("branch"):
    branch = output_msg.data["branch"]  # "true" or "false"
    # Only proceed to successors connected via the matching handle
    matching_edges = [e for e in edges_list if e["source"] == node_id and e.get("sourceHandle") == branch]
    non_matching_edges = [e for e in edges_list if e["source"] == node_id and e.get("sourceHandle") != branch]
    # Mark non-matching branch targets as skipped
    for e in non_matching_edges:
        skipped_nodes.add(e["target"])
```

### Anti-Patterns to Avoid

- **Don't use eval() for condition expressions:** Use a safe expression evaluator. The codebase already has security concerns about arbitrary code execution (CONCERNS.md section 1.4).
- **Don't create a separate approval microservice:** The platform is single-process Flask. Use in-memory Events + DB persistence for approval state, matching the TeamExecutionService pattern.
- **Don't rewrite the DAG engine:** The existing engine handles topological sort, retry, error modes, timeout, and cancellation correctly. Extend it; don't replace it.
- **Don't add new npm dependencies for the canvas:** VueFlow already provides everything needed for custom nodes, handles, edge labels, and drag-and-drop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Topological sort | Custom topo sort | `graphlib.TopologicalSorter` | Already stdlib, already in use, handles cycles |
| Graph layout | Custom layout algorithm | `@dagrejs/dagre` via `useCanvasLayout` | Already integrated, handles TB/LR direction |
| Fallback chain routing | Custom provider rotation | `OrchestrationService.execute_with_fallback()` | Handles rate limits, budget checks, account selection |
| Approval pause/resume | Custom polling/sleep loop | `threading.Event.wait(timeout)` | Clean, timeout-aware, proven in TeamExecutionService |
| SSE streaming | Custom event system | `ExecutionLogService` subscriber pattern | Already handles fan-out, replay, cleanup |
| Canvas drag-and-drop | Custom DnD | VueFlow's built-in `onDragOver`/`onDrop` + `screenToFlowCoordinate` | Already working in WorkflowCanvas.vue |
| Expression parsing | `eval()` or regex | AST-based safe evaluator | Security; avoids code injection |

**Key insight:** The platform already has 70-80% of the infrastructure. The major risk is building new systems instead of extending existing ones. Every requirement maps to existing code that needs enhancement, not replacement.

## Common Pitfalls

### Pitfall 1: Conditional Branching Breaks Topological Order

**What goes wrong:** The topological sort executes ALL downstream nodes of a conditional, even nodes on the branch that should be skipped.
**Why it happens:** The current engine's `predecessors` map does not account for `sourceHandle` -- it treats all edges from a conditional as equal.
**How to avoid:** After a conditional node executes and returns a branch label, immediately add all non-matching branch targets to `skipped_nodes` before continuing the topological loop.
**Warning signs:** Both true and false branch paths execute for every conditional node.

### Pitfall 2: Approval Gate State Lost on Server Restart

**What goes wrong:** In-memory `threading.Event` objects are lost when the server restarts, leaving workflows permanently stuck in `pending_approval`.
**Why it happens:** The pattern from `TeamExecutionService` stores approval Events only in memory (`cls._executions` dict).
**How to avoid:** Persist approval state to DB (`workflow_approval_states` table). On startup, `cleanup_stale_executions()` already marks stale running executions as failed -- extend it to handle pending approval states.
**Warning signs:** After server restart, workflow executions show status "running" forever in the UI.

### Pitfall 3: Retry Backoff Blocks Entire DAG Thread

**What goes wrong:** The current retry implementation uses `time.sleep(delay)` in the DAG execution thread, blocking all subsequent nodes.
**Why it happens:** The execution loop is single-threaded per workflow. When node B retries with exponential backoff, nodes C, D, E must wait.
**How to avoid:** For Phase 7, this is acceptable since execution is sequential anyway. Document it as a known limitation. For future parallel execution, use `threading.Timer` instead of `time.sleep()`.
**Warning signs:** Slow workflows where early nodes have retries, causing unnecessary delays for independent downstream nodes.

### Pitfall 4: Circular Notification on Approval Gates

**What goes wrong:** Approval gate sends notification, notification triggers a webhook, webhook triggers the workflow again.
**Why it happens:** No deduplication between approval notifications and workflow triggers.
**How to avoid:** Approval notifications should be fire-and-forget (log-based, not webhook-based). Use the existing SSE mechanism (`useWorkflowExecution`) to push approval status to the frontend rather than external webhooks.
**Warning signs:** Infinite workflow execution loops after adding approval gates.

### Pitfall 5: VueFlow Node Type Not Registered with markRaw()

**What goes wrong:** Custom node components wrapped in Vue's reactive proxy cause rendering issues and console warnings.
**Why it happens:** VueFlow requires raw (non-reactive) component references in the `nodeTypes` object.
**How to avoid:** Always use `markRaw()` when registering new node types, following the existing pattern in `WorkflowCanvas.vue` line 30.
**Warning signs:** Console warnings about "Non-function value encountered for default slot" or nodes not rendering.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:** Number and type of nodes in workflow (trigger, conditional, approval_gate, agent, command), complexity of conditional expressions, fallback chain depth, retry configuration.
**Dependent variables:** Workflow completion time, node execution order correctness, conditional branch routing accuracy, approval gate pause/resume correctness, fallback chain failover time, retry behavior under failure.
**Controlled variables:** Same SQLite database, single-process Flask server, fixed test data.

**Baseline comparison:**
- Method: Current workflow engine with 7 node types, no approval gates, basic conditionals
- Expected performance: Linear sequential execution, all conditional branches execute (no edge-aware routing)
- Our target: Correct edge-aware branching (only matching branch executes), approval gates pause/resume correctly, fallback chain fires within 5 seconds of rate-limit

**Ablation plan:**
1. Full implementation vs. without conditional branching -- tests that branch routing is the critical differentiator for WF-02/WF-05
2. Full implementation vs. without approval gates -- tests that the pause/resume mechanism works independently
3. Full implementation vs. without fallback chains in agent nodes -- tests that multi-model failover is correctly wired

**Statistical rigor:**
- Number of runs: 3 per test scenario (approval gate timing can vary)
- Success criteria: 100% deterministic for branch routing, retry, and fallback; approval gate timing within 500ms of expected

### Recommended Metrics

| Metric | Why | How to Compute | Baseline |
|--------|-----|----------------|----------|
| Branch routing accuracy | Core WF-05 correctness | Count correct branch selections / total conditionals | 0% (no branch routing exists) |
| Approval gate response time | WF-03 user experience | Time from approve API call to DAG resumption | N/A (no approval gates) |
| Fallback chain failover time | WF-04 availability | Time from rate-limit detection to next provider attempt | < 5 seconds target |
| Retry behavior correctness | WF-06 resilience | Retry count and backoff timing match config | Already working (extend to new node types) |
| Conditional expression evaluation | WF-02 rule engine | Pass/fail on 5+ distinct condition expressions | 0% (only has_text/exit_code/contains) |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| New node types execute without error | Level 1 (Sanity) | Can check immediately with unit test |
| Conditional branch routes to correct path | Level 1 (Sanity) | Deterministic, testable with _make_graph fixtures |
| Approval gate pauses and resumes | Level 2 (Proxy) | Requires threading timing, use polling helper |
| Fallback chain fires on rate-limit | Level 2 (Proxy) | Mock rate-limit, verify account rotation |
| Full pipeline end-to-end | Level 2 (Proxy) | Use _wait_for_execution pattern from existing tests |
| Canvas drag-drop and save | Level 3 (Deferred) | Requires Playwright E2E test |
| Notification delivery for approval gates | Level 3 (Deferred) | Requires integration with notification system |
| PR attribute condition evaluation accuracy | Level 2 (Proxy) | Unit test with 5+ condition expressions |

**Level 1 checks to always include:**
- New node types (approval_gate) registered in `NODE_DISPATCHERS` and executable
- Conditional branch node skips non-matching branch targets
- Per-node retry_policy config is respected (max_attempts, backoff_strategy)
- `WorkflowNodeType` enum includes all new types
- VueFlow `nodeTypes` object includes all new node component registrations

**Level 2 proxy metrics:**
- Approval gate pauses execution for at least N seconds, resumes on approve API call
- Rejection aborts downstream nodes
- Fallback chain rotates to next provider within 5 seconds of simulated rate-limit
- 5+ distinct conditional expressions evaluate correctly against mock PR data
- Condition branch nodes with 3+ branching scenarios (pass/fail/skip) route correctly

**Level 3 deferred items:**
- Full E2E: drag nodes onto canvas, connect edges, save, execute, verify results in UI
- Slack/email notification delivery for approval gates
- Multi-workflow chaining with approval gates at each stage

## Production Considerations

### Known Failure Modes

- **Server restart during pending approval:** In-memory `threading.Event` lost. The `cleanup_stale_executions()` method already marks running executions as failed on restart. Extend it to handle `pending_approval` status.
  - Prevention: Persist approval state to DB immediately when entering pending state.
  - Detection: On startup, query for executions with `status = 'pending_approval'` and mark as timed_out.

- **Fallback chain exhaustion with no retry:** When all accounts in a fallback chain are rate-limited, `OrchestrationService` returns `CHAIN_EXHAUSTED` and schedules a retry. Workflow agent nodes must handle this result gracefully.
  - Prevention: Surface chain exhaustion as a node failure with `continue_with_error` mode option.
  - Detection: Check `ExecutionResult.status == CHAIN_EXHAUSTED` in agent node executor.

- **SQLite write contention during approval polling:** Multiple SSE subscribers polling approval status while the approval API endpoint writes to DB could cause busy timeout.
  - Prevention: Use in-memory status for SSE (existing pattern) and only write to DB on state transitions.
  - Detection: `sqlite3.OperationalError: database is locked` in logs.

### Scaling Concerns

- **At current scale (single-user, single-process):** threading.Event approval gates work fine. In-memory execution tracking is sufficient.
- **At production scale (multi-process):** Would need Redis pub/sub for approval events and shared execution state. This is a known limitation documented in CONCERNS.md (section 7.2) and is out of scope for Phase 7.

### Common Implementation Traps

- **Trap: Adding eval() for condition expressions.** The codebase already has security concerns about script node executing arbitrary code (CONCERNS.md section 1.4). Adding `eval()` for conditions would introduce another code injection vector.
  - Correct approach: Build a safe expression evaluator using `ast.parse` + whitelist of allowed operations, or use a simple operator-based evaluation on a fixed context dict.

- **Trap: Re-implementing fallback chain logic inside workflow nodes.** The `OrchestrationService` already handles all edge cases (rate limit detection, budget pre-checks, account rotation, retry scheduling).
  - Correct approach: Call `OrchestrationService.execute_with_fallback()` from within `_execute_agent_node`, passing a synthetic trigger dict built from the workflow node config.

## Code Examples

Verified patterns from the existing codebase:

### Adding a New Workflow Node Type (Backend)

```python
# Source: backend/app/services/workflow_execution_service.py (existing pattern)
# Step 1: Add to NODE_DISPATCHERS
NODE_DISPATCHERS = {
    # ... existing ...
    "approval_gate": "_execute_approval_gate_node",
    "condition_branch": "_execute_condition_branch_node",
}

# Step 2: Add to WorkflowNodeType enum in models/workflow.py
class WorkflowNodeType(str, Enum):
    # ... existing ...
    APPROVAL_GATE = "approval_gate"
    CONDITION_BRANCH = "condition_branch"
```

### Registering a New Node Type (Frontend)

```typescript
// Source: frontend/src/components/workflow/WorkflowCanvas.vue (existing pattern)
import ApprovalGateNode from './nodes/ApprovalGateNode.vue'

const nodeTypes: NodeTypesObject = {
  // ... existing ...
  approval_gate: markRaw(ApprovalGateNode) as NodeTypesObject[string],
}
```

### Safe Expression Evaluation Pattern

```python
# Safe evaluator for PR attribute conditions (WF-02)
import ast
import operator

SAFE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.And: lambda a, b: a and b,
    ast.Or: lambda a, b: a or b,
    ast.Not: operator.not_,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

def evaluate_condition(expression: str, context: dict) -> bool:
    """Safely evaluate a condition expression against a context dict.

    Example: evaluate_condition("pr.lines_changed > 500", {"pr": {"lines_changed": 600}})
    """
    # Parse and walk AST, only allowing safe operations
    # Returns True/False without executing arbitrary code
    ...
```

### Approval Gate Endpoint Pattern

```python
# Source: Adapted from backend/app/services/team_execution_service.py line 673
# In backend/app/routes/workflows.py
@workflows_bp.post("/executions/<execution_id>/nodes/<node_id>/approve")
def approve_node(path: ApproveNodePath):
    result = WorkflowExecutionService.approve_node(
        path.execution_id, path.node_id, action="approve"
    )
    if result:
        return {"message": "Node approved"}, HTTPStatus.OK
    return {"error": "Node not in pending approval state"}, HTTPStatus.BAD_REQUEST
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Simple sequential execution | DAG with topo sort + error modes + retry | Already implemented | Foundation for Phase 7 |
| Only 3 condition types (has_text, exit_code_zero, contains) | Expression-based conditions on structured data | Phase 7 (WF-02/WF-05) | Enables PR attribute filtering |
| Stub agent node (returns mock text) | Agent node with OrchestrationService fallback chain | Phase 7 (WF-04) | Real multi-model agent execution |
| No human-in-loop for workflows | Approval gate nodes with pause/resume | Phase 7 (WF-03) | Human oversight for critical pipelines |

**Already implemented (no changes needed):**
- Per-node retry with exponential backoff (WF-06 is 90% done -- existing `retry_max` and `retry_backoff_seconds` fields)
- DAG validation with cycle detection
- In-memory execution tracking with DB persistence
- SSE streaming for execution monitoring
- Node config panel with per-type forms

## Open Questions

1. **Should approval gate notifications use a new notification system or the existing SSE mechanism?**
   - What we know: WF-03 mentions "Slack/email notification". The codebase has no Slack or email integration.
   - What's unclear: Whether to build notification infrastructure or scope it to SSE-only for Phase 7.
   - Recommendation: Scope to SSE + in-UI notification for Phase 7. Add a `notification_config` field to the approval node for future Slack/email integration.

2. **How should "cheap vs expensive model routing" (WF-04) determine diff size thresholds?**
   - What we know: WF-04 says "cheap model for small diffs, expensive for large". The `OrchestrationService` currently uses a fixed fallback chain order.
   - What's unclear: The exact threshold logic (line count? token count? file count?).
   - Recommendation: Add a `routing_rules` config to workflow agent nodes with a simple `diff_size_threshold` field. Below threshold -> first chain entry (cheap), above -> last chain entry (expensive).

3. **Should conditional branch nodes support more than binary (true/false) branches?**
   - What we know: WF-05 mentions "pass/fail/skip" as three branching scenarios. The current ConditionalNode has only `true` and `false` handles.
   - What's unclear: Whether a third "skip" handle is needed or if "skip" means the node itself is skipped.
   - Recommendation: Keep binary branching (true/false) for the conditional node. "Skip" is handled by the existing `skipped_nodes` set when a node's predecessor fails. Add a `condition_branch` node type if ternary branching is needed.

## Sources

### Primary (HIGH confidence)
- [Python graphlib docs](https://docs.python.org/3/library/graphlib.html) -- TopologicalSorter API, get_ready()/done() protocol
- [VueFlow Official Docs](https://vueflow.dev/) -- Custom nodes, drag-and-drop, handles, edge labels
- [VueFlow Drag & Drop Example](https://vueflow.dev/examples/dnd.html) -- Canonical DnD pattern
- Codebase: `backend/app/services/workflow_execution_service.py` -- Existing DAG engine (989 lines)
- Codebase: `backend/app/services/team_execution_service.py` lines 589-691 -- Approval gate pattern
- Codebase: `backend/app/services/orchestration_service.py` -- Fallback chain routing
- Codebase: `frontend/src/components/workflow/WorkflowCanvas.vue` -- VueFlow canvas integration
- Codebase: `frontend/src/composables/useWorkflowCanvas.ts` -- Canvas state management

### Secondary (MEDIUM confidence)
- [VueFlow Best Practices](https://dev.to/monsterpi13/vue-flow-quickstart-and-best-practices-482k) -- Community patterns
- [DAG Workflow Engine Design](https://bugfree.ai/knowledge-hub/designing-a-dag-based-workflow-engine-from-scratch) -- Architecture patterns
- [Workflow Orchestration State 2025](https://www.pracdata.io/p/state-of-workflow-orchestration-ecosystem-2025) -- Industry survey of patterns

### Tertiary (LOW confidence)
- [Torra Community Edition](https://github.com/orgs/vuejs/discussions/13717) -- VueFlow-based AI workflow builder showcase (2025)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries already installed and in use; no new dependencies
- Architecture: HIGH -- Extending existing patterns with proven codebase precedents
- Paper recommendations: HIGH -- Based on working code in the same repository, not theoretical papers
- Pitfalls: HIGH -- Identified from actual codebase patterns and documented concerns

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (30 days -- stable patterns, all based on existing codebase)
