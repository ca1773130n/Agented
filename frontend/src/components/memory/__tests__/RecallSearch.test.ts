import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a :href="hrefStr"><slot /></a>',
    computed: {
      hrefStr() {
        const t = (this as unknown as { to: unknown }).to;
        if (typeof t === 'string') return t;
        const params = (t as { params?: { thread_id?: string } })?.params;
        return params?.thread_id ? `/threads/${params.thread_id}` : '#';
      },
    },
  },
}));

vi.mock('../../../services/api/agentMemory', () => ({
  agentMemoryApi: { recall: vi.fn() },
}));

import { agentMemoryApi } from '../../../services/api/agentMemory';
import RecallSearch from '../RecallSearch.vue';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('RecallSearch', () => {
  it('shows empty state and does not call API on mount', () => {
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    expect(wrapper.find('[data-testid="recall-empty"]').exists()).toBe(true);
    expect(agentMemoryApi.recall).not.toHaveBeenCalled();
  });

  it('submitting empty query does not call API', async () => {
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    await wrapper.find('form').trigger('submit.prevent');
    expect(agentMemoryApi.recall).not.toHaveBeenCalled();
  });

  it('submit calls recall with query + topK', async () => {
    (agentMemoryApi.recall as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      results: [], count: 0, query: 'hello', search_mode: 'fts', relevance_score: 0,
    });
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    await wrapper.find('[data-testid="recall-input"]').setValue('hello');
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    expect(agentMemoryApi.recall).toHaveBeenCalledWith('agent-01', 'hello', 5);
  });

  it('renders results list with one row per result', async () => {
    (agentMemoryApi.recall as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      results: [
        { id: 'm1', thread_id: 't1', role: 'user', content: 'hello world', created_at: '2026-05-04T00:00:00Z' },
        { id: 'm2', thread_id: 't2', role: 'assistant', content: 'hi there', created_at: '2026-05-04T00:00:01Z' },
      ],
      count: 2, query: 'hello', search_mode: 'fts', relevance_score: 1,
    });
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    await wrapper.find('[data-testid="recall-input"]').setValue('hello');
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    const rows = wrapper.findAll('[data-testid="recall-result"]');
    expect(rows).toHaveLength(2);
  });

  it('shows no-match state when results array is empty after search', async () => {
    (agentMemoryApi.recall as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      results: [], count: 0, query: 'nope', search_mode: 'fts', relevance_score: 0,
    });
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    await wrapper.find('[data-testid="recall-input"]').setValue('nope');
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    expect(wrapper.find('[data-testid="recall-no-matches"]').exists()).toBe(true);
  });

  it('top_k select changes the topK arg passed to recall', async () => {
    (agentMemoryApi.recall as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      results: [], count: 0, query: 'x', search_mode: 'fts', relevance_score: 0,
    });
    const wrapper = mount(RecallSearch, { props: { agentId: 'agent-01' } });
    await wrapper.find('[data-testid="recall-input"]').setValue('x');
    await wrapper.find('[data-testid="recall-topk"]').setValue('20');
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    expect(agentMemoryApi.recall).toHaveBeenCalledWith('agent-01', 'x', 20);
  });
});
