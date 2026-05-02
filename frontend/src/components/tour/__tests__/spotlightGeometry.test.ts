/**
 * Tests for the OB-11 spotlight geometry helper.
 */
import { describe, expect, it } from 'vitest'

import { computeSpotlightGeometry } from '../spotlightGeometry'

function fakeStyle(borderRadius = '0px'): CSSStyleDeclaration {
  return { borderRadius } as CSSStyleDeclaration
}

function makeElement(
  tag: string,
  attrs: Record<string, string> = {},
  dataset: Record<string, string> = {},
): HTMLElement {
  const el = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  for (const [k, v] of Object.entries(dataset)) el.dataset[k] = v
  return el
}

describe('computeSpotlightGeometry — defaults', () => {
  it('returns sensible defaults for a null target', () => {
    const { padding, borderRadius } = computeSpotlightGeometry(null)
    expect(padding).toBe(12)
    expect(borderRadius).toBe('8px')
  })

  it('returns the section/card default for unknown tags', () => {
    const el = makeElement('section')
    const { padding } = computeSpotlightGeometry(el, () => fakeStyle())
    expect(padding).toBe(12)
  })
})

describe('computeSpotlightGeometry — per-tag padding', () => {
  it('input gets 4px', () => {
    const { padding } = computeSpotlightGeometry(
      makeElement('input'),
      () => fakeStyle(),
    )
    expect(padding).toBe(4)
  })

  it('textarea gets 4px', () => {
    expect(
      computeSpotlightGeometry(makeElement('textarea'), () => fakeStyle()).padding,
    ).toBe(4)
  })

  it('select gets 4px', () => {
    expect(
      computeSpotlightGeometry(makeElement('select'), () => fakeStyle()).padding,
    ).toBe(4)
  })

  it('button gets 6px', () => {
    expect(
      computeSpotlightGeometry(makeElement('button'), () => fakeStyle()).padding,
    ).toBe(6)
  })

  it('anchor gets 6px (clickable)', () => {
    expect(
      computeSpotlightGeometry(makeElement('a'), () => fakeStyle()).padding,
    ).toBe(6)
  })

  it('div with role=button gets 6px', () => {
    const el = makeElement('div', { role: 'button' })
    expect(
      computeSpotlightGeometry(el, () => fakeStyle()).padding,
    ).toBe(6)
  })

  it('section gets 12px (card)', () => {
    expect(
      computeSpotlightGeometry(makeElement('section'), () => fakeStyle()).padding,
    ).toBe(12)
  })
})

describe('computeSpotlightGeometry — overrides', () => {
  it('data-tour-padding wins over tag default', () => {
    const el = makeElement('input', {}, { tourPadding: '20' })
    expect(
      computeSpotlightGeometry(el, () => fakeStyle()).padding,
    ).toBe(20)
  })

  it('data-tour-padding="0" yields 0 (no padding)', () => {
    const el = makeElement('button', {}, { tourPadding: '0' })
    expect(
      computeSpotlightGeometry(el, () => fakeStyle()).padding,
    ).toBe(0)
  })

  it('non-numeric data-tour-padding falls back to tag default', () => {
    const el = makeElement('input', {}, { tourPadding: 'wat' })
    expect(
      computeSpotlightGeometry(el, () => fakeStyle()).padding,
    ).toBe(4)
  })

  it('data-tour-radius wins over computed border-radius', () => {
    const el = makeElement('button', {}, { tourRadius: '9999px' })
    expect(
      computeSpotlightGeometry(el, () => fakeStyle('4px')).borderRadius,
    ).toBe('9999px')
  })
})

describe('computeSpotlightGeometry — border-radius from computed style', () => {
  it('uses computed border-radius when present', () => {
    const el = makeElement('button')
    expect(
      computeSpotlightGeometry(el, () => fakeStyle('16px')).borderRadius,
    ).toBe('16px')
  })

  it('uses the default when computed value is 0px', () => {
    const el = makeElement('button')
    expect(
      computeSpotlightGeometry(el, () => fakeStyle('0px')).borderRadius,
    ).toBe('8px')
  })

  it('falls back to default when getComputedStyle throws', () => {
    const el = makeElement('button')
    const throwing = () => {
      throw new Error('not in DOM')
    }
    expect(
      computeSpotlightGeometry(el, throwing as never).borderRadius,
    ).toBe('8px')
  })
})
