import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SuperAgentPlayground from '../SuperAgentPlayground.vue'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ params: { superAgentId: 'super-abc123' } }),
}))

const mockSuperAgent = {
  id: 'super-abc123',
  name: 'Test Agent',
  description: 'A test super agent',
  backend_type: 'claude',
  preferred_model: 'opus',
  team_id: 'team-xyz',
  max_concurrent_sessions: 3,
  enabled: 1,
  created_at: '2026-02-16T00:00:00Z',
}

const mockSessions = [
  {
    id: 'sess-001',
    super_agent_id: 'super-abc123',
    status: 'active' as const,
    token_count: 100,
    started_at: '2026-02-16T10:00:00Z',
  },
  {
    id: 'sess-002',
    super_agent_id: 'super-abc123',
    status: 'completed' as const,
    token_count: 500,
    started_at: '2026-02-16T08:00:00Z',
    ended_at: '2026-02-16T09:00:00Z',
  },
]

const mockStreamInstance = {
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  close: vi.fn(),
}

vi.mock('../../services/api', () => ({
  superAgentApi: {
    get: vi.fn(),
    list: vi.fn(),
  },
  superAgentDocumentApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
  superAgentSessionApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    sendMessage: vi.fn(),
    sendChatMessage: vi.fn(),
    end: vi.fn(),
    stream: vi.fn(),
    chatStream: vi.fn(),
  },
  agentMessageApi: {
    listInbox: vi.fn(),
    listOutbox: vi.fn(),
    markRead: vi.fn(),
    send: vi.fn(),
  },
  teamApi: {
    listMembers: vi.fn(),
  },
  backendApi: {
    list: vi.fn(),
  },
  API_BASE: '',
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

// Mock EventSource globally for MessageInbox SSE and chatStream
const mockEventSource = {
  addEventListener: vi.fn(),
  close: vi.fn(),
  onmessage: null as ((event: MessageEvent) => void) | null,
  onerror: null as ((event: Event) => void) | null,
}
vi.stubGlobal('EventSource', function() { return mockEventSource })

/**
 * Helper: creates a session, captures the state_delta handler,
 * sends a message, and simulates SSE finish to clear isProcessing.
 * Returns { wrapper, stateDeltaHandler }.
 */
async function setupWithMessage(mountFn: () => ReturnType<typeof mount>, messageText: string) {
  // Capture state_delta handler
  let stateDeltaHandler: ((event: Event) => void) | null = null
  vi.mocked(mockEventSource.addEventListener).mockImplementation((event: string, handler: any) => {
    if (event === 'state_delta') {
      stateDeltaHandler = handler
    }
  })

  const wrapper = mountFn()
  await flushPromises()

  // Create a session
  const newSessionBtn = wrapper.findAll('button').find(
    (b) => b.text().includes('New Session'),
  )
  await newSessionBtn!.trigger('click')
  await flushPromises()

  // Send a message
  const textarea = wrapper.find('.input-wrapper textarea')
  await textarea.setValue(messageText)
  await textarea.trigger('keydown', { key: 'Enter' })
  await flushPromises()

  // Simulate SSE finish event to complete processing
  const handler = stateDeltaHandler as ((event: Event) => void) | null
  if (handler) {
    const finishEvent = {
      data: JSON.stringify({ type: 'finish', content: '' }),
      lastEventId: '2',
    } as unknown as Event
    handler(finishEvent)
    await flushPromises()
  }

  return { wrapper, stateDeltaHandler: handler }
}

describe('SuperAgentPlayground', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(SuperAgentPlayground, {
      global: {
        provide: {
          showToast: mockShowToast,
        },
        stubs: {
          teleport: true,
          AiChatSelector: true,
        },
      },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    mockEventSource.addEventListener.mockReset()
    mockEventSource.close.mockReset()
    const api = await import('../../services/api')
    vi.mocked(api.superAgentApi.get).mockResolvedValue(mockSuperAgent as any)
    vi.mocked(api.superAgentApi.list).mockResolvedValue({ super_agents: [] })
    vi.mocked(api.superAgentSessionApi.list).mockResolvedValue({ sessions: mockSessions })
    vi.mocked(api.superAgentSessionApi.get).mockResolvedValue(mockSessions[0] as any)
    vi.mocked(api.superAgentSessionApi.create).mockResolvedValue({
      message: 'Created',
      session_id: 'sess-new',
    })
    vi.mocked(api.superAgentSessionApi.sendMessage).mockResolvedValue({
      message: 'Sent',
    })
    vi.mocked(api.superAgentSessionApi.sendChatMessage).mockResolvedValue({
      status: 'ok',
      message_id: 'msg-001',
    })
    vi.mocked(api.superAgentSessionApi.end).mockResolvedValue({
      message: 'Ended',
    })
    vi.mocked(api.superAgentSessionApi.stream).mockReturnValue(
      mockStreamInstance as any,
    )
    vi.mocked(api.superAgentSessionApi.chatStream).mockReturnValue(
      mockEventSource as any,
    )
    vi.mocked(api.superAgentDocumentApi.list).mockResolvedValue({ documents: [] })
    vi.mocked(api.teamApi.listMembers).mockResolvedValue({ members: [] })
    vi.mocked(api.backendApi.list).mockResolvedValue({ backends: [] })
    vi.mocked(api.agentMessageApi.listInbox).mockResolvedValue({ messages: [] })
    vi.mocked(api.agentMessageApi.listOutbox).mockResolvedValue({ messages: [] })
  })

  it('renders with chat panel and right panel', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // Left panel with chat
    expect(wrapper.find('.left-panel').exists()).toBe(true)
    expect(wrapper.find('.chat-panel').exists()).toBe(true)

    // Right panel with tabs
    expect(wrapper.find('.right-panel').exists()).toBe(true)
    expect(wrapper.findAll('.right-tab').length).toBe(4)
  })

  it('loads super agent details on mount', async () => {
    const api = await import('../../services/api')
    mountComponent()
    await flushPromises()

    expect(api.superAgentApi.get).toHaveBeenCalledWith('super-abc123')
  })

  it('creates session on New Session click', async () => {
    const api = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Find and click "New Session" button
    const newSessionBtn = wrapper.findAll('button').find(
      (b) => b.text().includes('New Session'),
    )
    expect(newSessionBtn).toBeDefined()
    await newSessionBtn!.trigger('click')
    await flushPromises()

    expect(api.superAgentSessionApi.create).toHaveBeenCalledWith('super-abc123')
  })

  it('sends message through chat panel using sendChatMessage', async () => {
    const api = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // First create a session so sending is allowed
    const newSessionBtn = wrapper.findAll('button').find(
      (b) => b.text().includes('New Session'),
    )
    await newSessionBtn!.trigger('click')
    await flushPromises()

    // Type a message and send
    const textarea = wrapper.find('.input-wrapper textarea')
    await textarea.setValue('Hello SuperAgent')
    // Trigger keydown Enter to send
    await textarea.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(api.superAgentSessionApi.sendChatMessage).toHaveBeenCalledWith(
      'super-abc123',
      'sess-new',
      'Hello SuperAgent',
      { backend: undefined, account_id: undefined, model: undefined },
    )
  })

  it('switches right panel tabs', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const tabs = wrapper.findAll('.right-tab')
    expect(tabs.length).toBe(4)

    // Default is Identity tab
    expect(tabs[0].classes()).toContain('active')
    expect(wrapper.find('.identity-panel').exists()).toBe(true)

    // Switch to Team tab
    await tabs[1].trigger('click')
    await flushPromises()
    expect(tabs[1].classes()).toContain('active')
    expect(wrapper.find('.subagent-composition').exists()).toBe(true)

    // Switch to Sessions tab
    await tabs[2].trigger('click')
    await flushPromises()
    expect(tabs[2].classes()).toContain('active')
    expect(wrapper.find('.session-list').exists()).toBe(true)
  })

  it('loads documents in DocumentEditor', async () => {
    const api = await import('../../services/api')
    mountComponent()
    await flushPromises()

    // DocumentEditor is mounted in the Identity tab (default)
    expect(api.superAgentDocumentApi.list).toHaveBeenCalledWith('super-abc123')
  })

  it('cleans up EventSource on unmount', async () => {
    const api = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Create a session to trigger stream connection
    const newSessionBtn = wrapper.findAll('button').find(
      (b) => b.text().includes('New Session'),
    )
    await newSessionBtn!.trigger('click')
    await flushPromises()

    // Verify chatStream was connected
    expect(api.superAgentSessionApi.chatStream).toHaveBeenCalledWith(
      'super-abc123',
      'sess-new',
    )

    // Unmount
    wrapper.unmount()

    // Verify close was called
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('shows session list with status badges', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // Navigate to sessions tab
    const tabs = wrapper.findAll('.right-tab')
    await tabs[2].trigger('click')
    await flushPromises()

    const sessionCards = wrapper.findAll('.session-card')
    expect(sessionCards.length).toBe(2)

    // Check status badges
    expect(wrapper.find('.status-active').exists()).toBe(true)
    expect(wrapper.find('.status-completed').exists()).toBe(true)
  })

  // --- New tests for 37-03/37-04: MessageBubble rendering, process groups, SSE protocol ---

  it('renders MessageBubble components when useSmartScroll is true', async () => {
    const { wrapper } = await setupWithMessage(mountComponent, 'Hello')

    // User message should be rendered as a MessageBubble (class .message-bubble)
    const bubbles = wrapper.findAll('.message-bubble')
    expect(bubbles.length).toBeGreaterThanOrEqual(1)
  })

  it('renders messages with correct content via MessageBubble', async () => {
    const { wrapper } = await setupWithMessage(mountComponent, 'Test content')

    // MessageBubble renders content in .bubble-text
    const bubbleTexts = wrapper.findAll('.bubble-text')
    const hasContent = bubbleTexts.some(
      (m) => m.text().includes('Test content'),
    )
    expect(hasContent).toBe(true)
  })

  it('scroll-to-bottom button not visible when at bottom', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // By default, user is at bottom so scroll button should not be visible
    expect(wrapper.find('.scroll-to-bottom-btn').exists()).toBe(false)
  })

  it('state_delta SSE events update messages', async () => {
    const api = await import('../../services/api')

    // Track addEventListener calls to capture handlers
    let stateDeltaHandler: ((event: Event) => void) | null = null
    mockEventSource.addEventListener.mockImplementation((event: string, handler: any) => {
      if (event === 'state_delta') {
        stateDeltaHandler = handler
      }
    })

    const wrapper = mountComponent()
    await flushPromises()

    // Create a session to trigger stream connection
    const newSessionBtn = wrapper.findAll('button').find(
      (b) => b.text().includes('New Session'),
    )
    await newSessionBtn!.trigger('click')
    await flushPromises()

    expect(api.superAgentSessionApi.chatStream).toHaveBeenCalled()
    expect(stateDeltaHandler).not.toBeNull()

    // Simulate a state_delta message event
    const fakeEvent = {
      data: JSON.stringify({
        type: 'message',
        role: 'assistant',
        content: 'Hello from SSE!',
        timestamp: '2026-02-17T12:00:00Z',
      }),
      lastEventId: '1',
    } as unknown as Event

    stateDeltaHandler!(fakeEvent)
    await flushPromises()

    // Verify the message was added -- MessageBubble uses .bubble-text
    const bubbleTexts = wrapper.findAll('.bubble-text')
    const hasSSEMessage = bubbleTexts.some(
      (m) => m.text().includes('Hello from SSE!'),
    )
    expect(hasSSEMessage).toBe(true)
  })

  it('passes useSmartScroll and processGroups to AiChatPanel', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // Verify the AiChatPanel component receives the props
    const chatPanel = wrapper.findComponent({ name: 'AiChatPanel' })
    expect(chatPanel.exists()).toBe(true)

    // Check that useSmartScroll prop is passed as true
    expect(chatPanel.props('useSmartScroll')).toBe(true)
    // Check that processGroups prop is defined (Map instance)
    expect(chatPanel.props('processGroups')).toBeDefined()
  })

  it('chatStream connects with correct parameters on session creation', async () => {
    const api = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Create a session
    const newSessionBtn = wrapper.findAll('button').find(
      (b) => b.text().includes('New Session'),
    )
    await newSessionBtn!.trigger('click')
    await flushPromises()

    // Verify chatStream was called with proper args
    expect(api.superAgentSessionApi.chatStream).toHaveBeenCalledWith(
      'super-abc123',
      'sess-new',
    )
  })

  // --- 37-04: MessageActions tests ---

  it('renders MessageActions on messages after processing completes', async () => {
    const { wrapper } = await setupWithMessage(mountComponent, 'Hello')

    // MessageActions renders .message-actions container
    // After SSE finish, isProcessing is false, so actions should be visible
    const actions = wrapper.findAll('.message-actions')
    expect(actions.length).toBeGreaterThanOrEqual(1)
  })

  it('copy message calls clipboard API', async () => {
    // Mock clipboard API
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextMock },
      writable: true,
      configurable: true,
    })
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      writable: true,
      configurable: true,
    })

    const { wrapper } = await setupWithMessage(mountComponent, 'Copy me')

    // Find the first copy button (action-btn) in message actions
    const actionBtns = wrapper.findAll('.action-btn')
    expect(actionBtns.length).toBeGreaterThanOrEqual(1)

    // Click the first action button (copy message)
    await actionBtns[0].trigger('click')
    await flushPromises()

    expect(writeTextMock).toHaveBeenCalledWith('Copy me')
  })

  it('export conversation generates download', async () => {
    // Mock URL.createObjectURL and revokeObjectURL
    const createObjectURLMock = vi.fn().mockReturnValue('blob:test-url')
    const revokeObjectURLMock = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectURLMock,
      revokeObjectURL: revokeObjectURLMock,
    })

    // Track created <a> elements
    const clickMock = vi.fn()
    const origCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreateElement(tag)
      if (tag === 'a') {
        el.click = clickMock
      }
      return el
    })

    const { wrapper } = await setupWithMessage(mountComponent, 'Export me')

    // Find export buttons -- the last message has allMessages prop,
    // so its MessageActions has 3 buttons: copy, copy-all, export
    const allActionBtns = wrapper.findAll('.action-btn')
    expect(allActionBtns.length).toBeGreaterThanOrEqual(3)

    // The export button (download icon) is the last one
    const exportBtn = allActionBtns[allActionBtns.length - 1]
    await exportBtn.trigger('click')
    await flushPromises()

    // Verify download was triggered
    expect(createObjectURLMock).toHaveBeenCalled()
    expect(clickMock).toHaveBeenCalled()
    expect(revokeObjectURLMock).toHaveBeenCalled()

    vi.restoreAllMocks()
  })
})
