/**
 * Tests for `TourFormGuide` (Phase 5 plan 05-01).
 *
 * The component is renderless — it watches `props.active` + `containerSelector`,
 * resolves the container DOM node, drives `useFormGuide`, and emits
 * `field-change` / `complete` events.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import TourFormGuide from '../TourFormGuide.vue'

let cleanup: Array<() => void> = []

afterEach(() => {
  cleanup.forEach(fn => fn())
  cleanup = []
})

function createForm(html: string, attrs: Record<string, string> = {}): HTMLElement {
  const container = document.createElement('div')
  for (const [k, v] of Object.entries(attrs)) container.setAttribute(k, v)
  // DOMParser keeps the security-warning hook quiet vs. innerHTML.
  const parsed = new DOMParser().parseFromString(
    `<!doctype html><html><body>${html}</body></html>`,
    'text/html',
  )
  for (const child of Array.from(parsed.body.childNodes)) {
    container.appendChild(child)
  }
  document.body.appendChild(container)
  cleanup.push(() => container.remove())
  return container
}

describe('TourFormGuide', () => {
  it('emits field-change with the first field when active', async () => {
    createForm(
      `
      <div class="form-group">
        <label for="a">First</label><input id="a">
        <small>First help.</small>
      </div>
      <div class="form-group">
        <label for="b">Second</label><input id="b">
      </div>
      <button type="submit">Save</button>
      `,
      { 'data-test': 'host' },
    )

    const wrapper = mount(TourFormGuide, {
      props: { active: true, containerSelector: '[data-test="host"]' },
    })
    await flushPromises()
    const fieldEvents = wrapper.emitted('field-change') ?? []
    // The first emit happens immediately on activation with the first field.
    const firstWithField = fieldEvents.find(args => args[0] !== null)
    expect(firstWithField?.[0]).toEqual({
      target: '#a',
      message: 'First help.',
    })
    wrapper.unmount()
  })

  it('emits field-change null when active=false (deactivation cleanup)', async () => {
    createForm(
      `<div class="form-group"><label for="a">One</label><input id="a"></div>`,
      { 'data-test': 'host-2' },
    )

    const wrapper = mount(TourFormGuide, {
      props: { active: true, containerSelector: '[data-test="host-2"]' },
    })
    await flushPromises()
    await wrapper.setProps({ active: false })
    await flushPromises()
    const fieldEvents = wrapper.emitted('field-change') ?? []
    const lastNullEmit = [...fieldEvents].reverse().find(args => args[0] === null)
    expect(lastNullEmit).toBeDefined()
    wrapper.unmount()
  })

  it('emits field-change null when the container selector does not match', async () => {
    const wrapper = mount(TourFormGuide, {
      props: { active: true, containerSelector: '#nope' },
    })
    await flushPromises()
    const fieldEvents = wrapper.emitted('field-change') ?? []
    expect(fieldEvents.length).toBeGreaterThan(0)
    expect(fieldEvents[fieldEvents.length - 1][0]).toBeNull()
    wrapper.unmount()
  })

  it('emits complete when nextField walks past the last field', async () => {
    createForm(
      `
      <div class="form-group"><label for="a">One</label><input id="a"></div>
      <button type="submit">Save</button>
      `,
      { 'data-test': 'host-3' },
    )

    const wrapper = mount(TourFormGuide, {
      props: { active: true, containerSelector: '[data-test="host-3"]' },
    })
    await flushPromises()
    // 1 field + 1 submit = 2 entries. Advance to submit, then once more.
    const exposed = wrapper.vm as unknown as {
      nextField: () => void
      prevField: () => void
    }
    exposed.nextField()  // → submit (returns true)
    exposed.nextField()  // → past last (returns false → emits complete)
    await flushPromises()
    expect(wrapper.emitted('complete')).toBeTruthy()
    wrapper.unmount()
  })

  it('exposes nextField + prevField via defineExpose', async () => {
    createForm(
      `
      <div class="form-group"><label for="a">One</label><input id="a"></div>
      <div class="form-group"><label for="b">Two</label><input id="b"></div>
      `,
      { 'data-test': 'host-4' },
    )

    const wrapper = mount(TourFormGuide, {
      props: { active: true, containerSelector: '[data-test="host-4"]' },
    })
    await flushPromises()
    const exposed = wrapper.vm as unknown as {
      nextField: () => void
      prevField: () => void
    }
    expect(typeof exposed.nextField).toBe('function')
    expect(typeof exposed.prevField).toBe('function')
    wrapper.unmount()
  })
})
