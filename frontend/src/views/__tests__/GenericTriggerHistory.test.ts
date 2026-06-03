import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import GenericTriggerHistory from '../GenericTriggerHistory.vue'
import type { AuditRecord, ProjectInfo, Trigger } from '../../services/api'
// The real ApiError, imported from the un-mocked client submodule. handleApiError
// (services/api/error-handler) does `instanceof ApiError` against THIS class, so the
// thrown error must be a genuine instance for the STATUS_MAP-formatted message to fire.
import { ApiError } from '../../services/api/client'

// triggerId is read from useRoute().params.triggerId (falling back to the
// `triggerId` prop). Pin it via the router mock so loadData targets 'trig-1'.
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { triggerId: 'trig-1' }, query: {}, hash: '' }),
  useRouter: () => ({ push: mockPush, back: vi.fn(), replace: vi.fn() }),
}))

const mockTrigger = {
  id: 'trig-1',
  name: 'Security Audit',
} as unknown as Trigger

const mockAudits = [
  {
    audit_id: 'aud-1',
    project_path: '/repo/web',
    project_name: 'Web App',
    audit_date: '2026-01-01T00:00:00Z',
    trigger_id: 'trig-1',
    trigger_name: 'Security Audit',
    total_findings: 3,
    status: 'pass',
    trigger_content: 'Run the weekly security audit',
  },
  {
    audit_id: 'aud-2',
    project_path: '/repo/api',
    project_name: 'API Service',
    audit_date: '2026-01-02T00:00:00Z',
    trigger_id: 'trig-1',
    trigger_name: 'Security Audit',
    total_findings: 0,
    status: 'fail',
    trigger_content: 'Audit the backend',
  },
] as unknown as AuditRecord[]

const mockProjects = [
  { project_path: '/repo/web', project_name: 'Web App' },
  { project_path: '/repo/api', project_name: 'API Service' },
] as unknown as ProjectInfo[]

vi.mock('../../services/api', () => ({
  triggerApi: { get: vi.fn() },
  auditApi: { getHistory: vi.fn(), getProjects: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

describe('GenericTriggerHistory', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(GenericTriggerHistory, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { triggerApi, auditApi } = await import('../../services/api')
    vi.mocked(triggerApi.get).mockResolvedValue(mockTrigger)
    vi.mocked(auditApi.getHistory).mockResolvedValue({ audits: mockAudits })
    vi.mocked(auditApi.getProjects).mockResolvedValue({ projects: mockProjects })
  })

  it('renders the loading state while the request is in flight', async () => {
    const { auditApi } = await import('../../services/api')
    // getHistory never resolves -> EntityLayout keeps its initial isLoading=true.
    vi.mocked(auditApi.getHistory).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    // EntityLayout starts isLoading=true and loads in onMounted; let that tick run.
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.entity-layout__loading').exists()).toBe(true)
  })

  it('renders the history rows after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // One <tr> per audit record in the DataTable body.
    const rows = wrapper.findAll('.ds-data-table tbody tr')
    expect(rows.length).toBe(2)

    expect(wrapper.text()).toContain('Web App')
    expect(wrapper.text()).toContain('API Service')
    // Findings count + status badges come from the cell slots.
    expect(wrapper.text()).toContain('3 findings')
    expect(wrapper.text()).toContain('pass')
    expect(wrapper.text()).toContain('fail')
    // Title is interpolated from the loaded trigger name.
    expect(wrapper.text()).toContain('Security Audit History')

    expect(wrapper.find('.ds-empty-state').exists()).toBe(false)
    expect(wrapper.find('.entity-layout__error').exists()).toBe(false)
  })

  it('shows the empty state when there is no history', async () => {
    const { auditApi } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockResolvedValue({ audits: [] })
    const wrapper = mountComponent()
    await flushPromises()

    // DataTable collapses to a single row hosting the #empty EmptyState slot.
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No execution history available')
    expect(wrapper.find('.entity-layout__error').exists()).toBe(false)
  })

  // loadData() calls handleApiError (fires a toast) AND re-throws; EntityLayout
  // catches the throw and renders its error state with a retry button. A 404
  // would instead redirect to not-found, so this uses 500 to exercise the
  // visible error path.
  it('shows the error state and re-fetches on retry', async () => {
    const { auditApi } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.entity-layout__error').exists()).toBe(true)
    expect(wrapper.find('.ds-empty-state').exists()).toBe(false)
    // handleApiError formats the 500 via STATUS_MAP and toasts it.
    expect(mockShowToast).toHaveBeenCalledWith(
      'Server error: boom (ERR-500). The server encountered an error. Try again later.',
      'error',
    )

    // Retry button is the first action in the error block.
    vi.mocked(auditApi.getHistory).mockResolvedValueOnce({ audits: mockAudits })
    await wrapper.find('.entity-layout__error-actions button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.entity-layout__error').exists()).toBe(false)
    expect(wrapper.text()).toContain('Web App')
    expect(auditApi.getHistory).toHaveBeenCalledTimes(2)
  })
})
