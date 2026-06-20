# Loop Builder UI — Implementation Plan

> REQUIRED SUB-SKILL: subagent-driven-development / executing-plans. Steps use `- [ ]`.

**Goal:** A frontend Loop Builder modal that composes a LoopSpec and launches a goal-loop/ralph session via the existing engine + routes (no backend changes).

**Architecture:** static templates → a focus-trapped modal form bound to the existing `GoalLoopConfig`/`RalphConfig` TS types → builds the POST body for `grdApi.createSession`/`createRalphSession`. Hosted from `PlanningCommandBar` on `ProjectPlanningPage`; the launched session renders via the sp3 `LoopTracePanel`.

**Tech:** Vue 3 + TS, Vitest + @vue/test-utils, vue-i18n (en/ko/ja/zh), house CSS vars; reuse `useFocusTrap`, `useToast`, `ApiError`.

**Spec:** `docs/superpowers/specs/2026-06-20-loop-builder-design.md`

---

## Authoritative launch contract (verified against the live routes — DO NOT deviate)

The two launch routes have **different** requirements. Mirror `ProjectSessionPanel.vue:586-676` exactly.

**ralph (`agentic_task` template)** — `grdApi.createRalphSession(projectId, req)` where
`req = { cwd?, ralph_config: { max_iterations, completion_promise, task_description, no_progress_threshold } }`.
The ralph handler builds its own command and resolves accounts itself → **no `cmd`, no `account_id`, no `yolo_mode`**. All four `ralph_config` fields are required (non-optional in `RalphConfig`).

**goal_loop (`eval_refine` / `custom` templates)** — `grdApi.createSession(projectId, req)`. The `create_session` route **requires a non-empty `cmd` list** and (unless `yolo_mode`) an `account_id` in the project's allowed-accounts whitelist — a missing `cmd` is 400, a missing/un-whitelisted account is 400/403. Build exactly:
```ts
const GOAL_LOOP_CMD = ['claude','--print','--input-format','stream-json','--output-format','stream-json','--verbose','--include-hook-events','--include-partial-messages'];
const req: CreateSessionRequest = {
  cmd: GOAL_LOOP_CMD,
  execution_type: 'goal_loop',
  execution_mode: 'interactive',
  stream_json: true,
  use_pty: false,
  cwd,                                   // when provided
  ...(yolo ? { yolo_mode: true } : { account_id: selectedAccountId }),
  goal_loop_config: <stripped GoalLoopConfig>,  // drop undefined / empty-string optionals so backend defaults apply
};
```
**Accounts:** on mount call `grdApi.listAllowedAccounts(projectId)` → `{ allowed_accounts: { account_id, created_at }[] }`. Render an account `<select>` (default = first allowed) + a `yolo` toggle, shown **only for goal_loop templates**. If not yolo and no allowed account → disable Launch with a hint toast (don't POST a guaranteed 403). Ralph templates hide both controls.

---

## Task 1: Loop templates

**Files:** Create `frontend/src/const/loopTemplates.ts`; Test `frontend/src/const/__tests__/loopTemplates.test.ts`

- [ ] **Step 1: Failing test**
```typescript
// loopTemplates.test.ts
import { LOOP_TEMPLATES } from '../loopTemplates';
import { describe, it, expect } from 'vitest';
describe('LOOP_TEMPLATES', () => {
  it('has the three patterns with correct execution types', () => {
    const ids = LOOP_TEMPLATES.map(t => t.id);
    expect(ids).toEqual(['agentic_task', 'eval_refine', 'custom']);
    expect(LOOP_TEMPLATES.find(t => t.id === 'agentic_task')!.executionType).toBe('ralph_loop');
    expect(LOOP_TEMPLATES.find(t => t.id === 'eval_refine')!.executionType).toBe('goal_loop');
    expect(LOOP_TEMPLATES.find(t => t.id === 'custom')!.executionType).toBe('goal_loop');
  });
  it('eval_refine seeds an llm_judge quality gate + min_confidence', () => {
    const t = LOOP_TEMPLATES.find(x => x.id === 'eval_refine')!;
    expect((t.config as any).quality_gate.kind).toBe('llm_judge');
    expect((t.config as any).quality_gate.min_confidence).toBeGreaterThan(0);
  });
});
```
- [ ] **Step 2:** `cd frontend && npx vitest run src/const/__tests__/loopTemplates.test.ts` → FAIL (module missing).
- [ ] **Step 3: Implement** — read the `GoalLoopConfig`/`RalphConfig` types from `src/services/api/grd.ts`, then:
```typescript
// frontend/src/const/loopTemplates.ts
import type { GoalLoopConfig, RalphConfig } from '../services/api/grd';
export type LoopExecutionType = 'goal_loop' | 'ralph_loop';
export interface LoopTemplate {
  id: 'agentic_task' | 'eval_refine' | 'custom';
  labelKey: string;        // loopBuilder.tpl.<id>.label
  descKey: string;         // loopBuilder.tpl.<id>.desc
  executionType: LoopExecutionType;
  config: Partial<GoalLoopConfig> | Partial<RalphConfig>;
}
export const LOOP_TEMPLATES: LoopTemplate[] = [
  { id: 'agentic_task', labelKey: 'loopBuilder.tpl.agentic_task.label', descKey: 'loopBuilder.tpl.agentic_task.desc',
    executionType: 'ralph_loop',
    config: { task_description: '', max_iterations: 50, no_progress_threshold: 3, completion_promise: 'COMPLETE' } },
  { id: 'eval_refine', labelKey: 'loopBuilder.tpl.eval_refine.label', descKey: 'loopBuilder.tpl.eval_refine.desc',
    executionType: 'goal_loop',
    config: { goal: '', max_iterations: 20, ouroboros: true, context_policy: 'carry',
      quality_gate: { kind: 'llm_judge', min_confidence: 0.7 }, sandbox: 'isolated' } },
  { id: 'custom', labelKey: 'loopBuilder.tpl.custom.label', descKey: 'loopBuilder.tpl.custom.desc',
    executionType: 'goal_loop', config: { goal: '', max_iterations: 20 } },
];
```
- [ ] **Step 4:** test PASS.
- [ ] **Step 5:** `git commit -m "feat(loops): Loop Builder templates (3 patterns)"`

---

## Task 2: i18n `loopBuilder.*` (4 locales)

**Files:** Modify `frontend/src/locales/{en,ko,ja,zh}.json`

- [ ] **Step 1:** Add a `loopBuilder` namespace to en.json (key-identical translations in ko/ja/zh). Keys: `title`, `subtitle`, `pickTemplate`, `tpl.agentic_task.label/desc`, `tpl.eval_refine.label/desc`, `tpl.custom.label/desc`, section headers `secGoal`/`secExit`/`secGate`/`secState`/`secJudge`, `goal`, `task`, `checkCmd`, `gateKind`, `metricName`, `threshold`, `comparator`, `rubric`, `judgeVersion`, `minConfidence`, `humanGate`, `gateEveryN`, `account`, `yolo`, `noAccount`, `launch`, `cancel`, `goalRequired`, `accountRequired`, `launched`, `launchFailed`. (Reuse `loopConfig.*` for tokenBudget/contextPolicy/sandbox/stagnation labels rather than duplicating.)
- [ ] **Step 2:** verify all four files parse + are key-identical (a quick node script comparing keys).
- [ ] **Step 3:** `git commit -m "feat(loops): loopBuilder i18n (en/ko/ja/zh)"`

---

## Task 3: `LoopBuilder.vue` modal

**Files:** Create `frontend/src/components/grd/LoopBuilder.vue`; Test `frontend/src/components/grd/__tests__/LoopBuilder.test.ts`

- [ ] **Step 1: Failing test** (mirror `LoopTracePanel.test.ts` harness)
```typescript
// LoopBuilder.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import en from '../../../locales/en.json';
const calls = vi.hoisted(() => ({
  createSession: vi.fn().mockResolvedValue({ session_id: 'gls-1', pid: 1, status: 'active' }),
  createRalphSession: vi.fn().mockResolvedValue({ session_id: 'ralph-1', pid: 1, status: 'active' }),
  listAllowedAccounts: vi.fn().mockResolvedValue({ allowed_accounts: [{ account_id: 'acc-1', created_at: '' }] }),
}));
vi.mock('../../../services/api', async (o) => ({ ...(await o<any>()), grdApi: calls, ApiError: class extends Error {} }));
import LoopBuilder from '../LoopBuilder.vue';
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { loopBuilder: en.loopBuilder, loopConfig: en.loopConfig } } as never });
const mountP = (props = {}) => mount(LoopBuilder, { props: { projectId: 'p', cwd: '/w', ...props }, global: { plugins: [i18n], provide: { showToast: vi.fn() } } });
beforeEach(() => vi.clearAllMocks());

describe('LoopBuilder', () => {
  it('launch is disabled until goal is set, then POSTs createSession for a goal-loop template', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-eval_refine"]').trigger('click');
    expect(w.find('[data-testid="lb-launch"]').attributes('disabled')).toBeDefined();
    await w.find('[data-testid="lb-goal"]').setValue('make tests pass');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    expect(calls.createSession).toHaveBeenCalledTimes(1);
    const [pid, req] = calls.createSession.mock.calls[0];
    expect(pid).toBe('p');
    expect(req.cmd[0]).toBe('claude');           // route requires a non-empty cmd
    expect(req.execution_type).toBe('goal_loop');
    expect(req.account_id).toBe('acc-1');         // first allowed account auto-selected
    expect(req.goal_loop_config.goal).toBe('make tests pass');
    expect(req.goal_loop_config.quality_gate.kind).toBe('llm_judge');
    expect(w.emitted('launched')![0]).toEqual(['gls-1']);
  });
  it('agentic_task template POSTs createRalphSession with ralph_config', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-agentic_task"]').trigger('click');
    await w.find('[data-testid="lb-task"]').setValue('build the widget');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    expect(calls.createRalphSession).toHaveBeenCalledTimes(1);
    const [, req] = calls.createRalphSession.mock.calls[0];
    expect(req.ralph_config.task_description).toBe('build the widget');
    expect(req.ralph_config.no_progress_threshold).toBe(3);
  });
  it('human_gate=every_n includes mode+n in the goal_loop_config', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-custom"]').trigger('click');
    await w.find('[data-testid="lb-goal"]').setValue('g');
    await w.find('[data-testid="lb-human-gate"]').setValue('every_n');
    await w.find('[data-testid="lb-gate-n"]').setValue('3');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    const [, req] = calls.createSession.mock.calls[0];
    expect(req.goal_loop_config.human_gate).toEqual({ mode: 'every_n', n: 3 });
  });
});
```
- [ ] **Step 2:** `cd frontend && npx vitest run src/components/grd/__tests__/LoopBuilder.test.ts` → FAIL.
- [ ] **Step 3: Implement** `LoopBuilder.vue` per the spec §2b **and the "Authoritative launch contract" block above**. Read `GrdSettings.vue` + `AddTriggerModal.vue` for the card/modal/focus-trap/toast house style and `ProjectDiscoveryModal.vue` for the modal-overlay shell. Mirror `ProjectSessionPanel.vue:586-676` for the exact goal_loop `cmd`/flags. On mount, `grdApi.listAllowedAccounts(projectId)` → keep `allowedAccounts` + `selectedAccountId` (default first). Required `data-testid`s: `tpl-<id>` (template cards), `lb-goal`, `lb-task`, `lb-check-cmd`, `lb-gate-kind`, `lb-human-gate`, `lb-gate-n`, `lb-account` (goal_loop only), `lb-yolo` (goal_loop only), `lb-launch`, `lb-cancel`. `launch()` builds the payload per the contract (ralph → `createRalphSession`; goal_loop → `createSession` with `cmd`/`execution_mode`/`stream_json`/`use_pty` + `account_id`-or-`yolo_mode`; strip empty optionals from `goal_loop_config`), emits `launched(session_id)` + `close`, toasts on `ApiError`. Launch disabled until goal/task non-empty **and** (ralph, or yolo, or an account is selected).
- [ ] **Step 4:** test PASS; `npm run build` (vue-tsc) clean.
- [ ] **Step 5:** `git commit -m "feat(loops): LoopBuilder modal — compose a LoopSpec + launch"`

---

## Task 4: Host wiring (PlanningCommandBar + ProjectPlanningPage)

**Files:** Modify `frontend/src/components/grd/PlanningCommandBar.vue`, `frontend/src/views/ProjectPlanningPage.vue`; extend `frontend/src/components/grd/__tests__/PlanningCommandBar.test.ts` if present.

- [ ] **Step 1:** Read both files for the existing command/emit pattern. Add a "Build Loop" command to `PlanningCommandBar` that `emit`s e.g. `open-loop-builder` (match the bar's existing emit style).
- [ ] **Step 2:** In `ProjectPlanningPage.vue`: add `const showLoopBuilder = ref(false)`; handle the bar's event to set it true; render `<LoopBuilder v-if="showLoopBuilder" :project-id="projectId" :cwd="..." @close="showLoopBuilder=false" @launched="onLoopLaunched" />`. `onLoopLaunched(sessionId)` opens the session panel (reuse the existing `showSessionPanel` + session-select wiring so the sp3 `LoopTracePanel` shows the new loop).
- [ ] **Step 3:** `npm run build` clean; if a PlanningCommandBar test exists, assert the new command emits the event.
- [ ] **Step 4:** `git commit -m "feat(loops): host LoopBuilder from the planning command bar"`

---

## Task 5: Full verification
- [ ] `cd frontend && npm run build` → clean.
- [ ] `cd frontend && npm run test:run` → 7-failure baseline + the new loopTemplates/LoopBuilder tests passing; no NEW failures.
- [ ] Finish the branch (PR).

## Self-review
Spec §2a→T1, §2e→T2, §2b→T3, §2c+2d→T4, §2f→T3 test, verification→T5. Types bound to the real `GoalLoopConfig`/`QualityGate`/`LoopGate`/`RalphConfig`. `executionType` is the single goal_loop-vs-ralph switch (T1 data → T3 launch → test). No backend changes.
