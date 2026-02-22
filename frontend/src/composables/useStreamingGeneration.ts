import { ref } from 'vue';

export interface StreamLogEntry {
  type: string;
  text: string;
}

export function useStreamingGeneration() {
  const log = ref<StreamLogEntry[]>([]);
  const phase = ref('');
  const isStreaming = ref(false);

  function reset() {
    log.value = [];
    phase.value = '';
    isStreaming.value = false;
  }

  async function startStream<T = any>(
    url: string,
    body: Record<string, any>,
  ): Promise<T | null> {
    reset();
    isStreaming.value = true;
    phase.value = 'Starting...';

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: 'Unknown error' }));
        log.value.push({ type: 'error', text: err.error || `HTTP ${response.status}` });
        return null;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        log.value.push({ type: 'error', text: 'Streaming not supported' });
        return null;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let resultData: T | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let eventType = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7);
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          } else if (line === '' && eventType && eventData) {
            try {
              const data = JSON.parse(eventData);

              if (eventType === 'phase') {
                phase.value = data.message;
                log.value.push({ type: 'phase', text: data.message });
              } else if (eventType === 'thinking') {
                log.value.push({ type: 'thinking', text: data.content });
              } else if (eventType === 'output') {
                log.value.push({ type: 'output', text: data.content });
              } else if (eventType === 'result') {
                log.value.push({ type: 'phase', text: 'Complete!' });
                resultData = data as T;
              } else if (eventType === 'error') {
                log.value.push({ type: 'error', text: data.error });
              }
            } catch {
              // ignore malformed JSON
            }
            eventType = '';
            eventData = '';
          }
        }
      }

      return resultData;
    } catch (e) {
      log.value.push({ type: 'error', text: 'Connection failed' });
      return null;
    } finally {
      isStreaming.value = false;
    }
  }

  return { log, phase, isStreaming, startStream, reset };
}
