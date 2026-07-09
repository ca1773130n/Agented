import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import TourOverlay from '../TourOverlay.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { path: '/' } } }),
}))

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

const workspaceStep = {
  id: 'workspace',
  route: '/settings',
  target: '[data-tour="workspace-root"]',
  title: 'Workspace Directory',
  message: 'Set the root directory',
  skippable: false,
}

const productStep = {
  id: 'product',
  route: '/products',
  target: '[data-tour="create-product"]',
  title: 'First Product',
  message: 'Create your first product',
  skippable: true,
}

describe('TourOverlay', () => {
  it('does not render when inactive', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: false, step: null, effectiveTarget: null, substepLabel: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('renders overlay when active with a step', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
  })

  it('renders TourSpotlight child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const spotlight = wrapper.findComponent({ name: 'TourSpotlight' })
    expect(spotlight.exists()).toBe(true)
  })

  it('renders TourTooltip child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const tooltip = wrapper.findComponent({ name: 'TourTooltip' })
    expect(tooltip.exists()).toBe(true)
  })

  it('renders TourProgressBar child component', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    const progressBar = wrapper.findComponent({ name: 'TourProgressBar' })
    expect(progressBar.exists()).toBe(true)
  })

  it('shows step counter via TourProgressBar', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.text()).toContain('STEP 2 OF 8')
    expect(wrapper.text()).toContain('Set the root directory')
  })

  it('shows skip button for skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 6, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(true)
  })

  it('hides skip button for non-skippable steps', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-skip-btn').exists()).toBe(false)
  })

  it('emits next on next button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    expect(wrapper.emitted('next')).toBeTruthy()
  })

  it('emits skip on skip button click', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 6, totalSteps: 8 },
    })
    await wrapper.find('.tour-skip-btn').trigger('click')
    expect(wrapper.emitted('skip')).toBeTruthy()
  })

  it('shows substep label when provided', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: 'Claude Code (1/4)', stepNumber: 3, totalSteps: 8 },
    })
    expect(wrapper.text()).toContain('Claude Code (1/4)')
  })

  it('shows spinner when target not found', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-spinner').exists()).toBe(true)
  })

  it('displays correct step counter text for different step numbers', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 5, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-step-counter').text()).toContain('STEP 5 OF 8')
  })

  it('does not show substep label when null', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-substep-label').exists()).toBe(false)
  })

  it('shows effectiveTarget message when different from step message', () => {
    const customTarget = {
      target: '[data-tour="workspace-root"]',
      message: 'Override message from effective target',
    }
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: customTarget, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-step-message').text()).toBe('Override message from effective target')
    expect(wrapper.find('.tour-step-message').text()).not.toBe('Set the root directory')
  })

  it('emits events in correct order for rapid clicks', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    await wrapper.find('.tour-next-btn').trigger('click')
    await wrapper.find('.tour-next-btn').trigger('click')
    const nextEmits = wrapper.emitted('next')
    expect(nextEmits).toBeTruthy()
    expect(nextEmits!.length).toBe(2)
  })

  it('handles null step gracefully when active', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: null, effectiveTarget: null, substepLabel: null, stepNumber: 1, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('shows dim fallback when target element not in DOM', () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    expect(wrapper.find('.tour-dim-fallback').exists()).toBe(true)
  })

  // OB-44: a modal opening during a tour step (e.g. "Add Account")
  // must remain interactive — the overlay reduces dimming and the
  // spotlight enters its `reduced` mode. Driven by the `isModalOpen`
  // prop, which is provided/injected from App.vue.
  describe('OB-44 — modal coordination', () => {
    const baseProps = {
      active: true,
      step: workspaceStep,
      effectiveTarget: workspaceStep,
      substepLabel: null,
      stepNumber: 2,
      totalSteps: 8,
    }

    it('adds .modal-open to the dim fallback when isModalOpen is true', () => {
      const wrapper = mount(TourOverlay, {
        props: { ...baseProps, isModalOpen: true },
      })
      const dim = wrapper.find('.tour-dim-fallback')
      expect(dim.exists()).toBe(true)
      expect(dim.classes()).toContain('modal-open')
    })

    it('omits .modal-open by default (isModalOpen unset)', () => {
      const wrapper = mount(TourOverlay, { props: baseProps })
      const dim = wrapper.find('.tour-dim-fallback')
      expect(dim.classes()).not.toContain('modal-open')
    })

    it('passes isModalOpen through to TourSpotlight as :reduced', () => {
      const target = document.createElement('div')
      target.setAttribute('data-tour', 'workspace-root')
      document.body.appendChild(target)
      try {
        const wrapper = mount(TourOverlay, {
          props: { ...baseProps, isModalOpen: true },
          attachTo: document.body,
        })
        const spotlight = wrapper.findComponent({ name: 'TourSpotlight' })
        expect(spotlight.exists()).toBe(true)
        expect(spotlight.props('reduced')).toBe(true)
        wrapper.unmount()
      } finally {
        document.body.removeChild(target)
      }
    })
  })

  it('Enter key emits next when active', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('next')).toBeTruthy()
    expect(wrapper.emitted('next')!.length).toBe(1)
    wrapper.unmount()
  })

  it('Escape key emits skip when step is skippable', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 6, totalSteps: 8 },
    })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('skip')).toBeTruthy()
    expect(wrapper.emitted('skip')!.length).toBe(1)
    wrapper.unmount()
  })

  it('Escape key does nothing when step is not skippable', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('skip')).toBeFalsy()
    wrapper.unmount()
  })

  it('keyboard handler is inactive when active=false', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: false, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('next')).toBeFalsy()
    wrapper.unmount()
  })

  it('overlay click does not emit dismiss or any event', async () => {
    const wrapper = mount(TourOverlay, {
      props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
    })
    await wrapper.find('.tour-overlay').trigger('click')
    // Should not emit next, skip, or any dismiss-like event
    expect(wrapper.emitted('next')).toBeFalsy()
    expect(wrapper.emitted('skip')).toBeFalsy()
    wrapper.unmount()
  })

  describe('ARIA live announcements (OB-38)', () => {
    it('renders aria-live region when active', () => {
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 1, totalSteps: 4 },
      })
      const liveRegion = wrapper.find('[aria-live="polite"]')
      expect(liveRegion.exists()).toBe(true)
      expect(liveRegion.text()).toBe('STEP 1 OF 4: Workspace Directory. Set the root directory')
      wrapper.unmount()
    })

    it('updates announcement when step changes', async () => {
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 1, totalSteps: 4 },
      })
      const liveRegion = wrapper.find('[aria-live="polite"]')
      expect(liveRegion.text()).toContain('Workspace Directory')

      await wrapper.setProps({ step: productStep, effectiveTarget: productStep, stepNumber: 2 })
      expect(liveRegion.text()).toBe('STEP 2 OF 4: First Product. Create your first product')
      wrapper.unmount()
    })

    it('announcement includes step number and total', () => {
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: productStep, effectiveTarget: productStep, substepLabel: null, stepNumber: 3, totalSteps: 5 },
      })
      const liveRegion = wrapper.find('[aria-live="polite"]')
      expect(liveRegion.text()).toMatch(/^STEP 3 OF 5:/)
      wrapper.unmount()
    })

    it('aria-live region is not display:none (screen reader accessible)', () => {
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 1, totalSteps: 4 },
      })
      const liveRegion = wrapper.find('[aria-live="polite"]')
      expect(liveRegion.exists()).toBe(true)
      // sr-only uses clip/overflow hidden, NOT display:none
      expect((liveRegion.element as HTMLElement).style.display).not.toBe('none')
      expect(liveRegion.attributes('aria-atomic')).toBe('true')
      wrapper.unmount()
    })
  })

  describe('loading timeout fallback (OB-40)', () => {
    it('shows the element-not-found fallback once past the 45s threshold', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })
      // Initially shows spinner, no fallback
      expect(wrapper.find('.tour-spinner').exists()).toBe(true)
      expect(wrapper.find('.tour-timeout-fallback').exists()).toBe(false)

      // Past 45s element-not-found threshold (and 30s page-slow before it).
      await vi.advanceTimersByTimeAsync(50000)

      expect(wrapper.find('.tour-spinner').exists()).toBe(false)
      // Element-not-found takes precedence over the page-slow hint.
      expect(wrapper.find('.tour-element-fallback').exists()).toBe(true)

      wrapper.unmount()
      vi.useRealTimers()
    })

    it('shows the gentle page-slow hint (not the error) during a slow load (30–45s window)', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      // 35s: page-slow (30s) has fired, element-not-found (45s) has not.
      // Operator-requested: the slow-load popup must NOT show early — a
      // busy machine routinely takes >10s to route+render+fetch a step's
      // target, and an early popup reads as a broken onboarding.
      await vi.advanceTimersByTimeAsync(35000)

      expect(wrapper.find('.tour-element-fallback').exists()).toBe(false)
      expect(wrapper.find('.tour-timeout-fallback').exists()).toBe(true)
      expect(wrapper.text()).not.toContain("We couldn't find")

      wrapper.unmount()
      vi.useRealTimers()
    })

    it('shows NO popup at all before 30s (busy-machine patience)', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      await vi.advanceTimersByTimeAsync(29000)

      expect(wrapper.find('.tour-timeout-fallback').exists()).toBe(false)
      expect(wrapper.find('.tour-element-fallback').exists()).toBe(false)
      expect(wrapper.find('.tour-spinner').exists()).toBe(true)

      wrapper.unmount()
      vi.useRealTimers()
    })

    it('shows element-not-found fallback after 45s', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      await vi.advanceTimersByTimeAsync(50000)

      expect(wrapper.find('.tour-element-fallback').exists()).toBe(true)
      expect(wrapper.text()).toContain("We couldn't find")
      expect(wrapper.text()).toContain('Workspace Directory')

      wrapper.unmount()
      vi.useRealTimers()
    })

    it('clicking Skip in fallback emits skip', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      await vi.advanceTimersByTimeAsync(50000)

      const skipBtn = wrapper.find('.btn-fallback-skip')
      expect(skipBtn.exists()).toBe(true)
      await skipBtn.trigger('click')
      expect(wrapper.emitted('skip')).toBeTruthy()

      wrapper.unmount()
      vi.useRealTimers()
    })

    it('clicking Retry in fallback hides fallback and emits retry', async () => {
      vi.useFakeTimers()
      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      await vi.advanceTimersByTimeAsync(50000)

      expect(wrapper.find('.tour-element-fallback').exists()).toBe(true)

      const retryBtn = wrapper.find('.btn-fallback-retry')
      await retryBtn.trigger('click')
      expect(wrapper.emitted('retry')).toBeTruthy()
      // Fallback should be hidden after retry
      expect(wrapper.find('.tour-element-fallback').exists()).toBe(false)
      // Spinner should show again
      expect(wrapper.find('.tour-spinner').exists()).toBe(true)

      wrapper.unmount()
      vi.useRealTimers()
    })

    // OB-31: skip confirmation for non-trivial steps. Phase 6 plan 06-01
    // extended SIGNIFICANT_STEP_TITLES from just `'AI Backend Accounts'` to
    // also include the three product/project/team titles. Each test below
    // mounts the overlay with a step that should trigger the confirm row.
    describe('OB-31 — significant-step skip confirmation', () => {
      function mountWithStep(step: typeof workspaceStep) {
        return mount(TourOverlay, {
          props: {
            active: true,
            step,
            effectiveTarget: step,
            substepLabel: null,
            stepNumber: 5,
            totalSteps: 8,
          },
        })
      }


      it('"Create Your First Product" triggers confirm', async () => {
        const wrapper = mountWithStep({
          id: 'create_product',
          route: '/products',
          target: '[data-tour="create-product"]',
          title: 'Create Your First Product',
          message: 'Products group related projects under a shared context.',
          skippable: true,
        })
        await wrapper.find('.tour-skip-btn').trigger('click')
        expect(wrapper.find('.tour-skip-confirm').exists()).toBe(true)
      })

      it('"Create Your First Project" triggers confirm', async () => {
        const wrapper = mountWithStep({
          id: 'create_project',
          route: '/products',
          target: '[data-tour="create-project"]',
          title: 'Create Your First Project',
          message: 'Projects track work within a product.',
          skippable: true,
        })
        await wrapper.find('.tour-skip-btn').trigger('click')
        expect(wrapper.find('.tour-skip-confirm').exists()).toBe(true)
      })

      it('"Assign Teams to Project" triggers confirm', async () => {
        const wrapper = mountWithStep({
          id: 'create_team',
          route: '/projects',
          target: '[data-tour="assign-teams"]',
          title: 'Assign Teams to Project',
          message: 'Bundled teams are ready to assign.',
          skippable: true,
        })
        await wrapper.find('.tour-skip-btn').trigger('click')
        expect(wrapper.find('.tour-skip-confirm').exists()).toBe(true)
      })

      it('a non-significant skippable step (Token Monitoring) skips without confirm', async () => {
        const wrapper = mountWithStep({
          id: 'monitoring',
          route: '/settings',
          target: '[data-tour="token-monitoring"]',
          title: 'Token Monitoring',
          message: 'Configure rate limit monitoring.',
          skippable: true,
        })
        await wrapper.find('.tour-skip-btn').trigger('click')
        expect(wrapper.find('.tour-skip-confirm').exists()).toBe(false)
        expect(wrapper.emitted('skip')).toBeTruthy()
      })
    })

    it('does not show fallback when element is found before timeout', async () => {
      vi.useFakeTimers()

      // Create a target element in the DOM
      const el = document.createElement('div')
      el.setAttribute('data-tour', 'workspace-root')
      document.body.appendChild(el)

      const wrapper = mount(TourOverlay, {
        props: { active: true, step: workspaceStep, effectiveTarget: workspaceStep, substepLabel: null, stepNumber: 2, totalSteps: 8 },
      })

      await vi.advanceTimersByTimeAsync(200)
      await vi.advanceTimersByTimeAsync(5001)

      // Element was found, so no fallback
      expect(wrapper.find('.tour-timeout-fallback').exists()).toBe(false)
      expect(wrapper.find('.tour-element-fallback').exists()).toBe(false)

      wrapper.unmount()
      document.body.removeChild(el)
      vi.useRealTimers()
    })
  })

  // OB-36: tour spinner + dim transition are no-op under
  // prefers-reduced-motion. The other tour components (Spotlight,
  // Tooltip, CompletionScreen) have their own coverage; this asserts
  // TourOverlay's two unguarded animations are now guarded.
  describe('OB-36 — reduced motion', () => {
    it('disables spinner animation + dim transition under prefers-reduced-motion', () => {
      const source = readFileSync(
        resolve(__dirname, '../TourOverlay.vue'),
        'utf-8',
      )
      const styleMatch = source.match(/<style[^>]*>([\s\S]*?)<\/style>/)!
      const styleBlock = styleMatch[1]
      const reducedBlock = styleBlock.match(
        /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\}\s*\}/,
      )
      expect(reducedBlock).not.toBeNull()
      expect(reducedBlock![0]).toMatch(/\.spinner-icon\s*\{[^}]*animation:\s*none/)
      expect(reducedBlock![0]).toMatch(/\.tour-dim-fallback\s*\{[^}]*transition:\s*none/)
    })
  })
})
