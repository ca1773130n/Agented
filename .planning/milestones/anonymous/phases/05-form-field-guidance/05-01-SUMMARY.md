---
phase: 05-form-field-guidance
plan: 01
subsystem: frontend/tour
tags: [tour, form-guide, auto-discovery, composable]
dependency_graph:
  requires: []
  provides: [useFormGuide, FormField, TourFormGuide]
  affects: [TourOverlay]
tech_stack:
  added: []
  patterns: [renderless-component, composable-with-ref-container]
key_files:
  created:
    - frontend/src/composables/useFormGuide.ts
    - frontend/src/components/tour/TourFormGuide.vue
  modified: []
decisions:
  - "Selector generation prefers input id-based selectors (.form-group:has(#id)) for uniqueness, falls back to nth-of-type"
  - "Checkbox groups use the .form-group element itself as inputSelector rather than the checkbox input"
  - "TourFormGuide is a renderless component using slot-only template for zero DOM footprint"
  - "field-change emit shape { target: string, message: string } is compatible with TourOverlay TargetLike interface"
metrics:
  duration: 8min
  completed: 2026-03-22
---

# Phase 05 Plan 01: Form Field Auto-Discovery Summary

useFormGuide composable and TourFormGuide renderless component providing DOM-order form field discovery with help text extraction and sequential navigation state.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create useFormGuide composable | 1f60246 | frontend/src/composables/useFormGuide.ts |
| 2 | Create TourFormGuide component | 8d02f90 | frontend/src/components/tour/TourFormGuide.vue |

## What Was Built

### useFormGuide Composable

- **FormField interface** with selector, inputSelector, label, helpText, isSubmit, element properties
- **Auto-discovery** queries all `.form-group` elements within a container ref, building fields in DOM order
- **Help text priority chain:** `data-tour-help` attribute > `.form-help`/`.form-description` > `<small>` > generated fallback
- **Submit button detection:** `button[type=submit]` > `.btn-primary` in `.inline-form-actions` > `[data-tour=submit-btn]`, appended as last field
- **Navigation API:** activate/deactivate, nextField/prevField (return boolean), reset, currentField computed, totalFields computed
- **Edge cases:** checkbox groups use .form-group as inputSelector, empty containers leave isActive false

### TourFormGuide Component

- Renderless Vue 3 component wrapping useFormGuide
- Accepts `active` boolean and `containerSelector` string props
- Emits `field-change` with `{ target: string, message: string }` matching TourOverlay TargetLike interface
- Emits `complete` when user advances past last field (submit button)
- Exposes nextField/prevField and reactive state via defineExpose for parent control

## Verification

- `just build` passes with zero TypeScript errors
- Frontend tests: 977/980 pass (3 pre-existing failures in App.test.ts provide/inject tests, unrelated to this plan)
- Backend tests: not affected (frontend-only changes)

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

- [x] frontend/src/composables/useFormGuide.ts exists
- [x] frontend/src/components/tour/TourFormGuide.vue exists
- [x] Commit 1f60246 exists
- [x] Commit 8d02f90 exists
- [x] TypeScript compiles cleanly
