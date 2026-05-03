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

// Global stub for AiChatPanel — the restored 808-line component is heavy
// and depends on subcomponents that themselves require @ai-accounts plugin
// state. Stub it with a placeholder declaring the restored prop surface so
// unit tests mounting consumer pages don't emit Vue "Extraneous non-props
// attribute" warnings. v0.5.5 surface is a superset of v0.5.4 — adds
// processGroups / backendResponses / synthesisState / isAllModeActive +
// the legacy "smart-chat fallback" pass-throughs (density, defaultBackend,
// defaultModel, placeholder, welcomeTitle, welcomeSubtitle).
// Stub registered under both upstream component names:
//   - `AiChatPanel` — upstream's self-managed component (used by
//     AIBackendsPage + SuperAgentPlayground post-v0.5.9). Drives
//     state internally via `useSmartChat`; needs the global plugin
//     context which tests don't install.
//   - `AiChatPanelManaged` — upstream's caller-managed component
//     (used by the 9 path-Y-migrated wizard pages).
//
// Same stub object for both — its prop list is the union of both
// upstream surfaces, which is harmless: undeclared props are
// silently consumed without `Extraneous` warnings, and the wrapper
// div + slot forwarding work identically.
const aiChatPanelStub = {
    name: 'AiChatPanel',
    props: [
      // Caller-managed state
      'messages', 'isProcessing', 'streamingContent', 'inputMessage',
      'conversationId', 'canFinalize', 'isFinalizing',
      // Backend selector
      'showBackendSelector', 'selectedBackend', 'selectedAccountId',
      'selectedModel', 'chatMode',
      // Display
      'inputPlaceholder', 'entityLabel', 'bannerTitle', 'bannerButtonLabel',
      'assistantIconPaths', 'detectedEntityName',
      // Hooks
      'initStreamingParser', 'useSmartScroll', 'configParser',
      // Restored b2ee00d~1 — All/Compound mode state
      'processGroups', 'backendResponses', 'synthesisState', 'isAllModeActive',
      // Legacy "smart-chat fallback" pass-throughs (AIBackendsPage, SuperAgentPlayground)
      'density', 'defaultBackend', 'defaultModel', 'placeholder',
      'welcomeTitle', 'welcomeSubtitle', 'readOnly',
      'showProcessGroups', 'showActions',
    ],
    emits: [
      'update:inputMessage', 'update:selectedBackend',
      'update:selectedAccountId', 'update:selectedModel',
      'update:chatMode', 'send', 'keydown', 'finalize',
    ],
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
}

config.global.stubs = {
  ...(config.global.stubs || {}),
  AiChatPanel: aiChatPanelStub,
  AiChatPanelManaged: aiChatPanelStub,
}

// Reset mocks before each test
beforeEach(() => {
  vi.clearAllMocks()
})

// Export mocks for use in tests
export { mockShowToast, mockRefreshTriggers }
