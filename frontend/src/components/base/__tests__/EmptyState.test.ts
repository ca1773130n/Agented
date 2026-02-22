import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import EmptyState from '../EmptyState.vue'

describe('EmptyState', () => {
  it('renders title in h3', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'No items found' },
    })
    expect(wrapper.find('h3').text()).toBe('No items found')
  })

  it('renders description when provided', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty', description: 'Try creating one' },
    })
    expect(wrapper.find('.ds-empty-description').text()).toBe('Try creating one')
  })

  it('does not render description element when not provided', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty' },
    })
    expect(wrapper.find('.ds-empty-description').exists()).toBe(false)
  })

  it('renders default icon SVG when no icon slot', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty' },
    })
    expect(wrapper.find('.ds-empty-icon svg').exists()).toBe(true)
  })

  it('renders custom icon slot content replacing default', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty' },
      slots: { icon: '<span class="custom-icon">ICON</span>' },
    })
    expect(wrapper.find('.ds-empty-icon .custom-icon').exists()).toBe(true)
    expect(wrapper.find('.ds-empty-icon svg').exists()).toBe(false)
  })

  it('renders actions slot content', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty' },
      slots: { actions: '<button>Add Item</button>' },
    })
    expect(wrapper.find('.ds-empty-state-actions button').text()).toBe('Add Item')
  })

  it('does not render actions wrapper when no actions slot', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty' },
    })
    expect(wrapper.find('.ds-empty-state-actions').exists()).toBe(false)
  })
})
