import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MessageInbox from '../MessageInbox.vue'

const mockInboxMessages = [
  {
    id: 'msg-aaa111',
    from_agent_id: 'super-peer01',
    to_agent_id: 'super-test01',
    message_type: 'message',
    priority: 'high',
    subject: 'Urgent task',
    content: 'Please review the deployment changes before we merge.',
    status: 'delivered',
    created_at: '2026-02-16T10:00:00Z',
  },
  {
    id: 'msg-bbb222',
    from_agent_id: 'super-peer02',
    to_agent_id: 'super-test01',
    message_type: 'message',
    priority: 'normal',
    subject: 'Status update',
    content: 'All tests are passing on the staging branch now.',
    status: 'read',
    created_at: '2026-02-16T09:00:00Z',
  },
]

const mockOutboxMessages = [
  {
    id: 'msg-ccc333',
    from_agent_id: 'super-test01',
    to_agent_id: 'super-peer01',
    message_type: 'message',
    priority: 'normal',
    subject: 'Re: Urgent task',
    content: 'Will review shortly.',
    status: 'delivered',
    created_at: '2026-02-16T10:05:00Z',
  },
]

const mockEventSource = {
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  close: vi.fn(),
  onmessage: null as ((event: MessageEvent) => void) | null,
  onerror: null as ((event: Event) => void) | null,
  onopen: null as (() => void) | null,
  queueDepth: 0,
}

vi.mock('../../../services/api', () => ({
  agentMessageApi: {
    listInbox: vi.fn().mockResolvedValue({ messages: [] }),
    listOutbox: vi.fn().mockResolvedValue({ messages: [] }),
    markRead: vi.fn().mockResolvedValue({ message: 'OK' }),
    send: vi.fn().mockResolvedValue({ message: 'Sent', message_id: 'msg-new123' }),
  },
  superAgentApi: {
    list: vi.fn().mockResolvedValue({ super_agents: [] }),
  },
  API_BASE: '',
  createAuthenticatedEventSource: vi.fn(() => mockEventSource),
}))

describe('MessageInbox', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(MessageInbox, {
      props: {
        superAgentId: 'super-test01',
      },
      global: {
        provide: {
          showToast: mockShowToast,
        },
        stubs: {
          SendMessageForm: true,
        },
      },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    mockEventSource.addEventListener.mockReset()
    mockEventSource.close.mockReset()
    const { agentMessageApi, createAuthenticatedEventSource } = await import('../../../services/api')
    vi.mocked(createAuthenticatedEventSource).mockReturnValue(mockEventSource as any)
    vi.mocked(agentMessageApi.listInbox).mockResolvedValue({ messages: mockInboxMessages as any })
    vi.mocked(agentMessageApi.listOutbox).mockResolvedValue({ messages: mockOutboxMessages as any })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders inbox tab by default', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const toggleBtns = wrapper.findAll('.toggle-btn')
    const inboxBtn = toggleBtns.find(b => b.text().includes('Inbox'))
    expect(inboxBtn?.classes()).toContain('active')

    const outboxBtn = toggleBtns.find(b => b.text().includes('Outbox'))
    expect(outboxBtn?.classes()).not.toContain('active')
  })

  it('loads inbox messages on mount', async () => {
    const { agentMessageApi } = await import('../../../services/api')
    mountComponent()
    await flushPromises()

    expect(agentMessageApi.listInbox).toHaveBeenCalledWith('super-test01')
  })

  it('toggles between inbox and outbox', async () => {
    const { agentMessageApi } = await import('../../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    const toggleBtns = wrapper.findAll('.toggle-btn')
    const outboxBtn = toggleBtns.find(b => b.text().includes('Outbox'))
    await outboxBtn!.trigger('click')
    await flushPromises()

    expect(outboxBtn!.classes()).toContain('active')
    // Outbox was already loaded on mount via loadAll
    expect(agentMessageApi.listOutbox).toHaveBeenCalledWith('super-test01')
  })

  it('renders message cards with sender and subject', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const cards = wrapper.findAll('.message-card')
    expect(cards.length).toBe(2)

    expect(wrapper.text()).toContain('super-peer01')
    expect(wrapper.text()).toContain('Urgent task')
    expect(wrapper.text()).toContain('super-peer02')
    expect(wrapper.text()).toContain('Status update')
  })

  it('shows priority badge for high priority messages', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const highBadge = wrapper.find('.priority-high')
    expect(highBadge.exists()).toBe(true)
    expect(highBadge.text()).toBe('high')
  })

  it('opens send form when New Message clicked', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.findComponent({ name: 'SendMessageForm' }).exists()).toBe(false)

    const newMsgBtn = wrapper.find('.new-message-btn')
    await newMsgBtn.trigger('click')
    await flushPromises()

    // SendMessageForm is stubbed but should be rendered now
    expect(wrapper.find('.send-form-overlay').exists()).toBe(true)
  })

  it('connects EventSource on mount', async () => {
    mountComponent()
    await flushPromises()

    const { createAuthenticatedEventSource } = await import('../../../services/api')
    expect(createAuthenticatedEventSource).toHaveBeenCalledWith('/admin/super-agents/super-test01/messages/stream')
  })

  it('closes EventSource on unmount', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    wrapper.unmount()
    expect(mockEventSource.close).toHaveBeenCalled()
  })

  it('shows unread badge count on inbox toggle', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const badge = wrapper.find('.unread-badge')
    expect(badge.exists()).toBe(true)
    // 1 message is 'delivered' (unread), 1 is 'read'
    expect(badge.text()).toBe('1')
  })

  it('shows empty state when no messages', async () => {
    const { agentMessageApi } = await import('../../../services/api')
    vi.mocked(agentMessageApi.listInbox).mockResolvedValue({ messages: [] })
    vi.mocked(agentMessageApi.listOutbox).mockResolvedValue({ messages: [] })

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No messages yet')
  })

  it('displays status dots with correct classes', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.status-delivered').exists()).toBe(true)
    expect(wrapper.find('.status-read').exists()).toBe(true)
  })
})
