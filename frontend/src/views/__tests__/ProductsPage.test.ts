import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProductsPage from '../ProductsPage.vue'
import type { Product } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockProducts = [
  { id: 'prod-1', name: 'Acme Platform', description: 'Core product', team_id: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'prod-2', name: 'Beta Suite', description: 'Secondary product', team_id: null, created_at: '2026-01-02T00:00:00Z' },
] as unknown as Product[]

vi.mock('../../services/api', () => ({
  productApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
  teamApi: { list: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('ProductsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(ProductsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { productApi, teamApi } = await import('../../services/api')
    vi.mocked(productApi.list).mockResolvedValue({ products: mockProducts })
    vi.mocked(teamApi.list).mockResolvedValue({ teams: [] })
    vi.mocked(productApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { productApi } = await import('../../services/api')
    vi.mocked(productApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the product list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Acme Platform')
    expect(wrapper.text()).toContain('Beta Suite')
    expect(wrapper.findAll('.product-card').length).toBe(2)
  })

  it('shows the empty state when there are no products', async () => {
    const { productApi } = await import('../../services/api')
    vi.mocked(productApi.list).mockResolvedValue({ products: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { productApi, ApiError } = await import('../../services/api')
    vi.mocked(productApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(productApi.list).mockResolvedValueOnce({ products: mockProducts })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Acme Platform')
    expect(productApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a product after confirmation', async () => {
    const { productApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Open the confirm modal from the first card's delete button.
    await wrapper.findAll('.product-card .btn-danger')[0].trigger('click')
    await flushPromises()

    // Confirm in the ConfirmModal (danger variant -> .btn-danger in .confirm-actions).
    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(productApi.delete).toHaveBeenCalledWith('prod-1')
  })
})
