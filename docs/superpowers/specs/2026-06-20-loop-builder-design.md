# Loop Builder UI — Design Spec

**Milestone:** v0.6.x post-MVP loop slice (after the unified-loops MVP #232/#233/#234 + hardening #235).
**Date:** 2026-06-20
**Approved direction:** a frontend Loop Builder modal that composes a `LoopSpec` and launches a session, reusing the existing engine + routes. **No backend changes.**

## 1. Recon facts (verified)

- Launch API already exists: `POST /{project_id}/sessions` with `goal_loop_config` (goal-loop) and `POST /{project_id}/sessions/ralph` with `ralph_config` (`grd_routes.py:890`, `:1549`). **No new endpoint needed.** ⚠️ `create_session` **requires a non-empty `cmd` list** (400 otherwise) and (unless `yolo_mode`) an allowlisted `account_id` (400/403 otherwise); the ralph route requires neither (its handler builds its own cmd + accounts). See the plan's "Authoritative launch contract".
- Allowed-accounts API exists: `grdApi.listAllowedAccounts(projectId)` → `{ allowed_accounts: { account_id, created_at }[] }`.
- Frontend client + types exist (`frontend/src/services/api/grd.ts`): `grdApi.createSession(projectId, CreateSessionRequest)`, `grdApi.createRalphSession(projectId, CreateRalphSessionRequest)`; interfaces `GoalLoopConfig` (incl. the v0.6 fields), `QualityGate`, `LoopGate`, `RalphConfig`, `CreateSessionRequest{execution_type, goal_loop_config}`.
- Host: `ProjectPlanningPage.vue` + `PlanningCommandBar.vue` (add a command) → open a modal, mirroring `AddTriggerModal`/`ProjectDiscoveryModal` (focus-trap + toast). Active session then renders via the sp3 `LoopTracePanel`.
- Form patterns: `GrdSettings.vue` (cards/toggles), `AddTriggerModal.vue` (modal + `useFocusTrap` + `useToast` + `ApiError`). i18n: `loopConfig.*` exists; tests mock `grdApi` (see `LoopTracePanel.test.ts`).

## 2. Deliverables (all frontend)

### 2a. `const/loopTemplates.ts` — three presets
Pure data + a `LoopTemplate` type. Each template = `{ id, label, description, executionType: 'goal_loop'|'ralph_loop', config }` where config is a partial `GoalLoopConfig` or `RalphConfig`:
- **agentic_task** → `ralph_loop`, `RalphConfig{ task_description:'', max_iterations:50, no_progress_threshold:3, completion_promise:'COMPLETE' }`.
- **eval_refine** → `goal_loop`, `GoalLoopConfig{ goal:'', max_iterations:20, ouroboros:true, context_policy:'carry', quality_gate:{kind:'llm_judge', min_confidence:0.7}, sandbox:'isolated' }`.
- **custom** → `goal_loop`, `GoalLoopConfig{ goal:'', max_iterations:20 }` (blank, all fields exposed).

### 2b. `components/grd/LoopBuilder.vue` — the modal
Props `{ projectId: string; cwd?: string }`; emits `close`, `launched(sessionId)`. Uses `useFocusTrap` + `useToast` + `useI18n`. Sections:
1. **Template picker** — three cards; selecting one calls `applyTemplate(t)` which resets the form refs to the template's config + sets `executionType`.
2. **Goal/task** — textarea (`goal` for goal_loop / `task_description` for ralph); `check_cmd` (goal_loop only).
3. **Exit budgets** — `max_iterations`, `max_wall_seconds`, `max_cost_usd`, `max_tokens`, `stagnation_no_progress_for` (number inputs; ralph maps `stagnation_no_progress_for`→`no_progress_threshold`).
4. **Quality gate** (goal_loop only) — `kind` select (test_pass/metric/llm_judge); conditional: metric → `metric_name`+`threshold`+`comparator`; llm_judge → `rubric`+`judge_version`+`min_confidence`; test_pass → (uses check_cmd).
5. **State** — `context_policy` (carry/reset), `sandbox` (isolated/inherit), `human_gate` mode (off/every_n/on_exit) + `n` when every_n.
6. **Judge** (goal_loop only) — `judge_backend_kind` select, `judge_model_override`.
7. **Account** (goal_loop only) — account `<select>` populated on mount from `grdApi.listAllowedAccounts(projectId)` (default = first allowed) + a `yolo` toggle. The `create_session` route requires `account_id` (whitelisted) unless `yolo_mode`. Ralph hides this (its handler resolves accounts itself).
Footer: **Launch** (disabled until goal/task non-empty + numeric fields valid + (ralph, or yolo, or an account selected)) + Cancel.

`launch()`:
- Validate (goal/task required; iters/wall/cost/tokens ≥ 0; `n` ≥ 1 when every_n; goal_loop non-yolo requires a selected account). On invalid → toast + return.
- Build payload **per the live-route contract** (see the plan's "Authoritative launch contract"):
  - ralph → `grdApi.createRalphSession(projectId, { cwd, ralph_config })` (no cmd/account).
  - goal_loop → `grdApi.createSession(projectId, { cmd: GOAL_LOOP_CMD, execution_type:'goal_loop', execution_mode:'interactive', stream_json:true, use_pty:false, cwd, …(yolo ? {yolo_mode:true} : {account_id}), goal_loop_config })` where `GOAL_LOOP_CMD` is the stream-json claude argv from `ProjectSessionPanel.vue:640-660`. Strip undefined/empty-optional `goal_loop_config` fields so the backend `from_legacy_config` defaults apply.
- On success → `emit('launched', sessionId)` + `emit('close')` + success toast; on `ApiError` → error toast.

### 2c. `PlanningCommandBar.vue` — "Build Loop" trigger
Add a command/button that emits an event the page handles to open the Builder. (Match the existing command pattern in the bar.)

### 2d. `ProjectPlanningPage.vue` — host
A `showLoopBuilder` ref; render `<LoopBuilder :project-id :cwd @close @launched>`; on `launched(sessionId)` open the session panel / point the trace at it (reuse the existing `showSessionPanel` + session wiring).

### 2e. i18n `loopBuilder.*` (en/ko/ja/zh, key-identical)
title, subtitle, the 3 template labels+descriptions, section headers (goal/exit/qualityGate/state/judge), field labels (reuse `loopConfig.*` where they exist), launch, cancel, validation toasts, launchedToast, launchFailed.

### 2f. Tests
`components/grd/__tests__/LoopBuilder.test.ts` (mock `grdApi`, mirror `LoopTracePanel.test.ts`): (1) selecting the eval_refine template fills the goal-loop form + shows the quality-gate section; (2) Launch with a goal-loop template POSTs `createSession` with `execution_type:'goal_loop'` + the built `goal_loop_config`; (3) selecting agentic_task switches to ralph and Launch POSTs `createRalphSession` with the `ralph_config`; (4) Launch is disabled with an empty goal and validation blocks it; (5) `human_gate=every_n` includes `{mode:'every_n', n}`.

## 3. Non-goals
- No backend endpoint (reuse `create_session`/`create_ralph_session`).
- Not editing RUNNING loops (that's the sp3 control surface — pause/intervene/gate).
- No cyclic-workflow body kind.
- No persistence of "saved loop configs" (templates are static for v1).

## 4. Risks & mitigations
- **Config-heavy form** → templates pre-fill + conditional sections (quality-gate/judge only for goal_loop; gate-`n` only for every_n) keep it scannable.
- **Payload shape drift** → bind directly to the existing `GoalLoopConfig`/`RalphConfig` TS types; strip empty optionals so backend defaults apply; the test asserts the exact POST body.
- **ralph vs goal_loop divergence** → the template's `executionType` is the single switch deciding which API + config shape is built.

## 5. Verification
`just build` (vue-tsc + vite) clean; `npm run test:run` at the 7-failure baseline + the new LoopBuilder test; i18n parity across 4 locales.
