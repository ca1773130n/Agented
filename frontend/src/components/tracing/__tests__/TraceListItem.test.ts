import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';

const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a :href="hrefStr" data-testid="router-link"><slot/></a>',
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

import TraceListItem from '../TraceListItem.vue';
import type { Trace } from '../../../services/api/tracing';

function makeTrace(overrides: Partial<Trace> = {}): Trace {
  return {
    id: 'trace-abc',
    name: 'agent-run',
    entity_type: 'agent',
    entity_id: 'agent-01',
    status: 'running',
    started_at: '2026-05-03T12:00:00Z',
    finished_at: null,
    duration_ms: null,
    ...overrides,
  };
}

describe('TraceListItem', () => {
  it('renders trace name + entity ref + status', () => {
    const wrapper = mount(TraceListItem, {
      props: { trace: makeTrace() },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    expect(wrapper.text()).toContain('agent-run');
    expect(wrapper.text()).toContain('agent:agent-01');
    expect(wrapper.find('[data-testid="trace-status"]').text()).toBe('running');
  });

  it('shows duration in ms when available', () => {
    const wrapper = mount(TraceListItem, {
      props: { trace: makeTrace({ status: 'completed', duration_ms: 1234 }) },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    expect(wrapper.find('[data-testid="trace-duration"]').text()).toContain('1234');
  });

  it('shows "running" indicator when no duration yet', () => {
    const wrapper = mount(TraceListItem, {
      props: { trace: makeTrace() },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    expect(wrapper.find('[data-testid="trace-duration"]').text().toLowerCase())
      .toContain('running');
  });

  it('renders a RouterLink whose href carries the trace id', () => {
    const wrapper = mount(TraceListItem, {
      props: { trace: makeTrace({ id: 'trace-xyz' }) },
      global: { components: { RouterLink: RouterLinkStub } },
    });
    const link = wrapper.find('[data-testid="router-link"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes('href')).toContain('trace-xyz');
  });
});
