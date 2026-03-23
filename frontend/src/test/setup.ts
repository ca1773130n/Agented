import { config } from '@vue/test-utils'
import { vi } from 'vitest'
import { createI18n } from 'vue-i18n'
import en from '../locales/en.json'

// Global i18n plugin for all test mounts
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
})

// Global mock for provide/inject toast
const mockShowToast = vi.fn()
const mockRefreshTriggers = vi.fn()

config.global.plugins = [i18n]
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
