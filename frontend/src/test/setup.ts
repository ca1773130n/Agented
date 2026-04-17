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

// Global stub for AiChatPanel -- the real component requires the aiAccountsPlugin
// (provided at app level) which isn't installed in test mounts. Stub it with a
// simple placeholder that preserves the component name for findComponent lookups.
config.global.stubs = {
  ...(config.global.stubs || {}),
  AiChatPanel: {
    name: 'AiChatPanel',
    // Render all named slots so tests can assert on content passed via
    // #header-extra, #welcome, etc. Default slot last.
    template: `
      <div class="stub-ai-chat-panel">
        <slot name="header-extra" />
        <slot name="welcome" />
        <slot name="footer" />
        <slot />
      </div>
    `,
  },
}

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks()
})

// Export mocks for use in tests
export { mockShowToast, mockRefreshTriggers }
