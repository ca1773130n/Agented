import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AuditHistory from '../AuditHistory.vue'
import type { AuditRecord, ProjectInfo } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockAudits = [
  {
    audit_id: 'audit-1',
    project_path: '/repo/web',
    project_name: 'Web App',
    audit_date: '2026-01-01T00:00:00Z',
    audit_week: '2026-W01',
    group_id: 'grp-1',
    trigger_id: 'bot-security',
    trigger_name: 'Security Bot',
    total_findings: 5,
    critical: 1,
    high: 2,
    medium: 1,
    low: 1,
    status: 'fail',
  },
  {
    audit_id: 'audit-2',
    project_path: '/repo/api',
    project_name: 'API Service',
    audit_date: '2026-01-02T00:00:00Z',
    audit_week: '2026-W01',
    group_id: 'grp-2',
    trigger_id: 'bot-security',
    trigger_name: 'Security Bot',
    total_findings: 0,
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    status: 'pass',
  },
] as unknown as AuditRecord[]

const mockProjects = [
  {
    project_path: '/repo/web',
    project_name: 'Web App',
    project_type: 'github',
    audit_count: 3,
    last_audit: '2026-01-01T00:00:00Z',
    last_status: 'fail',
    registered_by_triggers: ['bot-security'],
  },
] as unknown as ProjectInfo[]

vi.mock('../../services/api', () => ({
  auditApi: { getHistory: vi.fn(), getProjects: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

describe('AuditHistory', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(AuditHistory, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { auditApi } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockResolvedValue({ audits: mockAudits })
    vi.mocked(auditApi.getProjects).mockResolvedValue({ projects: mockProjects })
  })

  it('renders the loading state initially', async () => {
    const { auditApi } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    // isLoading starts true, so the loading state is present on first render.
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the audit list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(false)
    // Only real item rows carry .ds-row-clickable (the empty-slot row does not).
    expect(wrapper.findAll('.ds-row-clickable').length).toBe(2)
    expect(wrapper.text()).toContain('Web App')
    expect(wrapper.text()).toContain('API Service')
    // status badge + findings count are rendered per row.
    expect(wrapper.text()).toContain('pass')
    expect(wrapper.text()).toContain('fail')
  })

  it('shows the empty state when there are no audits', async () => {
    const { auditApi } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockResolvedValue({ audits: [] })
    vi.mocked(auditApi.getProjects).mockResolvedValue({ projects: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.findAll('.ds-row-clickable').length).toBe(0)
    expect(wrapper.text()).toContain('No audit data available')
  })

  // The catch block is toast-only: it shows a toast and leaves audits empty
  // (there is no ErrorState component on this page), so the table falls back
  // to its empty slot. Assert the toast fired with the error message.
  it('shows a toast and no rows when the load fails', async () => {
    const { auditApi, ApiError } = await import('../../services/api')
    vi.mocked(auditApi.getHistory).mockRejectedValueOnce(new ApiError(500, 'boom'))
    const wrapper = mountComponent()
    await flushPromises()

    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')
    expect(wrapper.find('.ds-loading-state').exists()).toBe(false)
    expect(wrapper.findAll('.ds-row-clickable').length).toBe(0)
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })
})
