import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PageHeader from '../PageHeader.vue'

describe('PageHeader', () => {
  it('renders title text in h1', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'My Page Title' },
    })
    expect(wrapper.find('h1').text()).toBe('My Page Title')
  })

  it('renders subtitle when provided', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Title', subtitle: 'A helpful subtitle' },
    })
    expect(wrapper.find('.ds-subtitle').text()).toBe('A helpful subtitle')
  })

  it('does not render subtitle element when subtitle not provided', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Title' },
    })
    expect(wrapper.find('.ds-subtitle').exists()).toBe(false)
  })

  it('applies gradient class to h1 when gradient prop set', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Title', gradient: 'cyan-emerald' },
    })
    expect(wrapper.find('h1').classes()).toContain('gradient-cyan-emerald')
  })

  it('renders actions slot content when provided', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Title' },
      slots: { actions: '<button>Create</button>' },
    })
    expect(wrapper.find('.ds-header-actions').exists()).toBe(true)
    expect(wrapper.find('.ds-header-actions button').text()).toBe('Create')
  })

  it('does not render actions wrapper when no actions slot', () => {
    const wrapper = mount(PageHeader, {
      props: { title: 'Title' },
    })
    expect(wrapper.find('.ds-header-actions').exists()).toBe(false)
  })
})
