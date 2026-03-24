# Onboarding & Interactive Setup Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bare API key banner with a full-screen welcome page, key generation, and a guided tour that walks users through real app pages with spotlight highlights and a bottom progress bar.

**Architecture:** Full-screen `/welcome` route for branding + key gen. After auth, `TourOverlay.vue` mounts globally in `App.vue` and guides users through settings pages (workspace, backends, monitoring, plugins) then optionally through product/project/team creation. `useTour.ts` composable manages state machine with localStorage persistence. Backend adds `everything-claude-code` to both bundle plugin lists.

**Tech Stack:** Vue 3, TypeScript, Vue Router 4, CSS animations, localStorage

**Spec:** `docs/superpowers/specs/2026-03-20-onboarding-setup-wizard-design.md`

---

### Task 1: Add `everything-claude-code` to backend bundle plugin lists

**Files:**
- Modify: `backend/app/services/setup_service.py:22-25`
- Modify: `backend/app/services/harness_plugin_installer.py:10`
- Test: `backend/tests/test_setup_service.py` (if exists, else new)

- [ ] **Step 1: Write failing test for new plugin in bundle list**

```python
# backend/tests/test_bundle_plugins.py
from app.services.setup_service import BUNDLE_PLUGINS
from app.services.harness_plugin_installer import BUNDLE_PLUGINS as CLI_BUNDLE_PLUGINS


def test_everything_claude_code_in_setup_bundle():
    names = [p["remote_name"] for p in BUNDLE_PLUGINS]
    assert "affaan-m/everything-claude-code" in names


def test_everything_claude_code_in_cli_bundle():
    assert "everything-claude-code" in CLI_BUNDLE_PLUGINS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_bundle_plugins.py -v`
Expected: FAIL — `everything-claude-code` not in either list

- [ ] **Step 3: Add plugin to both lists**

In `backend/app/services/setup_service.py:22-25`, change:
```python
BUNDLE_PLUGINS = [
    {"remote_name": "HarnessSync", "is_harness": True},
    {"remote_name": "grd", "is_harness": False},
]
```
to:
```python
BUNDLE_PLUGINS = [
    {"remote_name": "HarnessSync", "is_harness": True},
    {"remote_name": "grd", "is_harness": False},
    {"remote_name": "affaan-m/everything-claude-code", "is_harness": False},
]
```

In `backend/app/services/harness_plugin_installer.py:10`, change:
```python
BUNDLE_PLUGINS = ["HarnessSync", "grd"]
```
to:
```python
BUNDLE_PLUGINS = ["HarnessSync", "grd", "everything-claude-code"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_bundle_plugins.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend test suite**

Run: `cd backend && uv run pytest`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/setup_service.py backend/app/services/harness_plugin_installer.py backend/tests/test_bundle_plugins.py
git commit -m "feat(plugins): add everything-claude-code to bundled plugins"
```

---

### Task 2: Create `useTour.ts` composable — tour state machine

**Files:**
- Create: `frontend/src/composables/useTour.ts`
- Test: `frontend/src/composables/__tests__/useTour.test.ts`

- [ ] **Step 1: Write failing tests for useTour composable**

```typescript
// frontend/src/composables/__tests__/useTour.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    currentRoute: { value: { path: '/' } },
  }),
}))

describe('useTour', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts inactive', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    expect(tour.active.value).toBe(false)
    expect(tour.currentStep.value).toBeNull()
  })

  it('activates and sets first step on startTour', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    expect(tour.active.value).toBe(true)
    expect(tour.currentStepIndex.value).toBe(0)
    expect(tour.currentStep.value).not.toBeNull()
  })

  it('advances to next step', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.nextStep()
    expect(tour.currentStepIndex.value).toBe(1)
  })

  it('skips only skippable steps', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    // Step 0 (workspace) is not skippable
    tour.skipStep()
    expect(tour.currentStepIndex.value).toBe(0) // didn't skip
  })

  it('persists state to localStorage', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.nextStep()
    const stored = JSON.parse(localStorage.getItem('agented-tour-state') || '{}')
    expect(stored.currentStepIndex).toBe(1)
    expect(stored.active).toBe(true)
  })

  it('restores state from localStorage', async () => {
    localStorage.setItem('agented-tour-state', JSON.stringify({
      active: true,
      currentStepIndex: 3,
      completed: ['workspace', 'backends', 'monitoring'],
    }))
    // Need fresh import to pick up localStorage
    vi.resetModules()
    const { useTour } = await import('../useTour')
    const tour = useTour()
    expect(tour.active.value).toBe(true)
    expect(tour.currentStepIndex.value).toBe(3)
  })

  it('ends tour and marks complete', async () => {
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    tour.endTour()
    expect(tour.active.value).toBe(false)
    const stored = JSON.parse(localStorage.getItem('agented-tour-state') || '{}')
    expect(stored.tourComplete).toBe(true)
  })

  it('does not start if tour already completed', async () => {
    localStorage.setItem('agented-tour-state', JSON.stringify({ tourComplete: true }))
    vi.resetModules()
    const { useTour } = await import('../useTour')
    const tour = useTour()
    tour.startTour()
    expect(tour.active.value).toBe(false)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/composables/__tests__/useTour.test.ts`
Expected: FAIL — module not found

- [ ] **Step 3: Implement useTour composable**

```typescript
// frontend/src/composables/useTour.ts
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'

export interface TourStep {
  id: string
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  waitFor?: () => boolean
  onEnter?: () => void | Promise<void>
  onComplete?: () => void
}

interface PersistedTourState {
  active: boolean
  currentStepIndex: number
  completed: string[]
  tourComplete?: boolean
}

const STORAGE_KEY = 'agented-tour-state'

const TOUR_STEPS: TourStep[] = [
  {
    id: 'workspace',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="workspace-root"]',
    title: 'Workspace Directory',
    message: 'Set the root directory where project repos will be cloned and managed',
    skippable: false,
  },
  {
    id: 'backends',
    route: '/backends',
    target: '[data-tour="ai-backends"]',
    title: 'AI Backend Accounts',
    message: 'Register your Anthropic, OpenAI, or other provider accounts — agents schedule work across them seamlessly',
    skippable: false,
  },
  {
    id: 'monitoring',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="token-monitoring"]',
    title: 'Token Monitoring',
    message: 'Turn on token monitoring to predict usage and hand off between accounts before hitting rate limits',
    skippable: false,
  },
  {
    id: 'harness',
    route: '/settings',
    routeHash: '#harness',
    target: '[data-tour="harness-plugins"]',
    title: 'Harness Plugins',
    message: 'Verifying bundled plugins are installed — HarnessSync, GRD, and Everything Claude Code',
    skippable: false,
  },
  {
    id: 'product',
    route: '/products',
    target: '[data-tour="create-product"]',
    title: 'First Product',
    message: 'Create your first product — this is what your agent teams will build',
    skippable: true,
  },
  {
    id: 'project',
    route: '', // dynamic — set after product creation
    target: '[data-tour="create-project"]',
    title: 'First Project',
    message: 'Connect a GitHub repo as a project under your product',
    skippable: true,
  },
  {
    id: 'teams',
    route: '', // dynamic — set after project creation
    target: '[data-tour="assign-teams"]',
    title: 'Assign Teams',
    message: 'Assign Matrix teams to your project — Command, Development, Research, Operations, or QA',
    skippable: true,
  },
]

function loadState(): PersistedTourState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveState(state: PersistedTourState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function useTour() {
  const router = useRouter()

  const saved = loadState()
  const active = ref(saved?.active ?? false)
  const currentStepIndex = ref(saved?.currentStepIndex ?? 0)
  const completed = ref<string[]>(saved?.completed ?? [])
  const tourComplete = ref(saved?.tourComplete ?? false)

  const currentStep = computed<TourStep | null>(() => {
    if (!active.value) return null
    return TOUR_STEPS[currentStepIndex.value] ?? null
  })

  const totalSteps = TOUR_STEPS.length
  // +1 for the welcome/key-gen step shown on welcome page
  const displayStepNumber = computed(() => currentStepIndex.value + 2)
  const displayTotalSteps = totalSteps + 1 // 8 total (1 welcome + 7 tour)

  function persist() {
    saveState({
      active: active.value,
      currentStepIndex: currentStepIndex.value,
      completed: completed.value,
      tourComplete: tourComplete.value,
    })
  }

  watch([active, currentStepIndex, completed], persist, { deep: true })

  function startTour() {
    if (tourComplete.value) return
    active.value = true
    currentStepIndex.value = 0
    navigateToStep(0)
  }

  function nextStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (step) {
      completed.value = [...completed.value, step.id]
      step.onComplete?.()
    }
    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      navigateToStep(currentStepIndex.value)
    } else {
      endTour()
    }
  }

  function skipStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (!step?.skippable) return
    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      navigateToStep(currentStepIndex.value)
    } else {
      endTour()
    }
  }

  function endTour() {
    active.value = false
    tourComplete.value = true
    persist()
    router.push('/')
  }

  function navigateToStep(index: number) {
    const step = TOUR_STEPS[index]
    if (!step) return
    const route = step.routeHash ? step.route + step.routeHash : step.route
    if (route) router.push(route)
    step.onEnter?.()
  }

  function updateStepRoute(stepId: string, route: string) {
    const step = TOUR_STEPS.find(s => s.id === stepId)
    if (step) step.route = route
  }

  return {
    active,
    currentStepIndex,
    currentStep,
    completed,
    totalSteps: displayTotalSteps,
    displayStepNumber,
    tourComplete,
    startTour,
    nextStep,
    skipStep,
    endTour,
    updateStepRoute,
    steps: TOUR_STEPS,
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/composables/__tests__/useTour.test.ts`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useTour.ts frontend/src/composables/__tests__/useTour.test.ts
git commit -m "feat(tour): add useTour composable with state machine and localStorage persistence"
```

---

### Task 3: Create `TourOverlay.vue` — spotlight + bottom bar

**Files:**
- Create: `frontend/src/components/tour/TourOverlay.vue`
- Test: `frontend/src/components/tour/__tests__/TourOverlay.test.ts`

- [ ] **Step 1: Write failing test for TourOverlay rendering**

```typescript
// frontend/src/components/tour/__tests__/TourOverlay.test.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TourOverlay from '../TourOverlay.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { path: '/' } } }),
}))

describe('TourOverlay', () => {
  it('does not render when inactive', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: false, step: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('renders overlay and bottom bar when active with a step', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace Directory',
          message: 'Set the root directory',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    expect(wrapper.find('.tour-bottom-bar').exists()).toBe(true)
    expect(wrapper.text()).toContain('STEP 2 OF 8')
    expect(wrapper.text()).toContain('Set the root directory')
  })

  it('shows skip button for skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'product',
          route: '/products',
          target: '[data-tour="create-product"]',
          title: 'First Product',
          message: 'Create your first product',
          skippable: true,
        },
        stepNumber: 6,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(true)
  })

  it('hides skip button for non-skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace Directory',
          message: 'Set the root directory',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(false)
  })

  it('emits next on next button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'workspace',
          route: '/settings',
          target: '[data-tour="workspace-root"]',
          title: 'Workspace',
          message: 'Set workspace',
          skippable: false,
        },
        stepNumber: 2,
        totalSteps: 8,
      },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    expect(wrapper.emitted('next')).toBeTruthy()
  })

  it('emits skip on skip button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: {
        active: true,
        step: {
          id: 'product',
          route: '/products',
          target: '[data-tour="create-product"]',
          title: 'Product',
          message: 'Create product',
          skippable: true,
        },
        stepNumber: 6,
        totalSteps: 8,
      },
    })
    await wrapper.find('.tour-skip-btn').trigger('click')
    expect(wrapper.emitted('skip')).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/components/tour/__tests__/TourOverlay.test.ts`
Expected: FAIL — component not found

- [ ] **Step 3: Implement TourOverlay.vue**

Create `frontend/src/components/tour/TourOverlay.vue` with:
- Props: `active`, `step` (TourStep | null), `stepNumber`, `totalSteps`
- Emits: `next`, `skip`
- Dim overlay with `position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 9998`
- Spotlight: Uses `ResizeObserver` and `MutationObserver` to track target element position, renders a cutout via `box-shadow: 0 0 0 9999px rgba(0,0,0,0.4)` on a positioned div with indigo glow
- Click-through on spotlight area using `pointer-events: none` on overlay + `pointer-events: auto` on target zone
- Bottom bar: `position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999`
  - Left: step tag ("STEP N OF 8") + message text
  - Right: progress dots + Next button + optional Skip button
- CSS transitions for spotlight morph (400ms), bottom bar slide-up (400ms), text crossfade (250ms)
- Progress dots: filled circle for completed, elongated pill for current, hollow circle for remaining
- `onMounted`/`onUnmounted` lifecycle to set up/tear down observers

Full implementation with all animations, spotlight tracking, and bottom bar layout. The component receives props from the parent (`App.vue`) which connects it to the `useTour` composable.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/components/tour/__tests__/TourOverlay.test.ts`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/tour/TourOverlay.vue frontend/src/components/tour/__tests__/TourOverlay.test.ts
git commit -m "feat(tour): add TourOverlay component with spotlight, bottom bar, and animations"
```

---

### Task 4: Create `WelcomePage.vue` — full-screen welcome + key generation

**Files:**
- Create: `frontend/src/views/WelcomePage.vue`
- Modify: `frontend/src/router/routes/misc.ts:614-620`

- [ ] **Step 1: Write failing test for WelcomePage**

```typescript
// frontend/src/views/__tests__/WelcomePage.test.ts
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WelcomePage from '../WelcomePage.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('../../composables/useToast', () => ({
  useToast: () => vi.fn(),
}))

vi.mock('../../services/api', () => ({
  healthApi: {
    setup: vi.fn().mockResolvedValue({ api_key: 'test-key-abc123', role: 'admin' }),
  },
}))

describe('WelcomePage', () => {
  it('renders welcome view by default', () => {
    const wrapper = mount(WelcomePage)
    expect(wrapper.text()).toContain('Your virtual startup')
    expect(wrapper.text()).toContain('Begin setup')
  })

  it('transitions to key generation on Begin Setup click', async () => {
    const wrapper = mount(WelcomePage)
    await wrapper.find('.cta-btn').trigger('click')
    expect(wrapper.text()).toContain('Generate Admin Key')
  })

  it('generates and displays API key', async () => {
    const wrapper = mount(WelcomePage)
    await wrapper.find('.cta-btn').trigger('click')
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click')
    // Wait for async API call to resolve
    await flushPromises()
    expect(wrapper.text()).toContain('test-key-abc123')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/views/__tests__/WelcomePage.test.ts`
Expected: FAIL — component not found

- [ ] **Step 3: Implement WelcomePage.vue**

Create `frontend/src/views/WelcomePage.vue` with the approved design from brainstorming:
- Two-phase view: `phase = ref<'welcome' | 'keygen'>('welcome')`
- Welcome phase: Mesh gradient BG, grain texture, grid lines (all via CSS), hero with badge + headline + subtitle, bento grid (2x2: Products & Projects, Agent Teams, Seamless Backend Scheduling, Harness & Plugins), "Begin setup" CTA
- Key generation phase: Clean centered card, "Generate Admin Key" button, monospace key display with copy button, "Continue" button
- Animations: Crossfade between phases (300ms opacity + translateY)
- On "Continue": calls `setApiKey(key)` from `services/api/client.ts`, emits `authenticated` event, router pushes to `/` with query param `?tour=start`
- Uses the exact visual design from brainstorming session (v8 welcome page mockup)

- [ ] **Step 4: Update route in misc.ts**

In `frontend/src/router/routes/misc.ts:614-620`, change:
```typescript
  {
    path: '/onboarding',
    name: 'guided-onboarding-wizard',
    component: () => import('../../views/GuidedOnboardingWizardPage.vue'),
    meta: { title: 'Get Started' },
  },
```
to:
```typescript
  {
    path: '/welcome',
    name: 'welcome',
    component: () => import('../../views/WelcomePage.vue'),
    meta: { title: 'Welcome to Agented', fullBleed: true },
  },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm run test:run -- --reporter=verbose src/views/__tests__/WelcomePage.test.ts`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/WelcomePage.vue frontend/src/views/__tests__/WelcomePage.test.ts frontend/src/router/routes/misc.ts
git commit -m "feat(onboarding): add WelcomePage with branded landing and API key generation"
```

---

### Task 5: Wire tour into App.vue and modify auth flow

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/layout/ApiKeyBanner.vue`

- [ ] **Step 1: Modify App.vue to mount TourOverlay and redirect to /welcome on first run**

In `App.vue`:

1. Import TourOverlay, useTour, and ensure `useRouter` is available (App.vue currently only imports `useRoute` — add `useRouter`):
```typescript
import { useRoute, useRouter } from 'vue-router'
import TourOverlay from './components/tour/TourOverlay.vue'
import { useTour } from './composables/useTour'
```
Add `const router = useRouter()` in `<script setup>` if not already present.

2. In `setup()`, create tour instance:
```typescript
const tour = useTour()
```

3. In `checkAuthStatus()` (around line 99-112): When `needs_setup === true`, instead of showing ApiKeyBanner, redirect to `/welcome`:
```typescript
if (data.needs_setup) {
  router.push({ name: 'welcome' })
  return
}
```

4. In `onAuthenticated()` handler: Check if tour should start (query param `?tour=start` or first time after setup):
```typescript
function onAuthenticated() {
  showApiKeyBanner.value = false
  const shouldStartTour = route.query.tour === 'start'
  loadSidebarData()
  if (shouldStartTour) {
    router.replace({ query: {} }) // clean URL
    tour.startTour()
  }
}
```

5. Mount TourOverlay in template (after the main layout, using Teleport to body):
```html
<Teleport to="body">
  <TourOverlay
    :active="tour.active.value"
    :step="tour.currentStep.value"
    :step-number="tour.displayStepNumber.value"
    :total-steps="tour.totalSteps"
    @next="tour.nextStep()"
    @skip="tour.skipStep()"
  />
</Teleport>
```

- [ ] **Step 2: Simplify ApiKeyBanner.vue — remove first-run mode**

In `ApiKeyBanner.vue`, remove the `needsSetup` prop handling and the "Generate Admin Key" path (lines 85-99). Keep only the re-auth mode (password input for existing key verification). The first-run flow is now handled by WelcomePage.

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All pass (some ApiKeyBanner tests may need updating if they test needsSetup mode)

- [ ] **Step 4: Run type check**

Run: `just build`
Expected: Pass — no type errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.vue frontend/src/components/layout/ApiKeyBanner.vue
git commit -m "feat(onboarding): wire tour into App.vue, redirect first-run to /welcome"
```

---

### Task 6: Add `data-tour` attributes to settings components

**Files:**
- Modify: `frontend/src/components/settings/GeneralSettings.vue`
- Modify: `frontend/src/components/settings/HarnessSettings.vue`
- Modify: `frontend/src/views/SettingsPage.vue`

- [ ] **Step 1: Add data-tour attributes to GeneralSettings.vue**

Add `data-tour="workspace-root"` to the workspace root section wrapper div.
Add `data-tour="token-monitoring"` to the token monitoring section wrapper div.

These are the CSS selectors that `TourOverlay` uses to find spotlight targets.

- [ ] **Step 2: Add data-tour="ai-backends" to AIBackendsPage.vue**

The AI backends page is at `frontend/src/views/AIBackendsPage.vue` (route `/backends`), NOT in GeneralSettings. Add `data-tour="ai-backends"` to the "Add Account" button or the backends list section.

- [ ] **Step 3: Add data-tour attribute to HarnessSettings.vue**

Add `data-tour="harness-plugins"` to the main harness plugin section wrapper div.

- [ ] **Step 4: Expose tab switching on SettingsPage.vue**

Add a `watch` on `route.hash` so the tour can navigate to `/settings#general` or `/settings#harness` and the correct tab activates automatically. The existing hash-based tab switching may already handle this — verify and fix if needed. Note: Vue Router may not trigger `hashchange` events the same way as `window.location.hash`. Test by navigating to `/settings#harness` via `router.push` and verifying the tab switches.

- [ ] **Step 5: Run type check and tests**

Run: `just build && cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings/GeneralSettings.vue frontend/src/components/settings/HarnessSettings.vue frontend/src/views/SettingsPage.vue frontend/src/views/AIBackendsPage.vue
git commit -m "feat(onboarding): add data-tour attributes to settings and backends pages for spotlight targeting"
```

---

### Task 7: Add `data-tour` attributes to products/projects/teams views

**Files:**
- Modify: `frontend/src/views/ProductsPage.vue`
- Modify: `frontend/src/views/ProductDashboard.vue`
- Modify: `frontend/src/views/ProjectSettingsPage.vue`

- [ ] **Step 1: Add data-tour="create-product" to ProductsPage.vue**

Add `data-tour="create-product"` to the "New Product" / "Create Product" button.

- [ ] **Step 2: Add data-tour="create-project" to ProductDashboard.vue**

Add `data-tour="create-project"` to the "Add Project" button in `frontend/src/views/ProductDashboard.vue`.

- [ ] **Step 3: Add data-tour="assign-teams" to ProjectSettingsPage.vue**

Add `data-tour="assign-teams"` to the team assignment section (around line 46-48 where teams grid renders).

- [ ] **Step 4: Run type check and tests**

Run: `just build && cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ProductsPage.vue frontend/src/views/ProductDashboard.vue frontend/src/views/ProjectSettingsPage.vue
git commit -m "feat(onboarding): add data-tour attributes to product/project/team views"
```

---

### Task 8: Delete old GuidedOnboardingWizardPage.vue

**Files:**
- Delete: `frontend/src/views/GuidedOnboardingWizardPage.vue`

- [ ] **Step 1: Remove old wizard page**

Delete `frontend/src/views/GuidedOnboardingWizardPage.vue` — it's fully replaced by WelcomePage + tour flow.

- [ ] **Step 2: Check for any imports or references**

Search for `GuidedOnboardingWizardPage` or `guided-onboarding-wizard` across the codebase and remove any remaining references.

- [ ] **Step 3: Run type check and tests**

Run: `just build && cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git rm frontend/src/views/GuidedOnboardingWizardPage.vue
git commit -m "chore: remove old GuidedOnboardingWizardPage, replaced by welcome + tour"
```

---

### Task 9: Full verification

- [ ] **Step 1: Run full backend tests**

Run: `cd backend && uv run pytest`
Expected: All pass

- [ ] **Step 2: Run full frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All pass

- [ ] **Step 3: Run production build**

Run: `just build`
Expected: vue-tsc type check passes, vite build succeeds

- [ ] **Step 4: Manual smoke test**

1. Delete the SQLite DB to simulate first run
2. Start backend and frontend (`just dev-backend` + `just dev-frontend`)
3. Open browser → should redirect to `/welcome`
4. Verify welcome page renders with correct branding and content
5. Click "Begin setup" → verify key generation works
6. Click "Continue" → verify tour starts on Settings page
7. Walk through all 8 steps, verify spotlight highlights correct elements
8. Verify skippable steps (6-8) show Skip button
9. Complete tour → verify landing on dashboard
10. Refresh page → verify tour doesn't restart (localStorage `tourComplete`)
