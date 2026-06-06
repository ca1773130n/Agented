import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// OB-35a: a "Restart Setup Guide" button in Settings clears tour state
// and starts from the first incomplete step. The full GeneralSettings
// component is intentionally untested at the render level (form state,
// DirectoryBrowser, harness wiring); these source-string tests guard
// against the restart wiring being silently dropped.
describe('GeneralSettings — restart-tour wiring (OB-35a)', () => {
  const source = readFileSync(
    resolve(__dirname, '../GeneralSettings.vue'),
    'utf-8',
  )

  it('imports the tour machine composable', () => {
    expect(source).toMatch(/import\s+\{[^}]*useTourMachine[^}]*\}/)
  })

  it('defines a handleRestartTour handler that calls restartTour()', () => {
    expect(source).toMatch(/function\s+handleRestartTour\s*\(/)
    expect(source).toMatch(/restartTour\s*\(/)
  })

  it('renders a restart-tour-btn wired to the handler', () => {
    expect(source).toMatch(/class="[^"]*restart-tour-btn[^"]*"/)
    expect(source).toMatch(/@click="handleRestartTour"/)
  })

  // Saving the workspace path completes the workspace tour step; it must
  // auto-advance the tour instead of leaving it stuck (regression guard).
  it('auto-advances the tour after saving the workspace during onboarding', () => {
    const save = source.slice(source.indexOf('async function saveWorkspaceRoot'))
    expect(save).toMatch(/currentStep\.value === 'workspace'/)
    expect(save).toMatch(/tourMachine\.nextStep\(\)/)
  })
})
