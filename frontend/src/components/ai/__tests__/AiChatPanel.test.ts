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
      listBackends: vi.fn().mockResolvedValue({ items: [] }),
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
      { role: 'user' as const, content: 'Hello' },
      { role: 'assistant' as const, content: 'Hi there' },
    ]
    const wrapper = mount(AiChatPanel, { props: { messages } })
    const items = wrapper.findAll('[data-testid="bubble-row"]')
    expect(items).toHaveLength(2)
  })

  it('renders streamingContent as an in-flight bubble after the messages', () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        messages: [{ role: 'user' as const, content: 'Hi' }],
        streamingContent: 'partial response...',
      },
    })
    const rows = wrapper.findAll('[data-testid="bubble-row"]')
    expect(rows).toHaveLength(1)
    expect(wrapper.find('[data-testid="streaming-bubble"]').exists()).toBe(true)
  })

  it('does not render a streaming bubble when streamingContent is empty', () => {
    const wrapper = mount(AiChatPanel, {
      props: { messages: [{ role: 'user' as const, content: 'Hi' }], streamingContent: '' },
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

  it('shows backend selector when showBackendSelector is true', () => {
    const wrapper = mount(AiChatPanel, { props: { showBackendSelector: true } })
    expect(wrapper.find('[data-testid="backend-selector"]').exists()).toBe(true)
  })

  it('hides backend selector by default', () => {
    const wrapper = mount(AiChatPanel)
    expect(wrapper.find('[data-testid="backend-selector"]').exists()).toBe(false)
  })

  it('emits update:selectedBackend / update:selectedAccountId / update:selectedModel when ChatControls fires', async () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        showBackendSelector: true,
        selectedBackend: 'claude',
        selectedAccountId: 'acc-1',
        selectedModel: 'opus-4',
      },
    })
    const { ChatControls } = await import('@ai-accounts/vue-styled')
    const controls = wrapper.findComponent(ChatControls)
    expect(controls.exists()).toBe(true)
    controls.vm.$emit('update:selectedBackend', 'codex')
    controls.vm.$emit('update:selectedAccount', 'acc-2')
    controls.vm.$emit('update:selectedModel', 'sonnet-4')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:selectedBackend')!.at(-1)).toEqual(['codex'])
    expect(wrapper.emitted('update:selectedAccountId')!.at(-1)).toEqual(['acc-2'])
    expect(wrapper.emitted('update:selectedModel')!.at(-1)).toEqual(['sonnet-4'])
  })

  it('shows finalization banner when canFinalize is true', () => {
    const wrapper = mount(AiChatPanel, {
      props: {
        canFinalize: true,
        bannerTitle: 'Plugin Ready',
        bannerButtonLabel: 'Create',
        entityLabel: 'plugin',
      },
    })
    expect(wrapper.find('[data-testid="finalize-banner"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Plugin Ready')
  })

  it('does not show banner when canFinalize is false', () => {
    const wrapper = mount(AiChatPanel, { props: { canFinalize: false } })
    expect(wrapper.find('[data-testid="finalize-banner"]').exists()).toBe(false)
  })

  it('forwards header-extra slot', () => {
    const wrapper = mount(AiChatPanel, {
      slots: { 'header-extra': '<div data-testid="header-extra-content">CUSTOM</div>' },
    })
    expect(wrapper.find('[data-testid="header-extra-content"]').exists()).toBe(true)
  })

  it('forwards welcome slot when no messages', () => {
    const wrapper = mount(AiChatPanel, {
      props: { messages: [] },
      slots: { welcome: '<div data-testid="welcome-content">Hi there</div>' },
    })
    expect(wrapper.find('[data-testid="welcome-content"]').exists()).toBe(true)
  })

  it('does not show welcome slot when messages exist', () => {
    const wrapper = mount(AiChatPanel, {
      props: { messages: [{ role: 'user' as const, content: 'x' }] },
      slots: { welcome: '<div data-testid="welcome-content">Hi</div>' },
    })
    expect(wrapper.find('[data-testid="welcome-content"]').exists()).toBe(false)
  })

  it('attaches useSmartScroll containerRef when useSmartScroll is true (smoke)', () => {
    expect(() => mount(AiChatPanel, { props: { useSmartScroll: true } })).not.toThrow()
  })

  it('invokes initStreamingParser on mount if provided', () => {
    const initStreamingParser = vi.fn()
    mount(AiChatPanel, { props: { initStreamingParser } })
    expect(initStreamingParser).toHaveBeenCalledTimes(1)
  })

  it('readOnly disables the textarea', () => {
    const wrapper = mount(AiChatPanel, { props: { readOnly: true } })
    const ta = wrapper.find('[data-testid="input"]')
    expect(ta.attributes('disabled')).toBeDefined()
  })

  it('density=minimal does not render ProcessGroup (v0.5.4 path-Z minimal scope)', async () => {
    const { ProcessGroup } = await import('@ai-accounts/vue-styled')
    const wrapper = mount(AiChatPanel, {
      props: {
        density: 'minimal',
        messages: [{ role: 'assistant' as const, content: 'with tool call' }],
      },
    })
    expect(wrapper.findComponent(ProcessGroup).exists()).toBe(false)
  })

  it('emits finalize with parsed config when banner fires', async () => {
    const configParser = (s: string) => ({ parsed: s })
    const wrapper = mount(AiChatPanel, {
      props: {
        canFinalize: true,
        bannerTitle: 'Plugin Ready',
        bannerButtonLabel: 'Create',
        entityLabel: 'plugin',
        detectedEntityName: 'foo',
        messages: [
          { role: 'user' as const, content: 'q' },
          { role: 'assistant' as const, content: 'parseable-config-content' },
        ],
        configParser,
      },
    })
    const { FinalizationBanner } = await import('@ai-accounts/vue-styled')
    const banner = wrapper.findComponent(FinalizationBanner)
    expect(banner.exists()).toBe(true)
    banner.vm.$emit('finalize')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('finalize')).toBeTruthy()
    expect(wrapper.emitted('finalize')!.at(-1)).toEqual([{ parsed: 'parseable-config-content' }])
  })
})

// 11 production call sites whose AiChatPanel prop sets are smoke-tested
// against the rebuilt wrapper. Each prop set is the union of bindings
// inspected from the actual <AiChatPanel /> in the named view file.
// Mounting must complete with NO Vue "Extraneous non-props attribute"
// warnings — that warning is exactly the silent breakage symptom the
// b2ee00d WIP introduced. Anything new the wrapper needs comes out of
// running this suite.
const callSitePropSets: Array<{ name: string; props: Record<string, unknown> }> = [
  {
    name: 'SketchChatPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'sketch',
      bannerTitle: '',
      bannerButtonLabel: '',
      showBackendSelector: false,
    },
  },
  {
    name: 'PluginDesignPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      initStreamingParser: () => {},
      showBackendSelector: true,
      useSmartScroll: true,
      selectedBackend: null,
      selectedAccountId: null,
      selectedModel: null,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'plugin',
      bannerTitle: '',
      bannerButtonLabel: '',
      detectedEntityName: undefined,
    },
  },
  {
    name: 'RuleDesignPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      initStreamingParser: () => {},
      showBackendSelector: true,
      useSmartScroll: true,
      selectedBackend: null,
      selectedAccountId: null,
      selectedModel: null,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'rule',
      bannerTitle: 'Rule Ready to Create!',
      bannerButtonLabel: 'Create Rule Now',
      detectedEntityName: undefined,
    },
  },
  {
    name: 'WorkflowPlaygroundPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'Workflow',
      bannerTitle: '',
      bannerButtonLabel: '',
      showBackendSelector: true,
      selectedBackend: null,
      selectedAccountId: null,
      selectedModel: null,
    },
  },
  {
    name: 'ProjectManagementPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'],
      inputPlaceholder: 'x',
      entityLabel: 'project',
      bannerTitle: '',
      bannerButtonLabel: '',
      readOnly: false,
      useSmartScroll: true,
    },
  },
  {
    name: 'HookDesignPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      initStreamingParser: () => {},
      showBackendSelector: true,
      useSmartScroll: true,
      selectedBackend: null,
      selectedAccountId: null,
      selectedModel: null,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'hook',
      bannerTitle: 'Hook Ready to Create!',
      bannerButtonLabel: 'Create Hook Now',
      detectedEntityName: undefined,
    },
  },
  {
    name: 'CommandDesignPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      initStreamingParser: () => {},
      showBackendSelector: true,
      useSmartScroll: true,
      selectedBackend: null,
      selectedAccountId: null,
      selectedModel: null,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'command',
      bannerTitle: 'Command Ready to Create!',
      bannerButtonLabel: 'Create Command Now',
      detectedEntityName: undefined,
    },
  },
  {
    name: 'AIBackendsPage',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'backend',
      bannerTitle: '',
      bannerButtonLabel: '',
    },
  },
  {
    name: 'SuperAgentPlayground',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'super-agent',
      bannerTitle: '',
      bannerButtonLabel: '',
    },
  },
  {
    name: 'SkillCreateWizard',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'skill',
      bannerTitle: '',
      bannerButtonLabel: '',
    },
  },
  {
    name: 'AgentCreateWizard',
    props: {
      messages: [],
      isProcessing: false,
      streamingContent: '',
      inputMessage: '',
      conversationId: null,
      canFinalize: false,
      isFinalizing: false,
      assistantIconPaths: [],
      inputPlaceholder: 'x',
      entityLabel: 'agent',
      bannerTitle: '',
      bannerButtonLabel: '',
    },
  },
]

describe('AiChatPanel — 11 call site smoke', () => {
  for (const { name, props } of callSitePropSets) {
    it(`mounts cleanly with ${name} props (no Extraneous attribute warnings)`, () => {
      const warnings: string[] = []
      const origWarn = console.warn
      console.warn = (msg: unknown) => {
        warnings.push(String(msg))
      }
      try {
        mount(AiChatPanel, { props })
      } finally {
        console.warn = origWarn
      }
      const extraneous = warnings.filter((w) => w.includes('Extraneous non-props attribute'))
      expect(extraneous, `${name} prop set leaked: ${extraneous.join(' | ')}`).toEqual([])
    })
  }
})
