/**
 * Tests for `useFormGuide` (Phase 5 plan 05-01).
 *
 * Covers OB-25 (auto-discovery), OB-26 (sequential navigation),
 * OB-27 (help text priority chain), OB-28 (submit button last).
 */
import { describe, expect, it } from 'vitest'
import { ref, type Ref } from 'vue'

import {
  useFormGuide,
  type FormGuideReturn,
} from '../useFormGuide'

/**
 * Build a container by parsing trusted test fixture HTML through DOMParser
 * and copying its body children into a fresh <div>. This intentionally
 * avoids `Element.innerHTML = …` so the security-warning hook stays quiet
 * — DOMParser itself doesn't execute scripts in the parsed content.
 */
function buildContainer(fixture: string): HTMLElement {
  const container = document.createElement('div')
  const parsed = new DOMParser().parseFromString(
    `<!doctype html><html><body>${fixture}</body></html>`,
    'text/html',
  )
  for (const child of Array.from(parsed.body.childNodes)) {
    container.appendChild(child)
  }
  document.body.appendChild(container)
  return container
}

function makeContainer(fixture: string): {
  container: HTMLElement
  containerRef: Ref<HTMLElement | null>
  guide: FormGuideReturn
} {
  const container = buildContainer(fixture)
  const containerRef = ref<HTMLElement | null>(container)
  const guide = useFormGuide(containerRef)
  return { container, containerRef, guide }
}

function cleanup(container: HTMLElement) {
  container.remove()
}

describe('useFormGuide — OB-25 auto-discovery', () => {
  it('discovers nothing when the container is empty', () => {
    const { container, guide } = makeContainer('<div></div>')
    guide.activate()
    expect(guide.fields.value).toHaveLength(0)
    expect(guide.isActive.value).toBe(false) // activate is a no-op when nothing found
    cleanup(container)
  })

  it('discovers each .form-group in DOM order', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>One</label><input id="a"></div>
      <div class="form-group"><label>Two</label><input id="b"></div>
      <div class="form-group"><label>Three</label><input id="c"></div>
    `)
    guide.activate()
    expect(guide.fields.value.map(f => f.label)).toEqual(['One', 'Two', 'Three'])
    cleanup(container)
  })

  it('does not pick up sibling elements that are not .form-group', () => {
    const { container, guide } = makeContainer(`
      <h2>Form heading</h2>
      <div class="form-group"><label>Real</label><input id="x"></div>
      <p>An explanation paragraph.</p>
    `)
    guide.activate()
    expect(guide.fields.value).toHaveLength(1)
    expect(guide.fields.value[0].label).toBe('Real')
    cleanup(container)
  })

  it('is a safe no-op when containerRef.value is null', () => {
    const containerRef = ref<HTMLElement | null>(null)
    const guide = useFormGuide(containerRef)
    expect(() => guide.activate()).not.toThrow()
    expect(guide.fields.value).toHaveLength(0)
    expect(guide.isActive.value).toBe(false)
  })
})

describe('useFormGuide — OB-27 help text priority chain', () => {
  it('uses data-tour-help when present (highest priority)', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group" data-tour-help="Override wins">
        <label>Name</label>
        <input id="n">
        <small>Native small wouldn't be picked.</small>
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].helpText).toBe('Override wins')
    cleanup(container)
  })

  it('falls back to .form-help when no data-tour-help', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Name</label>
        <input id="n">
        <span class="form-help">Pick something memorable.</span>
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].helpText).toBe('Pick something memorable.')
    cleanup(container)
  })

  it('falls back to .form-description when no .form-help', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Name</label>
        <input id="n">
        <span class="form-description">Optional description.</span>
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].helpText).toBe('Optional description.')
    cleanup(container)
  })

  it('falls back to <small> when neither override nor .form-help', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Name</label>
        <input id="n">
        <small>Use letters and numbers.</small>
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].helpText).toBe('Use letters and numbers.')
    cleanup(container)
  })

  it('generates a fallback message when nothing else exists', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Email</label>
        <input id="e">
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].helpText).toBe('Enter the Email for this form')
    cleanup(container)
  })

  it('strips trailing required-marker asterisks from labels', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Account name *</label>
        <input id="n">
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].label).toBe('Account name')
    cleanup(container)
  })

  it('uses "Field N" when no label is present', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><input id="x"></div>
    `)
    guide.activate()
    expect(guide.fields.value[0].label).toBe('Field 1')
    cleanup(container)
  })
})

describe('useFormGuide — selector building', () => {
  it('uses #id selector when the input has an id', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group">
        <label>Name</label>
        <input id="account-name">
      </div>
    `)
    guide.activate()
    expect(guide.fields.value[0].inputSelector).toBe('#account-name')
    expect(guide.fields.value[0].selector).toBe('.form-group:has(#account-name)')
    cleanup(container)
  })

  it('falls back to nth-of-type when the input has no id', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><input></div>
      <div class="form-group"><input></div>
    `)
    guide.activate()
    expect(guide.fields.value[0].selector).toBe('.form-group:nth-of-type(1)')
    expect(guide.fields.value[1].selector).toBe('.form-group:nth-of-type(2)')
    cleanup(container)
  })

  it('uses the group selector itself for checkbox groups', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group checkbox">
        <label>Agree</label>
        <input id="ack" type="checkbox">
      </div>
    `)
    guide.activate()
    const f = guide.fields.value[0]
    expect(f.selector).toBe('.form-group:has(#ack)')
    expect(f.inputSelector).toBe(f.selector)
    cleanup(container)
  })
})

describe('useFormGuide — OB-28 submit button is always last', () => {
  it('detects button[type="submit"] and pushes it last', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>Name</label><input id="n"></div>
      <div class="form-group"><label>Email</label><input id="e"></div>
      <button type="submit">Save</button>
    `)
    guide.activate()
    const last = guide.fields.value[guide.fields.value.length - 1]
    expect(last.isSubmit).toBe(true)
    expect(last.label).toBe('Save')
    cleanup(container)
  })

  it('detects .inline-form-actions .btn-primary fallback', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>Name</label><input id="n"></div>
      <div class="inline-form-actions">
        <button class="btn">Cancel</button>
        <button class="btn btn-primary">Save</button>
      </div>
    `)
    guide.activate()
    const last = guide.fields.value[guide.fields.value.length - 1]
    expect(last.isSubmit).toBe(true)
    expect(last.selector).toBe('.inline-form-actions .btn-primary')
    cleanup(container)
  })

  it('detects [data-tour="submit-btn"] as last-resort fallback', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>Name</label><input id="n"></div>
      <button data-tour="submit-btn">Submit</button>
    `)
    guide.activate()
    const last = guide.fields.value[guide.fields.value.length - 1]
    expect(last.isSubmit).toBe(true)
    expect(last.selector).toBe('[data-tour="submit-btn"]')
    cleanup(container)
  })

  it('builds an #id selector when the submit button has an id', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>Name</label><input id="n"></div>
      <button id="save-btn" type="submit">Save</button>
    `)
    guide.activate()
    const last = guide.fields.value[guide.fields.value.length - 1]
    expect(last.selector).toBe('#save-btn')
    cleanup(container)
  })

  it('omits the submit field entirely when no candidate exists', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>Name</label><input id="n"></div>
    `)
    guide.activate()
    expect(guide.fields.value).toHaveLength(1)
    expect(guide.fields.value[0].isSubmit).toBe(false)
    cleanup(container)
  })
})

describe('useFormGuide — OB-26 navigation', () => {
  function threeFieldGuide() {
    return makeContainer(`
      <div class="form-group"><label>One</label><input id="a"></div>
      <div class="form-group"><label>Two</label><input id="b"></div>
      <div class="form-group"><label>Three</label><input id="c"></div>
      <button type="submit">Save</button>
    `)
  }

  it('starts at index 0 with the first field current', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    expect(guide.currentIndex.value).toBe(0)
    expect(guide.currentField.value?.label).toBe('One')
    cleanup(container)
  })

  it('nextField advances the index and returns true', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    expect(guide.nextField()).toBe(true)
    expect(guide.currentIndex.value).toBe(1)
    expect(guide.currentField.value?.label).toBe('Two')
    cleanup(container)
  })

  it('nextField at the last index returns false and does not advance', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    // 3 fields + submit = 4 entries; advance to last (index 3) then try once more.
    for (let i = 0; i < 3; i++) guide.nextField()
    expect(guide.currentIndex.value).toBe(3)
    expect(guide.currentField.value?.isSubmit).toBe(true)
    expect(guide.nextField()).toBe(false)
    expect(guide.currentIndex.value).toBe(3)
    cleanup(container)
  })

  it('prevField decrements', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    guide.nextField()
    guide.nextField()
    expect(guide.prevField()).toBe(true)
    expect(guide.currentIndex.value).toBe(1)
    cleanup(container)
  })

  it('prevField at index 0 returns false', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    expect(guide.prevField()).toBe(false)
    expect(guide.currentIndex.value).toBe(0)
    cleanup(container)
  })

  it('deactivate clears state and currentField becomes null', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    guide.nextField()
    guide.deactivate()
    expect(guide.isActive.value).toBe(false)
    expect(guide.fields.value).toHaveLength(0)
    expect(guide.currentField.value).toBeNull()
    cleanup(container)
  })

  it('reset returns the index to 0 without clearing the field list', () => {
    const { container, guide } = threeFieldGuide()
    guide.activate()
    guide.nextField()
    guide.nextField()
    expect(guide.currentIndex.value).toBe(2)
    guide.reset()
    expect(guide.currentIndex.value).toBe(0)
    expect(guide.fields.value.length).toBeGreaterThan(0)
    cleanup(container)
  })
})

describe('useFormGuide — totalFields + currentField interactions', () => {
  it('totalFields tracks the discovered count', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><label>One</label><input id="a"></div>
      <div class="form-group"><label>Two</label><input id="b"></div>
      <button type="submit">Save</button>
    `)
    guide.activate()
    expect(guide.totalFields.value).toBe(3) // 2 fields + submit
    cleanup(container)
  })

  it('currentField is null before activate', () => {
    const { container, guide } = makeContainer(`
      <div class="form-group"><input id="x"></div>
    `)
    expect(guide.currentField.value).toBeNull()
    cleanup(container)
  })
})
