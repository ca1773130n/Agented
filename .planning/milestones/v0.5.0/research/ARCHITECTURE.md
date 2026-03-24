# Onboarding System Architecture Research

> Agented v0.5.0 -- Production-level onboarding for a Vue 3 + TypeScript dark-themed bot automation platform.
> Date: 2026-03-21

---

## Table of Contents

1. [State Machine Architecture](#1-state-machine-architecture)
2. [Component Architecture](#2-component-architecture)
3. [Animation & Transition Patterns](#3-animation--transition-patterns)
4. [Data-Driven Step Definitions](#4-data-driven-step-definitions)
5. [Persistence & Resume](#5-persistence--resume)
6. [Progressive Disclosure](#6-progressive-disclosure)
7. [Accessibility](#7-accessibility)
8. [Driver.js Alternatives](#8-driverjs-alternatives)
9. [Form Integration](#9-form-integration)
10. [Conditional Steps](#10-conditional-steps)

---

## 1. State Machine Architecture

### Recommendation: XState v5 (or manual finite-state machine)

The current `useTour.ts` uses flat index tracking (`currentStepIndex` / `currentSubstepIndex`) with ad-hoc branching. This breaks when steps are conditional, when the user can go backward, or when substeps have their own lifecycle (e.g., "fill form -> validate -> submit -> wait for response -> confirm").

**Use a hierarchical state machine** with the following states:

```
idle -> welcome -> setup -> complete
                     |
                     +-- workspace (atomic)
                     +-- backends (compound)
                     |     +-- claude -> codex -> gemini -> opencode
                     +-- monitoring (atomic)
                     +-- harness (atomic)
                     +-- product (compound)
                     |     +-- create -> configure
                     +-- project (compound)
                     |     +-- create -> configure
                     +-- team (compound)
                           +-- create -> assign
```

### Option A: XState v5 (Prescriptive Choice)

XState v5 is the production standard for UI state machines in TypeScript. It provides:

- **Hierarchical states** (compound states for multi-substep flows)
- **Guards** (conditional transitions: skip backend if already installed)
- **Actions** (side effects: navigate, persist, scroll to element)
- **Delays** (wait for element to appear in DOM before transitioning)
- **Snapshots** (serialize/deserialize for persistence)
- **Devtools** (visual state inspector during development)

```typescript
// composables/useTourMachine.ts
import { setup, createActor, assign } from 'xstate'
import { useActor } from '@xstate/vue'

const tourMachine = setup({
  types: {
    context: {} as {
      completedSteps: string[]
      currentFormField: number
      formFields: FormFieldDef[]
    },
    events: {} as
      | { type: 'NEXT' }
      | { type: 'SKIP' }
      | { type: 'BACK' }
      | { type: 'FIELD_COMPLETE'; fieldId: string }
      | { type: 'FORM_SUBMITTED' }
      | { type: 'ELEMENT_FOUND'; selector: string }
  },
  guards: {
    isBackendInstalled: ({ context }, { backendId }: { backendId: string }) => {
      // Check backend installation status from API cache
      return getBackendStatus(backendId) === 'installed'
    },
    hasMoreFields: ({ context }) => {
      return context.currentFormField < context.formFields.length - 1
    },
  },
  actions: {
    navigateTo: (_, { route }: { route: string }) => {
      router.push(route)
    },
    persistState: ({ context }) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(context))
    },
    scrollToTarget: (_, { selector }: { selector: string }) => {
      document.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    },
  },
}).createMachine({
  id: 'onboarding',
  initial: 'idle',
  states: {
    idle: {
      on: { START: 'welcome' },
    },
    welcome: {
      on: { NEXT: 'setup' },
    },
    setup: {
      initial: 'workspace',
      states: {
        workspace: {
          entry: [{ type: 'navigateTo', params: { route: '/settings#general' } }],
          on: {
            NEXT: 'backends',
            FIELD_COMPLETE: { actions: 'persistState' },
          },
        },
        backends: {
          initial: 'claude',
          states: {
            claude: {
              always: {
                guard: { type: 'isBackendInstalled', params: { backendId: 'claude' } },
                target: 'codex',
              },
              on: { NEXT: 'codex', SKIP: 'codex' },
            },
            codex: { /* ... */ },
            gemini: { /* ... */ },
            opencode: {
              on: { NEXT: '#onboarding.setup.monitoring' },
            },
          },
        },
        monitoring: { /* ... */ },
        harness: { /* ... */ },
        product: { /* ... */ },
        project: { /* ... */ },
        team: { /* ... */ },
        complete: { type: 'final' },
      },
      onDone: 'complete',
    },
    complete: {
      entry: ['persistState'],
      type: 'final',
    },
  },
})

// Vue composable wrapper
export function useTourMachine() {
  const actor = createActor(tourMachine)
  const { snapshot, send } = useActor(actor)

  return {
    state: computed(() => snapshot.value),
    send,
    isActive: computed(() => !snapshot.value.matches('idle') && !snapshot.value.matches('complete')),
    currentStepId: computed(() => {
      // Extract leaf state name from state value
      return getLeafState(snapshot.value.value)
    }),
  }
}
```

### Option B: Manual FSM (Lightweight Alternative)

If XState is too heavy (adds ~15KB gzipped), implement a minimal state machine:

```typescript
// composables/useTourFSM.ts
type State = string  // dot-notation: 'setup.backends.claude'
type Event = 'NEXT' | 'SKIP' | 'BACK' | 'FIELD_COMPLETE'

interface Transition {
  target: State
  guard?: () => boolean
  actions?: (() => void)[]
}

interface StateNode {
  on?: Record<Event, Transition | State>
  entry?: () => void
  exit?: () => void
  always?: Transition  // auto-transition (for conditional skipping)
  meta?: {
    route: string
    target: string
    title: string
    message: string
    skippable: boolean
  }
}

const states: Record<State, StateNode> = { /* ... */ }
```

### Verdict

**Use XState v5** (`@xstate/vue` for Vue integration). The onboarding flow is complex enough to justify it: substeps, conditional skipping, form field sequences, persistence, and backward navigation. XState's devtools will also accelerate debugging the "highlight doesn't match element" issues.

---

## 2. Component Architecture

### Recommendation: Custom overlay with portal pattern (no library)

The current implementation uses a bottom bar + spotlight overlay approach. This is a good foundation but needs restructuring.

### Architecture

```
App.vue
  +-- <Teleport to="body">
        +-- <OnboardingProvider>         (manages state machine, context)
              +-- <TourOverlay>          (dimming layer, event interception)
              +-- <TourSpotlight>        (positioned highlight around target)
              +-- <TourTooltip>          (popover with step info, anchored to target)
              +-- <TourProgressBar>      (bottom bar or sidebar progress)
              +-- <TourFormGuide>        (form field step-through sub-component)
```

### Component Responsibilities

**OnboardingProvider** (renderless / provide-inject):
- Owns the state machine instance
- Provides tour context to all children via `provide()`
- Handles route navigation on state transitions
- Manages element discovery (MutationObserver + polling fallback)

```typescript
// components/onboarding/OnboardingProvider.vue
<script setup lang="ts">
import { provide, watch } from 'vue'
import { useTourMachine } from '@/composables/useTourMachine'
import { TOUR_INJECTION_KEY } from '@/types/tour'

const { state, send, isActive, currentStepId } = useTourMachine()

provide(TOUR_INJECTION_KEY, {
  state,
  send,
  isActive,
  currentStepId,
})
</script>

<template>
  <slot />
  <Teleport to="body">
    <TourOverlay v-if="isActive" />
  </Teleport>
</template>
```

**TourSpotlight** (the highlight element):
- Uses `box-shadow: 0 0 0 9999px` technique (current approach -- keep it)
- Tracks target via `ResizeObserver` + `scroll` listener (more reliable than polling `getBoundingClientRect`)
- Uses CSS `transition` for smooth movement between targets
- Renders a `<div>` with `pointer-events: none` and a cutout

```typescript
// Improved target tracking using ResizeObserver
function useElementTracker(selector: Ref<string | null>) {
  const rect = ref<DOMRect | null>(null)
  let resizeObserver: ResizeObserver | null = null
  let mutationObserver: MutationObserver | null = null

  function track(el: HTMLElement) {
    cleanup()
    rect.value = el.getBoundingClientRect()

    // ResizeObserver catches layout changes
    resizeObserver = new ResizeObserver(() => {
      rect.value = el.getBoundingClientRect()
    })
    resizeObserver.observe(el)

    // Scroll listener for position changes
    const update = () => { rect.value = el.getBoundingClientRect() }
    window.addEventListener('scroll', update, { capture: true, passive: true })
    window.addEventListener('resize', update, { passive: true })
  }

  // MutationObserver to detect when element appears in DOM
  watch(selector, (sel) => {
    if (!sel) { cleanup(); return }
    const el = document.querySelector(sel) as HTMLElement | null
    if (el) {
      track(el)
    } else {
      // Wait for element to appear
      mutationObserver = new MutationObserver(() => {
        const found = document.querySelector(sel) as HTMLElement | null
        if (found) {
          mutationObserver?.disconnect()
          track(found)
        }
      })
      mutationObserver.observe(document.body, { childList: true, subtree: true })
    }
  }, { immediate: true })

  return { rect }
}
```

**TourTooltip** (the instruction popover):
- Positioned using **Floating UI** (`@floating-ui/vue`) -- anchored to target element
- Supports 12 placement positions with auto-flip
- Contains: title, message, action buttons, progress indicator
- Dark glass-morphism styling to match the app aesthetic

```typescript
// components/onboarding/TourTooltip.vue
<script setup lang="ts">
import { useFloating, autoUpdate, offset, flip, shift } from '@floating-ui/vue'

const props = defineProps<{
  referenceEl: HTMLElement | null
  title: string
  message: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
}>()

const { floatingStyles } = useFloating(
  () => props.referenceEl,
  tooltipRef,
  {
    placement: props.placement ?? 'bottom',
    middleware: [offset(12), flip(), shift({ padding: 16 })],
    whileElementsMounted: autoUpdate,
  }
)
</script>
```

### Why Not Inline or Sidebar?

- **Inline hints** (coachmarks next to elements) are good for feature discovery in an already-learned app, not initial onboarding. They clutter the UI.
- **Sidebar checklist** is good as a progress indicator but insufficient alone -- users need directional guidance to the actual UI elements.
- **Overlay + tooltip** is the correct pattern for first-run onboarding because it focuses attention and prevents the user from getting lost.

**Use overlay + tooltip + progress bar (bottom or sidebar).** The bottom bar from the current implementation works well; add a tooltip anchored to the target element for context.

---

## 3. Animation & Transition Patterns

### Spotlight Movement

The current implementation transitions spotlight position with `transition: top/left/width/height 300ms ease`. This is correct but can be improved:

```css
.tour-spotlight {
  /* Use transform for GPU-accelerated movement */
  position: fixed;
  /* Instead of animating top/left/width/height individually,
     use a single transform + clip-path approach */
  transition: all 350ms cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform, width, height, top, left;
}
```

### Step Transitions

When moving between steps, use a three-phase animation:

```typescript
// 1. Fade out current tooltip (150ms)
// 2. Move spotlight to new target (350ms)  -- can overlap with fade-out
// 3. Fade in new tooltip (200ms) -- after spotlight arrives

const TRANSITION = {
  tooltipExit: 150,
  spotlightMove: 350,
  tooltipEnter: 200,
  // Total perceived: ~500ms (overlapping)
}
```

### Vue Transition Components

```vue
<!-- TourTooltip with enter/leave transitions -->
<Transition name="tooltip" mode="out-in">
  <div v-if="showTooltip" :key="stepId" class="tour-tooltip" :style="floatingStyles">
    <!-- content -->
  </div>
</Transition>

<style>
.tooltip-enter-active {
  transition: opacity 200ms ease-out, transform 200ms ease-out;
}
.tooltip-leave-active {
  transition: opacity 150ms ease-in, transform 150ms ease-in;
}
.tooltip-enter-from {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}
.tooltip-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
```

### Glow Animation

The current pulsing glow (`tour-glow` keyframes) is good. Enhance with a subtle breathing effect:

```css
.tour-spotlight-ring {
  position: absolute;
  inset: -3px;
  border-radius: inherit;
  border: 1.5px solid rgba(99, 102, 241, 0.6);
  animation: spotlight-breathe 2s ease-in-out infinite;
}

@keyframes spotlight-breathe {
  0%, 100% {
    box-shadow: 0 0 8px 2px rgba(99, 102, 241, 0.3);
    border-color: rgba(99, 102, 241, 0.5);
  }
  50% {
    box-shadow: 0 0 20px 4px rgba(99, 102, 241, 0.5);
    border-color: rgba(99, 102, 241, 0.8);
  }
}

/* Respect user preference */
@media (prefers-reduced-motion: reduce) {
  .tour-spotlight-ring {
    animation: none;
    box-shadow: 0 0 8px 2px rgba(99, 102, 241, 0.3);
  }
}
```

### Micro-interactions

- **Button hover**: Scale 1.02 + slight brightness increase
- **Step counter update**: Number flip animation (CSS `@keyframes` or `<Transition>`)
- **Progress bar fill**: Smooth width transition with ease-out curve
- **Target element**: Add a subtle `ring` class to the target element itself (not just the overlay) for extra visibility

```css
/* Added to target elements during tour */
[data-tour-active] {
  position: relative;
  z-index: 10002; /* Above overlay dimming */
}
```

---

## 4. Data-Driven Step Definitions

### Recommendation: TypeScript config objects with runtime auto-discovery

The current approach hardcodes steps in `useTour.ts`. This works for the main step sequence but fails for form fields (which vary by page). Use a **hybrid approach**:

### Layer 1: Static Step Registry (config)

```typescript
// config/tourSteps.ts
import type { TourStepDef } from '@/types/tour'

export const TOUR_STEPS: TourStepDef[] = [
  {
    id: 'workspace',
    phase: 'setup',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="workspace-root"]',
    title: 'Workspace Directory',
    message: 'Set the root directory where repos will be cloned.',
    skippable: false,
    formGuide: true,  // triggers auto-discovery of form fields within target
    waitForElement: true,
    condition: undefined,  // always show
  },
  {
    id: 'backends',
    phase: 'setup',
    route: '/backends/backend-claude',
    target: '[data-tour="backend-section"]',
    title: 'AI Backend Accounts',
    message: 'Register accounts for each AI backend.',
    skippable: true,
    formGuide: true,
    condition: { type: 'api', check: 'backends.needsSetup' },
    substeps: [
      { id: 'claude',   route: '/backends/backend-claude',   label: 'Claude Code' },
      { id: 'codex',    route: '/backends/backend-codex',    label: 'Codex CLI' },
      { id: 'gemini',   route: '/backends/backend-gemini',   label: 'Gemini CLI' },
      { id: 'opencode', route: '/backends/backend-opencode', label: 'OpenCode' },
    ],
  },
  // ... more steps
]
```

### Layer 2: Runtime Auto-Discovery (for form fields)

When a step has `formGuide: true`, the system scans the target's DOM subtree for form elements:

```typescript
// composables/useFormFieldDiscovery.ts
export interface DiscoveredField {
  element: HTMLElement
  selector: string
  label: string
  type: 'input' | 'select' | 'textarea' | 'checkbox' | 'button'
  required: boolean
}

export function discoverFormFields(container: HTMLElement): DiscoveredField[] {
  const fields: DiscoveredField[] = []

  // Strategy 1: .form-group pattern (Agented's convention)
  const formGroups = container.querySelectorAll('.form-group')
  formGroups.forEach((group, i) => {
    const label = group.querySelector('label')?.textContent?.trim() ?? `Field ${i + 1}`
    const input = group.querySelector('input, select, textarea') as HTMLElement | null
    if (input) {
      fields.push({
        element: input,
        selector: buildUniqueSelector(input),
        label,
        type: getFieldType(input),
        required: input.hasAttribute('required'),
      })
    }
  })

  // Strategy 2: data-tour-field attributes (explicit marking)
  const explicit = container.querySelectorAll('[data-tour-field]')
  explicit.forEach((el) => {
    const htmlEl = el as HTMLElement
    if (!fields.some(f => f.element === htmlEl)) {
      fields.push({
        element: htmlEl,
        selector: buildUniqueSelector(htmlEl),
        label: htmlEl.getAttribute('data-tour-field') || htmlEl.getAttribute('aria-label') || '',
        type: getFieldType(htmlEl),
        required: htmlEl.hasAttribute('required'),
      })
    }
  })

  // Strategy 3: Submit button (always last)
  const submitBtn = container.querySelector('button[type="submit"], [data-tour="save-btn"]') as HTMLElement | null
  if (submitBtn) {
    fields.push({
      element: submitBtn,
      selector: buildUniqueSelector(submitBtn),
      label: submitBtn.textContent?.trim() ?? 'Submit',
      type: 'button',
      required: false,
    })
  }

  return fields
}

function buildUniqueSelector(el: HTMLElement): string {
  // Prefer data attributes for stability
  if (el.id) return `#${el.id}`
  if (el.getAttribute('data-tour')) return `[data-tour="${el.getAttribute('data-tour')}"]`
  if (el.getAttribute('name')) return `[name="${el.getAttribute('name')}"]`
  // Fallback: nth-child path
  return generateNthChildPath(el)
}
```

### Layer 3: Step Metadata Type

```typescript
// types/tour.ts
export interface TourStepDef {
  id: string
  phase: 'welcome' | 'setup' | 'firstRun' | 'advanced'
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  formGuide?: boolean           // auto-discover form fields
  waitForElement?: boolean      // wait for target to appear (lazy-loaded pages)
  condition?: StepCondition     // conditional display
  substeps?: SubstepDef[]       // explicit sub-navigation
  placement?: 'top' | 'bottom' | 'left' | 'right'
  action?: 'click' | 'fill' | 'observe'  // what user should do
}

export interface StepCondition {
  type: 'api' | 'localStorage' | 'dom'
  check: string                 // dot-path or selector
  negate?: boolean              // skip when condition is TRUE
}

export interface SubstepDef {
  id: string
  route: string
  label: string
  condition?: StepCondition
}
```

---

## 5. Persistence & Resume

### Problem

Current implementation saves to `localStorage` but has conflicts with DB resets (issue #9 from user feedback). The tour state and app state can desync.

### Recommendation: Dual-layer persistence with version tagging

```typescript
// composables/useTourPersistence.ts
const STORAGE_KEY = 'agented-onboarding-v2'

interface PersistedTourState {
  version: number               // schema version (bump to invalidate)
  appInstanceId: string         // unique per DB instance (detect resets)
  machineState: string          // serialized XState snapshot
  completedSteps: string[]
  skippedSteps: string[]
  formFieldProgress: Record<string, string[]>  // stepId -> completed fieldIds
  lastActiveAt: string          // ISO timestamp
}

export function useTourPersistence() {
  function save(state: PersistedTourState) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  }

  function load(): PersistedTourState | null {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedTourState

    // Version mismatch: discard
    if (parsed.version !== CURRENT_VERSION) return null

    // App instance mismatch (DB was reset): discard
    if (parsed.appInstanceId !== getAppInstanceId()) {
      localStorage.removeItem(STORAGE_KEY)
      return null
    }

    return parsed
  }

  function clear() {
    localStorage.removeItem(STORAGE_KEY)
  }

  return { save, load, clear }
}

// The app instance ID is fetched from the backend on startup.
// When `just reset` clears the DB, the instance ID changes,
// automatically invalidating stale tour state.
async function getAppInstanceId(): Promise<string> {
  const res = await fetch('/api/instance-id')
  const data = await res.json()
  return data.instanceId  // Generated once in DB init, persisted in DB
}
```

### Backend Support

Add a simple `instance_id` to the database initialization:

```python
# app/database.py -- in init_db()
import uuid

def init_db():
    with get_connection() as conn:
        # ... existing table creation ...
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        # Generate instance ID if not exists
        existing = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'instance_id'"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES ('instance_id', ?)",
                (str(uuid.uuid4()),)
            )
```

### Resume Flow

On app load:
1. Fetch `instance_id` from backend
2. Load persisted state from localStorage
3. If `instanceId` matches and state exists -> resume from saved state
4. If mismatch or no state -> check if onboarding is needed (API: `needs_setup`)
5. If `needs_setup` -> start fresh onboarding
6. If not `needs_setup` -> do nothing (user already set up)

---

## 6. Progressive Disclosure

### Pattern: Phase-based onboarding

Not all setup needs to happen at once. Split onboarding into phases:

```typescript
enum OnboardingPhase {
  ESSENTIAL = 'essential',   // workspace, 1 backend account
  RECOMMENDED = 'recommended', // monitoring, harness plugins
  FIRST_RUN = 'firstRun',    // create product, project, team
  ADVANCED = 'advanced',     // hooks, rules, schedules (triggered later)
}
```

### Implementation

**Phase 1 (Essential):** Runs on first visit. Blocks usage until complete.
- Set workspace directory
- Register at least one backend account

**Phase 2 (Recommended):** Runs after Phase 1. Optional but encouraged.
- Enable token monitoring
- Verify harness plugins
- Shown as a checklist in a sidebar panel, not a blocking overlay

**Phase 3 (First Run):** Triggered when user navigates to relevant pages for the first time.
- "Create your first product" -- shown when user visits /products and has 0 products
- "Create a project" -- shown after product exists
- "Create a team" -- shown after project exists

**Phase 4 (Advanced):** Contextual tips, not a guided tour.
- Feature coachmarks that appear once per feature
- Triggered by user actions, not a linear sequence

```typescript
// composables/useContextualHints.ts
export function useContextualHint(featureId: string) {
  const dismissed = ref(false)
  const shown = ref(false)

  onMounted(() => {
    const hints = JSON.parse(localStorage.getItem('agented-hints') || '{}')
    if (!hints[featureId]) {
      shown.value = true
    }
  })

  function dismiss() {
    shown.value = false
    dismissed.value = true
    const hints = JSON.parse(localStorage.getItem('agented-hints') || '{}')
    hints[featureId] = Date.now()
    localStorage.setItem('agented-hints', JSON.stringify(hints))
  }

  return { shown: readonly(shown), dismiss }
}
```

### UI for Progress

A sidebar progress panel (collapsible) shows overall onboarding completion:

```
Setup Progress
------------------
[x] Workspace directory
[x] AI backend (1/4)
[ ] Token monitoring
[ ] Harness plugins
------------------
[~] Create product      <- grayed, Phase 3
[~] Create project
[~] Create team
```

This panel is accessible from the sidebar and auto-opens during guided steps.

---

## 7. Accessibility

### ARIA Patterns for Guided Tours

The tour overlay creates a modal-like experience. Apply dialog semantics:

```vue
<template>
  <div
    v-if="isActive"
    role="dialog"
    aria-modal="true"
    aria-label="Setup guide"
    aria-describedby="tour-step-message"
  >
    <!-- Dimming overlay -->
    <div aria-hidden="true" class="tour-dim" />

    <!-- Tooltip (receives focus) -->
    <div
      ref="tooltipRef"
      role="alertdialog"
      :aria-label="currentStep.title"
      tabindex="-1"
    >
      <h2 id="tour-step-title">{{ currentStep.title }}</h2>
      <p id="tour-step-message">{{ currentStep.message }}</p>

      <div role="group" aria-label="Tour navigation">
        <button v-if="canSkip" @click="skip">Skip this step</button>
        <button v-if="canGoBack" @click="back">Previous</button>
        <button @click="next" ref="nextBtnRef">
          {{ isLastStep ? 'Finish' : 'Next' }}
        </button>
      </div>

      <p aria-live="polite" class="sr-only">
        Step {{ stepNumber }} of {{ totalSteps }}: {{ currentStep.title }}
      </p>
    </div>
  </div>
</template>
```

### Keyboard Navigation

```typescript
function handleKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'Escape':
      // Don't dismiss immediately -- show confirmation if step is not skippable
      if (currentStep.value?.skippable) {
        showSkipConfirmation()
      }
      break
    case 'Tab':
      // Trap focus within tooltip + target element
      trapFocus(e, [tooltipRef.value, targetEl.value])
      break
    case 'Enter':
      // If focus is on next button, advance
      if (document.activeElement === nextBtnRef.value) {
        next()
      }
      break
    case 'ArrowRight':
      next()
      break
    case 'ArrowLeft':
      if (canGoBack.value) back()
      break
  }
}

// Focus trap: allow Tab between tooltip controls and the target element
function trapFocus(e: KeyboardEvent, containers: (HTMLElement | null)[]) {
  const focusable = containers
    .filter(Boolean)
    .flatMap(c => [...c!.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )])

  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]

  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}
```

### Screen Reader Announcements

```typescript
// Use an aria-live region for step changes
function announceStep(step: TourStepDef) {
  const announcer = document.getElementById('tour-announcer')
  if (announcer) {
    announcer.textContent = '' // Clear first to trigger re-announcement
    requestAnimationFrame(() => {
      announcer.textContent = `Step ${stepNumber} of ${totalSteps}: ${step.title}. ${step.message}`
    })
  }
}
```

```html
<!-- In App.vue, always present -->
<div id="tour-announcer" aria-live="assertive" class="sr-only" />
```

### Focus Management

- When a step activates, move focus to the tooltip
- When the tooltip has a "Next" button, it should be the default focus target
- When highlighting a form field, the field itself should receive focus
- On tour end, return focus to the element that triggered the tour (or main content)

---

## 8. Driver.js Alternatives

### Comparison Matrix

| Feature | driver.js | shepherd.js | intro.js | Custom CSS |
|---|---|---|---|---|
| **Size (gzip)** | ~5KB | ~25KB | ~8KB | 0KB |
| **Vue 3 support** | Vanilla only | @shepherdpro/vue | Vanilla only | Native |
| **Dark theme** | CSS override | CSS override | CSS override | Native |
| **Form interaction** | Poor (blocks clicks) | Good (attachTo) | Poor | Full control |
| **Spotlight accuracy** | Padding issues | Good | Basic | Full control |
| **Step-by-step forms** | Not designed for it | Possible | Not designed for it | Full control |
| **State machine** | None | None | None | BYO |
| **Keyboard nav** | Basic | Good | Basic | BYO |
| **Scroll handling** | Auto | Auto | Auto | BYO |
| **Custom positioning** | Limited | Floating UI | CSS | Full control |
| **Maintenance** | Active | Active | Stale | N/A |

### Analysis

**driver.js** -- Currently installed. Issues from user testing:
- `stagePadding` / `stageRadius` don't align with actual element boundaries on dark backgrounds
- Close button (X) interferes with tour flow
- Clicking outside dismisses without confirmation
- No form field guidance -- it highlights but blocks interaction
- Styling overrides are fragile (fights the library's defaults)

**shepherd.js** -- Most feature-complete library:
- Has `@shepherdpro/vue` package with Vue 3 support
- `attachTo` properly positions tooltips relative to targets
- Allows interaction with highlighted elements via `canClickTarget: true`
- Built-in accessibility (aria attributes, focus management)
- BUT: Large bundle size (25KB), opinionated styling that fights dark themes, still no state machine

**intro.js** -- Legacy, not recommended:
- Stale maintenance
- Poor TypeScript support
- No form interaction support

**Custom CSS overlay** -- The current approach, refined:
- Zero dependency overhead
- Full control over every pixel (critical for the dark theme aesthetic)
- Native Vue 3 integration (transitions, teleport, provide/inject)
- Can implement exact form field guidance needed
- Requires implementing scroll handling, positioning, and accessibility from scratch

### Verdict: Custom Implementation + Floating UI

**Drop driver.js. Build a custom overlay system.**

Rationale:
1. The user feedback explicitly identifies driver.js issues (padding, X button, click-to-dismiss)
2. The dark theme aesthetic demands pixel-perfect control
3. Form field step-through requires the overlay to NOT block interaction
4. The state machine (XState) handles all flow logic -- the overlay is purely visual
5. **Floating UI** (`@floating-ui/vue`, ~3KB) handles tooltip positioning -- the hardest part to get right

The current `TourOverlay.vue` already has 80% of the visual layer. It needs:
- Floating UI for tooltip positioning (replace manual rect calculations)
- ResizeObserver for target tracking (replace MutationObserver polling)
- Proper z-index management for interactive elements
- Transition orchestration (spotlight move -> tooltip fade)

```bash
# Remove driver.js, add Floating UI
npm uninstall driver.js
npm install @floating-ui/vue
npm install xstate @xstate/vue  # if using XState
```

---

## 9. Form Integration

### The Core Problem

Current tour highlights the "Add Account" button but doesn't guide through the form fields. Users need field-by-field guidance: account name -> email -> config path -> API key -> save.

### Architecture: TourFormGuide Component

```typescript
// components/onboarding/TourFormGuide.vue
<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { discoverFormFields, type DiscoveredField } from '@/composables/useFormFieldDiscovery'
import { inject } from 'vue'
import { TOUR_INJECTION_KEY } from '@/types/tour'

const tour = inject(TOUR_INJECTION_KEY)!

const fields = ref<DiscoveredField[]>([])
const currentFieldIndex = ref(0)
const currentField = computed(() => fields.value[currentFieldIndex.value] ?? null)

// Discover fields when the step container is rendered
watch(() => tour.currentStepId.value, async (stepId) => {
  const stepDef = getStepDef(stepId)
  if (!stepDef?.formGuide) {
    fields.value = []
    return
  }

  // Wait for the DOM to settle (lazy-loaded page)
  await waitForElement(stepDef.target)
  const container = document.querySelector(stepDef.target) as HTMLElement
  if (!container) return

  fields.value = discoverFormFields(container)
  currentFieldIndex.value = 0
}, { immediate: true })

function advanceField() {
  if (currentFieldIndex.value < fields.value.length - 1) {
    currentFieldIndex.value++
    focusCurrentField()
  } else {
    // All fields done, advance to next tour step
    tour.send({ type: 'NEXT' })
  }
}

function focusCurrentField() {
  const field = currentField.value
  if (!field) return
  field.element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  // Focus the input after scroll completes
  setTimeout(() => field.element.focus(), 400)
}
</script>
```

### Interaction Model

The key insight: **the overlay must allow interaction with the highlighted element**.

```css
/* The spotlight cutout area allows pointer events */
.tour-spotlight {
  /* ... existing spotlight styles ... */
  pointer-events: none;
}

/* The target element is elevated above the overlay */
.tour-overlay [data-tour-active] {
  position: relative;
  z-index: 10002; /* Above the dimming layer */
  pointer-events: auto;
}
```

But we can't just set `z-index` on arbitrary elements -- it breaks stacking contexts. Instead, use a **clone approach** or **CSS isolation**:

### Approach: Elevate via CSS isolation

```typescript
function elevateElement(el: HTMLElement) {
  // Find the nearest positioned ancestor and temporarily elevate it
  const positioned = findPositionedAncestor(el)
  const originalZIndex = positioned.style.zIndex
  const originalPosition = positioned.style.position

  positioned.style.position = positioned.style.position || 'relative'
  positioned.style.zIndex = '10002'

  return () => {
    positioned.style.zIndex = originalZIndex
    positioned.style.position = originalPosition
  }
}

// In the tour system:
let restoreElevation: (() => void) | null = null

watch(currentField, (field) => {
  restoreElevation?.()
  if (field) {
    restoreElevation = elevateElement(field.element)
  }
})
```

### Form Validation During Tour

When the user fills a field and moves to the next, validate:

```typescript
function validateField(field: DiscoveredField): boolean {
  const el = field.element as HTMLInputElement
  if (field.required && !el.value?.trim()) {
    // Show inline validation message
    showFieldError(el, `${field.label} is required`)
    return false
  }
  return true
}

// On "Next Field" click:
function handleNextField() {
  const field = currentField.value
  if (field && field.type !== 'button') {
    if (!validateField(field)) return
  }
  advanceField()
}
```

### Auto-advance on Interaction

For certain field types, auto-advance when the user interacts:

```typescript
// Watch for user interaction with current field
function watchFieldInteraction(field: DiscoveredField) {
  const el = field.element

  if (field.type === 'button') {
    // Auto-advance when button is clicked
    const handler = () => {
      el.removeEventListener('click', handler)
      // Wait for form submission effect
      setTimeout(advanceField, 500)
    }
    el.addEventListener('click', handler)
    return () => el.removeEventListener('click', handler)
  }

  if (field.type === 'select') {
    // Auto-advance when selection changes
    const handler = () => {
      el.removeEventListener('change', handler)
      setTimeout(advanceField, 300)
    }
    el.addEventListener('change', handler)
    return () => el.removeEventListener('change', handler)
  }

  // For text inputs: no auto-advance, require explicit "Next" click
  return () => {}
}
```

---

## 10. Conditional Steps

### Problem

Some steps should be skipped based on application state:
- Skip Claude backend setup if Claude Code is already installed and configured
- Skip "Create product" if products already exist
- Skip workspace setup if workspace is already configured

### Architecture: Guard Functions

Each step can define one or more guards. Guards are evaluated before entering the step:

```typescript
// config/tourGuards.ts
import type { StepCondition } from '@/types/tour'

type GuardFn = () => boolean | Promise<boolean>

const guardRegistry: Record<string, GuardFn> = {
  'backends.claude.needed': async () => {
    const res = await fetch('/admin/backends/backend-claude')
    const data = await res.json()
    return !data.is_installed || data.accounts.length === 0
  },

  'backends.codex.needed': async () => {
    const res = await fetch('/admin/backends/backend-codex')
    const data = await res.json()
    return !data.is_installed || data.accounts.length === 0
  },

  'workspace.needed': async () => {
    const res = await fetch('/admin/settings')
    const data = await res.json()
    return !data.workspace_root
  },

  'products.empty': async () => {
    const res = await fetch('/admin/products')
    const data = await res.json()
    return data.products.length === 0
  },

  'monitoring.needed': async () => {
    const res = await fetch('/admin/settings')
    const data = await res.json()
    return !data.token_monitoring_enabled
  },
}

export async function evaluateGuard(condition: StepCondition): Promise<boolean> {
  const guardFn = guardRegistry[condition.check]
  if (!guardFn) {
    console.warn(`Unknown guard: ${condition.check}`)
    return true // Show step if guard is unknown
  }
  const result = await guardFn()
  return condition.negate ? !result : result
}
```

### Integration with State Machine

In XState, guards are first-class:

```typescript
// In the machine definition:
states: {
  backends: {
    initial: 'checking',
    states: {
      checking: {
        // Evaluate all backend conditions on entry
        invoke: {
          src: 'checkBackendStatus',
          onDone: [
            { target: 'claude', guard: 'claudeNeeded' },
            { target: 'codex', guard: 'codexNeeded' },
            { target: 'gemini', guard: 'geminiNeeded' },
            { target: 'opencode', guard: 'opencodeNeeded' },
            { target: '#onboarding.setup.monitoring' }, // All installed, skip
          ],
        },
      },
      claude: {
        on: { NEXT: 'codex', SKIP: 'codex' },
      },
      // ...
    },
  },
}
```

### Prefetching Guard Data

To avoid showing a loading spinner at every conditional step, prefetch all guard data at tour start:

```typescript
// composables/useTourGuards.ts
export function useTourGuards() {
  const guardCache = ref<Record<string, boolean>>({})
  const loading = ref(true)

  async function prefetchAll() {
    loading.value = true
    const [backends, settings, products] = await Promise.all([
      fetch('/admin/backends').then(r => r.json()),
      fetch('/admin/settings').then(r => r.json()),
      fetch('/admin/products').then(r => r.json()),
    ])

    guardCache.value = {
      'backends.claude.needed': !backends.find(
        (b: any) => b.id === 'backend-claude' && b.is_installed && b.accounts.length > 0
      ),
      'backends.codex.needed': !backends.find(
        (b: any) => b.id === 'backend-codex' && b.is_installed && b.accounts.length > 0
      ),
      'workspace.needed': !settings.workspace_root,
      'monitoring.needed': !settings.token_monitoring_enabled,
      'products.empty': products.products.length === 0,
    }
    loading.value = false
  }

  function check(guardId: string): boolean {
    return guardCache.value[guardId] ?? true
  }

  return { prefetchAll, check, loading }
}
```

---

## Summary of Prescriptive Decisions

| Decision | Choice | Rationale |
|---|---|---|
| State management | XState v5 + @xstate/vue | Complex flow with conditions, substeps, persistence |
| Overlay library | Custom (drop driver.js) | Full control, dark theme, form interaction |
| Tooltip positioning | @floating-ui/vue | Lightweight, battle-tested, Vue 3 native |
| Step definitions | TypeScript config + runtime auto-discovery | Static for flow, dynamic for form fields |
| Persistence | localStorage + backend instance ID | Survives refresh, invalidates on DB reset |
| Form guidance | Auto-discover .form-group + elevate z-index | Matches app conventions, allows interaction |
| Accessibility | ARIA dialog + focus trap + live regions | Standards compliance |
| Progressive disclosure | 4 phases (essential/recommended/firstRun/advanced) | Don't overwhelm on first visit |
| Animations | CSS transitions + Vue `<Transition>` | GPU-accelerated, respects reduced-motion |
| Conditional steps | XState guards + prefetched API data | No loading spinners mid-tour |

### New Dependencies

```
@floating-ui/vue    ~3KB gzip   (tooltip positioning)
xstate              ~15KB gzip  (state machine)
@xstate/vue         ~2KB gzip   (Vue integration)
```

### Removed Dependencies

```
driver.js           ~5KB gzip   (replaced by custom overlay)
```

### File Structure

```
frontend/src/
  components/
    onboarding/
      OnboardingProvider.vue    # State machine owner, provide/inject
      TourOverlay.vue           # Dimming layer
      TourSpotlight.vue         # Highlight ring around target
      TourTooltip.vue           # Instruction popover (Floating UI)
      TourProgressBar.vue       # Bottom bar or sidebar progress
      TourFormGuide.vue         # Form field step-through
      TourSkipConfirmation.vue  # "Skip this step?" dialog
  composables/
    useTourMachine.ts           # XState machine definition + Vue wrapper
    useTourPersistence.ts       # localStorage + instance ID
    useTourGuards.ts            # Conditional step evaluation
    useFormFieldDiscovery.ts    # Auto-discover form fields in DOM
    useElementTracker.ts        # ResizeObserver-based rect tracking
    useContextualHints.ts       # Phase 4 feature coachmarks
  config/
    tourSteps.ts                # Static step registry
    tourGuards.ts               # Guard function registry
  types/
    tour.ts                     # All tour-related TypeScript types
```
