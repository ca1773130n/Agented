import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'trace-1' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { name: 'RouterLink', props: ['to'], template: '<a :href="to"><slot/></a>' },
}));

const eventSourceListeners = new Map<string, ((e: MessageEvent) => void)[]>();
const closeFn = vi.fn();

vi.mock('../../services/api/tracing', () => ({
  tracingApi: {
    get: vi.fn(),
    list: vi.fn(),
    stats: vi.fn(),
    stream: vi.fn(() => ({
      addEventListener: (type: string, fn: (e: MessageEvent) => void) => {
        if (!eventSourceListeners.has(type)) eventSourceListeners.set(type, []);
        eventSourceListeners.get(type)!.push(fn);
      },
      removeEventListener: vi.fn(),
      close: closeFn,
      readyState: 1,
    })),
  },
}));

import { tracingApi } from '../../services/api/tracing';
import TraceDetailPage from '../TraceDetailPage.vue';

beforeEach(() => {
  vi.clearAllMocks();
  eventSourceListeners.clear();
  closeFn.mockClear();
});

describe('TraceDetailPage', () => {
  it('fetches the trace + spans on mount and renders the header', async () => {
    (tracingApi.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      trace: {
        id: 'trace-1',
        name: 'agent-run',
        entity_type: 'agent',
        entity_id: 'agent-01',
        status: 'completed',
        started_at: '2026-05-03T00:00:00Z',
        finished_at: '2026-05-03T00:00:01Z',
        duration_ms: 1000,
      },
      spans: [
        { id: 'span-1', trace_id: 'trace-1', parent_span_id: null, name: 'Root', span_type: 'AGENT_RUN', status: 'completed', started_at: '2026-05-03T00:00:00Z', finished_at: '2026-05-03T00:00:01Z', duration_ms: 1000 },
      ],
    });
    const wrapper = mount(TraceDetailPage);
    await flushPromises();
    expect(wrapper.text()).toContain('agent-run');
    expect(wrapper.text()).toContain('Root');
  });

  it('builds a tree from parent_span_id and renders nested SpanTreeNode entries', async () => {
    (tracingApi.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      trace: {
        id: 'trace-1', name: 't', entity_type: 'agent', entity_id: 'a',
        status: 'completed', started_at: '2026-05-03T00:00:00Z',
        finished_at: '2026-05-03T00:00:01Z', duration_ms: 1000,
      },
      spans: [
        { id: 'p', trace_id: 'trace-1', parent_span_id: null, name: 'parent', span_type: 'X', status: 'completed', started_at: '2026-05-03T00:00:00Z', finished_at: '2026-05-03T00:00:01Z', duration_ms: 1000 },
        { id: 'c', trace_id: 'trace-1', parent_span_id: 'p', name: 'child', span_type: 'Y', status: 'completed', started_at: '2026-05-03T00:00:00Z', finished_at: '2026-05-03T00:00:01Z', duration_ms: 500 },
      ],
    });
    const wrapper = mount(TraceDetailPage);
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain('parent');
    expect(text).toContain('child');
  });

  it('does not open SSE when trace is already completed', async () => {
    (tracingApi.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      trace: {
        id: 'trace-1', name: 't', entity_type: 'agent', entity_id: 'a',
        status: 'completed', started_at: '2026-05-03T00:00:00Z',
        finished_at: '2026-05-03T00:00:01Z', duration_ms: 1000,
      },
      spans: [],
    });
    mount(TraceDetailPage);
    await flushPromises();
    expect((tracingApi.stream as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  });

  it('opens SSE and patches a new span when trace is running', async () => {
    (tracingApi.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      trace: {
        id: 'trace-1', name: 't', entity_type: 'agent', entity_id: 'a',
        status: 'running', started_at: '2026-05-03T00:00:00Z',
        finished_at: null, duration_ms: null,
      },
      spans: [],
    });
    const wrapper = mount(TraceDetailPage);
    await flushPromises();
    expect((tracingApi.stream as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
    // Simulate a span_started event arriving on the stream.
    const newSpan = {
      id: 'live-span', trace_id: 'trace-1', parent_span_id: null,
      name: 'mid-run', span_type: 'AGENT_RUN', status: 'running',
      started_at: '2026-05-03T00:00:01Z', finished_at: null, duration_ms: null,
    };
    eventSourceListeners.get('span_started')![0](
      new MessageEvent('span_started', { data: JSON.stringify(newSpan) }),
    );
    await flushPromises();
    expect(wrapper.text()).toContain('mid-run');
  });
});
