import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { TOUR_STEP_DEFINITIONS, TOUR_STEP_MAP } from '../tourSteps'

// OB-22 / OB-23 / OB-24: each step's data-tour selector must exist
// in production code. The 3s element-not-found fallback would
// otherwise fire on every product/project/team step. These tests
// guard against the target attribute being renamed or removed.
describe('tour step targets exist in production source (OB-22, OB-23, OB-24)', () => {
  function viewSource(filename: string): string {
    return readFileSync(resolve(__dirname, '../../views', filename), 'utf-8')
  }

  it('OB-22 — [data-tour="create-product"] exists in ProductsPage.vue', () => {
    const step = TOUR_STEP_MAP['create_product']
    expect(step?.target).toBe('[data-tour="create-product"]')
    expect(viewSource('ProductsPage.vue')).toContain('data-tour="create-product"')
  })

  it('OB-23 — [data-tour="create-project"] exists in ProductDashboard.vue', () => {
    const step = TOUR_STEP_MAP['create_project']
    expect(step?.target).toBe('[data-tour="create-project"]')
    expect(viewSource('ProductDashboard.vue')).toContain('data-tour="create-project"')
  })

  // OB-24 (v0.5.1 fix): the tour step navigates to `/projects` (the
  // list page). The anchor lives on ProjectsPage.vue so the spotlight
  // resolves immediately rather than relying on the 3s element-not-
  // found fallback. The previous anchor on ProjectSettingsPage.vue
  // (project-detail page) is gone — the second assertion guards
  // against accidental double-anchoring during a refactor.
  it('OB-24 — [data-tour="assign-teams"] is on ProjectsPage.vue and not ProjectSettingsPage.vue', () => {
    const step = TOUR_STEP_MAP['create_team']
    expect(step?.target).toBe('[data-tour="assign-teams"]')
    expect(step?.route).toBe('/projects')
    expect(viewSource('ProjectsPage.vue')).toContain('data-tour="assign-teams"')
    expect(viewSource('ProjectSettingsPage.vue')).not.toContain('data-tour="assign-teams"')
  })

  it('all step keys are unique', () => {
    const keys = TOUR_STEP_DEFINITIONS.map((d) => d.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})
