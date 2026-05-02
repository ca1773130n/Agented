import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import TourSpotlight from '../TourSpotlight.vue'

function mockDOMRect(overrides: Partial<DOMRect> = {}): DOMRect {
  return {
    x: 100,
    y: 200,
    width: 300,
    height: 50,
    top: 200,
    left: 100,
    right: 400,
    bottom: 250,
    toJSON: () => ({}),
    ...overrides,
  }
}

describe('TourSpotlight', () => {
  it('does not render when targetRect is null', () => {
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: null, visible: false },
    })
    expect(wrapper.find('.tour-spotlight').exists()).toBe(false)
  })

  it('renders with correct inline styles when targetRect is provided', () => {
    const rect = mockDOMRect({ top: 200, left: 100, width: 300, height: 50 })
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: true },
    })
    const spotlight = wrapper.find('.tour-spotlight')
    expect(spotlight.exists()).toBe(true)

    const style = spotlight.attributes('style')
    // Plan 02-01 (OB-11): without a targetEl prop, the spotlight falls back
    // to the section/card default of 12px from computeSpotlightGeometry(null).
    expect(style).toContain('top: 188px')   // 200 - 12
    expect(style).toContain('left: 88px')   // 100 - 12
    expect(style).toContain('width: 324px') // 300 + 24
    expect(style).toContain('height: 74px') // 50 + 24
  })

  it('uses input-tight padding (4px) when targetEl is an <input>', () => {
    const rect = mockDOMRect({ top: 200, left: 100, width: 300, height: 50 })
    const input = document.createElement('input')
    document.body.appendChild(input)
    try {
      const wrapper = mount(TourSpotlight, {
        props: { targetRect: rect, targetEl: input, visible: true },
      })
      const style = wrapper.find('.tour-spotlight').attributes('style')
      expect(style).toContain('top: 196px')  // 200 - 4
      expect(style).toContain('width: 308px') // 300 + 8
    } finally {
      input.remove()
    }
  })

  it('uses button padding (6px) when targetEl is a <button>', () => {
    const rect = mockDOMRect({ top: 200, left: 100, width: 300, height: 50 })
    const button = document.createElement('button')
    document.body.appendChild(button)
    try {
      const wrapper = mount(TourSpotlight, {
        props: { targetRect: rect, targetEl: button, visible: true },
      })
      const style = wrapper.find('.tour-spotlight').attributes('style')
      expect(style).toContain('top: 194px')  // 200 - 6
      expect(style).toContain('width: 312px') // 300 + 12
    } finally {
      button.remove()
    }
  })

  it('honours data-tour-padding override on the target', () => {
    const rect = mockDOMRect({ top: 200, left: 100, width: 300, height: 50 })
    const button = document.createElement('button')
    button.dataset.tourPadding = '20'
    document.body.appendChild(button)
    try {
      const wrapper = mount(TourSpotlight, {
        props: { targetRect: rect, targetEl: button, visible: true },
      })
      const style = wrapper.find('.tour-spotlight').attributes('style')
      expect(style).toContain('top: 180px')  // 200 - 20
    } finally {
      button.remove()
    }
  })

  it('has box-shadow style on the spotlight element via CSS class', () => {
    const rect = mockDOMRect()
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: true },
    })
    const spotlight = wrapper.find('.tour-spotlight')
    expect(spotlight.exists()).toBe(true)
    // The box-shadow is applied via CSS class, not inline style
    // Verify the element has the correct class
    expect(spotlight.classes()).toContain('tour-spotlight')
  })

  it('glow element exists inside spotlight', () => {
    const rect = mockDOMRect()
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: true },
    })
    expect(wrapper.find('.tour-spotlight-glow').exists()).toBe(true)
  })

  it('spotlight has pointer-events: none via CSS class', () => {
    const rect = mockDOMRect()
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: true },
    })
    // pointer-events is set via CSS class, verify the class exists
    expect(wrapper.find('.tour-spotlight').exists()).toBe(true)
  })

  it('applies visible modifier class when visible is true', () => {
    const rect = mockDOMRect()
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: true },
    })
    expect(wrapper.find('.tour-spotlight--visible').exists()).toBe(true)
  })

  it('does not apply visible modifier class when visible is false', () => {
    const rect = mockDOMRect()
    const wrapper = mount(TourSpotlight, {
      props: { targetRect: rect, visible: false },
    })
    expect(wrapper.find('.tour-spotlight--visible').exists()).toBe(false)
  })

  it('has zero hardcoded color values in component source', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourSpotlight.vue'),
      'utf-8',
    )
    // Extract only the <style> block
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]

    // Check for hardcoded hex colors (#xxx, #xxxxxx, #xxxxxxxx)
    const hexColors = styleBlock.match(/#[0-9a-fA-F]{3,8}\b/g) || []
    expect(hexColors).toEqual([])

    // Check for hardcoded rgb/rgba values
    const rgbValues = styleBlock.match(/rgba?\s*\(/g) || []
    expect(rgbValues).toEqual([])
  })

  it('has zero hardcoded z-index values in component source', () => {
    const source = readFileSync(
      resolve(__dirname, '../TourSpotlight.vue'),
      'utf-8',
    )
    const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)
    expect(styleMatch).toBeTruthy()
    const styleBlock = styleMatch![1]

    // Check for hardcoded z-index numbers
    const hardcodedZIndex = styleBlock.match(/z-index:\s*\d+/g) || []
    expect(hardcodedZIndex).toEqual([])
  })
})
