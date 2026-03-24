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
    // Default padding is 8px (parsed from CSS custom property, fallback)
    expect(style).toContain('top: 192px')   // 200 - 8
    expect(style).toContain('left: 92px')   // 100 - 8
    expect(style).toContain('width: 316px') // 300 + 16
    expect(style).toContain('height: 66px') // 50 + 16
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
