# Tour V2 — Loading States, Substeps, Per-Backend Navigation

## Overview

Improve the onboarding tour with loading spinners between steps, per-backend navigation with substeps for AI account registration, and better visual feedback during page transitions.

## Problems

1. No loading feedback when tour navigates to a lazy-loaded page — user sees nothing or premature dim
2. Step 3 (AI Backends) dumps user on the all-backends dashboard instead of guiding through each backend individually
3. No substep support — complex steps like "register AI accounts" need multiple guided interactions

## Design

### 1. Loading Spinner Between Steps

When the tour navigates to a new page and the target element hasn't appeared yet, show a small loading indicator in the bottom bar instead of showing nothing. The bottom bar already renders — just add a "Loading..." text or spinner next to the step message.

**Implementation:**
- In `TourOverlay.vue`, when `active && step && !hasTarget`, show the bottom bar with a loading spinner icon before the message text
- When `hasTarget` becomes true (MutationObserver fires), the spinner disappears and the spotlight appears
- No separate fullscreen spinner needed — the bottom bar provides context

### 2. Substep Architecture

Add substep support to `useTour.ts`:

```typescript
interface TourStep {
  id: string
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  substeps?: TourSubstep[]  // NEW
  // ... existing fields
}

interface TourSubstep {
  id: string
  route: string
  target: string
  label: string           // e.g., "Claude Code (1/4)"
  message: string
  skippable: boolean
}
```

**Bottom bar display when substeps active:**
- Left side: "STEP 3 OF 8 — Claude Code (1/4)" + message
- Substep counter shows progress within the step

**Navigation logic:**
- `nextStep()`: if current step has substeps and current substep < last, advance substep. Otherwise advance to next major step.
- `skipStep()`: skip all remaining substeps, advance to next major step.

### 3. Revised Tour Steps

Replace step 3 (single "AI Backends" step) with substeps:

```
Step 1: (welcome page — key gen)
Step 2: Workspace directory — /settings#general → [data-tour="workspace-root"]
Step 3: AI Backend Accounts (with 4 substeps):
  3a: Claude Code — /backends/claude → [data-tour="add-account-btn"]
      "Register your Anthropic account for Claude Code"
  3b: Codex CLI — /backends/codex → [data-tour="add-account-btn"]
      "Register your OpenAI account for Codex CLI"
  3c: Gemini CLI — /backends/gemini → [data-tour="add-account-btn"]
      "Register your Google account for Gemini CLI"
  3d: OpenCode — /backends/opencode → [data-tour="add-account-btn"]
      "Register an account for OpenCode"
Step 4: Token monitoring — /settings#general → [data-tour="token-monitoring"]
Step 5: Harness plugins — /settings#harness → [data-tour="harness-plugins"]
Step 6: Create product (skippable) — /products → [data-tour="create-product"]
Step 7: Create project (skippable) — dynamic → [data-tour="create-project"]
Step 8: Assign teams (skippable) — dynamic → [data-tour="assign-teams"]
```

All 4 backend substeps are individually skippable. Skipping the parent step 3 skips all 4.

### 4. Backend Detail Page `data-tour` Attributes

Each individual backend detail page (e.g., `AIBackendDetailPage.vue` or equivalent at `/backends/:backendId`) needs a `data-tour="add-account-btn"` attribute on its "Add Account" button.

Check existing routes:
- `/backends/claude` — Claude Code detail page
- `/backends/codex` — Codex CLI detail page
- `/backends/gemini` — Gemini CLI detail page
- `/backends/opencode` — OpenCode detail page

### 5. Files to Modify

- `frontend/src/composables/useTour.ts` — add substep support to TourStep interface, navigation logic
- `frontend/src/components/tour/TourOverlay.vue` — loading spinner, substep display in bottom bar
- `frontend/src/views/AIBackendDetailPage.vue` (or equivalent) — add data-tour attributes
- Remove `data-tour="ai-backends"` from `AIBackendsPage.vue` (no longer used)

### 6. No New Backend Changes

All required routes and pages already exist. This is frontend-only.

## Testing

- Unit: useTour substep navigation (advance substep, skip all substeps, substep counter)
- Unit: TourOverlay loading state rendering
- E2E: Full flow with substeps — verify each backend page is navigated to
