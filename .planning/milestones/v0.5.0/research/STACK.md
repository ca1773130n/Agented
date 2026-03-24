# Onboarding Stack Research

> Evaluated 2026-03-21 for Agented (Vue 3.5 + TypeScript, dark theme, Geist font family)

---

## 1. Tour / Guide Libraries

### 1a. driver.js

| Attribute | Value |
|---|---|
| npm | `driver.js` |
| Version | 1.4.0 (published 2025-11-18) |
| License | MIT |
| Bundle | ~5 KB gzipped, 83 KB unpacked |
| GitHub | 25.3k stars |
| Framework | Framework-agnostic (vanilla JS/TS) |

**How it works:** Renders a full-page SVG overlay with a cutout around the highlighted element, plus a popover tooltip anchored to that cutout. Steps are defined as a plain JS array. No Vue wrapper needed; you call `driver()` and `.drive()` imperatively.

**Dark theme support:** No built-in dark theme, but fully customizable via CSS. You set `popoverClass: 'my-theme'` globally or per-step, then override `.driver-popover`, `.driver-popover-title`, `.driver-popover-description`, `.driver-popover-next-btn`, etc. The overlay color is configurable via `overlayColor` and `overlayOpacity` options. This is a strength: total control, no fighting defaults.

**Pros:**
- Tiny bundle (~5 KB gzip) -- smallest in category by far
- Zero dependencies
- Written in TypeScript with full type definitions
- `onPopoverRender` hook gives raw DOM access for total popover customization
- Supports animated transitions between steps out of the box
- Async step support via `onNextClick` / `onPrevClick` callbacks
- Can highlight without popover (spotlight-only mode)
- Active maintenance (last publish Nov 2025)
- MIT license, no commercial restrictions

**Cons:**
- No official Vue wrapper -- integration is imperative, not declarative
- Cannot render Vue components inside popovers natively (must use `onPopoverRender` + `createApp` or raw DOM)
- No built-in progress indicators (must implement via `onPopoverRender`)
- Single maintainer project (kamranahmedse)
- Highlight relies on SVG overlay, which occasionally has stacking-context issues with `position: fixed` elements

**Current project status:** `driver.js@^1.4.0` is already in `package.json` dependencies but is NOT imported anywhere in source code. The current tour implementation (`TourOverlay.vue` + `useTour.ts`) is entirely custom, using `box-shadow: 0 0 0 9999px` for the overlay and manual `getBoundingClientRect()` tracking.

---

### 1b. shepherd.js + vue-shepherd

| Attribute | Value |
|---|---|
| npm | `shepherd.js` + `vue-shepherd` |
| Version | 15.2.2 / 6.0.0 (published 2026-03-11) |
| License | **AGPL-3.0** (dual-licensed; commercial license required for revenue-generating projects) |
| Bundle | ~656 KB unpacked (shepherd.js alone) |
| GitHub | ~13k stars |
| Framework | Vue wrapper via `vue-shepherd` with `useShepherd` composable |

**How it works:** Tour steps are JS objects; Shepherd creates popover elements anchored via Floating UI (formerly Popper.js). `vue-shepherd` provides a `useShepherd` composable for Composition API and `VueShepherdPlugin` for Options API.

**Pros:**
- Official Vue 3 wrapper with Composition API support
- Active maintenance (latest release 10 days ago)
- Floating UI positioning is robust against edge cases
- Rich event system (show, hide, cancel, complete per step)
- Built-in progress indicator support
- Accessibility: manages focus, supports keyboard navigation

**Cons:**
- **AGPL-3.0 license** -- commercial use requires a paid license. This is a dealbreaker for most proprietary projects.
- Significantly larger bundle (~12x driver.js)
- Floating UI dependency adds complexity
- Overlay implementation is less polished than driver.js (no smooth SVG cutout)
- Dark theme requires manual CSS overrides (no built-in theme)

---

### 1c. v-onboarding

| Attribute | Value |
|---|---|
| npm | `v-onboarding` |
| Version | 2.12.2 (published 2026-01-23) |
| License | MIT |
| Bundle | 86 KB unpacked |
| Framework | Vue 3 native (component + composable) |

**How it works:** Vue 3 component with slots for full template customization. Uses `<VOnboardingWrapper>` and `<VOnboardingStep>` components. Exposes a composable for programmatic control.

**Pros:**
- Built specifically for Vue 3 with TypeScript support
- Slot-based customization -- render any Vue component inside steps
- Lightweight, similar size to driver.js
- MIT license
- Active maintenance (Jan 2026 release)
- Nuxt 3 auto-import support

**Cons:**
- Much smaller community (~1k stars) than driver.js or shepherd
- Less battle-tested at scale
- Documentation is thin compared to driver.js
- Overlay implementation is basic
- Limited animation options between steps

---

### 1d. Custom CSS Overlay (Current Approach)

The project currently uses a custom overlay implementation with `box-shadow: 0 0 0 9999px rgba(0,0,0,0.7)` for the dimming effect, manual `getBoundingClientRect()` for positioning, and `MutationObserver` for dynamic target detection.

**When to use custom:**
- When the tour has complex multi-page routing logic (this project does)
- When tour steps require form interaction before advancing (this project does)
- When the visual design is highly specific and no library's DOM structure fits
- When bundle size is critical

**When NOT to use custom:**
- Popover positioning edge cases (viewport boundaries, scroll containers) require significant effort to handle correctly
- Accessibility (focus trapping, ARIA announcements) must be built from scratch
- Animation between steps requires manual implementation

---

### Recommendation: **driver.js (already installed) + custom overlay hybrid**

**Rationale:**

1. **driver.js is already a dependency.** It is in `package.json` but unused. The current custom overlay handles the multi-page routing and form-interaction logic well, but lacks popover positioning, accessibility, and polished animations.

2. **AGPL kills Shepherd.** The license requirement makes it unsuitable unless a commercial license is purchased.

3. **v-onboarding is too immature.** Small community, thin docs, unproven at scale.

4. **The hybrid approach:** Keep the custom `useTour.ts` composable for multi-page step orchestration (routing, substeps, persistence). Use driver.js for the visual layer: overlay rendering, spotlight cutouts, popover positioning, and step-to-step animations. This gives us battle-tested rendering with our custom orchestration logic.

**Implementation pattern:**
```typescript
// useTour.ts orchestrates routing + state
// useDriverOverlay.ts wraps driver.js for the visual layer
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'

// Custom dark theme via popoverClass
const driverObj = driver({
  popoverClass: 'agented-tour-popover',
  overlayColor: 'rgb(0, 0, 0)',
  overlayOpacity: 0.75,
  stagePadding: 8,
  stageRadius: 8,
  animate: true,
  smoothScroll: true,
  onPopoverRender: (popover, { config, state }) => {
    // Inject custom progress bar, step counter, etc.
  },
})
```

**Install:** Already installed. `driver.js@^1.4.0` (MIT, ~5 KB gzip).

---

## 2. Animation Libraries

### 2a. Vue Transition / TransitionGroup (built-in)

**What it is:** Vue's built-in `<Transition>` and `<TransitionGroup>` components apply CSS classes on enter/leave/move.

**Pros:**
- Zero additional dependencies
- Deeply integrated with Vue's reactivity and virtual DOM
- Sufficient for fade, slide, scale micro-interactions
- Works with `v-if`, `v-show`, `<component :is>`
- SSR compatible

**Cons:**
- Limited to enter/leave/move lifecycle -- no spring physics, no scroll-triggered animations
- Complex choreographed sequences require manual CSS or JS hooks
- No stagger built-in (must use `TransitionGroup` with index-based delays)

**Best for:** Step transitions, popover enter/exit, progress bar fills.

---

### 2b. @vueuse/motion

| Attribute | Value |
|---|---|
| npm | `@vueuse/motion` |
| Version | 3.0.3 (published 2025-03-10) |
| License | MIT |
| Bundle | <20 KB gzip |

**What it is:** Declarative animation composable and `v-motion` directive inspired by Framer Motion. Built on Popmotion for spring/keyframe/decay animations.

**Pros:**
- `v-motion` directive for declarative animations in templates
- Presets: `fadeVisible`, `slideVisibleLeft`, `pop`, etc. (20+ built-in)
- Spring physics for natural feel
- TypeScript support
- Part of VueUse ecosystem

**Cons:**
- **Last published March 2025** -- 12 months without an update is concerning
- Built on Popmotion which is no longer actively maintained (archived by author)
- Nightly channel exists but no stable release since 3.0.3
- Some users report issues with Vue 3.4+ reactivity changes

---

### 2c. @oku-ui/motion (Motion for Vue)

| Attribute | Value |
|---|---|
| npm | `@oku-ui/motion` |
| Version | 0.4.3 (published 2024-11-21) |
| License | MIT |
| Bundle | ~5 KB gzip |

**What it is:** Port of Motion (formerly Framer Motion's engine) for Vue 3. Provides `<Motion>` component with spring, keyframe, and hardware-accelerated animations.

**Pros:**
- Tiny bundle (5 KB)
- Modern API inspired by Motion/Framer Motion
- Springs, independent transforms, hardware acceleration
- TypeScript support

**Cons:**
- **Pre-1.0 (v0.4.3)** -- API may change
- Last stable release Nov 2024, over a year old
- Small community, limited docs
- Not yet proven at scale in production Vue apps

---

### 2d. GSAP

| Attribute | Value |
|---|---|
| npm | `gsap` |
| Version | 3.14.2 (published 2025-12) |
| License | Standard "no charge" (free for commercial use since Webflow acquisition) |
| Bundle | ~25 KB gzip (core) |

**What it is:** Industry-standard animation library. Framework-agnostic, works with any DOM element.

**Pros:**
- Most powerful animation engine available -- timelines, staggers, morphs, scroll triggers
- Actively maintained, huge community
- Now 100% free including all plugins (ScrollTrigger, Draggable, etc.)
- Battle-tested in production at massive scale
- Excellent performance, GPU-accelerated

**Cons:**
- Overkill for micro-interactions (step fades, popover enters)
- Imperative API doesn't integrate naturally with Vue's declarative templates
- Custom license (not OSI-approved), though free for all use
- Adds 25 KB+ to bundle for capabilities we may not need

---

### 2e. CSS @keyframes + Custom Properties

**What it is:** Pure CSS animations using `@keyframes`, CSS custom properties (`--tour-progress`, `--step-opacity`), and `transition` properties.

**Pros:**
- Zero bundle cost
- GPU-accelerated by default (transform, opacity)
- `prefers-reduced-motion` integration is trivial
- Already used in the project (`@keyframes tour-glow`, `@keyframes spin` in TourOverlay.vue)

**Cons:**
- No spring physics
- Complex choreography is verbose
- JavaScript control requires toggling classes or CSS custom properties

---

### Recommendation: **Vue `<Transition>` + CSS @keyframes (no additional library)**

**Rationale:**

1. The onboarding tour needs exactly three types of animation:
   - **Popover enter/exit:** fade + slight scale -- `<Transition>` handles this perfectly
   - **Spotlight movement:** CSS `transition` on position/size properties (already implemented)
   - **Progress indicators:** CSS @keyframes for pulse/glow effects (already implemented)

2. None of these require spring physics, scroll-triggered animations, or complex timelines. Adding a library would be over-engineering.

3. **@vueuse/motion** and **@oku-ui/motion** both have maintenance concerns. Neither has been updated in 12+ months with stable releases.

4. **GSAP** is phenomenal but adds 25 KB for capabilities that `<Transition>` + CSS handles natively.

5. `prefers-reduced-motion` is simpler with pure CSS than with any library.

**Implementation pattern:**
```vue
<Transition name="tour-popover" appear>
  <div v-if="showPopover" class="tour-popover">...</div>
</Transition>

<style>
.tour-popover-enter-active,
.tour-popover-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.tour-popover-enter-from,
.tour-popover-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .tour-popover-enter-active,
  .tour-popover-leave-active {
    transition: opacity 150ms ease;
  }
  .tour-popover-enter-from,
  .tour-popover-leave-to {
    transform: none;
  }
}
</style>
```

**Install:** Nothing to install. Already available in Vue 3.

---

## 3. Progress Tracking

### 3a. localStorage (Current Approach)

The project currently uses `localStorage` with the key `agented-tour-state`, storing:
```typescript
interface SavedState {
  active?: boolean
  currentStepIndex?: number
  currentSubstepIndex?: number
  completed?: string[]
  tourComplete?: boolean
}
```

**Pros:**
- Zero latency, works offline
- No backend changes needed
- Simple to implement (already done)

**Cons:**
- Lost on browser/device switch
- Lost on cache clear
- No analytics on onboarding completion rates
- No way to reset tour for a user remotely

---

### 3b. Backend-Persisted State

Store onboarding state in the SQLite database alongside user/workspace data.

**Pros:**
- Survives browser clears and device switches
- Enables analytics (completion rates, drop-off steps)
- Admin can reset a user's tour state
- Can gate features based on onboarding completion

**Cons:**
- Requires new API endpoints and DB migration
- Latency on every step transition
- Requires auth context (user identification)

---

### 3c. Hybrid Approach (Recommended)

**localStorage as primary, backend sync as secondary.**

```
Step advance -> write to localStorage (instant)
                 |
                 +-> debounced POST to /api/onboarding/state (async, fire-and-forget)
                      |
                      +-> on app load, merge backend state with localStorage
                           (backend wins for completed steps, localStorage wins for active position)
```

**Rationale:**
- Instant UX (no waiting for API on step advance)
- Resilience against browser clears (backend has the completed steps)
- Analytics capability (backend knows completion rates)
- Simple merge logic (completed steps are append-only)

**Implementation pattern:**
```typescript
// Enhance existing useTour.ts persist() function
function persist() {
  // Immediate localStorage write (existing behavior)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))

  // Debounced backend sync (new)
  debouncedSync(state)
}

async function debouncedSync(state: SavedState) {
  await fetch('/api/onboarding/state', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      completed_steps: state.completed,
      tour_complete: state.tourComplete,
    }),
  })
}
```

**Backend endpoint (new):**
- `PUT /api/onboarding/state` -- upsert onboarding progress
- `GET /api/onboarding/state` -- retrieve on app load
- New `onboarding_state` table in SQLite

**Phase:** Backend sync is a v0.5.0+ enhancement. For initial implementation, the existing localStorage approach is sufficient.

---

## 4. Accessibility

### 4a. Focus Management

#### focus-trap / focus-trap-vue

| Attribute | Value |
|---|---|
| npm | `focus-trap` / `focus-trap-vue` |
| Version | 8.0.0 / 4.1.0 (published 2025-08) |
| License | MIT |
| Bundle | ~10 KB (focus-trap core) |

**What it is:** Traps keyboard focus within a DOM node. `focus-trap-vue` is a thin Vue 3 component wrapper.

**Recommendation:** Use `focus-trap` directly (not the Vue wrapper). The tour popover is rendered imperatively by driver.js, so a Vue component wrapper adds no value. Call `createFocusTrap(popoverEl)` in the `onPopoverRender` callback.

```typescript
import { createFocusTrap } from 'focus-trap'

onPopoverRender: (popover) => {
  const trap = createFocusTrap(popover.wrapper, {
    initialFocus: popover.nextButton,
    allowOutsideClick: false,
    escapeDeactivates: false,  // Tour has its own escape handling
  })
  trap.activate()
}
```

**Install:** `npm install focus-trap`

#### VueUse useFocusTrap

`@vueuse/integrations` provides `useFocusTrap` which wraps `focus-trap`. If the project already uses VueUse, this is an alternative. However, Agented does NOT currently use `@vueuse/core`, so adding it solely for focus trapping is unnecessary overhead.

---

### 4b. ARIA Live Regions for Step Announcements

Screen readers need to announce step changes. Use an `aria-live` region that updates when the step changes.

```html
<!-- Persistent in App.vue, visually hidden -->
<div
  aria-live="polite"
  aria-atomic="true"
  class="sr-only"
>
  {{ tourAnnouncement }}
</div>
```

```typescript
// In useTour.ts
const tourAnnouncement = computed(() => {
  if (!active.value || !currentStep.value) return ''
  return `Tour step ${displayStepNumber.value} of ${totalSteps}: ${currentStep.value.title}. ${currentStep.value.message}`
})
```

**No library needed.** This is 10 lines of code.

---

### 4c. Reduced Motion Support

**CSS approach (primary):**
```css
@media (prefers-reduced-motion: reduce) {
  .tour-spotlight {
    transition: none;
  }
  .tour-spotlight-glow {
    animation: none;
  }
  .tour-popover-enter-active,
  .tour-popover-leave-active {
    transition-duration: 0.01ms;
  }
}
```

**JavaScript approach (for driver.js config):**
```typescript
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

const driverObj = driver({
  animate: !prefersReducedMotion,
  smoothScroll: !prefersReducedMotion,
  // ...
})
```

**In-app toggle (optional enhancement):**
For users on OSes without system-level reduced-motion settings, provide an in-app toggle that sets `document.body.classList.add('reduce-motion')` and use `body.reduce-motion` as a CSS selector alongside the media query.

**No library needed.**

---

### Accessibility Summary

| Concern | Solution | Library |
|---|---|---|
| Focus trapping | `focus-trap` in `onPopoverRender` | `focus-trap@8.0.0` |
| Step announcements | `aria-live` region + computed text | None (10 lines) |
| Reduced motion | CSS `prefers-reduced-motion` + driver.js config | None |
| Keyboard navigation | driver.js handles Escape; add Tab/Enter for Next/Skip | None |

**Install:** `npm install focus-trap` (MIT, ~10 KB)

---

## 5. Testing

### 5a. Unit Testing with Vitest + happy-dom

The project already uses `vitest@^4.0.18` with `happy-dom@^20.5.0` and `@vue/test-utils@^2.4.6`. Existing tests in `TourOverlay.test.ts` cover component rendering, emit behavior, and conditional display.

**Testing the tour composable (`useTour.ts`):**
```typescript
// Test step navigation, persistence, and edge cases
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock localStorage
const store: Record<string, string> = {}
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, val: string) => { store[key] = val },
  removeItem: (key: string) => { delete store[key] },
})
```

**Testing driver.js integration:**
driver.js manipulates real DOM (SVG overlays, absolutely positioned popovers). happy-dom does NOT support:
- `getBoundingClientRect()` returning meaningful values
- SVG rendering
- `MutationObserver` reliably for overlay positioning

**Strategy:** Mock driver.js at the module level in unit tests. Test the orchestration logic (step transitions, persistence, routing) independently from the visual layer.

```typescript
// Mock driver.js for unit tests
vi.mock('driver.js', () => ({
  driver: vi.fn(() => ({
    drive: vi.fn(),
    highlight: vi.fn(),
    destroy: vi.fn(),
    moveNext: vi.fn(),
    movePrevious: vi.fn(),
    isActive: vi.fn(() => false),
  })),
}))
```

**Known happy-dom limitations with overlays:**
- Teleport renders into a detached node; test with `wrapper.find('[data-teleport]')`
- Tooltip/popover positioning libraries return `{ top: 0, left: 0 }` in happy-dom
- Radix Vue has documented issues testing popovers in happy-dom (see radix-vue#904)

**Recommendation:** Unit-test the logic (composable state, step transitions, localStorage persistence). Do NOT unit-test visual positioning or overlay rendering -- that belongs in E2E tests.

---

### 5b. E2E Testing with Playwright

The project already has `@playwright/test@^1.58.2` and `playwright@^1.58.2` in devDependencies.

**Testing onboarding flows with Playwright:**

```typescript
// e2e/onboarding-tour.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Onboarding Tour', () => {
  test.beforeEach(async ({ page }) => {
    // Clear tour state
    await page.evaluate(() => localStorage.removeItem('agented-tour-state'))
    await page.goto('/')
  })

  test('completes full tour flow', async ({ page }) => {
    // Start tour from welcome page
    await page.click('[data-tour-action="start"]')

    // Step 1: Workspace directory
    await expect(page.locator('.driver-popover')).toBeVisible()
    await expect(page.locator('.driver-popover-title')).toContainText('Workspace')

    // Fill required field
    await page.fill('[data-tour="workspace-root"] input', '/workspace')
    await page.click('.driver-popover-next-btn')

    // Step 2: Verify navigation to backends
    await expect(page).toHaveURL(/\/backends/)
    await expect(page.locator('.driver-popover')).toBeVisible()

    // Skip optional step
    await page.click('[data-tour-action="skip"]')

    // ... continue through steps
  })

  test('persists progress across page reload', async ({ page }) => {
    await page.click('[data-tour-action="start"]')
    await page.click('.driver-popover-next-btn')

    // Reload
    await page.reload()

    // Should resume at step 2
    await expect(page.locator('.tour-step-counter')).toContainText('STEP 3')
  })

  test('respects reduced motion preference', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.click('[data-tour-action="start"]')

    // Verify no animations
    const spotlight = page.locator('.tour-spotlight')
    const transition = await spotlight.evaluate(
      el => getComputedStyle(el).transitionDuration
    )
    expect(transition).toBe('0s')
  })

  test('traps focus within popover', async ({ page }) => {
    await page.click('[data-tour-action="start"]')
    await expect(page.locator('.driver-popover')).toBeVisible()

    // Tab through popover buttons
    await page.keyboard.press('Tab')
    const focused = await page.evaluate(() => document.activeElement?.className)
    expect(focused).toContain('driver-popover')
  })
})
```

**Key Playwright patterns for tour testing:**
- Use `page.emulateMedia({ reducedMotion: 'reduce' })` to test a11y
- Use `page.evaluate(() => localStorage.setItem(...))` to set initial state
- Use `await expect(locator).toBeVisible()` with auto-retry for animated elements
- Test cross-page navigation with `await expect(page).toHaveURL()`
- Use `data-tour-*` attributes as stable selectors (already in place)

---

## Final Recommended Stack

| Category | Choice | Package | Version |
|---|---|---|---|
| **Tour engine** | driver.js (visual) + custom composable (orchestration) | `driver.js` | ^1.4.0 (already installed) |
| **Animations** | Vue `<Transition>` + CSS @keyframes | (built-in) | -- |
| **Progress tracking** | localStorage (now) + backend sync (later) | (built-in) | -- |
| **Focus trapping** | focus-trap | `focus-trap` | ^8.0.0 |
| **A11y announcements** | ARIA live region | (custom, ~10 lines) | -- |
| **Reduced motion** | CSS media query + JS detection | (built-in) | -- |
| **Unit tests** | Vitest + happy-dom (mock driver.js) | (already installed) | -- |
| **E2E tests** | Playwright | (already installed) | -- |

### New Dependencies to Add

```bash
npm install focus-trap
# That's it. One new dependency.
```

### Dependencies to Remove

None. `driver.js` is already installed and should be activated (it is currently unused).

### Total New Bundle Cost

~10 KB (focus-trap). The rest is zero-cost (built-in Vue, CSS, or already-installed packages).
