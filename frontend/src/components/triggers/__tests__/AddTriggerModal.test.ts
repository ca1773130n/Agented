import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AddTriggerModal from '../AddTriggerModal.vue'
import { triggerApi, utilityApi } from '../../../services/api'

vi.mock('../../../services/api', () => ({
  triggerApi: {
    create: vi.fn()
  },
  utilityApi: {
    discoverSkills: vi.fn()
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
  CLAUDE_MODELS: ['opus', 'sonnet', 'haiku'],
  OPENCODE_MODELS: ['codex', 'zen']
}))

describe('AddTriggerModal', () => {
  const mockShowToast = vi.fn()
  const mockSkills = [
    { name: 'code-review', description: 'Review code for issues' },
    { name: 'security-scan', description: 'Scan for security vulnerabilities' }
  ]

  function mountComponent() {
    return mount(AddTriggerModal, {
      global: {
        provide: {
          showToast: mockShowToast
        }
      }
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(utilityApi.discoverSkills).mockResolvedValue({ skills: mockSkills })
  })

  describe('rendering', () => {
    it('renders modal with form fields', () => {
      const wrapper = mountComponent()

      expect(wrapper.find('.modal').exists()).toBe(true)
      expect(wrapper.find('form').exists()).toBe(true)
      expect(wrapper.findAll('input').length).toBeGreaterThan(0)
      expect(wrapper.findAll('select').length).toBeGreaterThan(0)
    })

    it('loads skills on mount for claude backend', async () => {
      mountComponent()
      await flushPromises()

      expect(utilityApi.discoverSkills).toHaveBeenCalled()
    })
  })

  describe('form validation', () => {
    it('shows error when name is empty', async () => {
      const wrapper = mountComponent()

      await wrapper.find('textarea').setValue('Test prompt')
      await wrapper.find('form').trigger('submit')

      expect(mockShowToast).toHaveBeenCalledWith(
        'Please fill in name and prompt template',
        'error'
      )
    })

    it('shows error when prompt is empty', async () => {
      const wrapper = mountComponent()

      await wrapper.find('input[type="text"]').setValue('Trigger Name')
      await wrapper.find('form').trigger('submit')

      expect(mockShowToast).toHaveBeenCalledWith(
        'Please fill in name and prompt template',
        'error'
      )
    })

    it('shows error when webhook fields are incomplete', async () => {
      const wrapper = mountComponent()

      await wrapper.find('input[type="text"]').setValue('Trigger Name')
      await wrapper.find('textarea').setValue('Test prompt')

      // Find and fill only match_field_path but not match_field_value
      const inputs = wrapper.findAll('input')
      const matchFieldPathInput = inputs.find(i =>
        (i.element as HTMLInputElement).placeholder === 'event.type'
      )
      expect(matchFieldPathInput).toBeDefined()
      if (matchFieldPathInput) {
        await matchFieldPathInput.setValue('event.type')
      }
      await flushPromises()

      await wrapper.find('form').trigger('submit')

      expect(mockShowToast).toHaveBeenCalledWith(
        'Both Match Field Path and Match Field Value must be provided together',
        'error'
      )
    })
  })

  describe('trigger source selection', () => {
    it('shows webhook fields when webhook trigger is selected', async () => {
      const wrapper = mountComponent()

      // webhook is the default trigger - look for Match Field Path label
      expect(wrapper.text()).toContain('Match Field Path')
    })

    it('hides webhook fields when manual trigger is selected', async () => {
      const wrapper = mountComponent()

      // Find trigger select and set to manual
      const selects = wrapper.findAll('select')
      const triggerSelect = selects.find(s =>
        Array.from((s.element as HTMLSelectElement).options).some(o => o.value === 'manual')
      )

      if (triggerSelect) {
        await triggerSelect.setValue('manual')
        await flushPromises()

        // Match Field Path should not be visible for manual trigger
        expect(wrapper.text()).not.toContain('Match Field Path')
      }
    })
  })

  describe('backend and model selection', () => {
    it('clears model when backend changes', async () => {
      const wrapper = mountComponent()

      // Find backend select
      const selects = wrapper.findAll('select')
      const backendSelect = selects[0]

      // First set to opencode
      await backendSelect.setValue('opencode')
      await flushPromises()

      // Find model select and set a value
      const modelSelect = wrapper.findAll('select').find(s =>
        Array.from((s.element as HTMLSelectElement).options).some(o => o.value === 'codex')
      )
      if (modelSelect) {
        await modelSelect.setValue('codex')
      }

      // Change backend back to claude
      await backendSelect.setValue('claude')
      await flushPromises()

      // Model should be cleared
      const updatedModelSelect = wrapper.findAll('select').find(s =>
        Array.from((s.element as HTMLSelectElement).options).some(o =>
          o.value === 'opus' || o.value === 'sonnet' || o.value === 'haiku'
        )
      )
      if (updatedModelSelect) {
        expect((updatedModelSelect.element as HTMLSelectElement).value).toBe('')
      }
    })
  })

  describe('trigger creation', () => {
    it('creates trigger successfully with manual trigger source', async () => {
      vi.mocked(triggerApi.create).mockResolvedValue({
        message: 'Created',
        trigger_id: 'new-trigger',
        name: 'Test Trigger'
      })

      const wrapper = mountComponent()

      // Fill in required fields
      await wrapper.find('input[type="text"]').setValue('Test Trigger')
      await wrapper.find('textarea').setValue('Test prompt')

      // Change to manual trigger
      const triggerSelect = wrapper.findAll('select').find(s =>
        Array.from((s.element as HTMLSelectElement).options).some(o => o.value === 'manual')
      )
      if (triggerSelect) {
        await triggerSelect.setValue('manual')
      }
      await flushPromises()

      // Submit
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(triggerApi.create).toHaveBeenCalledWith(expect.objectContaining({
        name: 'Test Trigger',
        prompt_template: 'Test prompt',
        trigger_source: 'manual'
      }))
      expect(wrapper.emitted('created')).toBeTruthy()
    })

    it('creates trigger with webhook trigger source', async () => {
      vi.mocked(triggerApi.create).mockResolvedValue({
        message: 'Created',
        trigger_id: 'new-trigger',
        name: 'Test Trigger'
      })

      const wrapper = mountComponent()

      // Fill in required fields
      await wrapper.find('input[type="text"]').setValue('Test Trigger')
      await wrapper.find('textarea').setValue('Test prompt')
      await flushPromises()

      // Fill in webhook-specific fields by matching exact placeholder
      const inputs = wrapper.findAll('input')

      // Find match field path input by placeholder
      const matchPathInput = inputs.find(i =>
        (i.element as HTMLInputElement).placeholder === 'event.type'
      )
      expect(matchPathInput).toBeDefined()
      if (matchPathInput) {
        await matchPathInput.setValue('event.type')
      }

      // Find match field value input by placeholder
      const matchValueInput = inputs.find(i =>
        (i.element as HTMLInputElement).placeholder === 'security_alert'
      )
      expect(matchValueInput).toBeDefined()
      if (matchValueInput) {
        await matchValueInput.setValue('security_alert')
      }

      await flushPromises()
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(triggerApi.create).toHaveBeenCalledWith(expect.objectContaining({
        name: 'Test Trigger',
        prompt_template: 'Test prompt',
        trigger_source: 'webhook',
        match_field_path: 'event.type',
        match_field_value: 'security_alert'
      }))
    })

    it('shows error toast on API failure', async () => {
      const { ApiError } = await import('../../../services/api')
      vi.mocked(triggerApi.create).mockRejectedValue(new ApiError(400, 'Invalid data'))

      const wrapper = mountComponent()

      // Fill minimal fields and switch to manual trigger
      await wrapper.find('input[type="text"]').setValue('Test Trigger')
      await wrapper.find('textarea').setValue('Test prompt')

      const triggerSelect = wrapper.findAll('select').find(s =>
        Array.from((s.element as HTMLSelectElement).options).some(o => o.value === 'manual')
      )
      if (triggerSelect) {
        await triggerSelect.setValue('manual')
      }
      await flushPromises()

      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(mockShowToast).toHaveBeenCalledWith('Invalid data', 'error')
    })
  })

  describe('modal interactions', () => {
    it('emits close when overlay is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.modal-overlay').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })

    it('does not emit close when modal content is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.modal').trigger('click')

      expect(wrapper.emitted('close')).toBeFalsy()
    })
  })

  describe('close button', () => {
    it('emits close when close button is clicked', async () => {
      const wrapper = mountComponent()

      await wrapper.find('.close-btn').trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
    })
  })
})
