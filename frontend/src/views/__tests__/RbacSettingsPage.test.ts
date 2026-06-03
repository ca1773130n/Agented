import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RbacSettingsPage from '../RbacSettingsPage.vue'
import type { UserRole, PermissionMatrix } from '../../services/api'

const mockRoles = [
  {
    id: 'role-1',
    api_key: 'agnt_sk_aaaaaaaaaaaaaaaa',
    label: 'CI/CD Pipeline',
    role: 'operator',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'role-2',
    api_key: 'agnt_sk_bbbbbbbbbbbbbbbb',
    label: 'Dashboard Reader',
    role: 'viewer',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
] as unknown as UserRole[]

const mockPermissions = {
  admin: ['read', 'write', 'delete'],
  viewer: ['read'],
} as unknown as PermissionMatrix

vi.mock('../../services/api', () => ({
  rbacApi: {
    listRoles: vi.fn(),
    getPermissions: vi.fn(),
    createRole: vi.fn(),
    updateRole: vi.fn(),
    rotateRole: vi.fn(),
    deleteRole: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('RbacSettingsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(RbacSettingsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { rbacApi } = await import('../../services/api')
    vi.mocked(rbacApi.listRoles).mockResolvedValue({ roles: mockRoles })
    vi.mocked(rbacApi.getPermissions).mockResolvedValue({ permissions: mockPermissions })
    vi.mocked(rbacApi.deleteRole).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', () => {
    // isLoading starts true, so the LoadingState renders synchronously on mount.
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the role list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(false)
    expect(wrapper.findAll('.users-table tbody tr').length).toBe(2)
    expect(wrapper.text()).toContain('CI/CD Pipeline')
    expect(wrapper.text()).toContain('Dashboard Reader')
  })

  it('shows the empty state when there are no roles', async () => {
    const { rbacApi } = await import('../../services/api')
    vi.mocked(rbacApi.listRoles).mockResolvedValue({ roles: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.list-empty').exists()).toBe(true)
    expect(wrapper.find('.users-table').exists()).toBe(false)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { rbacApi, ApiError } = await import('../../services/api')
    vi.mocked(rbacApi.listRoles).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    const errorCard = wrapper.find('.error-card')
    expect(errorCard.exists()).toBe(true)
    expect(errorCard.text()).toContain('boom')
    expect(wrapper.find('.users-table').exists()).toBe(false)

    vi.mocked(rbacApi.listRoles).mockResolvedValueOnce({ roles: mockRoles })
    await errorCard.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('CI/CD Pipeline')
    expect(rbacApi.listRoles).toHaveBeenCalledTimes(2)
  })

  it('deletes a role (no confirm step) and shows a success toast', async () => {
    const { rbacApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Rows render in list order; target by label rather than index.
    const row = wrapper
      .findAll('.users-table tbody tr')
      .find((r) => r.text().includes('CI/CD Pipeline'))
    expect(row).toBeDefined()
    await row!.find('.btn-delete').trigger('click')
    await flushPromises()

    expect(rbacApi.deleteRole).toHaveBeenCalledWith('role-1')
    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'success')
    // Row is filtered out of the list on success.
    expect(wrapper.text()).not.toContain('CI/CD Pipeline')
  })
})
