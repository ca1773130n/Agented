# Plan 05-01: Form Field Guidance — close the test gap

**Phase:** 5 — Form Field Guidance
**Requirements:** OB-25 (auto-discovery), OB-26 (sequential highlighting), OB-27 (help text extraction), OB-28 (submit button last)
**Depends on:** Phase 2 visual layer, Phase 4 step-content navigation
**Verification:** sanity (unit tests called out in each acceptance criterion)

## Discovery

`useFormGuide.ts` (221 LOC) already implements OB-25 through OB-28 end-to-end:

| Requirement | Existing implementation |
|-------------|------------------------|
| OB-25 auto-discovery | `container.querySelectorAll('.form-group')` walks DOM order, no hardcoded selectors |
| OB-26 sequential | `currentIndex` ref, `nextField()` / `prevField()` move through `fields.value` |
| OB-27 help text | priority chain: `data-tour-help` → `.form-help` / `.form-description` → `<small>` → fallback "Enter the {label} for this form" |
| OB-28 submit | `findSubmitButton`: `button[type="submit"]` → `.inline-form-actions .btn-primary` → `[data-tour="submit-btn"]`; pushed last into `fields[]` |

`TourFormGuide.vue` (78 LOC) wraps the composable as a renderless component
that watches `props.active` + `containerSelector` and emits `field-change` /
`complete` events.

**Gaps:**
1. **No tests exist** for either file. Each OB-2X acceptance line explicitly
   says "Tested by: Unit test ..." — the success-criteria gate is open.
2. The renderless `TourFormGuide` component isn't wired into `TourOverlay` /
   the tour flow. AccountWizard is a third-party `@ai-accounts/vue-styled`
   component, so deciding when to enter form-guidance mode requires an
   integration story we don't have yet. **Out of scope for 05-01** — this
   plan only closes the test gap. The wiring is a Phase 5 followup once we
   know how the AccountWizard exposes its open/close lifecycle.

## What this plan delivers

Three new test files driving the existing helpers. No new production code.

### `useFormGuide.test.ts`

- **Discovery (OB-25):**
  - empty container → no fields
  - `.form-group × N` → N fields in DOM order
  - nested elements outside `.form-group` are ignored
  - `activate()` while `containerRef.value` is null is a safe no-op

- **Help text priority (OB-27):**
  - `data-tour-help="..."` wins over everything
  - `.form-help` / `.form-description` is read when no override
  - `<small>` is read when neither override nor `.form-help`
  - generic fallback `"Enter the {label} for this form"` when nothing matches
  - `<label>` text strips trailing asterisks (required markers)

- **Selector building:**
  - input with `id` → `#id`
  - input without `id` → `.form-group:nth-of-type(...)` 1-indexed
  - `.checkbox` group uses the group selector for both `selector` and `inputSelector`

- **Submit button detection (OB-28):**
  - `button[type="submit"]` is detected and pushed last
  - `.inline-form-actions .btn-primary` works as fallback
  - `[data-tour="submit-btn"]` works as last-resort fallback
  - `isSubmit: true` is set on the submit field
  - the submit field is *always* the last entry in `fields[]`

- **Navigation (OB-26):**
  - `nextField()` advances the index, returns `true`
  - `nextField()` at last index returns `false` and does not advance
  - `prevField()` decrements
  - `prevField()` at index 0 returns `false`
  - `deactivate()` clears state
  - `reset()` returns to index 0 without clearing the fields list

### `TourFormGuide.test.ts`

- emits `field-change` with `{target, message}` when active and a field is current
- emits `field-change` with `null` when deactivated
- emits `complete` when `nextField()` is called past the last field
- exposes `nextField` and `prevField` via `defineExpose`

### Mocking

`vitest` + `@vue/test-utils` already in the project. Tests use real DOM via
`document.createElement` + `document.body.appendChild` so the
`containerRef.value` lookups behave as in the browser.

## Files

- `frontend/src/composables/__tests__/useFormGuide.test.ts` — new
- `frontend/src/components/tour/__tests__/TourFormGuide.test.ts` — new

## Estimated size

~250 lines of test code; no production change. ~30 minutes.

## Followup (out of scope here)

Wiring `TourFormGuide` into the tour flow when the user clicks Add Account
on a backend page. Requires either:
- A bridge that listens for AccountWizard's open event (if `@ai-accounts/vue-styled`
  exposes one), or
- A `data-tour="add-account-btn"` click handler that toggles a parent flag
  passed to `TourFormGuide`'s `active` prop.

Either way it's a Phase 5 → Phase 4 integration that benefits from the
form-guide having tested behaviour first.
