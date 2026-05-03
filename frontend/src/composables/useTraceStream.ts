import { ref, watch, onUnmounted, type Ref, type Readonly } from 'vue';
import { tracingApi, type TraceSpan, type Trace } from '../services/api/tracing';

export type TraceStreamEvent =
  | { kind: 'span_started'; span: TraceSpan }
  | { kind: 'span_ended'; span: TraceSpan }
  | { kind: 'trace_ended'; trace: Trace }
  | { kind: 'error'; reason: string }
  | { kind: 'timeout'; reason: string };

export type TraceStreamStatus =
  | 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseTraceStreamReturn {
  events: Readonly<Ref<TraceStreamEvent[]>>;
  status: Readonly<Ref<TraceStreamStatus>>;
  start: () => void;
  stop: () => void;
}

export function useTraceStream(traceId: Ref<string>): UseTraceStreamReturn {
  const events = ref<TraceStreamEvent[]>([]);
  const status = ref<TraceStreamStatus>('idle');
  let source: ReturnType<typeof tracingApi.stream> | null = null;

  function stop() {
    if (source) {
      source.close();
      source = null;
    }
    status.value = 'closed';
  }

  function start() {
    stop();
    status.value = 'connecting';
    source = tracingApi.stream(traceId.value);
    source.addEventListener('span_started', (e) => {
      try {
        const span = JSON.parse((e as MessageEvent).data);
        events.value = [...events.value, { kind: 'span_started', span }];
      } catch { /* ignore non-JSON */ }
    });
    source.addEventListener('span_ended', (e) => {
      try {
        const span = JSON.parse((e as MessageEvent).data);
        events.value = [...events.value, { kind: 'span_ended', span }];
      } catch { /* ignore non-JSON */ }
    });
    source.addEventListener('trace_ended', (e) => {
      try {
        const trace = JSON.parse((e as MessageEvent).data);
        events.value = [...events.value, { kind: 'trace_ended', trace }];
        stop();
      } catch { /* ignore */ }
    });
    source.addEventListener('error', () => {
      events.value = [...events.value, { kind: 'error', reason: 'sse_error' }];
      status.value = 'error';
    });
    status.value = 'open';
  }

  // Stop the stream when traceId changes (caller switches traces).
  watch(traceId, () => stop());

  onUnmounted(stop);

  return {
    events: events as Readonly<Ref<TraceStreamEvent[]>>,
    status: status as Readonly<Ref<TraceStreamStatus>>,
    start,
    stop,
  };
}
