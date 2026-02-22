import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorState from '../ErrorState.vue'

describe('ErrorState', () => {
  it('renders default title "Something went wrong" when title not provided', () => {
    const wrapper = mount(ErrorState)
    expect(wrapper.find('h3').text()).toBe('Something went wrong')
  })

  it('renders custom title when provided', () => {
    const wrapper = mount(ErrorState, {
      props: { title: 'Failed to load data' },
    })
    expect(wrapper.find('h3').text()).toBe('Failed to load data')
  })

  it('renders error message when message prop provided', () => {
    const wrapper = mount(ErrorState, {
      props: { message: 'Network timeout' },
    })
    expect(wrapper.find('.ds-error-message').text()).toBe('Network timeout')
  })

  it('does not render message element when message not provided', () => {
    const wrapper = mount(ErrorState)
    expect(wrapper.find('.ds-error-message').exists()).toBe(false)
  })

  it('emits retry event when retry button is clicked', async () => {
    const wrapper = mount(ErrorState)
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('has role="alert" attribute on root element', () => {
    const wrapper = mount(ErrorState)
    expect(wrapper.find('.ds-error-state').attributes('role')).toBe('alert')
  })
})
