import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'agent-01', thread_id: 'thread-1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot/></a>' },
}));

vi.mock('../../services/api/agentMemory', () => ({
  agentMemoryApi: {
    getThread: vi.fn(),
    getMessages: vi.fn(),
  },
}));

import { agentMemoryApi } from '../../services/api/agentMemory';
import ThreadDetailPage from '../ThreadDetailPage.vue';

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a><slot/></a>',
};

beforeEach(() => {
  vi.clearAllMocks();
  (agentMemoryApi.getThread as ReturnType<typeof vi.fn>).mockResolvedValue({
    id: 'thread-1', resource_id: 'agent-01', resource_type: 'agent',
    title: 'planning chat', created_at: '2026-05-04T10:00:00Z',
    updated_at: '2026-05-04T10:00:00Z', message_count: 2,
  });
  (agentMemoryApi.getMessages as ReturnType<typeof vi.fn>).mockResolvedValue({
    messages: [
      { id: 'm1', thread_id: 'thread-1', role: 'user', content: 'hello', created_at: '2026-05-04T10:00:00Z' },
      { id: 'm2', thread_id: 'thread-1', role: 'assistant', content: 'hi', created_at: '2026-05-04T10:00:01Z' },
    ],
    total: 2,
  });
});

describe('ThreadDetailPage', () => {
  it('fetches thread + messages on mount', async () => {
    mount(ThreadDetailPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(agentMemoryApi.getThread).toHaveBeenCalledWith('agent-01', 'thread-1');
    expect(agentMemoryApi.getMessages).toHaveBeenCalledWith('agent-01', 'thread-1');
  });

  it('renders thread header with title', async () => {
    const wrapper = mount(ThreadDetailPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.text()).toContain('planning chat');
  });

  it('renders the messages list with 2 rows', async () => {
    const wrapper = mount(ThreadDetailPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.findAll('[data-testid="message-row"]')).toHaveLength(2);
  });

  it('renders "(untitled)" when thread title is null', async () => {
    (agentMemoryApi.getThread as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 'thread-1', resource_id: 'agent-01', resource_type: 'agent',
      title: null, created_at: '2026-05-04', updated_at: '2026-05-04', message_count: 0,
    });
    (agentMemoryApi.getMessages as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      messages: [], total: 0,
    });
    const wrapper = mount(ThreadDetailPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.text()).toContain('(untitled)');
  });

  it('shows error state when thread fetch fails', async () => {
    (agentMemoryApi.getThread as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('not found'),
    );
    const wrapper = mount(ThreadDetailPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="thread-detail-error"]').exists()).toBe(true);
  });
});
