# Phase 2: Visual Layer - Research

**Researched:** 2026-03-22
**Domain:** Vue 3 overlay/spotlight components + Floating UI tooltip positioning + CSS transitions
**Confidence:** HIGH

## Summary

This phase implements the visual tour components: a dimming overlay using the `box-shadow: 0 0 0 9999px` technique (already prototyped in the existing TourOverlay.vue), a spotlight that tracks target elements through resize/scroll/reflow, tooltips positioned via Floating UI's `@floating-ui/vue` composable with auto-flip middleware, a progress bar, and CSS transitions for step changes. All components must use the CSS custom properties already defined in App.vue's `:root`.

The existing TourOverlay.vue (314 lines) already implements the core box-shadow dimming and spotlight tracking with scroll/resize listeners plus MutationObserver for deferred DOM targets. It has hardcoded color values and z-index numbers that must be replaced with CSS custom properties. The bottom-bar currently serves as both tooltip and controls -- Phase 2 replaces this with a proper Floating UI-positioned tooltip that anchors to the spotlight target and a separate progress/controls bar.

The key technical decision is using `@floating-ui/vue` (v1.1.11) which provides a Vue 3 `useFloating` composable with reactive positioning. Combined with `autoUpdate` for continuous tracking, `flip()` + `shift()` + `offset()` middleware for viewport-edge handling, and `arrow()` for tooltip pointer positioning, this covers all tooltip requirements without hand-rolling positioning math.

**Primary recommendation:** Install `@floating-ui/vue` (which includes `@floating-ui/dom` as a dependency), use its `useFloating` composable with `whileElementsMounted: autoUpdate` for automatic position tracking, and split the existing TourOverlay.vue into three components: TourOverlay (dim + spotlight), TourTooltip (Floating UI positioned), and TourProgressBar (bottom bar).

## User Constraints

No CONTEXT.md exists for this phase. All decisions are at Claude's discretion, constrained by:

### Locked Decisions (from Phase 1 / Roadmap)
- Drop driver.js, use XState v5 + Floating UI + focus-trap (roadmap decision)
- z-index CSS custom properties already defined in App.vue: `--z-tour-overlay: 10000`, `--z-tour-spotlight: 10001`, `--z-tour-tooltip: 10002`, `--z-tour-controls: 10003`, `--z-tour-progress: 10004`
- Singleton XState actor pattern from Phase 1 composable (`useTourMachine.ts`)
- Toast z-index conflict (hardcoded `z-index: 10000` on `.toast-container`) deferred to Phase 7
- Box-shadow dimming technique (already in TourOverlay.vue, proven to work)
- Dark theme with CSS custom properties in App.vue `:root`
- Existing `data-tour="..."` attributes on target elements throughout codebase

### Claude's Discretion
- Component decomposition (how to split TourOverlay into sub-components)
- Floating UI middleware configuration (placement, offset distance, flip behavior)
- Spotlight tracking mechanism (keep existing scroll/resize listeners vs. use `autoUpdate`)
- CSS transition timing and easing functions
- Progress bar design and positioning
- Arrow/pointer design on tooltip

### Deferred Ideas (OUT OF SCOPE)
- Focus-trap integration (Phase 6)
- Form field guidance / auto-discovery (Phase 5)
- Welcome page modifications (Phase 3)
- Step content definitions (Phase 4)
- Toast z-index fix (Phase 7)

## Paper-Backed Recommendations

### Recommendation 1: Floating UI `@floating-ui/vue` with `useFloating` Composable
**Recommendation:** Use `@floating-ui/vue` v1.1.11 with `useFloating(reference, floating, options)` composable pattern for tooltip positioning.

**Evidence:**
- Floating UI official documentation (floating-ui.com/docs/vue) -- Demonstrates `useFloating` composable with Vue 3 `ref()` template refs, returning reactive `floatingStyles` and `middlewareData`. Verified via Context7 `/floating-ui/floating-ui`.
- Floating UI Vue examples (Context7) -- Show the exact pattern: `<script setup>` with `ref(null)` for reference/floating elements, `useFloating(reference, floating, { middleware: [offset(10), flip(), shift()] })`.
- Floating UI arrow middleware docs (Context7) -- Show `arrow({element: floatingArrow})` middleware with `middlewareData.arrow?.x/y` for dynamic arrow positioning.

**Confidence:** HIGH -- Official documentation verified via Context7 with 1069 code snippets, HIGH source reputation, 74.85 benchmark score.
**Expected improvement:** Zero custom positioning math. Handles viewport edge cases (flip, shift), scroll containers, and dynamic content automatically.
**Caveats:** `@floating-ui/vue` requires Vue 3.x. The `reference` parameter can be a template ref OR a virtual element (object with `getBoundingClientRect()`), which is useful for spotlight-to-tooltip bridging.

### Recommendation 2: `autoUpdate` with `whileElementsMounted` for Continuous Position Tracking
**Recommendation:** Use `autoUpdate` via the `whileElementsMounted` option in `useFloating` to automatically reposition tooltips on scroll, resize, and layout shifts.

**Evidence:**
- Floating UI autoUpdate docs (Context7) -- "If you're conditionally rendering the floating element with `v-if` (recommended), use the `whileElementsMounted` option. `whileElementsMounted` automatically handles calling and cleaning up `autoUpdate` based on the presence of the reference and floating element."
- `autoUpdate` configuration options (Context7) -- Supports `ancestorScroll`, `ancestorResize`, `elementResize`, `layoutShift`, `animationFrame`. Default enables all except `animationFrame`.

**Confidence:** HIGH -- Official documentation pattern. This is the recommended approach for Vue.
**Expected improvement:** Spotlight and tooltip track target within one frame of any DOM change. Handles scroll, resize, content reflow automatically. No manual `addEventListener` for scroll/resize needed for the tooltip positioning.
**Caveats:** The spotlight itself (box-shadow element) still needs its own tracking since it uses a different positioning approach (absolute coordinates). The existing scroll/resize listeners in TourOverlay.vue for spotlight tracking can be preserved. The tooltip uses `autoUpdate` independently.

### Recommendation 3: Box-Shadow Dimming with pointer-events Pass-Through
**Recommendation:** Keep the existing `box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.7)` technique on the spotlight element. Set `pointer-events: none` on the overlay container, `pointer-events: none` on the spotlight, allowing clicks to pass through to the highlighted element underneath.

**Evidence:**
- Existing TourOverlay.vue implementation -- Already uses this technique successfully. The overlay has `pointer-events: none` so users can interact with highlighted elements. The bottom bar has `pointer-events: auto` to capture button clicks.
- CSS specification (W3C Pointer Events) -- `pointer-events: none` makes the element invisible to pointer events, letting them pass through to elements below in the stacking context.
- User feedback (feedback_onboarding_tour.md) -- Critical issue #1 was highlighting misalignment. The box-shadow technique itself works; the issue was driver.js padding/radius miscalculation, not the dimming approach.

**Confidence:** HIGH -- Already proven in the codebase. The technique is well-established for tour overlays.

### Recommendation 4: CSS Transitions for Step Changes (opacity + transform, ~200ms)
**Recommendation:** Use CSS transitions with `opacity` and `transform` for step-to-step tooltip animation. Use the project's existing `--transition-normal: 250ms ease` custom property for consistency with the app's design language. The tooltip fades out (opacity 0, slight translateY), then fades in at the new position.

**Evidence:**
- App.vue CSS custom properties -- Already defines `--transition-fast: 150ms ease` and `--transition-normal: 250ms ease`. These are used throughout the codebase for consistent timing.
- Success criteria requirement -- "Step transitions use CSS transitions (opacity + transform, 200ms) with no flicker or jump." Using 250ms (--transition-normal) is close to 200ms and consistent with the rest of the app. Alternatively, define a `--transition-tour: 200ms ease` specifically.
- Existing TourOverlay.vue -- Already uses `transition: top 300ms ease, left 300ms ease, width 300ms ease, height 300ms ease` on the spotlight, proving CSS transitions work for this use case.

**Confidence:** HIGH -- Standard CSS technique, project conventions already established.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@floating-ui/vue` | ^1.1.11 | Vue 3 tooltip positioning composable | Official Floating UI Vue integration. Provides `useFloating` composable, reactive `floatingStyles`, auto-flip/shift/offset middleware. 1069 code snippets in Context7. |
| `@floating-ui/dom` | (transitive) | DOM positioning engine | Automatically installed as dependency of `@floating-ui/vue`. Provides `autoUpdate`, `computePosition`, all middleware. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `xstate` | 5.28.0 | Tour state machine | Already installed (Phase 1). Visual components read state from `useTourMachine` composable. |
| `@xstate/vue` | 3.1.4 | XState-Vue bridge | Already installed (Phase 1). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@floating-ui/vue` | `@floating-ui/dom` directly | Lower-level API, requires manual Vue reactivity integration. `@floating-ui/vue` wraps this with `useFloating` composable that handles ref management automatically. No reason to go lower-level. |
| `@floating-ui/vue` | Floating Vue (`floating-vue`) | Higher-level component library with built-in tooltip/dropdown components. Overkill -- we need precise control over tooltip content/styling for tour. Also adds a second positioning dependency alongside the one we actually need. |
| `@floating-ui/vue` | Popper.js | Deprecated. Floating UI is the official successor. |
| CSS `box-shadow` dimming | SVG `<clipPath>` overlay | SVG clip-path can create precise cutouts but is harder to animate, doesn't support border-radius as easily, and adds complexity. Box-shadow is simpler and already working. |

**Installation:**
```bash
cd frontend && npm install @floating-ui/vue@^1.1.11
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── components/tour/
│   ├── TourOverlay.vue           # Overlay container + spotlight (box-shadow dimming)
│   ├── TourTooltip.vue           # Floating UI positioned tooltip with arrow
│   ├── TourProgressBar.vue       # Bottom progress bar with step counter + controls
│   └── __tests__/
│       ├── TourOverlay.test.ts   # (existing, update for new API)
│       ├── TourTooltip.test.ts   # New
│       └── TourProgressBar.test.ts # New
├── composables/
│   └── useTourMachine.ts         # (existing from Phase 1, no changes)
├── machines/
│   └── tourMachine.ts            # (existing from Phase 1, no changes)
└── App.vue                       # CSS custom properties (existing, no changes)
```

### Pattern 1: Virtual Element Bridge (Spotlight → Tooltip Positioning)
**What:** The spotlight tracks a target DOM element and knows its `DOMRect`. The tooltip needs to position relative to this same element. Use Floating UI's virtual element support to pass the spotlight's tracked rect to `useFloating` as its reference.

**When to use:** When the tooltip must anchor to the same element the spotlight highlights, but through Floating UI's positioning system rather than manual coordinate math.

**Example:**
```vue
<script setup>
import { ref, computed, watch } from 'vue'
import { useFloating, offset, flip, shift, arrow, autoUpdate } from '@floating-ui/vue'

const props = defineProps<{
  targetRect: DOMRect | null
  visible: boolean
}>()

// Virtual element for Floating UI — wraps the target's DOMRect
const virtualReference = computed(() => {
  if (!props.targetRect) return null
  const r = props.targetRect
  return {
    getBoundingClientRect: () => ({
      x: r.x,
      y: r.y,
      top: r.top,
      left: r.left,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height,
    }),
  }
})

const floating = ref(null)
const floatingArrow = ref(null)

const { floatingStyles, placement, middlewareData } = useFloating(
  virtualReference,
  floating,
  {
    placement: 'bottom',
    middleware: [offset(12), flip(), shift({ padding: 8 }), arrow({ element: floatingArrow })],
    whileElementsMounted: autoUpdate,
  },
)
</script>
```

### Pattern 2: Spotlight Tracking with Existing Scroll/Resize Listeners
**What:** The spotlight element uses `position: fixed` with inline styles derived from `getBoundingClientRect()`. Tracking uses `scroll` (capture) + `resize` event listeners, plus a `MutationObserver` for deferred DOM targets.

**When to use:** For the spotlight overlay element that uses the box-shadow technique. This pattern is already implemented in the existing TourOverlay.vue.

**Key insight:** The spotlight does NOT use Floating UI. It uses fixed positioning with explicit top/left/width/height from `getBoundingClientRect()`. Floating UI is only for the tooltip. The spotlight tracking uses the existing event-listener approach, possibly enhanced with `ResizeObserver` on the target element for more precise content reflow detection.

### Pattern 3: CSS Custom Property Usage (Zero Hardcoded Colors)
**What:** All tour component styles reference CSS custom properties from App.vue's `:root`. No `#hex`, `rgb()`, or `rgba()` color values appear in tour component `<style>` blocks.

**When to use:** Always. This is a hard requirement (success criterion #5).

**Mapping from current hardcoded values:**
| Current Hardcoded | CSS Custom Property |
|-------------------|---------------------|
| `rgba(0, 0, 0, 0.7)` (overlay dim) | Define new `--tour-overlay-dim: rgba(0, 0, 0, 0.7)` or use `--bg-primary` with opacity |
| `#818cf8` (glow border, step counter) | Use `--accent-violet` (#8855ff) — closest match in existing palette |
| `rgba(99, 102, 241, 0.4/0.6)` (glow animation) | Use `--accent-violet-dim` with adjusted opacity |
| `#1a1a2e` (bottom bar bg) | Use `--bg-secondary` (#12121a) or `--bg-tertiary` (#1a1a24) |
| `#e4e4e7` (message text) | Use `--text-primary` (#f0f0f5) |
| `#a1a1aa` (substep label, skip btn) | Use `--text-secondary` (#a0a0b0) |
| `#71717a` (spinner text) | Use `--text-tertiary` (#606070) |
| `#6366f1` / `#818cf8` (next btn) | Use `--accent-violet` / `--accent-violet-dim` or `--accent-cyan` for consistency with app accent |
| `rgba(255, 255, 255, 0.1/0.2)` (borders) | Use `--border-default` / `--border-strong` |

**Design decision:** The existing tour uses indigo/violet tones (`#6366f1`, `#818cf8`) while the app's primary accent is cyan (`--accent-cyan: #00d4ff`). For consistency, tour components should use `--accent-cyan` as the primary accent (matching buttons, links, and active states throughout the app) with `--accent-violet` available as a secondary accent for the glow effect.

### Anti-Patterns to Avoid
- **Hardcoded z-index values:** The existing TourOverlay.vue has `z-index: 10000`, `10001`, `10002`, `10003` as raw numbers. MUST use `var(--z-tour-overlay)`, `var(--z-tour-spotlight)`, `var(--z-tour-tooltip)`, `var(--z-tour-controls)`.
- **Hardcoded color values:** All `#hex`, `rgb()`, `rgba()` in tour styles must be replaced with CSS custom properties. For overlay-specific values not in the global palette (like dim opacity), define tour-specific custom properties.
- **Manual tooltip positioning math:** Do NOT calculate tooltip x/y coordinates manually. Use Floating UI's `useFloating` composable which handles all viewport edge cases.
- **Using `animationFrame: true` in autoUpdate:** This polls on every frame, which is expensive. The default (`false`) uses `ResizeObserver` + `scroll`/`resize` listeners, which is more efficient and sufficient for our use case.
- **Blocking pointer events on highlighted elements:** The overlay MUST have `pointer-events: none` so users can click/type in highlighted form fields. Only tour UI elements (tooltip, progress bar) should have `pointer-events: auto`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tooltip positioning | Manual `getBoundingClientRect()` + offset math + viewport clamp | `@floating-ui/vue` `useFloating` with `flip()` + `shift()` | Viewport edge detection, scroll container awareness, placement flipping, and arrow positioning have dozens of edge cases. Floating UI handles them all. |
| Auto-update on scroll/resize (for tooltip) | Manual `addEventListener('scroll', ...)` + `addEventListener('resize', ...)` | `autoUpdate` via `whileElementsMounted` option | Floating UI's `autoUpdate` also handles `ResizeObserver`, layout shifts, and element visibility changes. Cleaner lifecycle management. |
| Arrow positioning | CSS `::before`/`::after` pseudo-elements with manual offset | `arrow()` middleware + `middlewareData.arrow` | Arrow must move dynamically based on which edge the tooltip flips to. Floating UI computes this automatically. |
| Overlay dimming with cutout | SVG clip-path or canvas rendering | `box-shadow: 0 0 0 9999px` | Already proven in the codebase. Simpler, animatable via CSS transitions, works with border-radius. |

**Key insight:** The hardest part of tour visual layers is tooltip positioning at viewport edges. Floating UI is purpose-built for exactly this problem and handles cases like: tooltip flipping from bottom to top when near page bottom, shifting left/right when near edges, and repositioning the arrow accordingly. Hand-rolling this would require 100+ lines of fragile positioning logic.

## Common Pitfalls

### Pitfall 1: Tooltip Flicker on Step Transitions
**What goes wrong:** When transitioning between steps, the tooltip briefly appears at the old position before jumping to the new position, causing a visible "flash" or "jump."
**Why it happens:** Floating UI computes position asynchronously. If the tooltip is visible while the reference element changes, there's a frame where the tooltip shows at stale coordinates.
**How to avoid:** Use a two-phase transition: (1) fade out the tooltip (opacity 0), (2) update the reference/target, (3) wait for Floating UI to compute new position (one frame), (4) fade in at the new position. Use `v-if` with a brief delay or `nextTick` between steps.
**Warning signs:** Tooltip appears to "jump" between positions during step changes.

### Pitfall 2: Spotlight Position Stale After Content Reflow
**What goes wrong:** The spotlight highlights the wrong area after content loads or changes (e.g., a lazy-loaded list pushes the target element down).
**Why it happens:** The current implementation only tracks `scroll` and `resize` events. Content reflow (dynamic content loading, accordion expand, etc.) doesn't fire these events.
**How to avoid:** Add a `ResizeObserver` on the target element to detect size/position changes from content reflow. The existing `MutationObserver` in TourOverlay.vue handles deferred DOM insertion but not size changes of existing elements.
**Warning signs:** Spotlight appears offset from the actual target element after page content loads.

### Pitfall 3: Virtual Element Reference Not Reactive
**What goes wrong:** Floating UI tooltip doesn't reposition when the spotlight moves, because the virtual reference object isn't reactive.
**Why it happens:** `@floating-ui/vue`'s `useFloating` watches the `reference` ref for changes. If the virtual element object is the same reference but its `getBoundingClientRect` returns different values, Floating UI won't detect the change.
**How to avoid:** Use a Vue `computed` that returns a NEW virtual element object whenever the target rect changes. This way, the reference ref value changes, triggering Floating UI to recompute.
**Warning signs:** Tooltip stays anchored at the initial position while spotlight moves.

### Pitfall 4: z-index Collision with Toast Container
**What goes wrong:** Toast notifications appear above the tour overlay, breaking the visual hierarchy.
**Why it happens:** `.toast-container` has `z-index: 10000` (hardcoded in App.vue line 863), which equals `--z-tour-overlay`. Both compete for the same stacking level.
**How to avoid:** This is explicitly deferred to Phase 7. For now, accept the collision. The toast and tour overlay are unlikely to appear simultaneously during normal usage. Phase 7 will refactor the toast z-index to use a CSS custom property below the tour layer.
**Warning signs:** Toast appears on top of tour overlay during tour.

### Pitfall 5: CSS Custom Properties Not Available in Scoped Styles
**What goes wrong:** `var(--z-tour-overlay)` doesn't resolve in a component's scoped `<style>` block.
**Why it happens:** This is actually NOT a real issue -- CSS custom properties defined on `:root` are available everywhere in the DOM regardless of Vue scoped styles. Scoped styles add data attributes but don't affect CSS variable inheritance.
**How to avoid:** No action needed. CSS custom properties from App.vue's `:root` are available in all component scoped styles. Just use `var(--z-tour-overlay)` directly.
**Warning signs:** None (this is a misconception, not a real issue).

### Pitfall 6: Spotlight Glow Animation Perf on Low-End Devices
**What goes wrong:** The `box-shadow` animation on the spotlight glow (the pulsing indigo border) causes jank on low-end devices because `box-shadow` triggers paint on every frame.
**Why it happens:** `box-shadow` is not GPU-accelerated. The existing `@keyframes tour-glow` animates box-shadow between two values, which requires a repaint on every frame.
**How to avoid:** Use `opacity` on a pseudo-element or separate div for the glow effect instead of animating `box-shadow`. Alternatively, use `will-change: opacity` on the glow element and animate opacity of a fixed box-shadow. This promotes the element to its own compositing layer.
**Warning signs:** Stuttering glow animation, high paint time in DevTools Performance panel.

## Experiment Design

### Recommended Experimental Setup

**Independent variables:**
- Tooltip placement strategy: `flip()` vs. `autoPlacement()`
- Spotlight tracking method: scroll/resize listeners vs. `autoUpdate` with `animationFrame: true`
- Transition timing: 150ms vs. 200ms vs. 250ms

**Dependent variables:**
- Tooltip viewport visibility (never clipped at any edge)
- Spotlight tracking latency (frames between DOM change and spotlight update)
- Perceived transition smoothness (no flicker or jump)
- CSS custom property compliance (zero hardcoded values)

**Baseline comparison:**
- Current TourOverlay.vue: hardcoded colors, no tooltip (bottom bar only), spotlight tracks via scroll/resize, 300ms transitions
- Target: CSS custom properties everywhere, Floating UI tooltip always visible in viewport, spotlight tracks within one frame, 200ms transitions

**Validation approach:**
1. Mount TourOverlay with a target element near each viewport edge (top, bottom, left, right)
2. Verify tooltip is fully visible (no clipping) in each case via `getBoundingClientRect()` assertions
3. Resize window to trigger flip/shift -- verify tooltip repositions correctly
4. Scroll to move target -- verify spotlight and tooltip follow within one frame
5. Change step -- verify no position jump (opacity transition only)
6. Inspect all `<style>` blocks -- verify zero hardcoded color/z-index values

**Statistical rigor:** Not applicable (deterministic DOM positioning, not stochastic). Binary pass/fail on each criterion.

### Recommended Metrics

| Metric | Why | How to Compute | Target |
|--------|-----|----------------|--------|
| Hardcoded values count | Success criterion #5 | `grep -c '#[0-9a-f]\\|rgba\\|rgb(' tour-components` | 0 |
| Tooltip viewport overflow | Success criterion #3 | `rect.left >= 0 && rect.right <= window.innerWidth && rect.top >= 0 && rect.bottom <= window.innerHeight` | Always true |
| Spotlight tracking latency | Success criterion #2 | Frames between `resize` event and spotlight `style` update | <= 1 frame |
| Transition flicker | Success criterion #4 | Visual inspection + `opacity` never jumps from 0→1 without transition | No flicker |
| Pointer-events pass-through | Success criterion #1 | `document.elementFromPoint(targetCenter.x, targetCenter.y)` returns the target, not the overlay | Target accessible |

## Verification Strategy

### Recommended Verification Tiers for This Phase

| Item | Recommended Tier | Rationale |
|------|-----------------|-----------|
| Overlay renders and dims background | Level 1 (Sanity) | Check DOM structure and CSS class presence |
| Spotlight positioned at target rect | Level 1 (Sanity) | Mock `getBoundingClientRect`, check inline styles |
| Tooltip uses Floating UI (not manual positioning) | Level 1 (Sanity) | Check `@floating-ui/vue` import, `useFloating` usage |
| All styles use CSS custom properties | Level 1 (Sanity) | Static analysis / grep for hardcoded values |
| z-index values use CSS custom properties | Level 1 (Sanity) | Static analysis / grep |
| Tooltip never clipped at viewport edges | Level 2 (Proxy) | Unit test with mock rects near edges, check `floatingStyles` |
| Spotlight repositions on resize | Level 2 (Proxy) | Trigger resize event, check updated styles |
| Step transitions have opacity/transform transitions | Level 2 (Proxy) | Check CSS `transition` property on tooltip element |
| Pointer-events pass through to highlighted element | Level 2 (Proxy) | Check `pointer-events: none` on overlay, `auto` on interactive elements |
| Progress bar shows correct step/total | Level 1 (Sanity) | Mount with props, check text content |
| Full visual flow (all steps, all positions) | Level 3 (Deferred) | Needs running app + all steps defined (Phase 4+) |
| Performance on low-end devices | Level 3 (Deferred) | Needs real browser profiling |

**Level 1 checks to always include:**
- TourOverlay renders when `active` prop is true
- TourOverlay does not render when `active` is false
- Spotlight element has `box-shadow` style
- All tour component `<style>` blocks contain zero hardcoded `#hex`/`rgb()`/`rgba()` color values (allow transparent/none/inherit)
- All z-index values use `var(--z-tour-*)` custom properties
- TourTooltip imports from `@floating-ui/vue`
- TourProgressBar displays step counter

**Level 2 proxy metrics:**
- Mount TourTooltip with virtual reference near bottom edge -- verify `placement` flips to `top`
- Mount TourTooltip with virtual reference near right edge -- verify shift moves tooltip left
- Verify spotlight inline styles update when `targetRect` prop changes
- Verify tooltip arrow position via `middlewareData.arrow`

**Level 3 deferred items:**
- Full E2E visual tour flow (needs Phase 4 step definitions, Phase 10 integration)
- Toast z-index collision visual testing (deferred to Phase 7)
- Performance profiling (needs production build + real device)

## Production Considerations

### Known Failure Modes
- **Target element not in DOM:** Page may not have loaded the target element yet (lazy-loaded routes). The existing MutationObserver pattern handles this by watching for the element to appear. The tooltip should not render until the target is found (use `v-if` on `targetRect`).
  - Prevention: Keep the existing MutationObserver + loading spinner pattern from TourOverlay.vue.
  - Detection: Spinner visible instead of tooltip when target is missing.

- **Floating UI position calculation failure:** If both reference and floating elements are removed from DOM simultaneously (e.g., route change), `computePosition` may throw.
  - Prevention: `whileElementsMounted` handles lifecycle automatically -- cleanup runs when either element is removed. Guard tooltip rendering with `v-if="visible && targetRect"`.
  - Detection: Console error from Floating UI.

- **Content Security Policy (CSP):** Floating UI uses inline styles via `floatingStyles`. Some strict CSP policies block inline styles.
  - Prevention: Not a concern for this project (no CSP configured). Note for future production hardening.

### Scaling Concerns
- **Not applicable:** Tour is single-user, client-side, one overlay instance. No scaling concerns.

### Common Implementation Traps
- **Trap: Importing driver.js alongside Floating UI.** driver.js (`^1.4.0`) is still listed as a dependency. Do NOT import it in any tour code.
  - Correct approach: Use `@floating-ui/vue` exclusively. driver.js removal can happen in a cleanup phase.

- **Trap: Using `position: absolute` instead of `position: fixed` for spotlight.** The spotlight must use `position: fixed` because `getBoundingClientRect()` returns viewport-relative coordinates.
  - Correct approach: Spotlight uses `position: fixed` with `top`/`left`/`width`/`height` from `getBoundingClientRect()`. This is already correct in the existing TourOverlay.vue.

- **Trap: Animating `box-shadow` spread for the spotlight dim.** The 9999px box-shadow itself should NOT be animated -- only the spotlight's position (top/left/width/height) should transition.
  - Correct approach: `transition: top 200ms ease, left 200ms ease, width 200ms ease, height 200ms ease` on the spotlight element. The box-shadow value stays constant.

## Code Examples

### Installing @floating-ui/vue
```bash
# Source: npm registry, verified 2026-03-22
cd frontend && npm install @floating-ui/vue@^1.1.11
```

### TourTooltip with Floating UI (Vue 3 SFC)
```vue
<!-- Source: @floating-ui/vue docs (Context7) + project conventions -->
<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFloating, offset, flip, shift, arrow, autoUpdate } from '@floating-ui/vue'

const props = defineProps<{
  targetRect: DOMRect | null
  title: string
  message: string
  visible: boolean
}>()

// Virtual reference from spotlight's tracked target rect
const reference = computed(() => {
  if (!props.targetRect) return null
  const r = props.targetRect
  return {
    getBoundingClientRect: () => ({
      x: r.x, y: r.y, top: r.top, left: r.left,
      right: r.right, bottom: r.bottom, width: r.width, height: r.height,
    }),
  }
})

const floating = ref(null)
const floatingArrow = ref(null)

const { floatingStyles, placement, middlewareData } = useFloating(reference, floating, {
  placement: 'bottom',
  middleware: [
    offset(12),
    flip({ fallbackAxisSideDirection: 'start' }),
    shift({ padding: 8 }),
    arrow({ element: floatingArrow }),
  ],
  whileElementsMounted: autoUpdate,
})

// Arrow positioning from middleware data
const arrowStyle = computed(() => {
  const arrowData = middlewareData.value.arrow
  if (!arrowData) return {}
  const staticSide = { top: 'bottom', right: 'left', bottom: 'top', left: 'right' }[
    placement.value.split('-')[0]
  ]
  return {
    left: arrowData.x != null ? `${arrowData.x}px` : '',
    top: arrowData.y != null ? `${arrowData.y}px` : '',
    [staticSide!]: '-4px',
  }
})
</script>

<template>
  <div
    v-if="visible && targetRect"
    ref="floating"
    :style="floatingStyles"
    class="tour-tooltip"
    role="tooltip"
  >
    <h4 class="tour-tooltip-title">{{ title }}</h4>
    <p class="tour-tooltip-message">{{ message }}</p>
    <div ref="floatingArrow" class="tour-tooltip-arrow" :style="arrowStyle" />
  </div>
</template>

<style scoped>
.tour-tooltip {
  z-index: var(--z-tour-tooltip);
  pointer-events: auto;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px 16px;
  max-width: 320px;
  box-shadow: var(--shadow-md);
  font-family: var(--font-sans);
  /* Step transition animation */
  transition: opacity var(--transition-normal), transform var(--transition-normal);
}

.tour-tooltip-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.tour-tooltip-message {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.tour-tooltip-arrow {
  position: absolute;
  width: 8px;
  height: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  transform: rotate(45deg);
}
</style>
```

### Spotlight Element with CSS Custom Properties
```vue
<!-- Source: Existing TourOverlay.vue pattern, refactored to use CSS custom properties -->
<style scoped>
.tour-spotlight {
  position: fixed;
  border-radius: 8px;
  z-index: var(--z-tour-spotlight);
  pointer-events: none;
  box-shadow: 0 0 0 9999px var(--tour-dim-color, rgba(0, 0, 0, 0.7));
  transition: top var(--transition-normal), left var(--transition-normal),
              width var(--transition-normal), height var(--transition-normal);
}

.tour-spotlight-glow {
  position: absolute;
  inset: -4px;
  border-radius: 10px;
  border: 2px solid var(--accent-cyan);
  animation: tour-glow 1.5s ease-in-out infinite;
}

@keyframes tour-glow {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}
</style>
```

### Progress Bar with CSS Custom Properties
```vue
<!-- Source: Existing bottom bar pattern, refactored as separate component -->
<style scoped>
.tour-progress-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: var(--z-tour-progress);
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 24px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-lg);
  pointer-events: auto;
  font-family: var(--font-sans);
}

.tour-step-counter {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--accent-cyan);
  text-transform: uppercase;
  white-space: nowrap;
}

.tour-next-btn {
  padding: 6px 16px;
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
  font-family: inherit;
}

.tour-next-btn:hover {
  opacity: 0.85;
}

.tour-skip-btn {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast);
  font-family: inherit;
}

.tour-skip-btn:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}
</style>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Popper.js | Floating UI (`@floating-ui/dom`) | 2022 | Complete rewrite. Floating UI is the official successor. Smaller bundle, middleware architecture, better tree-shaking. |
| driver.js manual positioning | `@floating-ui/vue` `useFloating` | Floating UI Vue v1.0 (2023) | Vue-native composable with reactive positioning. No manual DOM manipulation needed. |
| Manual scroll/resize listeners for tooltip | `autoUpdate` with `whileElementsMounted` | Floating UI v1.0 | Automatic lifecycle management. Adds `ResizeObserver` + layout shift detection beyond basic scroll/resize. |
| CSS z-index raw numbers | CSS custom properties | App convention | Centralized z-index scale in `:root`. Prevents collision, enables theming. |

**Deprecated/outdated:**
- **Popper.js:** Officially deprecated. Floating UI is the successor. Do not use `@popperjs/core`.
- **driver.js for positioning:** driver.js bundles its own positioning logic which caused the highlight alignment issues noted in user feedback. Floating UI's middleware approach is more precise.
- **Manual tooltip positioning:** Calculating `getBoundingClientRect()` + viewport clamp + offset by hand. Floating UI middleware handles all edge cases.

## Open Questions

1. **Tooltip placement preference: `bottom` vs. `autoPlacement`**
   - What we know: `flip()` middleware flips the tooltip to the opposite side when it overflows. `autoPlacement()` tries all sides and picks the best one. Both prevent clipping.
   - What's unclear: Which provides better UX for a tour tooltip. `flip()` (bottom → top) is more predictable. `autoPlacement()` might place the tooltip on unexpected sides.
   - Recommendation: Use `flip()` with `placement: 'bottom'` as default. This gives predictable bottom-preference positioning that flips to top only when necessary. The `shift()` middleware handles left/right edge cases.

2. **Tour-specific CSS custom properties scope**
   - What we know: Some values (like `rgba(0, 0, 0, 0.7)` for the dim overlay) are tour-specific and don't map to existing global custom properties.
   - What's unclear: Whether to add these to App.vue's `:root` or define them locally in the tour component.
   - Recommendation: Define tour-specific properties in App.vue's `:root` alongside the existing `--z-tour-*` properties, prefixed with `--tour-` (e.g., `--tour-dim-color`, `--tour-glow-color`). This keeps all tour configuration centralized and themeable.

3. **Accent color choice: cyan vs. violet**
   - What we know: Existing TourOverlay.vue uses indigo/violet (`#6366f1`, `#818cf8`). The app's primary accent is cyan (`--accent-cyan: #00d4ff`). The design aesthetic demands contemporary, cohesive visuals.
   - What's unclear: Whether the tour should use cyan (matching app) or violet (providing contrast/distinction).
   - Recommendation: Use `--accent-cyan` as the primary tour accent for consistency with the rest of the app. The glow effect can use `--accent-cyan` with reduced opacity. This creates visual cohesion rather than the current disconnected violet palette.

## Sources

### Primary (HIGH confidence)
- Floating UI official docs, Vue integration (floating-ui.com/docs/vue) -- `useFloating` composable API, middleware configuration, `autoUpdate` lifecycle. Verified via Context7 `/floating-ui/floating-ui` (1069 snippets, HIGH reputation).
- Floating UI `autoUpdate` docs (Context7) -- `whileElementsMounted` pattern for Vue, configuration options (ancestorScroll, elementResize, layoutShift).
- Floating UI `arrow` middleware docs (Context7) -- Arrow element positioning with `middlewareData.arrow`, static side calculation.
- Floating UI `flip`, `shift`, `offset` middleware docs (Context7) -- Viewport overflow prevention middleware composition.
- Floating UI virtual elements docs (Context7) -- Custom `getBoundingClientRect()` reference for non-DOM anchors.
- App.vue CSS custom properties (codebase) -- Full variable inventory including colors, spacing, typography, shadows, transitions, z-index.
- Existing TourOverlay.vue (codebase) -- Working box-shadow dimming, spotlight tracking, pointer-events pattern.
- User feedback (feedback_onboarding_tour.md, feedback_design_aesthetic.md) -- UX requirements, design standards, known issues.

### Secondary (MEDIUM confidence)
- npm registry (`@floating-ui/vue@1.1.11`, `@floating-ui/dom@1.7.6`) -- Current versions verified via `npm view`.
- Existing codebase patterns for `ResizeObserver` (useAutoScroll.ts) and `requestAnimationFrame` (useStreamingParser.ts, api/client.ts) -- Established patterns for DOM observation and frame-batched updates.

### Tertiary (LOW confidence)
- Performance impact of `box-shadow` animation vs. `opacity` animation -- General web performance guidance, not measured in this specific codebase. Recommend opacity approach but needs profiling.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- `@floating-ui/vue` is the official Vue integration for Floating UI, verified via Context7 with extensive documentation.
- Architecture: HIGH -- Component decomposition follows existing codebase patterns. Virtual element bridge is documented in Floating UI official docs.
- Recommendations: HIGH -- All recommendations based on official Floating UI documentation verified via Context7. Box-shadow technique already proven in codebase.
- Pitfalls: HIGH -- Derived from direct codebase analysis (existing TourOverlay.vue, z-index values, toast conflict, CSS custom properties) and Floating UI documentation.

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (Floating UI is stable; 30-day validity)