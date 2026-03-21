# Onboarding Pitfalls & Anti-Patterns

Research document for the Agented onboarding tour redesign. Covers common pitfalls in web application onboarding with specific focus on developer tools and automation platforms.

**Context:** Agented's onboarding flow involves API key generation, workspace directory setup, 4 AI backend account registrations (Claude, Codex, Gemini, OpenCode), token monitoring configuration, plugin verification, and product/project creation. The current implementation uses a custom `TourOverlay.vue` with `useTour.ts` composable, driver.js installed but not actively used, and a `WelcomePage.vue` for first-run key generation.

---

## 1. UX Pitfalls

### 1.1 Information Overload (Too Many Steps at Once)

Presenting all 7+ onboarding steps (workspace, 4 backends, monitoring, plugins, product, project, teams) as one continuous tour overwhelms the user. Developer tool users want to explore at their own pace — they are not consumer app users who need hand-holding.

**Warning signs:**
- Users skip multiple consecutive steps
- Completion rate drops sharply after step 3-4
- Users close the tour and never reopen it
- Feedback mentions "too long" or "I just want to use it"

**Prevention strategy:**
- Break onboarding into tiers: Critical (API key + workspace), Recommended (1 backend account), and Optional (remaining backends, monitoring, plugins, product/project)
- Let users complete Critical tier and start using the app immediately
- Surface Recommended/Optional as contextual nudges when users navigate to relevant pages
- Show a progress dashboard (checklist) rather than a forced linear tour

**Phase:** Phase 1 (Architecture) — define tier system before building any steps

---

### 1.2 No Escape Hatch (Forcing Completion)

Trapping users in a tour with no clear way to exit is the fastest way to create hostility. The current implementation has `pointer-events: none` on the overlay, which blocks interaction outside the spotlight. If a user needs to check something else, they are stuck.

**Warning signs:**
- Users refresh the page to escape
- Users open a new tab/window
- The only exit is "Skip" (which feels like failure) or "Next" (which forces progress)
- Non-skippable steps (`skippable: false`) with no alternative path

**Prevention strategy:**
- Always provide a clearly labeled "Exit Tour" or "I'll do this later" option distinct from "Skip Step"
- Exiting should save progress so users can resume from where they left off
- Never block the entire UI — allow clicking outside the spotlight to interact with the app
- Make every step skippable, even if the step is important (mark it as "incomplete" in the checklist instead)

**Phase:** Phase 1 (Architecture) — escape hatch must be a core design principle

---

### 1.3 Generic Tooltips That Don't Help

Messages like "Register your Anthropic account for Claude Code" tell users what they already know from the page title. Developer users need actionable guidance: where to find their API key, what format the config path expects, which env var name to use.

**Warning signs:**
- Tour messages repeat what the page heading already says
- Messages contain no information the user couldn't derive from the UI itself
- Users still ask "but what do I put here?" after reading the tooltip
- No links to relevant documentation

**Prevention strategy:**
- Each tooltip should answer "what do I do right now?" not "what is this?"
- Include concrete examples: "Enter `~/.config/claude` or leave blank for default"
- Link to external docs (Anthropic dashboard, OpenAI API keys page) where users need to go to get values
- Use micro-copy that acknowledges the user's context: "If you don't have an API key yet, you can get one at..."

**Phase:** Phase 2 (Content) — write all tooltip content after architecture is finalized

---

### 1.4 Highlight Misalignment (Spotlight Doesn't Match Element)

The spotlight cutout drifts from its target element due to: padding miscalculation, scroll position not accounted for, elements inside scrollable containers, or `getBoundingClientRect()` returning stale values after layout shifts.

**Warning signs:**
- Glow border appears offset from the target element
- Spotlight covers adjacent elements or cuts off part of the target
- Misalignment worsens after scrolling or resizing
- Different behavior on different screen sizes

**Prevention strategy:**
- Use `ResizeObserver` + `IntersectionObserver` in addition to `getBoundingClientRect()` for live tracking
- Account for scrollable parent containers (not just `window` scroll)
- Debounce position updates but keep them responsive (16ms / 1 frame)
- Test on multiple viewport sizes; ensure `padding` values adapt to element type (inputs need less padding than cards)
- Scroll the target into view before measuring: `element.scrollIntoView({ behavior: 'smooth', block: 'center' })`

**Phase:** Phase 3 (Implementation) — build robust position tracking system

---

### 1.5 Pointer Event Blocking (Can't Interact with Highlighted Elements)

The overlay uses `pointer-events: none` globally but the spotlight area doesn't re-enable pointer events. Users see a highlighted form field but can't click or type in it. This is the most frustrating tour UX failure.

**Warning signs:**
- Users click on the highlighted element and nothing happens
- Users can see the element but can't interact with it
- The "Next" button is the only clickable thing on the screen
- Form fields are highlighted but can't receive focus or input

**Prevention strategy:**
- The spotlight cutout element must have `pointer-events: auto` to pass clicks through to the underlying target
- Better: don't use a full-screen overlay at all — use a combination of `box-shadow` on a positioned element + `isolation: isolate` to create the dimming effect without blocking events
- Test every step by actually interacting with the highlighted element during development
- Consider "coaching marks" (small popovers next to elements) instead of full-screen spotlight overlays

**Phase:** Phase 3 (Implementation) — critical to get right, test with real interaction

---

### 1.6 Missing Loading States During Page Transitions

When the tour navigates to a new route (e.g., from `/settings` to `/backends/backend-claude`), Vue Router's lazy loading creates a gap where the target element doesn't exist yet. The current implementation shows a spinner, but it has no timeout, no retry logic, and no way for the user to know if something is broken vs. still loading.

**Warning signs:**
- Spinner appears indefinitely
- User sees a blank dimmed screen after navigation
- `MutationObserver` fires hundreds of times looking for a target that hasn't loaded yet
- Tour advances to next step even though the current page hasn't finished loading

**Prevention strategy:**
- Wait for `router.isReady()` after navigation before starting element search
- Set a maximum wait time (5 seconds) with a fallback message: "This page is taking longer than expected. [Skip] [Retry]"
- Use `nextTick()` + a small delay (100ms) after route change before querying the DOM
- Pre-load routes that the tour will visit using `router.prefetch()` or dynamic imports
- Show a skeleton/shimmer state instead of a generic spinner

**Phase:** Phase 3 (Implementation) — handle after route architecture is decided

---

### 1.7 Skip Without Confirmation

Pressing X or Skip immediately advances past an important step with no way to undo. In the current implementation, clicking "Skip" on the backends step skips all 4 backend registrations at once, and there's no way to go back.

**Warning signs:**
- Users accidentally skip steps by clicking X too quickly
- Users want to go back but can't
- Important configuration steps are missed because skip was too easy
- No distinction between "I'll do this later" and "I don't need this"

**Prevention strategy:**
- For critical steps, show a confirmation: "Skip backend setup? You can configure this later in Settings."
- Provide a "Back" button to return to previous steps
- Track skipped steps separately from completed steps in the checklist
- After the tour ends, show a summary of skipped steps with links to complete them
- Never use an X/close button that looks like "dismiss" — it should be explicitly labeled

**Phase:** Phase 2 (Design) — define skip/back behavior in the interaction model

---

### 1.8 No Way to Restart or Resume

Once a user exits or completes the tour, there's no way to go through it again. The current implementation sets `tourComplete: true` in localStorage and that's it — no restart button, no setup checklist, no way to revisit skipped steps.

**Warning signs:**
- Users ask "how do I set up X?" after the tour is over
- No setup checklist or progress indicator exists post-tour
- `localStorage` state is the only record of what was done
- Users who cleared their browser data lose all tour state

**Prevention strategy:**
- Provide a persistent "Setup Checklist" accessible from the sidebar or settings
- The checklist should show completed, skipped, and remaining items
- Each checklist item should be clickable and navigate to the relevant page
- Store completion state server-side (tied to the user/installation) not just in localStorage
- Add a "Restart Setup Guide" button in Settings

**Phase:** Phase 1 (Architecture) — checklist is a core architectural decision

---

### 1.9 Dismissal Confusion (X vs. Skip vs. Next)

Three different actions that could all mean "move forward" confuse users. X could mean "close the tour permanently," "skip this step," or "minimize." Skip could mean "skip this step" or "skip the entire tour." The user doesn't know the consequences of each action.

**Warning signs:**
- Users click X expecting to skip one step but the entire tour ends
- Users click Skip expecting to skip a sub-step but skip the whole step group
- Users are afraid to click anything because they don't know what will happen
- Different steps have different button configurations (some have Skip, some don't)

**Prevention strategy:**
- Remove the X button entirely — it creates ambiguity
- Use explicitly labeled actions only: "Next Step," "Skip This Step," "Exit Tour"
- Keep the button layout consistent across all steps
- For substeps (e.g., 4 backend registrations), make it clear that Skip skips only the current backend, not all backends
- Use destructive-action styling (red/warning) for "Exit Tour" to differentiate it

**Phase:** Phase 2 (Design) — button hierarchy and labeling

---

## 2. Technical Pitfalls

### 2.1 Race Conditions with Lazy-Loaded Routes

Vue Router lazy-loads route components. When the tour calls `router.push('/backends/backend-claude')`, the component hasn't mounted yet. The tour's `MutationObserver` starts scanning for `[data-tour="add-account-btn"]` but the element doesn't exist until the async component resolves, fetches data from the API, and renders.

**Warning signs:**
- Tour step shows spinner/loading state for unpredictable durations
- `document.querySelector(selector)` returns null intermittently
- `MutationObserver` callbacks fire dozens of times before finding the target
- Works in development (fast local server) but fails in production (slower loads)

**Prevention strategy:**
- After `router.push()`, await `router.isReady()` then wait for `nextTick()`
- Use a polling approach with exponential backoff: check at 50ms, 100ms, 200ms, 400ms, max 5s
- Emit a custom event (`tour:page-ready`) from each page component's `onMounted` after initial data is loaded
- Pre-fetch route components and their API data before navigating
- Never rely on `MutationObserver` alone — it fires too frequently and has no built-in timeout

**Phase:** Phase 3 (Implementation) — must be solved in the navigation layer

---

### 2.2 localStorage Conflicts Across DB Resets

When the backend database is reset (`just reset`), the frontend's localStorage still contains old tour state, API keys, and completion flags. The tour thinks it's complete when the backend is in a fresh state, or worse, the stored API key is invalid causing 401 errors on every request.

**Warning signs:**
- After `just reset`, the app shows the dashboard instead of the welcome page
- 401 errors flood the console because the stored API key doesn't exist in the new DB
- Tour state shows "complete" but no backends are configured
- User sees inconsistent state between what the tour says and what the app shows

**Prevention strategy:**
- On app startup, validate the stored API key against the backend (already partially implemented via `healthApi.check()`)
- If the backend returns `needs_setup`, clear all tour-related localStorage keys
- Use a "state version" in localStorage that includes a hash of the DB — if the hash changes, invalidate all cached state
- The `WelcomePage.vue` already clears stale state on mount (validated fix), but this should also happen in the router guard before the welcome page loads
- Store minimal state in localStorage; use the backend as source of truth for what's configured

**Phase:** Phase 1 (Architecture) — state management strategy must be decided early

---

### 2.3 Tour State Gets Stale When App State Changes

The tour tracks `currentStepIndex` but doesn't verify that the corresponding app state still makes sense. Example: the tour is on "Create a Product" but the user already created one via the API or another tab. The tour shows a step that's no longer relevant.

**Warning signs:**
- Tour prompts user to do something they've already done
- Tour says "Click Add Account" but there are already 3 accounts configured
- After a browser refresh, the tour resumes at a step that no longer makes sense
- Tour shows "Step 5 of 8" but steps 2-4 were completed outside the tour

**Prevention strategy:**
- Before showing each step, verify a precondition: "Does this step still need to be done?"
- Define step preconditions as functions: `() => backendAccounts.length === 0` for "Add Account" step
- If a step's precondition is already met, auto-advance to the next incomplete step
- Re-validate on every resume (page load, tab focus, route change)
- Use the backend's actual state (API responses) rather than frontend-only completion tracking

**Phase:** Phase 1 (Architecture) — precondition system is a core design decision

---

### 2.4 MutationObserver Performance Issues

The current `TourOverlay.vue` creates a `MutationObserver` watching `document.body` with `{ childList: true, subtree: true }`. Every DOM mutation in the entire application triggers the observer callback, which calls `document.querySelector()`. In a reactive Vue app with frequent re-renders, this can cause jank.

**Warning signs:**
- Page feels sluggish when the tour overlay is active
- Chrome DevTools Performance tab shows frequent long tasks from `MutationObserver` callbacks
- `document.querySelector()` is called hundreds of times per second
- Memory usage climbs steadily while the tour is active

**Prevention strategy:**
- Scope the `MutationObserver` to the specific container where the target element lives, not `document.body`
- Disconnect the observer as soon as the target is found — don't keep watching
- Use `requestAnimationFrame` to throttle observer callbacks
- Consider replacing `MutationObserver` with a targeted approach: emit events from components when they mount, or use Vue's `ref` system to track element availability
- Set a max observation duration (5 seconds) after which the observer disconnects and shows a fallback

**Phase:** Phase 3 (Implementation) — optimization concern during build

---

### 2.5 Z-Index Wars with Modals/Dropdowns

The tour overlay uses `z-index: 10000` and the bottom bar uses `z-index: 10003`. Any modal, dropdown, toast notification, or select menu that appears during the tour must have its z-index coordinated. The "Add Account" flow likely opens a modal — if the modal's z-index is lower than the overlay, the user can't interact with it.

**Warning signs:**
- Modals appear behind the tour overlay dimming
- Dropdown menus are clipped or hidden behind the overlay
- Toast notifications are invisible during the tour
- The tour's "Next" button covers a modal's "Save" button

**Prevention strategy:**
- Define a z-index scale in CSS custom properties and use it consistently:
  - `--z-dropdown: 1000`
  - `--z-modal: 2000`
  - `--z-toast: 3000`
  - `--z-tour-overlay: 4000`
  - `--z-tour-popover: 5000`
- When a modal opens during a tour step, temporarily adjust the overlay to accommodate it
- Better: pause the overlay dimming when a modal is active (detect via `aria-modal` or a shared reactive state)
- Test every step that involves opening modals, dropdowns, or popovers

**Phase:** Phase 3 (Implementation) — requires coordination with existing component z-indices

---

### 2.6 SSR/Hydration Issues with DOM-Dependent Tours

Not directly applicable to Agented (Vite SPA, no SSR), but relevant for future-proofing. If the app ever moves to Nuxt or SSR, any code that accesses `document`, `window`, `localStorage`, `MutationObserver`, or `getBoundingClientRect()` during server rendering will crash.

**Warning signs:**
- `ReferenceError: document is not defined` during server rendering
- Hydration mismatch warnings because server-rendered HTML doesn't include tour elements
- `localStorage` access in composable setup functions runs during SSR

**Prevention strategy:**
- Guard all DOM access with `onMounted` or `typeof window !== 'undefined'` checks
- Never access `localStorage` at module scope — only inside lifecycle hooks
- Use `shallowRef` for DOM element references to avoid deep reactivity on native objects
- Keep the tour composable lazy: don't initialize until explicitly called from a client-side context

**Phase:** Phase 1 (Architecture) — defensive coding practice, low cost to implement

---

### 2.7 Memory Leaks from Uncleared Observers/Listeners

The current `TourOverlay.vue` adds `scroll` and `resize` event listeners and a `MutationObserver`. If the component unmounts without cleanup (e.g., due to a route change or error boundary), these listeners persist, holding references to detached DOM elements and causing memory leaks.

**Warning signs:**
- Chrome DevTools Memory tab shows growing "Detached HTMLElement" counts
- Event listener count in Performance tab increases over time
- After navigating away from the tour and back, there are duplicate listeners
- `onUnmounted` cleanup code exists but isn't reached in error cases

**Prevention strategy:**
- Use `onScopeDispose` (Vue 3.5+) or `onUnmounted` for cleanup, but also implement `AbortController` for event listeners so they can be cleaned up from multiple code paths
- Disconnect `MutationObserver` in every exit path: unmount, tour end, step change, error
- Use `watchEffect` with automatic cleanup instead of manual `watch` + `observer.disconnect()`
- Test by navigating rapidly between pages while the tour is active — check for listener accumulation

**Phase:** Phase 3 (Implementation) — implement defensive cleanup patterns

---

## 3. Design Pitfalls

### 3.1 Tour Looks "Bolted On" Instead of Integrated

The tour overlay, bottom bar, and spotlight glow use a separate design language from the rest of the app. The bottom bar's `#1a1a2e` background and `#818cf8` accent don't necessarily match the app's theme variables. It feels like a third-party library overlay rather than a native part of the UI.

**Warning signs:**
- Tour elements have hardcoded colors instead of CSS custom properties
- Font sizes, border radii, and spacing don't match the app's design tokens
- The tour "feels" different from the rest of the app — like a demo mode
- Animations/transitions have different timing curves than the app's standard animations

**Prevention strategy:**
- Use the app's CSS custom properties (`--color-primary`, `--color-bg-secondary`, etc.) for all tour styling
- Match the tour's typography to the app's Geist font configuration exactly (size, weight, letter-spacing)
- Use the same border-radius, shadow, and spacing tokens as the rest of the app
- The tour should feel like an enhanced state of the normal UI, not a separate layer
- Reference the design language: Linear, Vercel, Raycast — their onboarding feels native to their UI

**Phase:** Phase 2 (Design) — establish visual integration principles

---

### 3.2 Inconsistent Styling Between Tour UI and App UI

Buttons in the tour (`.tour-next-btn`, `.tour-skip-btn`) don't match the app's button styles. If the app uses `.btn.btn-primary` with certain padding, border-radius, and transitions, the tour buttons should use the same classes or at minimum the same visual treatment.

**Warning signs:**
- Tour buttons are visually distinct from app buttons (different padding, radius, hover effects)
- Tour text uses different font sizes or line heights than adjacent app text
- Color palette in the tour doesn't include the app's accent/brand colors
- Users perceive the tour as "not part of the real app"

**Prevention strategy:**
- Reuse the app's existing button component/classes for tour actions
- Define tour-specific styles as extensions of app styles, not replacements
- Use a shared design token file that both the app and tour consume
- Review tour UI side-by-side with app UI to check for visual inconsistencies

**Phase:** Phase 2 (Design) — audit and align before implementation

---

### 3.3 Poor Contrast in Dark Themes

Agented uses a dark theme. Tour text, borders, and subtle UI elements can easily become unreadable against dark backgrounds, especially when the dimming overlay changes the perceived brightness of surrounding elements.

**Warning signs:**
- Tour message text blends into the dimmed background
- Step counter or substep labels are hard to read
- The spotlight glow is either too bright (distracting) or too dim (invisible)
- Accessibility audit fails WCAG AA contrast ratio (4.5:1 for normal text)

**Prevention strategy:**
- Test all tour text against the actual backdrop (including the dimming overlay)
- Ensure at least 4.5:1 contrast ratio for all text elements
- The spotlight glow border (`#818cf8` on dark) should be tested on various element backgrounds (dark cards, dark inputs, dark tables)
- Provide sufficient contrast between the dimmed area (overlay) and the un-dimmed spotlight
- Test with colorblindness simulation tools (Chromatic Vision Simulator)

**Phase:** Phase 2 (Design) — validate all color choices with contrast tools

---

### 3.4 Tour Popover Obscures the Target Element

When a tooltip or popover is positioned near its target element, it can cover the very element it's explaining. This is especially problematic for form fields — the user reads "Enter your config path" but the input field is behind the popover.

**Warning signs:**
- Users try to interact with the target but the popover is in the way
- The popover covers the target on small screens or when the target is near the edge
- Auto-positioning logic places the popover on top of the target instead of beside it
- Users have to dismiss the popover to see what it's pointing at

**Prevention strategy:**
- Use smart positioning: prefer placing popovers to the side of the target, not directly above/below
- If the target is a form field, position the popover so the field remains fully visible and interactive
- Implement viewport-aware repositioning: if the popover would go off-screen, flip it to the other side
- For the bottom bar approach (current design): ensure the bar doesn't cover elements near the bottom of the viewport — scroll the target into the upper 60% of the screen
- Keep popovers compact — long messages should be in expandable sections, not blocking the view

**Phase:** Phase 2 (Design) + Phase 3 (Implementation) — positioning logic is design-informed

---

### 3.5 Bottom Bar Covers Important Content

The current tour uses a fixed bottom bar (`position: fixed; bottom: 0`). Any content near the bottom of the page — including form submit buttons, table footers, or pagination — is hidden behind the bar.

**Warning signs:**
- Users can't see or click buttons at the bottom of the page
- The "Save" button for a form is behind the tour bar
- Scrolling to the bottom doesn't reveal hidden content because the bar is fixed
- The bar takes up vertical space that shrinks the usable viewport, especially on laptops

**Prevention strategy:**
- Add `padding-bottom` to the main content area equal to the bar height when the tour is active
- Keep the bar minimal height (48-56px) — the current 14px padding + text could be more compact
- Consider making the bar dismissable/collapsible
- Alternative: use floating popovers next to each element instead of a persistent bottom bar
- Alternative: use an inline progress indicator at the top (thinner, less intrusive)
- On small viewports, switch to a minimal indicator that expands on tap

**Phase:** Phase 2 (Design) — layout impact must be designed, not patched

---

## 4. Previously Encountered Issues (Validated from Agented Codebase)

These issues were identified through actual user testing of the Agented onboarding tour. They are validated pitfalls — not theoretical risks.

### 4.1 Spotlight Glow Misalignment with Target Elements

**Source:** Memory feedback item #1 — "driver.js stagePadding/stageRadius doesn't match the actual element boundaries. The spotlight area is offset or misaligned."

**Root cause:** The initial implementation used driver.js with `stagePadding` and `stageRadius` that didn't account for the target element's own border-radius, padding, or margin. The custom `TourOverlay.vue` replaced driver.js but uses a fixed `pad = 8` value that doesn't adapt to different element types.

**Warning signs:**
- Glow border doesn't align with input field borders
- Spotlight on a button has different visual weight than spotlight on a card
- The 8px padding looks wrong on small elements (icons) and large elements (full-width cards)

**Prevention strategy:**
- Use element-specific padding: read the target's computed `border-radius` and match it
- Define padding presets by element type: `input` = 4px, `button` = 6px, `card/section` = 12px
- Use `data-tour-padding` attributes on elements that need custom spacing
- Visually test every single tour step — automated tests can't catch visual misalignment

**Phase:** Phase 3 (Implementation)

---

### 4.2 X Button / Close Button Interference

**Source:** Memory feedback item #2 — "driver.js close button gets highlighted or interferes with the tour UI."

**Root cause:** When using driver.js, its built-in close button had its own styling and event handling that conflicted with the custom tour UI. Even after switching to a custom overlay, the dismiss behavior is ambiguous (see Pitfall 1.9).

**Warning signs:**
- Close button in the driver.js popover has different behavior than the custom tour's close
- Multiple dismiss mechanisms exist with different outcomes
- The close button's hit target overlaps with other interactive elements

**Prevention strategy:**
- Since driver.js was replaced with custom `TourOverlay.vue`, ensure no driver.js remnants interfere
- If driver.js is reintroduced, disable its built-in close button (`showButtons: ['next']`, no close)
- Use a single, unambiguous dismiss mechanism (see Pitfall 1.9 solution)

**Phase:** Phase 2 (Design) — finalize dismiss behavior before building

---

### 4.3 Step Skipping Without Confirmation or Guide Message

**Source:** Memory feedback item #3 — "pressing X skips the entire step (e.g., AI backend account setup) without any guide message or user confirmation."

**Root cause:** The `skipStep()` function in `useTour.ts` immediately advances `currentStepIndex` without any confirmation UI. For the backends step (which has 4 substeps), skipping jumps past all 4 backends at once.

**Warning signs:**
- A single click permanently skips a multi-part step
- No undo/back capability after skipping
- Users don't understand the consequences of skipping (can they come back? will things break?)
- The `completed` array doesn't distinguish between "completed" and "skipped"

**Prevention strategy:**
- Add a `skipped` array alongside `completed` to track the difference
- For multi-substep steps, ask: "Skip all remaining backends, or just this one?"
- Show a summary after skipping: "You skipped Claude Code setup. You can configure it later in Backends > Claude."
- Add a "Back" button to undo the last skip
- Mark skipped items distinctly in the post-tour checklist

**Phase:** Phase 2 (Design) — interaction model for skip/back

---

### 4.4 No Per-Field Form Guidance

**Source:** Memory feedback item #4 — "the tour should highlight EVERY input field one by one when setting up an AI account (account name -> email -> config path -> API key env -> save button). Not just the 'Add Account' button."

**Root cause:** The tour steps are defined at the page/section level, not the field level. The "backends" step targets `[data-tour="add-account-btn"]` which is just the "Add Account" button, not the individual form fields that appear after clicking it.

**Warning signs:**
- Tour highlights a button but not the form that appears after clicking it
- Users see "Register your account" but don't know which fields matter or what format to use
- No guidance on field-by-field completion (what goes in "config path"? what's "API key env"?)
- Tour advances to the next page before the user fills out the form

**Prevention strategy:**
- Define form-field-level substeps: highlight `#account_name`, then `#email`, then `#config_path`, then `#api_key_env`, then the submit button
- Each field substep should include a helpful message: "The environment variable that holds your API key (e.g., ANTHROPIC_API_KEY)"
- Wait for the form to be visible (after "Add Account" click) before starting field guidance
- Auto-advance substeps when the user fills a field and moves to the next (detect `blur` event)
- Use the auto-discovery framework (see 4.5) to generate field steps from DOM structure

**Phase:** Phase 3 (Implementation) — requires auto-discovery framework

---

### 4.5 Auto-Discovery Framework for Form Fields

**Source:** Memory feedback item #5 — "don't hardcode tour steps. Build a system that scans Vue views for .form-group elements and auto-generates tour steps."

**Root cause:** Hardcoded tour step definitions become stale when the UI changes. If a form field is added, removed, or renamed, the tour breaks silently. The app uses consistent patterns (`.form-group` with `<label>` + `input/select/textarea`) that can be leveraged for automatic step generation.

**Warning signs:**
- Tour targets a `data-tour` attribute that was removed in a refactor
- New form fields have no tour coverage
- Tour step count doesn't match the actual number of form fields
- Developers forget to update tour steps when modifying forms

**Prevention strategy:**
- Build a `discoverFormFields(container: HTMLElement)` utility that:
  1. Finds all `.form-group` elements within a container
  2. Extracts the `<label>` text for the step title
  3. Finds the associated `input`/`select`/`textarea` for the target selector
  4. Generates tour substeps dynamically
- Fall back to `data-tour` attributes for non-form elements (buttons, sections)
- Run discovery after the page is fully rendered (post-`onMounted` + data fetch)
- Validate discovered fields against expected fields to catch regressions

**Phase:** Phase 1 (Architecture) — auto-discovery is a core architectural feature

---

### 4.6 Page Loading Race Conditions

**Source:** Memory feedback items #6 and #7 — "pages lazy-load and the tour shows nothing or dims prematurely" and "the normal dashboard briefly flashes before redirecting to /welcome on first visit."

**Root cause:** Two separate timing issues. (1) Lazy-loaded route components haven't rendered when the tour tries to find target elements. (2) The router guard that redirects to `/welcome` runs after the default route's component has already started mounting, causing a visible flash.

**Warning signs:**
- Dashboard briefly visible before welcome page appears
- Tour overlay dims the screen but no element is highlighted
- Spinner shows for an uncomfortably long time
- Different behavior on fast vs. slow connections

**Prevention strategy:**
- For welcome redirect flash: use `router.beforeEach` guard that resolves before any component mounts, and check `needs_setup` status before rendering any route
- For lazy loading: implement a `tour:ready` event system where page components signal readiness
- Use Vue's `<Suspense>` with `<RouterView>` for graceful loading states
- Pre-resolve the initial auth state before mounting the Vue app (`await checkAuth()` before `app.mount()`)

**Phase:** Phase 1 (Architecture) — routing/auth flow must be right from the start

---

### 4.7 401 Errors from Premature API Calls

**Source:** Memory feedback item #8 — "API calls fire before authentication completes."

**Root cause:** Components make API calls in their `onMounted` hooks before the API key is set in the client. During the onboarding flow, the API key doesn't exist until the user completes the welcome page, but route components try to fetch data immediately.

**Warning signs:**
- Console shows 401 errors on first load
- Network tab shows failed requests before the welcome page appears
- Components render error states ("Failed to load") briefly before the tour redirects them

**Prevention strategy:**
- Gate all API calls behind an auth-ready check: `if (!apiKey.value) return`
- Use a global `authReady` promise that resolves only after the API key is confirmed valid
- In the API client, queue requests made before auth is ready and replay them after
- Route guard should prevent mounting any authenticated route until auth is confirmed
- The `setApiKey()` call in `WelcomePage.vue` should trigger a reactive update that unblocks pending requests

**Phase:** Phase 1 (Architecture) — auth flow must prevent premature API calls

---

### 4.8 localStorage State Persistence Across DB Resets

**Source:** Memory feedback item #9 — "tour state persists across DB resets."

This is a duplicate of Technical Pitfall 2.2 but validated by real user testing. The `WelcomePage.vue` fix (clearing stale localStorage on mount) is a partial solution — it only works if the user lands on the welcome page. If the router guard fails to redirect (due to a cached auth state), the stale localStorage persists.

**Prevention strategy (additional to 2.2):**
- Add a backend health-check response field: `{ "db_version": "sha256-abc123" }` — if this changes, invalidate all client-side state
- On every app startup, compare the stored DB version with the backend's response
- Clear localStorage proactively in the router guard, not just in `WelcomePage.vue`

**Phase:** Phase 1 (Architecture)

---

### 4.9 Backend Installation Detection Inaccuracy

**Source:** Memory feedback item #10 — "Not Installed status wrong — backend detection now runs at startup and updates DB."

**Root cause:** Backend tools (claude, codex, gemini-cli, opencode) are detected via `shutil.which()` in `_detect_backends()` at app startup. If a tool is installed after the backend starts, the DB still shows "not installed." If a tool is in a non-standard path, `which()` fails.

**Warning signs:**
- Tour tells user to configure a backend that shows "Not Installed" even though the CLI exists
- User installs a CLI tool but the status doesn't update until server restart
- Different behavior between `just dev-backend` (auto-reload) and production (no auto-reload)

**Prevention strategy:**
- Add an on-demand "Re-scan Backends" button/API endpoint
- Check installation status when the user navigates to a backend detail page, not just at startup
- Accept user override: "I know this is installed, trust me" with a manual path entry
- During the tour, re-check backend status before showing the step to avoid stale data

**Phase:** Phase 3 (Implementation) — backend-specific enhancement

---

## Summary: Phase Assignment Matrix

| Phase | Pitfalls to Address |
|-------|-------------------|
| **Phase 1: Architecture** | 1.1 (Tier system), 1.2 (Escape hatch), 1.8 (Restart/resume/checklist), 2.2 (localStorage conflicts), 2.3 (Stale state/preconditions), 2.6 (SSR-safe patterns), 4.5 (Auto-discovery framework), 4.6 (Loading race conditions), 4.7 (401 auth errors), 4.8 (DB reset persistence) |
| **Phase 2: Design** | 1.3 (Generic tooltips), 1.7 (Skip confirmation), 1.9 (Dismiss confusion), 3.1 (Bolted-on look), 3.2 (Inconsistent styling), 3.3 (Dark theme contrast), 3.4 (Popover covering target), 3.5 (Bottom bar covering content), 4.2 (Close button interference), 4.3 (Skip without confirmation) |
| **Phase 3: Implementation** | 1.4 (Highlight misalignment), 1.5 (Pointer event blocking), 1.6 (Loading states), 2.1 (Lazy-load race conditions), 2.4 (MutationObserver performance), 2.5 (Z-index wars), 2.7 (Memory leaks), 4.1 (Spotlight glow), 4.4 (Per-field guidance), 4.9 (Backend detection) |
