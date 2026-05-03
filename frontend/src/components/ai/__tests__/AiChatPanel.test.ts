import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// vue-headless composables touch the global aiAccountsPlugin; stub them.
// Surface mirrors what useSmartChat / useAiAccounts actually expose, NOT
// what the wrapper wishes they exposed (codex caught a `backendOptions`
// hallucination in an earlier draft of this plan).
vi.mock('@ai-accounts/vue-headless', () => ({
  useSmartChat: () => ({
    selectedBackend: { value: null },
    selectedAccount: { value: null },
    selectedModel: { value: null },
    chatMode: { value: 'single' },
    resetSession: vi.fn(),
  }),
  useSmartScroll: () => ({ containerRef: { value: null } }),
  useAiAccounts: () => ({
    client: {
      listBackends: vi.fn().mockResolvedValue({ backends: [] }),
      listModels: vi.fn().mockResolvedValue({ items: [] }),
    },
  }),
}))

import AiChatPanel from '../AiChatPanel.vue'

describe('AiChatPanel (translation wrapper)', () => {
  it('mounts without errors when given no props', () => {
    const wrapper = mount(AiChatPanel)
    expect(wrapper.find('.ai-chat-panel').exists()).toBe(true)
  })
})
