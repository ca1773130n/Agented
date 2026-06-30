# Phase 23: Stackable Policy / Governance Engine - Research

**Researched:** 2026-06-30
**Domain:** Backend policy/governance engine (Litestar + raw SQLite + subprocess.Popen harness + SSE), Vue 3 frontend
**Confidence:** HIGH (codebase anchors verified directly; no external papers needed — this is a build-on-existing-infra phase)

## Summary

Phase 23 adds ONE declarative ALLOW/DENY/ASK policy layer stacked across server -> team -> session
scopes, evaluated session-first with DENY short-circuit, that subsumes today's scattered controls
(goal_loop exit-ladder budgets, bot-security/bot-pr-review safety checks) and enforces at action
boundaries with an ASK approval card over SSE. The good news: **nearly every primitive this phase
needs already exists in the codebase** and the work is mostly consolidation + a thin new
PolicyService/table/router/middleware/UI, not green-field invention.

The single most important finding: **the ASK-over-SSE round-trip is already implemented** for
goal-loop human-gates. `goal_loop_runner._await_gate()` broadcasts `goal_loop_awaiting_human`,
blocks on `state.gate_decision` (polling `_PAUSE_POLL_SECONDS`, bounded by `max_wall_seconds`,
always responsive to `stop_event`), and is resolved by `submit_gate_decision(session_id, decision,
message)` exposed via the `loop_gate_decision` route (`grd_routes.py:1441`). The policy ASK verdict
should reuse this exact mechanism (a new `policy_awaiting_decision` event + `submit_policy_decision`)
rather than hand-rolling a blocking round-trip. Similarly `BudgetService.check_budget`
(`budget_service.py:340`) already returns a verdict-shaped dict (`block`/`soft_limit_warning`/`allow`
with hard/soft thresholds) — it is the template for `PolicyService.evaluate()` and the `cost_budget`
builtin maps onto it almost 1:1.

**Primary recommendation:** Build a `PolicyService.evaluate(scope_ctx, action) -> PolicyVerdict`
that stacks rows from a new `policies` table (next migration **176**), evaluating session scope
first and short-circuiting on the first DENY; route the four builtins through it; hook enforcement
at the `ExecutionService` Popen boundary (`execution_service.py:767`) and a `goal_loop_runner`
human-gate; reuse the existing `_await_gate`/`submit_gate_decision`/SSE-broadcast machinery for ASK;
ship `/admin/policies` CRUD mirroring `budgets_router`, a `PolicyMiddleware` mirroring the existing
`ASGIMiddleware` subclasses, a policy editor component, and en/ko/ja/zh key-identical catalogs.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase (`/grd:discuss-phase` was not run). The ROADMAP success criteria
are LOCKED and treated as the source of truth. Standing project rules apply (below).

### Locked Decisions (from ROADMAP success criteria + standing rules)
- **SC1:** `policies` store + `PolicyVerdict` (ALLOW/DENY/ASK) evaluator stacks server -> team ->
  session; session (stricter) evaluated FIRST; short-circuit on DENY; anchored on SESSION scope.
  Unit test: session DENY short-circuits a server ALLOW.
- **SC2:** Builtins: `cost_budget` (hard `max_cost_usd` + soft `ask_thresholds_usd`),
  `max_tool_calls_per_session`, `ask_on_os_tools` (approve before shell/file-write),
  `enforce_sandbox`; goal_loop exit-ladder budgets + bot-security/bot-pr-review checks route through.
- **SC3:** Enforcement at action boundaries in `ExecutionService` + `goal_loop_runner.py` human-gate
  hook; ASK surfaces an approval card over SSE, blocks until resolved.
- **SC4:** `/admin/policies` CRUD + `middleware.py` policy middleware + frontend policy editor +
  `budgets.ts` cost-cap verdicts; en/ko/ja/zh key-identical.
- **SC5:** End-to-end test: configured DENY blocks; ASK pauses for approval card and resumes on
  approve; ALLOW passes through.
- **SC6:** House gates: `just build`; backend pytest (watchdog/targeted-substitution disclosed if the
  known ~40-48% hang hits); frontend no-new-failures.
- **HARD session-not-bot rule:** orchestrate SESSIONS across project/super-agent/team/workflow/
  trigger; NEVER anchor governance on triggers/bots alone. Policy scope MUST anchor on session id.
- Raw SQLite, no ORM; numbered migrations applied via the version-bucketed registry.
- Entity IDs prefixed-random (use `pol-` for policy rows).
- Litestar canonical; gunicorn UvicornWorker workers=1 (in-process state is safe — single worker).
- i18n: every UI string in all four locales, key-identical.

### Claude's Discretion
- Exact `policies` column set and whether `params` is one JSON blob vs typed columns.
- Whether `PolicyService` is a classmethod service (matches `BudgetService`/`ExecutionService`) or
  instance — recommend **classmethod** for consistency.
- Builtin evaluation: table-driven dispatch dict `{policy_kind: evaluator_fn}`.

### Deferred Ideas (OUT OF SCOPE)
- OS-level sandbox implementation itself (Phase 24 — Phase 23 only ships the `enforce_sandbox`
  *policy flag* that Phase 24 reads).
- Multi-user collaboration governance UI (Phase 25 consumes the engine).
- Per-tool fine-grained allowlists beyond the four builtins.

## Paper-Backed Recommendations

This is an infrastructure-consolidation phase, not a research/ML phase — recommendations are
grounded in **verified codebase anchors** (the strongest evidence available here), not literature.
Each recommendation cites the exact file/line that proves the pattern already exists or where the
hook attaches.

### Recommendation 1: Reuse the existing human-gate round-trip for ASK-over-SSE
**Recommendation:** Implement the ASK verdict by reusing the `_await_gate` blocking pattern, not a
new mechanism.
**Evidence (codebase anchors):**
- `backend/app/services/goal_loop_runner.py:487` `_await_gate(state, session_id, iteration_no,
  gate_reason, *, max_wall_seconds)` — sets `state.awaiting_human=True`, broadcasts
  `goal_loop_awaiting_human`, polls `state.gate_decision` every `_PAUSE_POLL_SECONDS`, aborts on
  `max_wall_seconds`, always honors `stop_event`, broadcasts `goal_loop_gate_resolved` on resolve.
  This is EXACTLY "block the action until resolved (approve/deny round-trip)."
- `goal_loop_runner.py:452` `submit_gate_decision(session_id, decision, message=None)` — the resolver.
- `backend/app_litestar/routes/grd_routes.py:1441` `loop_gate_decision(project_id, session_id, data)`
  -> calls `submit_gate_decision` — the HTTP entry the approval card POSTs to.
- `backend/app/services/project_session_manager.py:1853` `_broadcast(cls, session_id, event_type,
  data)` — the SSE broadcast primitive; there is already an `ask_user_question` SSE event type
  (`project_session_manager.py:135,169,500`) the frontend renders, so a `policy_ask` card has prior art.

**Confidence:** HIGH — verified source. **Caveat:** `_await_gate` is loop-iteration-scoped; the
ExecutionService Popen boundary is not inside the goal loop, so it needs its OWN small await helper
keyed by session_id (same shape, different registry). Plan for two ASK call-sites sharing one
verdict/queue convention.

### Recommendation 2: Model `PolicyService.evaluate` on `BudgetService.check_budget`
**Recommendation:** Return a structured `PolicyVerdict` dict/Struct mirroring the verdict shape
BudgetService already returns.
**Evidence:**
- `backend/app/services/budget_service.py:340` `check_budget(cls, entity_type, entity_id) -> dict`
  returns `{"verdict-ish": ...}` with `block` when `current_spend >= hard_limit`,
  `soft_limit_warning` when `>= soft_limit`, else allow (lines 373-398). `cost_budget` builtin maps
  hard->`max_cost_usd` (DENY) and soft->`ask_thresholds_usd` (ASK) onto this directly.
- `goal_loop_runner.py:574` `max_cost_usd = state.spec.exit.max_cost_usd` and `get_runner_state`
  surfaces `total_cost_usd`/`max_cost_usd`/`max_tokens` (lines 525-528) — the live counters the
  `cost_budget` and `max_tool_calls_per_session` builtins read.

**Confidence:** HIGH — verified source.

### Recommendation 3: Stack server -> team -> session, evaluate session-first, short-circuit DENY
**Recommendation:** `evaluate()` collects matching policy rows for all three scopes, orders
`[session, team, server]`, and returns the FIRST terminal verdict — DENY short-circuits immediately;
ASK collected if no DENY; ALLOW is the default fall-through.
**Evidence:**
- Session is the canonical governance anchor per the standing session-not-bot rule. Sessions carry
  `project_id`/`team_id`: `super_agent_sessions.team_id TEXT REFERENCES teams(id)`
  (`backend/app/db/schema/_core.py:31`); session env injects `AGENTED_SESSION_ID` + `AGENTED_PROJECT_ID`
  (`project_session_manager.py:897-898`). "server" scope = a single sentinel row (no entity id).
- Single gunicorn worker (`workers=1`) means an in-process policy cache is coherent — no cross-worker
  invalidation needed.

**Confidence:** HIGH.

## Standard Stack

### Core (all already in-tree — no new dependencies)
| Component | Where | Purpose | Why Standard |
|-----------|-------|---------|--------------|
| Raw SQLite + `get_connection()` | `backend/app/database.py` | `policies` table storage | Project rule: no ORM |
| Versioned migration registry | `backend/app/db/migrations/v07_features.py` (`VERSIONED_MIGRATIONS`) | add migration **176** | Existing numbered pattern; entry shape `(N, "name", _migrate_N_fn)` |
| Classmethod service | `BudgetService`/`ExecutionService` | `PolicyService.evaluate/crud` | Matches existing services |
| `ASGIMiddleware` subclass | `backend/app_litestar/middleware.py` | `PolicyMiddleware` | All middleware subclass `ASGIMiddleware` |
| `Router(path=..., route_handlers=[...])` | `backend/app_litestar/routes/budgets.py:292` | `policies_router` | Mirror `budgets_router`; register in `main.py` |
| `ProjectSessionManager._broadcast` | `project_session_manager.py:1853` | SSE ASK card | Existing SSE primitive |
| `apiFetch` + barrel | `frontend/src/services/api/client.ts`, `index.ts` | `policies.ts` API module | Per-domain module convention |

### No external libraries to install. No `pip install` / `npm install` needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| Reuse `_await_gate` round-trip | OPA/Cedar policy engine lib | External dep, JSON-policy DSL, overkill for 4 builtins + 3 scopes | REJECT — hand-rolled is correct here; only 4 builtins |
| One `params` JSON column | typed columns per builtin | JSON is flexible for heterogeneous builtins | RECOMMEND JSON `params` + a typed `kind` column |

## Architecture Patterns

### Recommended file layout
```
backend/app/services/policy_service.py        # PolicyService: evaluate() + CRUD + builtin dispatch
backend/app/db/migrations/v07_features.py     # add _migrate_176_policies + register (176,"policies",...)
backend/app/db/schema/_core.py                # (optional) add policies to canonical schema
backend/app_litestar/routes/policies.py       # policies_router (/admin/policies CRUD + /decision)
backend/app_litestar/middleware.py            # PolicyMiddleware (ASGIMiddleware subclass)
backend/app_litestar/main.py                  # import + register policies_router (near line 260)
frontend/src/services/api/policies.ts         # policyApi (apiFetch); extend budgets.ts for cost verdicts
frontend/src/services/api/index.ts            # re-export policyApi
frontend/src/components/policy/PolicyEditor.vue (+ PolicyAskCard.vue)
frontend/src/locales/{en,ko,ja,zh}.json       # policy.* namespace, key-identical
```

### Pattern 1: `policies` table schema (recommended)
```sql
-- _migrate_176_policies
CREATE TABLE IF NOT EXISTS policies (
    id          TEXT PRIMARY KEY,            -- 'pol-XXXXXX' prefixed-random
    scope       TEXT NOT NULL,               -- 'server' | 'team' | 'session'
    scope_id    TEXT,                        -- team_id / session_id; NULL for server
    kind        TEXT NOT NULL,               -- 'cost_budget'|'max_tool_calls_per_session'|'ask_on_os_tools'|'enforce_sandbox'|'custom'
    effect      TEXT NOT NULL DEFAULT 'ask', -- 'allow' | 'deny' | 'ask'  (default verdict when matched)
    params      TEXT NOT NULL DEFAULT '{}',  -- JSON: {max_cost_usd, ask_thresholds_usd[], max_tool_calls, ...}
    enabled     INTEGER NOT NULL DEFAULT 1,
    priority    INTEGER NOT NULL DEFAULT 0,  -- tie-break within a scope
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policies_scope ON policies(scope, scope_id, enabled);
CREATE INDEX IF NOT EXISTS idx_policies_kind  ON policies(kind, enabled);
```
**When to use:** one row per policy instance; `evaluate()` queries by scope+scope_id.

### Pattern 2: `PolicyVerdict` evaluator shape (stacking + short-circuit)
```python
# backend/app/services/policy_service.py  (Source pattern: budget_service.py:340-398)
from typing import Literal, Optional
# PolicyVerdict: {"decision": "allow"|"deny"|"ask", "policy_id": str|None,
#                 "kind": str|None, "reason": str, "scope": str|None}

class PolicyService:
    # builtin dispatch: kind -> evaluator(params, action_ctx) -> ("allow"|"deny"|"ask", reason)
    _BUILTINS = {}  # populated below: cost_budget, max_tool_calls_per_session, ask_on_os_tools, enforce_sandbox

    @classmethod
    def evaluate(cls, *, session_id, team_id=None, action: dict) -> dict:
        # session (stricter) FIRST, then team, then server  -> first DENY short-circuits
        ask_verdict = None
        for scope, sid in (("session", session_id), ("team", team_id), ("server", None)):
            for row in cls._rows_for(scope, sid):              # enabled rows, ORDER BY priority DESC
                decision, reason = cls._eval_row(row, action)  # builtin dispatch or row.effect
                if decision == "deny":
                    return {"decision": "deny", "policy_id": row["id"], "kind": row["kind"],
                            "reason": reason, "scope": scope}     # SHORT-CIRCUIT
                if decision == "ask" and ask_verdict is None:
                    ask_verdict = {"decision": "ask", "policy_id": row["id"], "kind": row["kind"],
                                   "reason": reason, "scope": scope}
        return ask_verdict or {"decision": "allow", "policy_id": None, "kind": None,
                               "reason": "no matching deny/ask", "scope": None}
```
This satisfies SC1's unit test (session DENY short-circuits server ALLOW): a session-scope DENY row
returns before the server loop iteration runs.

### Pattern 3: Builtin set (SC2)
- `cost_budget`: read live `total_cost_usd` (goal loop: `get_runner_state`; executions: `BudgetService`).
  `>= max_cost_usd` -> DENY; crossing any `ask_thresholds_usd[]` -> ASK; else ALLOW. Mirror
  `budget_service.py:373-398`.
- `max_tool_calls_per_session`: counter per session; `>= max_tool_calls` -> DENY.
- `ask_on_os_tools`: action.kind in {shell, file_write} -> ASK (approve before shell/file-write).
  Routes through the ExecutionService Popen boundary + the existing `ask_user_question` precedent.
- `enforce_sandbox`: returns a flag/ALLOW with `params.require_sandbox=True` that Phase 24 reads; in
  Phase 23 it is a stored flag + a DENY if a non-sandboxed launch is attempted while set (inert until 24).

### Anti-Patterns to Avoid
- **Anchoring policy on `trigger_id`/`bot-*`:** violates the HARD session-not-bot rule. Route
  bot-security/bot-pr-review THROUGH the session-scoped policy layer; do not key policies on bot ids.
- **A second blocking mechanism for ASK:** reuse `_await_gate`'s shape; don't invent a new poll loop.
- **Per-worker cache invalidation logic:** unnecessary — `workers=1`. A simple in-process cache with
  invalidate-on-write is sufficient.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ASK approve/deny round-trip | new blocking queue | `_await_gate` + `submit_gate_decision` shape (`goal_loop_runner.py:452,487`) | already bounded, stop-aware, SSE-wired |
| SSE event delivery | new transport | `ProjectSessionManager._broadcast` (`:1853`) + `ask_user_question` precedent | existing queue-per-subscriber |
| Cost verdict math | new logic | `BudgetService.check_budget` (`:340`) | hard/soft threshold logic exists |
| Migration apply/version tracking | new runner | `VERSIONED_MIGRATIONS` registry + `_runner.py` | numbered, idempotent, tested |
| HTTP CRUD wiring | bespoke handlers | `budgets_router` (`:292`) as template | identical Router pattern |
| Frontend fetch/auth | new client | `apiFetch` from `client.ts` | X-API-Key + barrel convention |

**Key insight:** This phase is 80% wiring existing primitives together under one PolicyService.
The genuinely new code is: the `policies` table, `PolicyService.evaluate` (~80 lines), two
enforcement hook call-sites, one new SSE event + await helper, one router, one middleware, one Vue
editor + ask-card, and four locale namespaces.

## Common Pitfalls

### Pitfall 1: ASK at the Popen boundary blocks a daemon thread
**What goes wrong:** ExecutionService launches via `subprocess.Popen` at `execution_service.py:767`
and reads stdout/stderr on daemon threads. A naive blocking ASK could deadlock streaming.
**How to avoid:** Evaluate the policy BEFORE `Popen` (lines ~755-767, after `cmd`/`proc_env` are
built but before launch). The await helper blocks the launching call, not the stream reader threads.
For per-tool ASK (`ask_on_os_tools`) within a running session, surface via SSE and gate the next
action, not the live pipe. **Warning sign:** SSE stops flowing while awaiting.

### Pitfall 2: Stacking order inverted
**What goes wrong:** Evaluating server-first lets a permissive server ALLOW pre-empt a strict session
DENY. **How to avoid:** Iterate `[session, team, server]`; DENY short-circuits. SC1's unit test is
the guard. **Warning sign:** the SC1 test fails.

### Pitfall 3: `max_wall_seconds` unbounded ASK wait hangs a session
**What goes wrong:** An ASK that never resolves holds the action forever. **How to avoid:** Copy
`_await_gate`'s bounded wait — return a default (recommend `deny` on timeout for policy ASK, vs the
goal-gate's `abort`) after a configurable `max_wall_seconds`; always honor `stop_event`.

### Pitfall 4: Locale key drift breaks `just build` / frontend tests
**What goes wrong:** Adding `policy.*` keys to `en.json` only. **How to avoid:** add the identical
key set to en/ko/ja/zh in the same change (standing i18n rule).

### Pitfall 5: bot-security/bot-pr-review double-governed
**What goes wrong:** Leaving the old inline safety checks AND adding policy routing double-runs them.
**How to avoid:** Route the existing checks (`audit_service.py:161,259` reference `bot-security`;
`PREDEFINED_TRIGGERS` in `backend/app/db/triggers.py:28-43`) through the policy layer and remove the
now-duplicated inline gate, or make the inline gate delegate to `PolicyService.evaluate`.

## Experiment Design

Not an ML phase — "experiment design" = the test matrix that proves SC1-SC5.

**Independent variables:** policy scope (server/team/session), effect (allow/deny/ask), builtin kind.
**Dependent variable:** the `PolicyVerdict.decision` and whether the action proceeded/blocked/paused.
**Controlled:** single session id; isolated DB (`isolated_db` fixture).

**Test matrix (maps to success criteria):**
1. **Stacking + short-circuit (SC1):** seed server ALLOW + session DENY -> `evaluate` returns `deny`,
   `scope=="session"`. Also: session ASK + server ALLOW -> `ask`.
2. **Builtin evaluators (SC2):** one unit test per builtin — `cost_budget` (spend < soft -> allow;
   crosses `ask_thresholds_usd` -> ask; `>= max_cost_usd` -> deny), `max_tool_calls_per_session`
   (n+1 -> deny), `ask_on_os_tools` (shell/file_write action -> ask), `enforce_sandbox` (flag set +
   non-sandbox launch -> deny/flag).
3. **Enforcement + ASK-blocks-until-resolved (SC3):** mock the ExecutionService Popen boundary; a DENY
   verdict prevents `Popen`; an ASK blocks until `submit_policy_decision` resolves, then proceeds on
   approve / aborts on deny (mirror existing `_await_gate` tests in `test_*goal_loop*`).
4. **Route/middleware/component (SC4):** `/admin/policies` CRUD round-trip (TestClient; spy on
   `module.logger.warning` per the Litestar caplog note); middleware attaches verdict to request
   context; `PolicyEditor.vue` + `PolicyAskCard.vue` Vitest mount; locale parity assertion.
5. **End-to-end (SC5):** drive a real session — configured DENY blocks; ASK pauses then resumes on
   approve; ALLOW passes through.

**Statistical rigor:** deterministic functional tests, no runs/CIs needed.

### Recommended Metrics
| Metric | Why | How |
|--------|-----|-----|
| verdict correctness | core invariant | assert `decision`/`scope`/`policy_id` |
| short-circuit proof | SC1 | assert server-scope evaluator not consulted after session DENY |
| ASK latency-to-resolve | SC3 | assert blocked until `submit_policy_decision`, bounded by `max_wall_seconds` |

## Verification Strategy

| Item | Tier | Rationale |
|------|------|-----------|
| `evaluate()` stacking/short-circuit | Level 1 (Sanity) | pure function, immediate unit test |
| each builtin evaluator | Level 1 (Sanity) | table-driven unit tests |
| `policies` migration 176 applies | Level 1 | `test_migration_176_policies` (mirror `test_migration_175_*`) |
| `/admin/policies` CRUD | Level 2 (Proxy) | TestClient round-trip |
| ASK-blocks-until-resolved | Level 2 (Proxy) | mocked Popen + decision submit |
| frontend editor + ask-card | Level 2 | Vitest mount + locale parity |
| end-to-end real-session ALLOW/DENY/ASK (SC5) | Level 3 (Deferred) | needs full session pipeline |
| house gates (just build / pytest / frontend) | Level 3 | full integration; watchdog procedure for the known pytest hang |

**Level 1 always-include:** SC1 stacking-order test; one evaluator test per builtin; migration-176
apply/idempotency test.
**Level 2 proxy:** CRUD + middleware + ASK-round-trip with mocked Popen.
**Level 3 deferred:** SC5 real-session drive + the three house gates (pytest under the ~12-min
watchdog; on the known ~40-48% hang, run a targeted set covering policy + execution/streaming/harness
regressions and disclose the substitution per CLAUDE.md).

## Production Considerations

No milestone KNOWHOW.md exists. From CLAUDE.md + project memory:
- **Single worker (workers=1):** in-process policy cache is coherent; invalidate on CRUD write.
- **Backend pytest known hang (~40-48%):** use the watchdog + targeted-substitution disclosure.
- **Frontend baseline:** 7 known pre-existing failures; gate is **no NEW failures**.
- **`just kill` is port-scoped only** — never `pkill vite/node`.
- **session-not-bot is a repeated HARD rule** (told 3+ times in memory) — the reviewer WILL check that
  policies anchor on session scope, not trigger/bot ids. Make this explicit in tests.
- **ASK fail-safe default:** on `max_wall_seconds` timeout for a policy ASK, default to DENY (safer
  for a governance substrate) — distinct from the goal-gate's `abort` default.

## Code Examples

### Verdict at the ExecutionService action boundary (before Popen)
```python
# backend/app/services/execution_service.py  (insert ~line 760, before line 767 Popen)
verdict = PolicyService.evaluate(
    session_id=execution_id,            # or AGENTED_SESSION_ID-keyed session
    team_id=team_id,
    action={"kind": "process_launch", "cmd": cmd, "backend": backend},
)
if verdict["decision"] == "deny":
    raise PolicyDenied(verdict["reason"])
if verdict["decision"] == "ask":
    if PolicyService.await_decision(execution_id, verdict) != "approve":
        raise PolicyDenied("operator denied")
process = subprocess.Popen(cmd, cwd=effective_cwd, ...)   # existing line 767
```

### Reusing the SSE broadcast for the ASK card (Source: project_session_manager.py:1853)
```python
ProjectSessionManager._broadcast(
    session_id, "policy_ask",
    {"policy_id": verdict["policy_id"], "kind": verdict["kind"], "reason": verdict["reason"]},
)
# resolved by a /admin/policies/decision route -> PolicyService.submit_decision(session_id, decision)
# mirrors goal_loop_runner.submit_gate_decision (:452) + grd_routes.loop_gate_decision (:1441)
```

### Frontend API module (Source: budgets.ts + client.ts apiFetch)
```ts
// frontend/src/services/api/policies.ts
import { apiFetch } from './client';
export const policyApi = {
  list: () => apiFetch<{policies: Policy[]}>('/admin/policies'),
  upsert: (p: PolicyInput) => apiFetch<void>('/admin/policies', { method: 'PUT', body: JSON.stringify(p) }),
  remove: (id: string) => apiFetch<void>(`/admin/policies/${id}`, { method: 'DELETE' }),
  decide: (sessionId: string, decision: 'approve'|'deny') =>
    apiFetch<void>('/admin/policies/decision', { method: 'POST', body: JSON.stringify({ session_id: sessionId, decision }) }),
};
// re-export in src/services/api/index.ts
```

## State of the Art

| Old (scattered) | New (consolidated) | Impact |
|-----------------|--------------------|--------|
| goal_loop exit-ladder budgets inline in `goal_loop_runner._run` | `cost_budget` + `max_tool_calls_per_session` builtins via PolicyService | one governance layer; budgets become policy rows |
| bot-security/bot-pr-review inline safety checks (`audit_service.py`, `PREDEFINED_TRIGGERS`) | routed through PolicyService | session-scoped, not bot-anchored |
| per-call human-gate only in goal loop | ASK verdict reusable at any action boundary | ExecutionService gains the same gate |

## Open Questions

1. **Where exactly does a per-tool `ask_on_os_tools` fire for a live (already-running) session?**
   - Known: ExecutionService Popen boundary covers process launch; the existing `ask_user_question`
     SSE event covers harness-emitted permission prompts.
   - Unclear: whether shell/file-write tool calls *inside* a running harness surface a hookable
     boundary in `project_session_manager`'s stream parser (`:413` event parsing) or only post-hoc.
   - Recommendation: planner to confirm whether the harness emits a pre-execution permission event
     the policy can intercept; if not, scope `ask_on_os_tools` to the launch boundary + delegate
     in-session OS-tool gating to the harness's own permission system for Phase 23, tightening in
     Phase 24's sandbox.

2. **`enforce_sandbox` enforcement point in Phase 23 (inert until Phase 24).**
   - Recommendation: store + expose the flag; add a DENY if a non-sandboxed launch is attempted while
     set, but keep it effectively inert (no sandbox exists yet) — Phase 24 wires the real check.

3. **Team-scope id source.** `super_agent_sessions.team_id` exists; confirm executions/goal-loop
   sessions reliably carry `team_id` for the team-scope lookup (else team scope is best-effort).

## Sources

### Primary (HIGH confidence — verified codebase anchors)
- `backend/app/db/migrations/v07_features.py:1771-1797` — migration registry, highest = **175**, next = **176**; entry shape `(N,"name",fn)`
- `backend/app/db/migrations/__init__.py:49` — `VERSIONED_MIGRATIONS` assembly
- `backend/app/services/execution_service.py:767` — `subprocess.Popen` action boundary; `:907` PREDEFINED_TRIGGER_ID
- `backend/app/services/goal_loop_runner.py:452,459,483,487,513-529,574` — `submit_gate_decision`, `_wait_if_paused`, `_gate_due`, `_await_gate`, `get_runner_state`, `max_cost_usd`
- `backend/app/services/budget_service.py:340-398` — `check_budget` verdict shape (hard/soft thresholds)
- `backend/app/services/project_session_manager.py:135,169,500,897-898,1853` — `ask_user_question` SSE precedent, session env keys, `_broadcast`
- `backend/app/db/triggers.py:28-43,158-162` — `PREDEFINED_TRIGGERS` bot-security / bot-pr-review
- `backend/app/services/audit_service.py:161,259` — bot-security audit routing
- `backend/app/db/schema/_core.py:31` — `team_id` FK on sessions
- `backend/app_litestar/middleware.py:107,148,324,383,554` — `ASGIMiddleware` subclass pattern
- `backend/app_litestar/routes/budgets.py:32-292` — Router + handler decorators + `budgets_router`
- `backend/app_litestar/main.py:42,260` — router import + registration
- `backend/app_litestar/routes/grd_routes.py:1441,2101` — `loop_gate_decision` route + registration
- `frontend/src/services/api/budgets.ts`, `client.ts`, `index.ts` — apiFetch + barrel
- `frontend/src/locales/{en,ja,ko,zh}.json` — four-locale catalogs
- `docs/research/omnigent-vs-agented.md` — milestone motivation for the policy substrate

### Secondary / Tertiary
- CLAUDE.md, project memory (MEMORY.md) — standing rules (session-not-bot, pytest hang, i18n, `just kill`).

## Citation Recovery

| Component | Source | Status | Priority |
|-----------|--------|--------|----------|
| n/a (infra phase) | codebase anchors | Resolved | — |

**Unresolved critical dependencies:** 0 — no external papers; all anchors verified in-repo.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every primitive verified in-tree.
- Architecture (table/evaluator/hooks): HIGH — modeled on existing `BudgetService`/`_await_gate`.
- ASK-over-SSE round-trip: HIGH — exact prior art exists (`_await_gate`/`submit_gate_decision`).
- `ask_on_os_tools` in-session boundary: MEDIUM — Open Question 1 (launch boundary confirmed; live
  in-harness tool gating needs planner confirmation).
- Pitfalls: HIGH — derived from verified daemon-thread/SSE/locale realities.

**Research date:** 2026-06-30
**Valid until:** 2026-07-30 (stable internal infra; re-verify migration number if other phases merge first)
