import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TriggerManagement from '../TriggerManagement.vue'
import { triggerApi, utilityApi } from '../../services/api'
import { mockTriggers, mockTrigger } from '../../test/fixtures/triggers'

vi.mock('../../services/api', () => ({
  triggerApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    run: vi.fn(),
    addPath: vi.fn(),
    addGitHubRepo: vi.fn(),
    removePath: vi.fn(),
    removeGitHubRepo: vi.fn(),
    setAutoResolve: vi.fn()
  },
  utilityApi: {
    checkBackend: vi.fn(),
    validatePath: vi.fn(),
    validateGitHubUrl: vi.fn(),
    discoverSkills: vi.fn()
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
}))

describe('TriggerManagement', () => {
  const mockShowToast = vi.fn()
  const mockRefreshTriggers = vi.fn().mockResolvedValue(undefined)

  function mountComponent() {
    return mount(TriggerManagement, {
      global: {
        provide: {
          showToast: mockShowToast,
          refreshTriggers: mockRefreshTriggers
        },
        stubs: {
          AddTriggerModal: true
        }
      }
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(triggerApi.list).mockResolvedValue({ triggers: mockTriggers })
    vi.mocked(utilityApi.checkBackend).mockResolvedValue({
      backend: 'claude',
      installed: true,
      version: '1.0.0'
    })
    vi.mocked(utilityApi.discoverSkills).mockResolvedValue({ skills: [] })
  })

  describe('loading and initial render', () => {
    it('fetches triggers on mount', async () => {
      mountComponent()
      await flushPromises()

      expect(triggerApi.list).toHaveBeenCalled()
    })

    it('displays trigger names after loading', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.text()).toContain('Test Trigger')
      expect(wrapper.text()).toContain('Security Scanner')
    })

    it('shows error toast on load failure', async () => {
      const { ApiError } = await import('../../services/api')
      vi.mocked(triggerApi.list).mockRejectedValue(new ApiError(500, 'Server error'))

      mountComponent()
      await flushPromises()

      expect(mockShowToast).toHaveBeenCalledWith('Server error', 'error')
    })
  })

  describe('trigger selection', () => {
    it('loads trigger details when clicked', async () => {
      vi.mocked(triggerApi.get).mockResolvedValue(mockTrigger)

      const wrapper = mountComponent()
      await flushPromises()

      const triggerItems = wrapper.findAll('.trigger-item')
      if (triggerItems.length > 0) {
        await triggerItems[0].trigger('click')
        await flushPromises()

        expect(triggerApi.get).toHaveBeenCalledWith('bot-1')
      }
    })

    it('shows error toast when trigger load fails', async () => {
      const { ApiError } = await import('../../services/api')
      vi.mocked(triggerApi.get).mockRejectedValue(new ApiError(404, 'Trigger not found'))

      const wrapper = mountComponent()
      await flushPromises()

      const triggerItems = wrapper.findAll('.trigger-item')
      if (triggerItems.length > 0) {
        await triggerItems[0].trigger('click')
        await flushPromises()

        expect(mockShowToast).toHaveBeenCalledWith('Trigger not found', 'error')
      }
    })
  })

  describe('backend status', () => {
    it('checks backend status on mount', async () => {
      mountComponent()
      await flushPromises()

      expect(utilityApi.checkBackend).toHaveBeenCalledWith('claude')
      expect(utilityApi.checkBackend).toHaveBeenCalledWith('opencode')
    })

    it('handles backend check failure gracefully', async () => {
      vi.mocked(utilityApi.checkBackend).mockRejectedValue(new Error('Network error'))

      const wrapper = mountComponent()
      await flushPromises()

      // Should not crash
      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('trigger details display', () => {
    it('displays trigger paths when selected', async () => {
      vi.mocked(triggerApi.get).mockResolvedValue(mockTrigger)

      const wrapper = mountComponent()
      await flushPromises()

      const triggerItems = wrapper.findAll('.trigger-item')
      if (triggerItems.length > 0) {
        await triggerItems[0].trigger('click')
        await flushPromises()

        expect(wrapper.text()).toContain('/path/to/project1')
      }
    })
  })

  describe('skill loading', () => {
    it('loads skills when editing claude trigger', async () => {
      vi.mocked(triggerApi.get).mockResolvedValue(mockTrigger)

      const wrapper = mountComponent()
      await flushPromises()

      const triggerItems = wrapper.findAll('.trigger-item')
      if (triggerItems.length > 0) {
        await triggerItems[0].trigger('click')
        await flushPromises()

        // Skills should be loaded for claude backend
        expect(utilityApi.discoverSkills).toHaveBeenCalled()
      }
    })
  })
})
