# Plan 06-01: Navigation Controls polish — close OB-31/32 gaps

**Phase:** 6 — Navigation Controls
**Requirements:** OB-29 (bottom bar), OB-30 (substep labels), OB-31 (skip confirmation), OB-32 (no accidental dismissal), OB-33 (keyboard nav)
**Depends on:** Phase 2 visual layer, Phase 4 step content
**Verification:** sanity (unit tests for the two surface changes)

## Discovery

Most of Phase 6's surface is already implemented and tested:

| Requirement | Existing implementation | Gap |
|-------------|------------------------|-----|
| OB-29 (bottom bar with counter + Skip + Next) | `TourProgressBar.vue` renders all three; Skip is conditional on `skippable`. Counter via `tour.stepOf` i18n. | none |
| OB-30 (substep label) | `<span class="tour-substep-label">` shown when `substepLabel` is non-null. Step counter still shows the parent `stepNumber`. | none |
| OB-31 (skip confirmation for meaningful steps) | `skipNeedsConfirm` prop drives an inline confirmation row (`.tour-skip-confirm`). `TourOverlay.vue:178 SIGNIFICANT_STEP_TITLES` decides which step titles trigger the prompt. | **list is too narrow**: only `'AI Backend Accounts'`. OB-31 names "backend accounts, product/project creation" — product, project, team-assignment titles are missing. |
| OB-32 (no X/close button, no overlay-click dismiss) | Overlay click is `@click.stop` (`TourOverlay.vue:233`); explicit comment on the line. Progress bar exposes a `✕`-glyph dismiss button that calls `handleTourDismiss` in App.vue (which itself opens a `window.confirm`). | **`✕` button violates OB-32**: "no X/close button on the tour overlay or tooltip". The exit affordance must remain (the only way out short of completing every step), but the glyph has to become a labelled "Exit Tour" button. |
| OB-33 (keyboard nav) | `TourOverlay.vue:206 handleKeydown` binds Enter→next and Escape→skip (when skippable). `TourTooltip.vue:118 useFocusTrap` traps Tab inside the tooltip. | none |

## What this plan delivers

1. **`TourProgressBar.vue`** — replace the `✕` glyph + `class="tour-dismiss-btn"`
   button with a labelled "Exit Tour" button. Same emit, same behaviour;
   what changes is the visible affordance, which OB-32 forbids as a glyph.
2. **`TourOverlay.vue`** — extend `SIGNIFICANT_STEP_TITLES` to include the
   product/project/team titles so the skip confirmation fires there too:
   - `'AI Backend Accounts'` (existing)
   - `'Create Your First Product'`
   - `'Create Your First Project'`
   - `'Assign Teams to Project'`
3. **Tests** — add three `TourProgressBar` cases:
   - The dismiss button is labelled (not just `✕`).
   - The dismiss button still emits `dismiss` on click.
   - Verify `dismiss` is not triggered by overlay clicks (parent overlay
     test responsibility, but a smoke check at the progress-bar level).
4. **Tests** — add two `TourOverlay` cases asserting `skipNeedsConfirm` is
   true for each of the three new significant titles.

## Out of scope

- Refactoring the `window.confirm` in `App.vue:handleTourDismiss` to use
  the in-tour confirmation row. The progress bar's inline confirm
  pattern only handles per-step Skip; an Exit Tour confirm is a related
  but bigger change. Captured for a future plan.

## Files

- `frontend/src/components/tour/TourProgressBar.vue` — relabel dismiss
  button.
- `frontend/src/components/tour/TourOverlay.vue` — extend
  `SIGNIFICANT_STEP_TITLES`.
- `frontend/src/components/tour/__tests__/TourProgressBar.test.ts` —
  3 new cases.
- `frontend/src/components/tour/__tests__/TourOverlay.test.ts` —
  3 new cases (one per new significant title).
- `frontend/src/locales/en.json` — new `tour.exitTour` string used as
  the visible button label.

## Estimated size

~30 lines of source change, ~80 lines of tests. ~20 minutes.
