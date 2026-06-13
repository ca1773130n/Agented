import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

const mockStartResearch = vi.fn();
const mockResumeThread = vi.fn();
const mockStreamResearch = vi.fn();

// A fake AuthenticatedEventSource: records listeners + close calls.
interface FakeSource {
  listeners: Record<string, ((e: Event) => void)[]>;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: (() => void) | null;
  closed: boolean;
  addEventListener: (type: string, cb: (e: Event) => void) => void;
  close: () => void;
  emit: (type: string, data: unknown) => void;
}

function makeFakeSource(): FakeSource {
  const src: FakeSource = {
    listeners: {},
    onmessage: null,
    onerror: null,
    closed: false,
    addEventListener(type, cb) {
      (this.listeners[type] ||= []).push(cb);
    },
    close() {
      this.closed = true;
    },
    emit(type, data) {
      const evt = { data: JSON.stringify(data) } as MessageEvent;
      if (type === 'message' && this.onmessage) this.onmessage(evt);
      (this.listeners[type] || []).forEach((cb) => cb(evt as unknown as Event));
    },
  };
  return src;
}

vi.mock('../../services/api/research', () => ({
  researchApi: {
    startResearch: (...a: unknown[]) => mockStartResearch(...a),
    resumeThread: (...a: unknown[]) => mockResumeThread(...a),
    streamResearch: (...a: unknown[]) => mockStreamResearch(...a),
  },
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useResearchSession } from '../useResearchSession';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useResearchSession', () => {
  const projectId = ref('proj-abc');

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts a research run, subscribes to the SSE stream, and buffers output', async () => {
    const fake = makeFakeSource();
    mockStartResearch.mockResolvedValue({ session_id: 'sess-1' });
    mockStreamResearch.mockReturnValue(fake);

    const s = useResearchSession(projectId);
    await s.start('why is the sky blue?', { max_iterations: 3 });

    expect(mockStartResearch).toHaveBeenCalledWith('proj-abc', 'why is the sky blue?', {
      max_iterations: 3,
    });
    expect(s.sessionId.value).toBe('sess-1');
    expect(mockStreamResearch).toHaveBeenCalledWith('proj-abc', 'sess-1');

    fake.emit('output', { line: 'iteration 1' });
    expect(s.outputLines.value).toContain('iteration 1');
  });

  it('marks status complete and closes the source on the complete event', async () => {
    const fake = makeFakeSource();
    mockStartResearch.mockResolvedValue({ session_id: 'sess-2' });
    mockStreamResearch.mockReturnValue(fake);

    const s = useResearchSession(projectId);
    await s.start('q');

    fake.emit('complete', { exit_code: 0 });
    expect(s.status.value).toBe('complete');
    expect(s.exitCode.value).toBe(0);
    expect(fake.closed).toBe(true);
  });

  it('surfaces a structured question event as waiting_input', async () => {
    const fake = makeFakeSource();
    mockStartResearch.mockResolvedValue({ session_id: 'sess-3' });
    mockStreamResearch.mockReturnValue(fake);

    const s = useResearchSession(projectId);
    await s.start('q');

    fake.emit('question', { interaction_id: 'int-1', prompt: 'pick one', question_type: 'text' });
    expect(s.status.value).toBe('waiting_input');
    expect(s.currentQuestion.value?.prompt).toBe('pick one');
  });

  it('resumes an existing thread via resumeThread', async () => {
    const fake = makeFakeSource();
    mockResumeThread.mockResolvedValue({ session_id: 'sess-4' });
    mockStreamResearch.mockReturnValue(fake);

    const s = useResearchSession(projectId);
    await s.resume('thread-x');

    expect(mockResumeThread).toHaveBeenCalledWith('proj-abc', 'thread-x', undefined);
    expect(s.threadId.value).toBe('thread-x');
    expect(s.sessionId.value).toBe('sess-4');
  });

  it('records an error when startResearch rejects', async () => {
    mockStartResearch.mockRejectedValue(new Error('boom'));

    const s = useResearchSession(projectId);
    await s.start('q');

    expect(s.status.value).toBe('error');
    expect(s.error.value).toBe('boom');
  });

  it('clearOutput resets to idle and closes the source', async () => {
    const fake = makeFakeSource();
    mockStartResearch.mockResolvedValue({ session_id: 'sess-5' });
    mockStreamResearch.mockReturnValue(fake);

    const s = useResearchSession(projectId);
    await s.start('q');
    s.clearOutput();

    expect(s.status.value).toBe('idle');
    expect(s.outputLines.value).toEqual([]);
    expect(s.sessionId.value).toBeNull();
  });
});
