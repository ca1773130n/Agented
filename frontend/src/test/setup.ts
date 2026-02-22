import { config } from '@vue/test-utils'
import { vi } from 'vitest'

// Global mock for provide/inject toast
const mockShowToast = vi.fn()
const mockRefreshTriggers = vi.fn()

config.global.provide = {
  showToast: mockShowToast,
  refreshTriggers: mockRefreshTriggers
}

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks()
})

// Export mocks for use in tests
export { mockShowToast, mockRefreshTriggers }
