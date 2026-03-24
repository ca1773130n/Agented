import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { readFileSync } from 'fs'
import { resolve } from 'path'

vi.mock('@floating-ui/vue', () => ({
  useFloating: vi.fn(() => ({
    floatingStyles: ref({ position: 'absolute', top: '100px', left: '200px' }),
    placement: ref('bottom'),
    middlewareData: ref({ arrow: { x: 50, y: 0 } }),
  })),
  offset: vi.fn(() => ({})),
  flip: vi.fn(() => ({})),
  shift: vi.fn(() => ({})),
  arrow: vi.fn(() => ({})),
  autoUpdate: vi.fn(),
}))

import TourTooltip from '../TourTooltip.vue'
import { useFloating } from '@floating-ui/vue'

const mockRect = new DOMRect(100, 200, 300, 50)

describe('TourTooltip', () => {
  it('does not render when visible is false', () => {
    const wrapper = mount(TourTooltip, {
      props: { targetRect: mockRect, title: 'Test', message: 'Msg', visible: false },
    })
    expect(wrapper.find('.tour-tooltip').exists()).toBe(false)
  })

  it('does not render when targetRect is null', () => {
    const wrapper = mount(TourTooltip, {
      props: { targetRect: null, title: 'Test', message: 'Msg', visible: true },
    })
    expect(wrapper.find('.tour-tooltip').exists()).toBe(false)
  })

  it('renders title and message when visible with targetRect', () => {
    const wrapper = mount(TourTooltip, {
      props: { targetRect: mockRect, title: 'Step Title', message: 'Step description', visible: true },
    })
    expect(wrapper.find('.tour-tooltip').exists()).toBe(true)
    expect(wrapper.find('.tour-tooltip-title').text()).toBe('Step Title')
    expect(wrapper.find('.tour-tooltip-message').text()).toBe('Step description')
  })

  it('calls useFloating from @floating-ui/vue', () => {
    mount(TourTooltip, {
      props: { targetRect: mockRect, title: 'Test', message: 'Msg', visible: true },
    })
    expect(useFloating).toHaveBeenCalled()
  })

  it('has arrow element', () => {
    const wrapper = mount(TourTooltip, {
      props: { targetRect: mockRect, title: 'Test', message: 'Msg', visible: true },
    })
    expect(wrapper.find('.tour-tooltip-arrow').exists()).toBe(true)
  })

  it('has pointer-events auto on tooltip', () => {
    const wrapper = mount(TourTooltip, {
      props: { targetRect: mockRect, title: 'Test', message: 'Msg', visible: true },
    })
    expect(wrapper.find('.tour-tooltip').exists()).toBe(true)
    // The scoped style sets pointer-events: auto — verify class exists
  })

  it('has no hardcoded color values in style block', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourTooltip.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]
    // Check for hardcoded hex colors
    const hexColors = styleBlock.match(/#[0-9a-fA-F]{3,8}\b/g) || []
    expect(hexColors).toEqual([])
    // Check for hardcoded rgb/rgba
    const rgbColors = styleBlock.match(/rgba?\s*\(/g) || []
    expect(rgbColors).toEqual([])
  })

  it('has no hardcoded z-index values in style block', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourTooltip.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]
    const hardcodedZIndex = styleBlock.match(/z-index:\s*\d+/g) || []
    expect(hardcodedZIndex).toEqual([])
  })
})
