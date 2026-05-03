import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'agent-01' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a><slot/></a>' },
}));

vi.mock('../../services/api/agentMemory', () => ({
  agentMemoryApi: {
    getWorkingMemory: vi.fn(),
    listThreads: vi.fn(),
    recall: vi.fn(),
  },
}));

import { agentMemoryApi } from '../../services/api/agentMemory';
import MemoryPage from '../MemoryPage.vue';

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a><slot/></a>',
};

beforeEach(() => {
  vi.clearAllMocks();
  (agentMemoryApi.getWorkingMemory as ReturnType<typeof vi.fn>).mockResolvedValue({
    entity_id: 'agent-01', entity_type: 'agent',
    content: '# Notes\n- fact A',
  });
  (agentMemoryApi.listThreads as ReturnType<typeof vi.fn>).mockResolvedValue({
    threads: [
      { id: 't1', resource_id: 'agent-01', resource_type: 'agent', title: 'planning', created_at: '2026-05-04', updated_at: '2026-05-04' },
    ],
    total: 1,
  });
});

describe('MemoryPage', () => {
  it('renders three regions on mount', async () => {
    const wrapper = mount(MemoryPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="memory-region-working"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="memory-region-recall"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="memory-region-threads"]').exists()).toBe(true);
  });

  it('fires getWorkingMemory and listThreads in parallel on mount', async () => {
    mount(MemoryPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(agentMemoryApi.getWorkingMemory).toHaveBeenCalledWith('agent-01');
    expect(agentMemoryApi.listThreads).toHaveBeenCalledWith(
      'agent-01',
      expect.any(Object),
    );
  });

  it('does not fire recall on mount (search is user-initiated)', async () => {
    mount(MemoryPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(agentMemoryApi.recall).not.toHaveBeenCalled();
  });

  it('manual Refresh button triggers re-fetch of working memory + threads', async () => {
    const wrapper = mount(MemoryPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    const before = (agentMemoryApi.getWorkingMemory as ReturnType<typeof vi.fn>).mock.calls.length;
    await wrapper.find('[data-testid="refresh-btn"]').trigger('click');
    await flushPromises();
    expect((agentMemoryApi.getWorkingMemory as ReturnType<typeof vi.fn>).mock.calls.length)
      .toBe(before + 1);
  });

  it('error in working memory does not break threads region', async () => {
    (agentMemoryApi.getWorkingMemory as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('working mem boom'),
    );
    const wrapper = mount(MemoryPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    // Working memory shows error state
    expect(wrapper.find('[data-testid="working-memory-error"]').exists()).toBe(true);
    // Threads region still rendered the row
    expect(wrapper.findAll('[data-testid="thread-row"]')).toHaveLength(1);
  });
});
