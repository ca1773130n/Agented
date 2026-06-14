import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import TourCompletionScreen from '../TourCompletionScreen.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a :href="to"><slot/></a>',
  },
}))

describe('TourCompletionScreen', () => {
  it('renders when mounted with completed steps', () => {
    const wrapper = mount(TourCompletionScreen, {
      props: {
        completedSteps: ['workspace', 'monitoring'],
      },
    })

    expect(wrapper.find('.completion-heading').text()).toBe('Setup Complete')
    const configuredLabels = wrapper.findAll('.completion-list-item.configured .list-label')
    const labels = configuredLabels.map(el => el.text())
    expect(labels).toContain('Workspace Directory')
    expect(labels).toContain('Token Monitoring')
    wrapper.unmount()
  })

  it('shows skipped steps with links', () => {
    const wrapper = mount(TourCompletionScreen, {
      props: {
        completedSteps: [],
      },
    })

    const skippedLabels = wrapper.findAll('.completion-list-item.skipped .list-label')
    const labels = skippedLabels.map(el => el.text())
    expect(labels).toContain('Claude Code')
    expect(labels).toContain('Workspace Directory')
    wrapper.unmount()
  })

  it('emits done when Go to Dashboard clicked', async () => {
    const wrapper = mount(TourCompletionScreen, {
      props: {
        completedSteps: ['workspace'],
      },
    })

    await wrapper.find('.completion-btn').trigger('click')
    expect(wrapper.emitted('done')).toHaveLength(1)
    wrapper.unmount()
  })

  it('does not show skipped section when all steps completed', () => {
    const allSteps = [
      'workspace',
      'backends.claude',
      'backends.codex',
      'backends.gemini',
      'backends.opencode',
      'monitoring',
      'create_product',
      'create_project',
      'create_team',
    ]
    const wrapper = mount(TourCompletionScreen, {
      props: {
        completedSteps: allSteps,
      },
    })

    const skippedItems = wrapper.findAll('.completion-list-item.skipped')
    expect(skippedItems).toHaveLength(0)
    // Also verify section-divider-label "Skipped" is not shown
    expect(wrapper.find('.section-divider-label').exists()).toBe(false)
    wrapper.unmount()
  })

  // OB-36: completion icon animation is no-op under prefers-reduced-motion.
  it('disables completion icon animation under prefers-reduced-motion (OB-36)', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourCompletionScreen.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)!
    const styleBlock = styleMatch[1]
    const reducedBlock = styleBlock.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\}\s*\}/,
    )
    expect(reducedBlock).not.toBeNull()
    expect(reducedBlock![0]).toMatch(/\.completion-icon\s*\{[^}]*animation:\s*none/)
  })
})
