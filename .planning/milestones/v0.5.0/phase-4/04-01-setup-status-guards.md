# Plan 04-01: Wire `useTourMachine` to `/health/setup-status` (Phase 1 followup that unblocks OB-18)

**Phase:** 4 — Core Step Content
**Requirements:** OB-18 (parent step completes when at least one backend account registered), OB-08 (resume from last incomplete step) — also closes the Phase 1 followup
**Depends on:** Phase 1 endpoint (`/health/setup-status`), Phase 3 welcome→tour wiring
**Verification:** sanity (unit tests for the auto-skip walk + the API client)

## Discovery

Steps 1–4's tour metadata is wired:
- `[data-tour="workspace-root"]` → `GeneralSettings.vue:187` (OB-17)
- `[data-tour="add-account-btn"]` → `BackendDetailPage.vue:132` × 4 backend pages (OB-18)
- `[data-tour="opencode-info"]` → `BackendDetailPage.vue:91` (OB-18)
- `[data-tour="token-monitoring"]` → `GeneralSettings.vue:247` (OB-20)
- `[data-tour="harness-plugins"]` → `HarnessSettings.vue:122` (OB-21)

Routes for each step are declared in `src/constants/tourSteps.ts`, and
`App.vue:101 navigateToTourStep()` watches the machine state and calls
`router.push` on each transition. Auto-advance on success toasts is wired
at `App.vue:138`.

So Phase 4's success criteria 1, 2, 4 are wired structurally. The gap is
**criterion 2's "completing one backend satisfies the step requirement"**
+ OB-18's parent-completes-on-any-backend semantics.

The existing tour machine has guards stubbed to `() => false` — a Phase 1
holdover. The Phase 1 endpoint `GET /health/setup-status` (shipped in PR
#9) returns the booleans the tour needs, but `useTourMachine` doesn't call
it. This plan wires that.

## What this plan delivers

1. Add `fetchSetupStatus()` API helper that calls `/health/setup-status`
   and returns the typed shape (mirrors what the deleted Phase 1
   `setupStatus.ts` had).
2. Extend `initActor()` in `useTourMachine.ts` to fetch setup-status
   alongside instance-id, then walk the actor past any state whose key
   matches a completed step (per the response's `has_*` booleans).
3. Mapping table from setup-status fields to tour state keys:
   - `has_workspace` → `workspace`
   - `has_claude_account` → `backends.claude`
   - `has_codex_account` → `backends.codex`
   - `has_gemini_account` → `backends.gemini`
   - `has_opencode_account` → `backends.opencode`
   - `has_harness_synced` → `verification` (the plan's "harness" step in
     the legacy id; the tourMachine state is named `verification`)
   - `has_first_product` → `create_product`
4. The walk uses synthetic `SKIP` events through the existing machine
   transitions — no changes to the machine definition itself. (We leave
   the machine pure; the auto-skip lives in the composable.)

## Out of scope

- OB-19 (per-backend form field guidance after Add Account) is the
  Phase 5 auto-discovery mechanism. Phase 4 ensures the user lands on
  the backend page with `[data-tour="add-account-btn"]` highlighted;
  Phase 5 takes over from there.
- Auto-skip when *any* backend has an account (vs. skipping only the
  per-backend substep that's done). The roadmap's OB-18 says "completing
  one satisfies the requirement", which can mean either:
  - (a) Skip *just* the substeps whose backend already has an account
    (granular)
  - (b) Skip the whole `backends` compound state when *any* backend has
    an account (aggregate)

  We pick (a) because it matches the success criterion's wording
  ("individually skippable substeps") and is more useful — the user with
  Claude only configured still benefits from being shown Codex/Gemini/
  OpenCode tour steps. (b) can be added later behind a setting.

## Test plan

Unit tests for:
- `fetchSetupStatus()` parses 200 response correctly + returns null on
  network/HTTP errors.
- Mapping helper `setupStatusToCompleted()` produces the expected
  `Record<StepId, boolean>`.
- Synthetic SKIP walker: given a completed list and a starting state,
  drives the actor to the first incomplete step.

The walker test mounts a real `tourMachine` actor (no mocks) so we
exercise the actual transition table.

## Files

- `frontend/src/composables/useTourMachine.ts` — extend `initActor` with
  setup-status fetch + auto-skip walk; expose `setupStatusToCompleted`
  and `fetchSetupStatus` helpers (importable for tests).
- `frontend/src/composables/__tests__/useTourMachine.setup-status.test.ts`
  — new test file.

## Estimated size

~80 lines new code, ~120 lines tests. ~30 minutes.
