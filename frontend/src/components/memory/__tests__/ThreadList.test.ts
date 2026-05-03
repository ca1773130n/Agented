import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a :href="hrefStr"><slot /></a>',
  computed: {
    hrefStr(this: { to: unknown }) {
      const t = this.to;
      if (typeof t === 'string') return t;
      const params = (t as { params?: { thread_id?: string } })?.params;
      return params?.thread_id ? `/threads/${params.thread_id}` : '#';
    },
  },
};

vi.mock('vue-router', () => ({
  RouterLink: RouterLinkStub,
}));

vi.mock('../../../services/api/agentMemory', () => ({
  agentMemoryApi: { listThreads: vi.fn() },
}));

import { agentMemoryApi } from '../../../services/api/agentMemory';
import ThreadList from '../ThreadList.vue';

const sampleThreads = [
  {
    id: 'thread-1', resource_id: 'agent-01', resource_type: 'agent',
    title: 'planning chat', created_at: '2026-05-04T10:00:00Z',
    updated_at: '2026-05-04T11:00:00Z',
  },
  {
    id: 'thread-2', resource_id: 'agent-01', resource_type: 'agent',
    title: null, created_at: '2026-05-04T09:00:00Z',
    updated_at: '2026-05-04T09:30:00Z',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  (agentMemoryApi.listThreads as ReturnType<typeof vi.fn>).mockResolvedValue({
    threads: sampleThreads,
    total: 2,
  });
});

describe('ThreadList', () => {
  it('fetches threads on mount', async () => {
    mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(agentMemoryApi.listThreads).toHaveBeenCalledWith(
      'agent-01',
      expect.objectContaining({ limit: 50, offset: 0 }),
    );
  });

  it('renders one row per thread', async () => {
    const wrapper = mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.findAll('[data-testid="thread-row"]')).toHaveLength(2);
  });

  it('shows "(untitled)" for null titles', async () => {
    const wrapper = mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.text()).toContain('(untitled)');
  });

  it('row link points at the thread detail route', async () => {
    const wrapper = mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    const link = wrapper.findAll('[data-testid="thread-row"] a').at(0);
    expect(link?.attributes('href')).toContain('thread-1');
  });

  it('shows empty state when no threads', async () => {
    (agentMemoryApi.listThreads as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      threads: [], total: 0,
    });
    const wrapper = mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="thread-list-empty"]').exists()).toBe(true);
  });

  it('exposes refresh() on the instance for parent-driven refetch', async () => {
    const wrapper = mount(ThreadList, {
      props: { agentId: 'agent-01' },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(agentMemoryApi.listThreads).toHaveBeenCalledTimes(1);
    // The component exposes refresh via defineExpose; tests use vm.refresh().
    await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh();
    expect(agentMemoryApi.listThreads).toHaveBeenCalledTimes(2);
  });
});
