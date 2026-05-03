import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// vue-headless composables touch the global aiAccountsPlugin; stub them.
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

/**
 * Restored b2ee00d~1 AiChatPanel smoke set.
 *
 * The 808-line restored component has a much wider Props surface than the
 * v0.5.4 translation wrapper. This file replaces the deleted v0.5.4
 * wrapper tests; its purpose is the same: verify each of the 11 production
 * call sites can mount the component with the props they pass without
 * leaking Vue "Extraneous non-props attribute" warnings.
 *
 * The 11 prop sets are documented in
 * docs/superpowers/plans/2026-05-03-v0.5.4-ai-accounts-0.3.8-migration.md
 * Task 10. Reproduced here verbatim. Behavior tests for the restored
 * component's internals are out of scope for v0.5.5 — restoring code
 * deleted in b2ee00d means the implementation predates the test set;
 * v0.5.6+ adds back a behavior suite as call sites migrate.
 */

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
      selectedBackend: 'auto',
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
      selectedBackend: 'auto',
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
      selectedBackend: 'auto',
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
      selectedBackend: 'auto',
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
      selectedBackend: 'auto',
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
      // Stripped-down "smart-chat fallback" caller — all state props omitted.
      // The restored component treats them as optional; AIBackendsPage renders
      // an empty chat shell. v0.5.6+ revisits this caller's pattern.
      density: 'detailed',
      welcomeTitle: 'Test a backend',
      placeholder: 'Ask any backend...',
    },
  },
  {
    name: 'SuperAgentPlayground',
    props: {
      density: 'detailed',
      entityLabel: 'SuperAgent',
      placeholder: 'Send a message to your SuperAgent...',
      welcomeTitle: 'Chat with your SuperAgent',
      welcomeSubtitle: 'Type a message to begin.',
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

describe('AiChatPanel (restored from b2ee00d~1) — 11 call site smoke', () => {
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
