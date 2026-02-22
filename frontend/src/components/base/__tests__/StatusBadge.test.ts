import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusBadge from '../StatusBadge.vue'

describe('StatusBadge', () => {
  it('renders label text in span', () => {
    const wrapper = mount(StatusBadge, {
      props: { label: 'Active', variant: 'success' },
    })
    expect(wrapper.text()).toBe('Active')
  })

  it.each([
    ['success', 'ds-status-success'],
    ['warning', 'ds-status-warning'],
    ['danger', 'ds-status-danger'],
    ['info', 'ds-status-info'],
    ['neutral', 'ds-status-neutral'],
    ['violet', 'ds-status-violet'],
  ] as const)('applies correct CSS class for %s variant', (variant, expectedClass) => {
    const wrapper = mount(StatusBadge, {
      props: { label: 'Test', variant },
    })
    expect(wrapper.find('span').classes()).toContain(expectedClass)
  })

  it('renders as span element', () => {
    const wrapper = mount(StatusBadge, {
      props: { label: 'Badge', variant: 'info' },
    })
    expect(wrapper.element.tagName).toBe('SPAN')
  })
})
