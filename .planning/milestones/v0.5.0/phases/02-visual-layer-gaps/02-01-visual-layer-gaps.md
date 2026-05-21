# Plan 02-01: Visual Layer — close OB-11 + OB-13 gaps

**Phase:** 2 — Visual Layer
**Requirements:** OB-11 (element-adaptive padding + border-radius), OB-13 (dark theme custom properties)
**Depends on:** Existing tour components in `frontend/src/components/tour/` (shipped in earlier waves)
**Verification:** sanity (unit tests for padding logic + visual grep for hardcoded colors)

## Discovery

The Phase 1 plan documents implied a from-scratch tour engine, but the
production components and XState machine were already shipped through the
"tour wave 1–4" series. Their state is:

| Requirement | Existing implementation | Gap |
|-------------|------------------------|-----|
| OB-09 (full-screen overlay box-shadow) | TourSpotlight uses `box-shadow: 0 0 0 9999px var(--tour-overlay-dim)` | none |
| OB-10 (ResizeObserver tracking) | TourOverlay registers ResizeObserver + scroll listener that calls `updateRect()` | none |
| OB-11 (element-adaptive padding + border-radius) | Spotlight uses one global `--tour-spotlight-padding` and one global `--tour-spotlight-radius` | **needs adaptive computation** |
| OB-12 (Floating UI tooltip) | TourTooltip imports `useFloating` from `@floating-ui/vue` with offset/flip/shift/arrow + autoUpdate | none |
| OB-13 (dark theme via CSS custom properties) | All tour components read CSS variables — except TourCompletionScreen has 3 hardcoded `rgba(...)` values | **needs cleanup** |
| OB-14 (smooth transitions) | TourTooltip + TourSpotlight use CSS transitions + `prefers-reduced-motion` opt-out | none |
| OB-15 (pulsing glow with reduced-motion) | TourSpotlight `.tour-spotlight-glow` runs `animation: tour-glow 1.5s ease-in-out infinite` and disables under `prefers-reduced-motion: reduce` | none |
| OB-16 (progress indicator) | TourProgressBar shows `Step N of M`, current step label, Skip + Next buttons; bottom fixed | none |

So Phase 2 reduces to closing OB-11 and OB-13.

## OB-11 — element-adaptive padding + border-radius

The spotlight must read each target element's computed `border-radius` and
match it on its own border. Padding varies by element type:

- `<input>`, `<textarea>`, `<select>`: 4px
- `<button>`, `[role="button"]`: 6px
- `<section>`, `<article>`, `[data-tour-card]`, generic block elements: 12px

Override hook: any element with `data-tour-padding="<n>"` wins.

### Implementation

A new helper `computeSpotlightGeometry(target: Element)` returns
`{ padding: number, borderRadius: string }`. Called from TourSpotlight
whenever `props.targetRect` changes — but the rect doesn't carry the
element reference, so the parent (TourOverlay) needs to pass the element
alongside the rect, or TourSpotlight reads it via `document.elementFromPoint`
or a new prop. Cleanest: TourOverlay already has `targetEl`, so add a new
optional prop `targetEl: HTMLElement | null` to TourSpotlight and forward
the existing ref.

The spotlight's `style` becomes a derived computed that reads:
- `top`, `left`, `width`, `height` from the rect (already done)
- `borderRadius` from `getComputedStyle(targetEl).borderRadius` (new)
- the padding from the helper (new), used in `top -= pad` etc.

### Test plan

- `computeSpotlightGeometry.test.ts`: input → 4px, button → 6px, section → 12px,
  data-tour-padding="20" → 20px, unknown tag → 12px (default).
- Visual regression (manual): each step's spotlight matches the target's
  rounded corners.

## OB-13 — strip hardcoded colors from TourCompletionScreen

Three lines in `frontend/src/components/tour/TourCompletionScreen.vue`:

```css
background: rgba(0, 0, 0, 0.75);                 /* line 92 */
box-shadow: 0 0 0 0 rgba(0, 255, 136, 0);        /* line 129 */
box-shadow: 0 0 0 8px rgba(0, 255, 136, 0.4);    /* line 132 */
```

The first is the modal backdrop dim — replace with `var(--tour-overlay-dim)`
which already exists at the App.vue scale. The second/third are the
celebration pulse animation around the success icon — introduce two new
custom properties `--tour-success-pulse-from` and `--tour-success-pulse-to`
in App.vue, default to the existing accent green (`var(--accent-green)`
with calculated alpha), and reference them.

### Verification

`grep -E "rgba|rgb\(|#[0-9a-fA-F]{3,6}" frontend/src/components/tour/*.vue`
must return zero matches. CI would fail if a future change reintroduces a
hardcoded color.

## Files

- `frontend/src/components/tour/spotlightGeometry.ts` — new helper (~40 lines)
- `frontend/src/components/tour/__tests__/spotlightGeometry.test.ts` — new
- `frontend/src/components/tour/TourSpotlight.vue` — accept `targetEl` prop, use helper
- `frontend/src/components/tour/TourOverlay.vue` — pass `targetEl` to spotlight
- `frontend/src/components/tour/TourCompletionScreen.vue` — strip hardcoded colors
- `frontend/src/App.vue` — add `--tour-success-pulse-from` / `--tour-success-pulse-to`

## Estimated size

~80 lines new code, ~80 lines new tests. ~30 minutes of focused work.

## Out of scope (followups)

The discovery that the production XState machine + composable predate
the migration branch means Plan 01-01's `frontend/src/tour/` files were
duplicate code. They were deleted at the start of this branch. The new
`/health/setup-status` endpoint shipped in Phase 1 is currently unused;
wiring `useTourMachine` to call it (so guards are populated from the
backend instead of being `() => false` stubs) is a Phase 1 follow-up,
not Phase 2.
