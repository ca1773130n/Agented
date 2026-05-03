import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a :href="hrefStr"><slot/></a>',
  computed: {
    hrefStr(this: { to: unknown }) {
      const t = this.to as { params?: { id?: string } } | string;
      if (typeof t === 'string') return t;
      return t?.params?.id ?? JSON.stringify(t);
    },
  },
};

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: RouterLinkStub,
}));

vi.mock('../../services/api/tracing', () => ({
  tracingApi: {
    list: vi.fn(),
    stats: vi.fn(),
    get: vi.fn(),
    stream: vi.fn(),
  },
}));

import { tracingApi } from '../../services/api/tracing';
import TracesPage from '../TracesPage.vue';

beforeEach(() => {
  vi.clearAllMocks();
  (tracingApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
    traces: [
      { id: 't1', name: 'first', entity_type: 'agent', entity_id: 'a1', status: 'completed', started_at: '2026-05-03T00:00:00Z', finished_at: '2026-05-03T00:00:01Z', duration_ms: 1000 },
      { id: 't2', name: 'second', entity_type: 'team', entity_id: 'tm1', status: 'running', started_at: '2026-05-03T00:00:02Z', finished_at: null, duration_ms: null },
    ],
    total: 2,
  });
  (tracingApi.stats as ReturnType<typeof vi.fn>).mockResolvedValue({
    total_traces: 2,
    completed: 1,
    errors: 0,
  });
});

describe('TracesPage', () => {
  it('renders the trace list after loading', async () => {
    const wrapper = mount(TracesPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.text()).toContain('first');
    expect(wrapper.text()).toContain('second');
  });

  it('shows aggregate stats in the header', async () => {
    const wrapper = mount(TracesPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    const header = wrapper.find('[data-testid="stats-header"]');
    expect(header.exists()).toBe(true);
    expect(header.text()).toContain('2');  // total
    expect(header.text()).toContain('1');  // completed
  });

  it('status filter dropdown re-fetches with status param', async () => {
    const wrapper = mount(TracesPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    const select = wrapper.find('[data-testid="status-filter"]');
    await select.setValue('error');
    await flushPromises();
    const lastCall = (tracingApi.list as ReturnType<typeof vi.fn>).mock.calls.at(-1);
    expect(lastCall![0]).toMatchObject({ status: 'error' });
  });

  it('empty state when traces array is empty', async () => {
    (tracingApi.list as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ traces: [], total: 0 });
    const wrapper = mount(TracesPage, {
      global: { components: { RouterLink: RouterLinkStub } },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(true);
  });
});
