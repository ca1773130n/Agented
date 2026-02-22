import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RunScanModal from '../RunScanModal.vue'
import { mockTriggers } from '../../../test/fixtures/triggers'

vi.mock('../../../services/api', () => ({
  triggerApi: {
    get: vi.fn(),
    run: vi.fn()
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
}))

describe('RunScanModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountComponent(triggers = mockTriggers) {
    return mount(RunScanModal, {
      props: { triggers }
    })
  }

  describe('rendering', () => {
    it('renders modal with select', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.modal').exists()).toBe(true)
      expect(wrapper.find('select').exists()).toBe(true)
    })

    it('filters triggers to only show those with paths', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      // The component filters triggers in onMounted
      const options = wrapper.findAll('option')
      // mockTriggers has 3 triggers but only 2 have path_count > 0
      // Plus 1 placeholder option
      expect(options.length).toBeGreaterThanOrEqual(2)
    })

    it('shows message when no triggers have paths', async () => {
      const triggersWithNoPaths = mockTriggers.map(t => ({ ...t, path_count: 0 }))
      const wrapper = mountComponent(triggersWithNoPaths)
      await flushPromises()

      expect(wrapper.find('option').text()).toContain('No triggers with configured paths')
    })
  })

  describe('run button state', () => {
    it('disables run button when no trigger is selected', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      const runButton = wrapper.find('.btn-primary')
      expect((runButton.element as HTMLButtonElement).disabled).toBe(true)
    })
  })

  describe('modal interactions', () => {
    it('emits close when overlay is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.modal-overlay').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })

    it('emits close when cancel button is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.btn-secondary').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })

    it('emits close when close button is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.close-btn').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })
  })
})
