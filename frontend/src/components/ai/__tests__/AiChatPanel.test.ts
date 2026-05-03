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

  it('renders each message as a wrapper-owned bubble row', () => {
    const messages = [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there' },
    ]
    const wrapper = mount(AiChatPanel, { props: { messages } })
    const items = wrapper.findAll('[data-testid="bubble-row"]')
    expect(items).toHaveLength(2)
  })

  it('renders streamingContent as an in-flight bubble after the messages', () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        messages: [{ role: 'user', content: 'Hi' }],
        streamingContent: 'partial response...',
      },
    })
    const rows = wrapper.findAll('[data-testid="bubble-row"]')
    expect(rows).toHaveLength(1)
    expect(wrapper.find('[data-testid="streaming-bubble"]').exists()).toBe(true)
  })

  it('does not render a streaming bubble when streamingContent is empty', () => {
    const wrapper = mount(AiChatPanel, {
      props: { messages: [{ role: 'user', content: 'Hi' }], streamingContent: '' },
    })
    expect(wrapper.find('[data-testid="streaming-bubble"]').exists()).toBe(false)
  })

  it('emits update:inputMessage when the textarea changes', async () => {
    const wrapper = mount(AiChatPanel, { props: { inputMessage: '' } })
    const ta = wrapper.find('[data-testid="input"]')
    expect(ta.exists()).toBe(true)
    await ta.setValue('hello')
    expect(wrapper.emitted('update:inputMessage')).toBeTruthy()
    expect(wrapper.emitted('update:inputMessage')!.at(-1)).toEqual(['hello'])
  })

  it('emits send when the send button is clicked', async () => {
    const wrapper = mount(AiChatPanel, { props: { inputMessage: 'hello' } })
    const sendBtn = wrapper.find('[data-testid="send"]')
    expect(sendBtn.exists()).toBe(true)
    await sendBtn.trigger('click')
    expect(wrapper.emitted('send')).toBeTruthy()
  })

  it('forwards keydown events on the textarea', async () => {
    const wrapper = mount(AiChatPanel, { props: { inputMessage: '' } })
    const ta = wrapper.find('[data-testid="input"]')
    await ta.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('keydown')).toBeTruthy()
  })
})
