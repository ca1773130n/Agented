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
});
