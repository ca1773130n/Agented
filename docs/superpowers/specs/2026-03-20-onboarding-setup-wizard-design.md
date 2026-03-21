# Onboarding & Interactive Setup Wizard

## Overview

Replace the bare "API key required" banner with a full first-run experience: a branded welcome page, API key generation, then an interactive guided tour that walks users through real app pages — highlighting actual buttons and inputs with a soft-dim overlay and persistent bottom bar.

## Problem

1. First-run shows a minimal "API key required" banner with no context about what Agented is
2. After auth, user lands on an empty dashboard with no guidance
3. Critical settings (workspace dir, AI backends, token monitoring, harness plugins) are buried in settings tabs
4. No path to creating the first product/project or assigning teams

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Wizard model | Strict linear, steps 6-8 skippable | Ensures complete setup for core settings |
| Post-completion | Land on main dashboard | No persistent progress widget needed |
| Tour style | Soft dim + bottom bar | Target glows through dimmed page, bottom bar shows step/progress/nav |
| Implementation | Custom Vue composable + component | No external deps; driver.js would fight the bottom bar and cross-page navigation |
| Welcome page | Full-screen with feature overview | Branded introduction before key generation |
| New bundled plugin | `affaan-m/everything-claude-code` | Added to BUNDLE_PLUGINS alongside HarnessSync and grd |

## Architecture

### Components

#### 1. `WelcomePage.vue` — Full-screen first-run landing

New route `/welcome` with `meta: { fullBleed: true }` (existing router convention for hiding sidebar/padding). Shown when `needs_setup === true` from `/health/auth-status`.

**Layout:**
- Mesh gradient background with drift animation, grain texture, subtle grid lines
- Top bar: Agented logo + version
- Hero: badge "First-time setup", headline "Your virtual startup, fully autonomous", subtitle describing the platform — end-to-end product building with autonomous agents across Claude Code, ChatGPT, Gemini, OpenCode with harness sync and token usage prediction
- Bento grid (2x2):
  - **Vision** — Products & Projects: define what to build, connect GitHub repos
  - **Workforce** — Agent Teams: 5 departments, 17 agents across Command, Dev, Research, Ops, QA
  - **Fully autonomous** — Seamless Backend Scheduling: agents move between backends, harness sync keeps configs aligned, token prediction triggers handoff before limits hit
  - **Engineering** — Harness & Plugins: config sync, GRD planning, MCP servers, marketplace plugins
- CTA: "Begin setup" button → transitions to key generation

**After "Begin setup":**
- Transitions (fade) to API key generation view within the same full-screen layout
- "Generate Admin Key" button → calls `POST /health/setup`
- Shows generated key in monospace with copy button
- "Continue" button → stores key in localStorage, navigates to `/` with tour active

#### 2. `TourOverlay.vue` — Soft dim + bottom bar overlay

Global component mounted in `App.vue`. Renders when tour is active.

**Elements:**
- **Dim layer**: `position: fixed; inset: 0` semi-transparent overlay (`rgba(0,0,0,0.4)`)
- **Spotlight cutout**: CSS `clip-path` or `box-shadow` trick to cut out the target element area with a subtle indigo glow (`box-shadow: 0 0 20px rgba(79,70,229,0.3)`)
- **Bottom bar**: Fixed to bottom, gradient fade-up background
  - Left: step tag (e.g., "STEP 2 OF 8") + guidance text
  - Right: progress dots (filled for completed, elongated for current, hollow for upcoming) + "Next" button
  - Steps 6-8 also show "Skip" text button

**Behavior:**
- Target element identified by CSS selector from step config
- Spotlight position recalculated on window resize and route change
- Target element remains interactive (click-through the overlay)
- Clicking outside the spotlight does nothing (overlay blocks interaction)
- Bottom bar slides up with spring animation on step change
- Spotlight morphs (animates position/size) between steps on the same page
- On cross-page steps, dim fades out → route navigates → dim fades in with new spotlight

#### 3. `useTour()` composable — Tour state machine

```typescript
interface TourStep {
  id: string
  route: string                    // Vue Router path to navigate to
  target: string                   // CSS selector for spotlight target
  title: string                    // Bottom bar step tag
  message: string                  // Bottom bar guidance text
  skippable: boolean               // Show skip button
  waitFor?: () => boolean          // Reactive condition — advance only when true
  onEnter?: () => void             // Side effect on step activation
  onComplete?: () => void          // Side effect on step completion
}

interface TourState {
  active: boolean
  currentStepIndex: number
  steps: TourStep[]
  completed: string[]              // IDs of completed steps
}
```

**API:**
- `startTour()` — activate tour, navigate to step 0
- `nextStep()` — advance (checks `waitFor` condition first)
- `skipStep()` — skip current step (only if `skippable`)
- `endTour()` — deactivate tour, clean up
- `currentStep` — computed ref of active step

**Persistence:**
- Tour state stored in localStorage key `agented-tour-state`
- If user refreshes mid-tour, resumes from last step
- Tour marked complete in localStorage after final step; never shows again

### Tour Steps

#### Step 1: API Key Generation
- **Location**: `/welcome` (full-screen, before main app loads)
- **Action**: Click "Generate Key" → copy key → click "Continue"
- **waitFor**: API key exists in localStorage
- **Transition**: After auth, main app layout loads, tour overlay activates

#### Step 2: Set Workspace Directory
- **Route**: `/settings` (General tab)
- **Target**: Workspace root input field
- **Message**: "Set the root directory where project repos will be cloned and managed"
- **waitFor**: `workspace_root` setting saved (watch API response)

#### Step 3: Register AI Backend Accounts
- **Route**: `/settings` (General tab, or dedicated backends section)
- **Target**: AI backends section / "Add Account" button
- **Message**: "Register your Anthropic, OpenAI, or other provider accounts — agents schedule work across them seamlessly"
- **waitFor**: At least one backend account exists

#### Step 4: Enable Token Monitoring
- **Route**: `/settings` (General tab)
- **Target**: Token monitoring toggle
- **Message**: "Turn on token monitoring to predict usage and hand off between accounts before hitting rate limits"
- **waitFor**: Monitoring config saved with `enabled: true`

#### Step 5: Verify Harness Plugins
- **Route**: `/settings` (Harness Plugin tab)
- **Target**: Plugin list / status section
- **Message**: "Verifying bundled plugins are installed — HarnessSync, GRD, and Everything Claude Code"
- **onEnter**: Trigger `POST /api/setup/bundle-install` to ensure all three plugins are installed
- **waitFor**: All bundled plugins show as installed

#### Step 6: Create First Product (skippable)
- **Route**: `/products` (or product creation modal)
- **Target**: "New Product" button, then the creation form
- **Message**: "Create your first product — this is what your agent teams will build"
- **skippable**: true
- **waitFor**: Product created (product list non-empty)

#### Step 7: Create First Project (skippable)
- **Route**: Product detail page → project section
- **Target**: "Add Project" button / project creation form
- **Message**: "Connect a GitHub repo as a project under your product"
- **skippable**: true
- **waitFor**: Project created (with or without `github_repo` — GitHub repo is optional, the tour advances on any project creation)

#### Step 8: Assign Matrix Teams (skippable)
- **Route**: Project detail page → teams section
- **Target**: Team assignment area
- **Message**: "Assign Matrix teams to your project — Command, Development, Research, Operations, or QA"
- **skippable**: true
- **waitFor**: At least one team assigned to the project

### Backend Changes

#### Bundle Plugin Addition

Two separate plugin lists must be updated:

1. `backend/app/services/harness_plugin_installer.py` — simple string list for per-account CLI installs:
```python
BUNDLE_PLUGINS = ["HarnessSync", "grd", "everything-claude-code"]
```

2. `backend/app/services/setup_service.py` — dict list with `remote_name`/`is_harness` fields for the web-based `POST /api/setup/bundle-install` endpoint:
```python
# Add entry for everything-claude-code with remote_name "affaan-m/everything-claude-code"
```

Both must include `everything-claude-code`. The `bundle_installed` setting short-circuits repeat calls — Step 5 should treat `already_installed` as success.

#### No New Endpoints Needed

All required endpoints already exist:
- `POST /health/setup` — key generation
- `PUT /api/settings/<key>` — workspace root, monitoring config
- `POST /admin/backends/<id>/accounts` — backend accounts
- `POST /admin/monitoring/config` — monitoring toggle
- `POST /admin/products/` — product creation
- `POST /admin/projects/` — project creation
- `POST /admin/projects/<project_id>/teams/<team_id>` — team assignment
- `POST /api/setup/bundle-install` — bundled plugin installation

### Frontend Changes

#### New Files
- `src/views/WelcomePage.vue` — full-screen welcome + key generation
- `src/components/tour/TourOverlay.vue` — dim layer + spotlight + bottom bar
- `src/composables/useTour.ts` — tour state machine + step definitions

#### Modified Files
- `src/router/index.ts` — add `/welcome` route, add navigation guard to redirect to `/welcome` when `needs_setup`
- `src/App.vue` — mount `TourOverlay` globally, remove current `ApiKeyBanner` logic for first-run (keep for re-auth)
- `src/components/layout/ApiKeyBanner.vue` — remove first-run mode (`needsSetup` path), keep only the re-auth mode
- `backend/app/services/harness_plugin_installer.py` — add `everything-claude-code` to `BUNDLE_PLUGINS`

### Animations

- **Welcome → Key Generation**: Crossfade (opacity 0→1, translateY 10px→0, 300ms ease-out)
- **Key Generation → Main App**: Welcome page fades out (300ms), main app layout fades in (300ms), bottom bar slides up (400ms spring)
- **Same-page step transition**: Spotlight morphs position/size (400ms cubic-bezier)
- **Cross-page step transition**: Dim fades out (200ms) → route change → dim fades in (200ms) → spotlight appears (300ms)
- **Bottom bar text change**: Text slides out left, new text slides in from right (250ms)
- **Progress dots**: Current dot elongates with spring animation

### Edge Cases

- **User refreshes mid-tour**: Resume from localStorage state
- **User manually navigates away**: Tour pauses, bottom bar shows "Return to setup" link
- **Backend account already exists**: Step 3 auto-completes, advances
- **Plugins already installed**: Step 5 auto-completes after verification
- **User closes browser**: Tour resumes on next visit
- **Multiple tabs**: Tour state synced via `storage` event listener
- **Target element not found**: Wait up to 2s for DOM, then show bottom bar with "Element not found — try scrolling down" hint

## Testing Strategy

- **Unit**: `useTour` composable — step transitions, skip logic, persistence, waitFor conditions
- **Unit**: `TourOverlay` — spotlight positioning, click-through behavior
- **Integration**: Full tour flow with mocked API responses
- **E2E**: Happy path — complete all 8 steps, verify each setting was saved
- **E2E**: Skip path — complete 1-5, skip 6-8, verify landing on dashboard
