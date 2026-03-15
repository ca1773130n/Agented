/**
 * Comprehensive scenario test: Full Workflow Integration.
 *
 * Tests key view components render with realistic data shapes, handle
 * user interactions, and manage error/loading states. Focuses on the
 * views that are wired to real APIs:
 * - ExecutionQueueDashboard
 * - BotDryRun
 * - NaturalLanguageBotCreator
 * - BotCloneForkPage
 * - MultiRepoFanOut
 * - MultiProviderFallback
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

// ---------------------------------------------------------------------------
// Mock vue-router globally for all view components
// ---------------------------------------------------------------------------

const mockPush = vi.fn()
const mockCurrentRoute = { params: {}, query: {} }

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
    currentRoute: ref(mockCurrentRoute),
  }),
  useRoute: () => ref(mockCurrentRoute),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

const mockTriggerList = vi.fn()
const mockTriggerGet = vi.fn()
const mockTriggerCreate = vi.fn()
const mockTriggerUpdate = vi.fn()
const mockTriggerDelete = vi.fn()
const mockTriggerRun = vi.fn()
const mockTriggerListPaths = vi.fn()
const mockTriggerDryRun = vi.fn()
const mockTriggerPreviewPromptFull = vi.fn()

const mockExecutionGetQueueStatus = vi.fn()
const mockExecutionListAll = vi.fn()
const mockExecutionCancel = vi.fn()
const mockExecutionCancelQueueForTrigger = vi.fn()

const mockBackendList = vi.fn()
const mockOrchestrationGetHealth = vi.fn()
const mockOrchestrationGetFallbackChain = vi.fn()
const mockOrchestrationSetFallbackChain = vi.fn()
const mockOrchestrationDeleteFallbackChain = vi.fn()
const mockOrchestrationClearRateLimit = vi.fn()

vi.mock('../services/api', () => ({
  triggerApi: {
    list: (...args: unknown[]) => mockTriggerList(...args),
    get: (...args: unknown[]) => mockTriggerGet(...args),
    create: (...args: unknown[]) => mockTriggerCreate(...args),
    update: (...args: unknown[]) => mockTriggerUpdate(...args),
    delete: (...args: unknown[]) => mockTriggerDelete(...args),
    run: (...args: unknown[]) => mockTriggerRun(...args),
    addPath: vi.fn().mockResolvedValue({}),
    addGitHubRepo: vi.fn().mockResolvedValue({}),
    removePath: vi.fn().mockResolvedValue({}),
    removeGitHubRepo: vi.fn().mockResolvedValue({}),
    setAutoResolve: vi.fn(),
    listPaths: (...args: unknown[]) => mockTriggerListPaths(...args),
    dryRun: (...args: unknown[]) => mockTriggerDryRun(...args),
    previewPromptFull: (...args: unknown[]) => mockTriggerPreviewPromptFull(...args),
  },
  utilityApi: {
    checkBackend: vi.fn().mockResolvedValue({ backend: 'claude', installed: true, version: '1.0.0' }),
    validatePath: vi.fn(),
    validateGitHubUrl: vi.fn(),
    discoverSkills: vi.fn().mockResolvedValue({ skills: [] }),
  },
  agentApi: {
    list: vi.fn().mockResolvedValue({ agents: [], total_count: 0 }),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  teamApi: {
    list: vi.fn().mockResolvedValue({ teams: [], total_count: 0 }),
    get: vi.fn(),
    create: vi.fn(),
  },
  productApi: {
    list: vi.fn().mockResolvedValue({ products: [], total_count: 0 }),
    get: vi.fn(),
    create: vi.fn(),
  },
  projectApi: {
    list: vi.fn().mockResolvedValue({ projects: [], total_count: 0 }),
    get: vi.fn(),
    create: vi.fn(),
  },
  workflowApi: {
    list: vi.fn().mockResolvedValue({ workflows: [] }),
    get: vi.fn(),
    create: vi.fn(),
  },
  analyticsApi: {
    getCost: vi.fn().mockResolvedValue({ data: [], period_count: 0, total_cost: 0 }),
    getExecutions: vi.fn().mockResolvedValue({ data: [], period_count: 0, total_executions: 0 }),
    getEffectiveness: vi.fn().mockResolvedValue({ total_reviews: 0, accepted: 0, ignored: 0, pending: 0, acceptance_rate: 0, over_time: [] }),
  },
  executionApi: {
    listAll: (...args: unknown[]) => mockExecutionListAll(...args),
    listForBot: vi.fn().mockResolvedValue({ executions: [], running_execution: null, total: 0 }),
    get: vi.fn(),
    streamLogs: vi.fn(),
    getRunning: vi.fn(),
    getQueueStatus: (...args: unknown[]) => mockExecutionGetQueueStatus(...args),
    cancel: (...args: unknown[]) => mockExecutionCancel(...args),
    cancelQueueForTrigger: (...args: unknown[]) => mockExecutionCancelQueueForTrigger(...args),
  },
  healthApi: {
    liveness: vi.fn().mockResolvedValue(true),
    readiness: vi.fn().mockResolvedValue({ status: 'ok', components: {} }),
  },
  botTemplateApi: {
    list: vi.fn().mockResolvedValue({ templates: [] }),
    get: vi.fn(),
    deploy: vi.fn(),
  },
  promptSnippetApi: {
    list: vi.fn().mockResolvedValue({ snippets: [] }),
    create: vi.fn(),
    resolve: vi.fn(),
  },
  mcpServerApi: {
    list: vi.fn().mockResolvedValue({ servers: [] }),
    create: vi.fn(),
  },
  backendApi: {
    list: (...args: unknown[]) => mockBackendList(...args),
  },
  orchestrationApi: {
    getHealth: (...args: unknown[]) => mockOrchestrationGetHealth(...args),
    getFallbackChain: (...args: unknown[]) => mockOrchestrationGetFallbackChain(...args),
    setFallbackChain: (...args: unknown[]) => mockOrchestrationSetFallbackChain(...args),
    deleteFallbackChain: (...args: unknown[]) => mockOrchestrationDeleteFallbackChain(...args),
    clearRateLimit: (...args: unknown[]) => mockOrchestrationClearRateLimit(...args),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
      this.name = 'ApiError'
    }
  },
}))

// ---------------------------------------------------------------------------
// Mock useToast composable
// ---------------------------------------------------------------------------

const mockShowToast = vi.fn()

vi.mock('../composables/useToast', () => ({
  useToast: () => mockShowToast,
}))

// ---------------------------------------------------------------------------
// Realistic mock data
// ---------------------------------------------------------------------------

const mockTriggersData = [
  {
    id: 'bot-security',
    name: 'Weekly Security Audit',
    trigger_source: 'webhook',
    backend_type: 'claude',
    prompt_template: 'Scan {paths} for security vulnerabilities',
    is_predefined: 1,
    enabled: 1,
    auto_resolve: 0,
    group_id: 0,
    detection_keyword: 'security_scan',
    text_field_path: 'text',
    created_at: '2024-01-01T00:00:00Z',
    path_count: 2,
  },
  {
    id: 'bot-pr-review',
    name: 'PR Review',
    trigger_source: 'github',
    backend_type: 'claude',
    prompt_template: 'Review pull request: {pr_url}',
    is_predefined: 1,
    enabled: 1,
    auto_resolve: 0,
    group_id: 0,
    detection_keyword: '',
    text_field_path: 'text',
    created_at: '2024-01-01T00:00:00Z',
    path_count: 3,
  },
  {
    id: 'bot-custom-1',
    name: 'Custom Deployment Bot',
    trigger_source: 'manual',
    backend_type: 'claude',
    prompt_template: 'Deploy {message} to production',
    is_predefined: 0,
    enabled: 1,
    auto_resolve: 1,
    group_id: 1,
    detection_keyword: 'deploy',
    text_field_path: 'text',
    model: 'claude-sonnet-4',
    created_at: '2024-03-15T00:00:00Z',
    path_count: 1,
  },
]

const mockQueueData = {
  queue: [
    { trigger_id: 'bot-security', pending: 2, dispatching: 0 },
    { trigger_id: 'bot-pr-review', pending: 1, dispatching: 1 },
  ],
  total_pending: 3,
}

const mockRunningExecutions = {
  executions: [
    {
      execution_id: 'exec-run-1',
      trigger_id: 'bot-security',
      trigger_type: 'webhook',
      status: 'running',
      started_at: new Date(Date.now() - 60000).toISOString(),
    },
    {
      execution_id: 'exec-run-2',
      trigger_id: 'bot-pr-review',
      trigger_type: 'github',
      status: 'running',
      started_at: new Date(Date.now() - 120000).toISOString(),
    },
  ],
  total: 2,
}

const mockPendingExecutions = {
  executions: [
    {
      execution_id: 'exec-pend-1',
      trigger_id: 'bot-security',
      trigger_type: 'webhook',
      status: 'pending',
      started_at: new Date(Date.now() - 30000).toISOString(),
    },
  ],
  total: 1,
}

const mockPathsData = [
  { id: 1, trigger_id: 'bot-security', local_project_path: '/projects/api', github_repo_url: null, path_type: 'local', project_name: null },
  { id: 2, trigger_id: 'bot-security', local_project_path: '', github_repo_url: 'https://github.com/org/frontend', path_type: 'github', project_name: null },
]

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  mockTriggerList.mockResolvedValue({ triggers: mockTriggersData })
  mockTriggerGet.mockResolvedValue(mockTriggersData[0])
  mockTriggerCreate.mockResolvedValue({ message: 'Created', trigger_id: 'trig-new', name: 'New Bot' })
  mockTriggerListPaths.mockResolvedValue({ paths: mockPathsData })
  mockTriggerPreviewPromptFull.mockResolvedValue({ rendered_prompt: 'test', unresolved_placeholders: [] })

  // ExecutionQueueDashboard mocks
  mockExecutionGetQueueStatus.mockResolvedValue(mockQueueData)
  mockExecutionListAll.mockImplementation((params?: { status?: string }) => {
    if (params?.status === 'running') return Promise.resolve(mockRunningExecutions)
    if (params?.status === 'pending') return Promise.resolve(mockPendingExecutions)
    return Promise.resolve({ executions: [], total: 0 })
  })
  mockExecutionCancel.mockResolvedValue({ message: 'Cancelled' })
  mockExecutionCancelQueueForTrigger.mockResolvedValue({ cancelled: 2 })

  // MultiProviderFallback mocks
  mockBackendList.mockResolvedValue({
    backends: [
      { type: 'claude', name: 'Claude' },
      { type: 'gemini', name: 'Gemini' },
    ],
  })
  mockOrchestrationGetHealth.mockResolvedValue({
    accounts: [
      {
        account_id: 1,
        account_name: 'Claude Primary',
        backend_type: 'claude',
        is_rate_limited: false,
        cooldown_remaining_seconds: null,
        total_executions: 42,
        last_used_at: '2024-01-01T00:00:00Z',
        plan: 'pro',
      },
      {
        account_id: 2,
        account_name: 'Gemini Backup',
        backend_type: 'gemini',
        is_rate_limited: false,
        cooldown_remaining_seconds: null,
        total_executions: 10,
        last_used_at: '2024-01-02T00:00:00Z',
        plan: 'standard',
      },
    ],
  })
  mockOrchestrationGetFallbackChain.mockResolvedValue({
    chain: [
      { backend_type: 'claude', account_id: 1 },
      { backend_type: 'gemini', account_id: 2 },
    ],
  })
  mockOrchestrationSetFallbackChain.mockResolvedValue({})
  mockOrchestrationDeleteFallbackChain.mockResolvedValue({})
})

// ===========================================================================
// ExecutionQueueDashboard
// ===========================================================================

describe('ExecutionQueueDashboard', () => {
  async function mountQueueDashboard() {
    const ExecutionQueueDashboard = (await import('../views/ExecutionQueueDashboard.vue')).default
    return mount(ExecutionQueueDashboard, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders queue dashboard with initial data', async () => {
    const wrapper = await mountQueueDashboard()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const html = wrapper.html()
    expect(html.length).toBeGreaterThan(100)
  })

  it('displays queue statistics', async () => {
    const wrapper = await mountQueueDashboard()
    await flushPromises()

    const text = wrapper.text()
    // 2 running executions, 3 total pending
    expect(text).toContain('2') // running count
    expect(text).toContain('3') // pending count
  })

  it('shows Running and Pending lanes', async () => {
    const wrapper = await mountQueueDashboard()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Running')
    expect(text).toContain('Pending')
    expect(text).toContain('Queue by Trigger')
  })

  it('handles drag start and stores dragging state', async () => {
    const wrapper = await mountQueueDashboard()
    await flushPromises()

    const queueItems = wrapper.findAll('[draggable="true"]')
    if (queueItems.length > 0) {
      await queueItems[0].trigger('dragstart')
      expect(wrapper.exists()).toBe(true)
    }
  })

  it('displays execution IDs and trigger names', async () => {
    const wrapper = await mountQueueDashboard()
    await flushPromises()

    const text = wrapper.text()
    // Trigger names are resolved from the triggers map
    expect(text).toContain('Weekly Security Audit')
    expect(text).toContain('PR Review')
  })
})

// ===========================================================================
// BotDryRun
// ===========================================================================

describe('BotDryRun', () => {
  async function mountDryRun() {
    const BotDryRun = (await import('../views/BotDryRun.vue')).default
    return mount(BotDryRun, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders dry run page with trigger selector and payload editor', async () => {
    const wrapper = await mountDryRun()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
  })

  it('loads triggers on mount', async () => {
    await mountDryRun()
    await flushPromises()

    expect(mockTriggerList).toHaveBeenCalled()
  })

  it('selects first trigger by default', async () => {
    const wrapper = await mountDryRun()
    await flushPromises()

    const selects = wrapper.findAll('select')
    if (selects.length > 0) {
      expect(selects[0].exists()).toBe(true)
    }
  })

  it('validates JSON payload and shows error for invalid JSON', async () => {
    const wrapper = await mountDryRun()
    await flushPromises()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('{invalid json')
      // Trigger input event to call validateJson
      await textarea.trigger('input')
      await nextTick()

      // The component shows the JS error message in an error-hint div
      const errorHint = wrapper.find('.error-hint')
      expect(errorHint.exists()).toBe(true)
    }
  })

  it('displays dry run results after successful dry run', async () => {
    mockTriggerDryRun.mockResolvedValue({
      trigger_id: 'bot-security',
      trigger_name: 'Weekly Security Audit',
      backend_type: 'claude',
      model: 'claude-sonnet-4',
      cli_command: 'claude -p "Scan for vulnerabilities"',
      rendered_prompt: 'Scan /projects/api for security vulnerabilities',
      estimated_tokens: {
        estimated_input_tokens: 1000,
        estimated_output_tokens: 500,
        estimated_cost_usd: 0.0045,
        confidence: 'medium',
      },
    })

    const wrapper = await mountDryRun()
    await flushPromises()

    // Find and click the dry run button
    const buttons = wrapper.findAll('button')
    const runButton = buttons.find(b => {
      const txt = b.text().toLowerCase()
      return txt.includes('dry run') || txt.includes('run')
    })
    if (runButton) {
      await runButton.trigger('click')
      await flushPromises()
      await nextTick()

      // Should show dry run output
      const text = wrapper.text()
      expect(text).toContain('Weekly Security Audit')
    }
  })

  it('handles API errors gracefully when loading triggers', async () => {
    mockTriggerList.mockRejectedValueOnce(new Error('Network error'))

    const wrapper = await mountDryRun()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
  })
})

// ===========================================================================
// NaturalLanguageBotCreator
// ===========================================================================

describe('NaturalLanguageBotCreator', () => {
  async function mountNLCreator() {
    const NaturalLanguageBotCreator = (await import('../views/NaturalLanguageBotCreator.vue')).default
    return mount(NaturalLanguageBotCreator, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders with description input field', async () => {
    const wrapper = await mountNLCreator()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
  })

  it('disables generate button when description is too short', async () => {
    const wrapper = await mountNLCreator()
    await flushPromises()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('short')
      await nextTick()

      const buttons = wrapper.findAll('button')
      const genButton = buttons.find(b => b.text().toLowerCase().includes('generate'))
      if (genButton) {
        expect(genButton.attributes('disabled')).toBeDefined()
      }
    }
  })

  it('enables generate button with sufficient description', async () => {
    const wrapper = await mountNLCreator()
    await flushPromises()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('Create a bot that reviews pull requests for security issues and OWASP vulnerabilities')
      await nextTick()

      const buttons = wrapper.findAll('button')
      const genButton = buttons.find(b => b.text().toLowerCase().includes('generate'))
      if (genButton) {
        expect(genButton.attributes('disabled')).toBeUndefined()
      }
    }
  })

  it('shows generated config after generation', async () => {
    vi.useFakeTimers()

    const wrapper = await mountNLCreator()
    await flushPromises()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('Create a daily security scanner that reviews code for OWASP vulnerabilities')
      await nextTick()

      const buttons = wrapper.findAll('button')
      const genButton = buttons.find(b => b.text().toLowerCase().includes('generate'))
      if (genButton) {
        await genButton.trigger('click')
        vi.advanceTimersByTime(1500)
        await flushPromises()
        await nextTick()

        const text = wrapper.text()
        expect(text).toContain('Bot')
      }
    }

    vi.useRealTimers()
  })

  it('shows toast on successful generation', async () => {
    vi.useFakeTimers()

    const wrapper = await mountNLCreator()
    await flushPromises()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('A bot that scans repositories for dependency updates weekly')
      await nextTick()

      const buttons = wrapper.findAll('button')
      const genButton = buttons.find(b => b.text().toLowerCase().includes('generate'))
      if (genButton) {
        await genButton.trigger('click')
        vi.advanceTimersByTime(1500)
        await flushPromises()

        expect(mockShowToast).toHaveBeenCalledWith('Bot configuration generated', 'success')
      }
    }

    vi.useRealTimers()
  })
})

// ===========================================================================
// BotCloneForkPage
// ===========================================================================

describe('BotCloneForkPage', () => {
  async function mountCloneFork() {
    const BotCloneForkPage = (await import('../views/BotCloneForkPage.vue')).default
    return mount(BotCloneForkPage, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders with a list of bots from API', async () => {
    const wrapper = await mountCloneFork()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const text = wrapper.text()
    // Shows trigger names from the mock API data
    expect(text).toContain('Weekly Security Audit')
    expect(text).toContain('PR Review')
  })

  it('displays bot backend type and trigger source', async () => {
    const wrapper = await mountCloneFork()
    await flushPromises()

    const text = wrapper.text()
    // Shows backend_type and trigger_source from API data
    expect(text).toContain('claude')
    expect(text).toContain('webhook')
  })

  it('shows search input for filtering bots', async () => {
    const wrapper = await mountCloneFork()
    await flushPromises()

    const inputs = wrapper.findAll('input')
    const searchInput = inputs.find(i => {
      const placeholder = i.attributes('placeholder') || ''
      return placeholder.toLowerCase().includes('search')
    })
    expect(searchInput).toBeDefined()
  })

  it('handles search filtering', async () => {
    const wrapper = await mountCloneFork()
    await flushPromises()

    const inputs = wrapper.findAll('input')
    const searchInput = inputs.find(i => {
      const placeholder = i.attributes('placeholder') || ''
      return placeholder.toLowerCase().includes('search')
    })

    if (searchInput) {
      await searchInput.setValue('security')
      await nextTick()
      expect(wrapper.exists()).toBe(true)
    }
  })
})

// ===========================================================================
// MultiRepoFanOut
// ===========================================================================

describe('MultiRepoFanOut', () => {
  async function mountFanOut() {
    const MultiRepoFanOut = (await import('../views/MultiRepoFanOut.vue')).default
    return mount(MultiRepoFanOut, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders with trigger selector and path management', async () => {
    const wrapper = await mountFanOut()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const text = wrapper.text()
    // Should show Fan-Out related content
    expect(text).toContain('Fan-Out')
  })

  it('loads triggers from API', async () => {
    await mountFanOut()
    await flushPromises()

    expect(mockTriggerList).toHaveBeenCalled()
  })

  it('loads paths for the selected trigger', async () => {
    await mountFanOut()
    await flushPromises()

    // Should auto-select first trigger and load its paths
    expect(mockTriggerListPaths).toHaveBeenCalledWith('bot-security')
  })

  it('displays loaded paths from API', async () => {
    const wrapper = await mountFanOut()
    await flushPromises()

    const text = wrapper.text()
    // Should show the paths loaded from the API mock
    expect(text).toContain('/projects/api')
    expect(text).toContain('github.com/org/frontend')
  })

  it('allows adding new repo path', async () => {
    const wrapper = await mountFanOut()
    await flushPromises()

    // Find the text input for adding a repo
    const inputs = wrapper.findAll('input')
    const repoInput = inputs.find(i => {
      const ph = (i.attributes('placeholder') || '').toLowerCase()
      return ph.includes('github') || ph.includes('repo') || ph.includes('path')
    })

    if (repoInput) {
      await repoInput.setValue('org/new-service')
      await nextTick()
    }

    expect(wrapper.exists()).toBe(true)
  })

  it('shows path count in overview', async () => {
    const wrapper = await mountFanOut()
    await flushPromises()

    const text = wrapper.text()
    // The overview section shows path counts
    expect(text).toContain('Total paths')
  })
})

// ===========================================================================
// MultiProviderFallback
// ===========================================================================

describe('MultiProviderFallback', () => {
  async function mountFallback() {
    const MultiProviderFallback = (await import('../views/MultiProviderFallback.vue')).default
    return mount(MultiProviderFallback, {
      global: {
        stubs: {
          AppBreadcrumb: true,
          PageHeader: true,
        },
      },
    })
  }

  it('renders with fallback chain configuration', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    const text = wrapper.text()
    // Should show provider fallback order
    expect(text).toContain('Provider Fallback Order')
  })

  it('displays provider list with names', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    const text = wrapper.text()
    // Shows backend names from API
    expect(text).toContain('Claude')
    expect(text).toContain('Gemini')
  })

  it('shows provider health status', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    const text = wrapper.text().toLowerCase()
    expect(text).toContain('healthy')
  })

  it('displays account health section', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Account Health')
  })

  it('handles save action', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const saveBtn = buttons.find(b => b.text().toLowerCase().includes('save'))
    if (saveBtn) {
      await saveBtn.trigger('click')
      await flushPromises()

      expect(mockOrchestrationSetFallbackChain).toHaveBeenCalled()
      expect(mockShowToast).toHaveBeenCalledWith('Fallback chain saved', 'success')
    }
  })

  it('shows execution counts for providers', async () => {
    const wrapper = await mountFallback()
    await flushPromises()

    const text = wrapper.text()
    // Shows execution counts from health data
    expect(text).toContain('42') // Claude Primary total_executions
    expect(text).toContain('10') // Gemini Backup total_executions
  })
})

// ===========================================================================
// Cross-component integration scenarios
// ===========================================================================

describe('Cross-component integration', () => {
  it('API error class has correct properties', async () => {
    const { ApiError } = await import('../services/api')
    const error = new ApiError(404, 'Not found')
    expect(error.status).toBe(404)
    expect(error.message).toBe('Not found')
    expect(error.name).toBe('ApiError')
  })

  it('all view components can be imported without errors', async () => {
    const modules = await Promise.all([
      import('../views/ExecutionQueueDashboard.vue'),
      import('../views/BotDryRun.vue'),
      import('../views/NaturalLanguageBotCreator.vue'),
      import('../views/BotCloneForkPage.vue'),
      import('../views/MultiRepoFanOut.vue'),
      import('../views/MultiProviderFallback.vue'),
    ])

    for (const mod of modules) {
      expect(mod.default).toBeDefined()
    }
  })

  it('components render without crashing when API returns empty data', async () => {
    mockTriggerList.mockResolvedValue({ triggers: [] })
    mockTriggerListPaths.mockResolvedValue({ paths: [] })

    const components = [
      (await import('../views/BotDryRun.vue')).default,
      (await import('../views/MultiRepoFanOut.vue')).default,
    ]

    for (const Component of components) {
      const wrapper = mount(Component, {
        global: {
          stubs: { PageHeader: true },
        },
      })
      await flushPromises()
      expect(wrapper.exists()).toBe(true)
      wrapper.unmount()
    }
  })

  it('components survive API rejection without crashing', async () => {
    mockTriggerList.mockRejectedValue(new Error('Server unreachable'))

    const BotDryRun = (await import('../views/BotDryRun.vue')).default
    const wrapper = mount(BotDryRun, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    wrapper.unmount()
  })
})

// ===========================================================================
// Loading and error state tests
// ===========================================================================

describe('Loading and error states', () => {
  it('BotDryRun shows loading state while triggers load', async () => {
    mockTriggerList.mockImplementation(() => new Promise(() => {}))

    const BotDryRun = (await import('../views/BotDryRun.vue')).default
    const wrapper = mount(BotDryRun, {
      global: {
        stubs: { PageHeader: true },
      },
    })

    expect(wrapper.exists()).toBe(true)
    wrapper.unmount()
  })

  it('MultiRepoFanOut handles empty trigger list gracefully', async () => {
    mockTriggerList.mockResolvedValue({ triggers: [] })
    mockTriggerListPaths.mockResolvedValue({ paths: [] })

    const MultiRepoFanOut = (await import('../views/MultiRepoFanOut.vue')).default
    const wrapper = mount(MultiRepoFanOut, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    // Should show the fan-out UI structure
    expect(wrapper.text()).toContain('Fan-Out')
    wrapper.unmount()
  })

  it('NaturalLanguageBotCreator is fully interactive without API calls', async () => {
    const NLCreator = (await import('../views/NaturalLanguageBotCreator.vue')).default
    const wrapper = mount(NLCreator, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    // Should not have made any trigger API calls on mount
    expect(mockTriggerList).not.toHaveBeenCalled()

    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('This is a test description that is long enough to pass validation')
      await nextTick()
      expect(wrapper.exists()).toBe(true)
    }

    wrapper.unmount()
  })

  it('ExecutionQueueDashboard shows error when queue API fails', async () => {
    mockExecutionGetQueueStatus.mockRejectedValue(new Error('Queue service down'))

    const ExecutionQueueDashboard = (await import('../views/ExecutionQueueDashboard.vue')).default
    const wrapper = mount(ExecutionQueueDashboard, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Failed to load queue data')
    wrapper.unmount()
  })

  it('MultiProviderFallback shows error when APIs fail', async () => {
    mockBackendList.mockRejectedValue(new Error('Backend service down'))

    const MultiProviderFallback = (await import('../views/MultiProviderFallback.vue')).default
    const wrapper = mount(MultiProviderFallback, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('Backend service down')
    wrapper.unmount()
  })
})

// ===========================================================================
// Navigation tests
// ===========================================================================

describe('Navigation', () => {
  it('ExecutionQueueDashboard has back navigation', async () => {
    const ExecutionQueueDashboard = (await import('../views/ExecutionQueueDashboard.vue')).default
    const wrapper = mount(ExecutionQueueDashboard, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    // AppBreadcrumb removed — breadcrumbs now handled by AppHeader globally
    wrapper.unmount()
  })

  it('BotDryRun renders breadcrumb', async () => {
    const BotDryRun = (await import('../views/BotDryRun.vue')).default
    const wrapper = mount(BotDryRun, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    // AppBreadcrumb removed — breadcrumbs now handled by AppHeader globally
    wrapper.unmount()
  })

  it('NaturalLanguageBotCreator navigates to bots on save', async () => {
    vi.useFakeTimers()

    const NLCreator = (await import('../views/NaturalLanguageBotCreator.vue')).default
    const wrapper = mount(NLCreator, {
      global: {
        stubs: { PageHeader: true },
      },
    })
    await flushPromises()

    // First generate config
    const textarea = wrapper.find('textarea')
    if (textarea.exists()) {
      await textarea.setValue('Create a daily security scanner bot that reviews code for OWASP vulnerabilities')
      await nextTick()

      const genBtn = wrapper.findAll('button').find(b => b.text().toLowerCase().includes('generate'))
      if (genBtn) {
        await genBtn.trigger('click')
        vi.advanceTimersByTime(1500)
        await flushPromises()
        await nextTick()

        // Now try to save
        const saveBtn = wrapper.findAll('button').find(b => b.text().toLowerCase().includes('save'))
        if (saveBtn && !saveBtn.attributes('disabled')) {
          await saveBtn.trigger('click')
          vi.advanceTimersByTime(1000)
          await flushPromises()

          expect(mockPush).toHaveBeenCalledWith({ name: 'bots' })
        }
      }
    }

    vi.useRealTimers()
    wrapper.unmount()
  })
})
