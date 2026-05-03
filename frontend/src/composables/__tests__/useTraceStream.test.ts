import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref, nextTick } from 'vue';

// Capture the EventSource instances the composable creates.
const eventSources: Array<{
  url: string;
  listeners: Map<string, ((e: MessageEvent) => void)[]>;
  close: () => void;
}> = [];

vi.mock('../../services/api/tracing', () => ({
  tracingApi: {
    stream: vi.fn((traceId: string) => {
      const listeners = new Map<string, ((e: MessageEvent) => void)[]>();
      const stub = {
        url: `/admin/traces/${traceId}/stream`,
        listeners,
        readyState: 0,
        addEventListener(type: string, fn: (e: MessageEvent) => void) {
          if (!listeners.has(type)) listeners.set(type, []);
          listeners.get(type)!.push(fn);
        },
        removeEventListener(type: string, fn: (e: MessageEvent) => void) {
          const arr = listeners.get(type);
          if (arr) listeners.set(type, arr.filter((f) => f !== fn));
        },
        close: vi.fn(),
      };
      eventSources.push({
        url: stub.url,
        listeners,
        close: stub.close,
      });
      return stub;
    }),
  },
}));

import { useTraceStream } from '../useTraceStream';

beforeEach(() => {
  eventSources.length = 0;
  vi.clearAllMocks();
});

describe('useTraceStream', () => {
  it('start() opens an SSE connection to the trace stream URL', () => {
    const traceId = ref('trace-abc');
    const { start } = useTraceStream(traceId);
    start();
    expect(eventSources).toHaveLength(1);
    expect(eventSources[0].url).toBe('/admin/traces/trace-abc/stream');
  });

  it('span_started events accumulate in events ref', async () => {
    const traceId = ref('t1');
    const { events, start } = useTraceStream(traceId);
    start();
    const span = { id: 'span-1', name: 'Root', status: 'running' };
    const handlers = eventSources[0].listeners.get('span_started')!;
    handlers[0](new MessageEvent('span_started', { data: JSON.stringify(span) }));
    await nextTick();
    expect(events.value).toHaveLength(1);
    expect(events.value[0]).toEqual({ kind: 'span_started', span });
  });

  it('trace_ended event appends + auto-stops the stream', async () => {
    const traceId = ref('t1');
    const { events, status, start } = useTraceStream(traceId);
    start();
    const trace = { id: 't1', status: 'completed' };
    eventSources[0].listeners.get('trace_ended')![0](
      new MessageEvent('trace_ended', { data: JSON.stringify(trace) }),
    );
    await nextTick();
    expect(events.value.at(-1)).toEqual({ kind: 'trace_ended', trace });
    expect(status.value).toBe('closed');
    expect(eventSources[0].close).toHaveBeenCalled();
  });

  it('stop() closes the underlying EventSource', () => {
    const traceId = ref('t1');
    const { stop, start } = useTraceStream(traceId);
    start();
    stop();
    expect(eventSources[0].close).toHaveBeenCalled();
  });

  it('non-JSON event data is ignored without crashing', async () => {
    const traceId = ref('t1');
    const { events, start } = useTraceStream(traceId);
    start();
    eventSources[0].listeners.get('span_started')![0](
      new MessageEvent('span_started', { data: 'not-json' }),
    );
    await nextTick();
    expect(events.value).toHaveLength(0);
  });
});
