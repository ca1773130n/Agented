import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
//
// Mirror the existing useProjectSession.test.ts harness: grdApi + vue are
// mocked the same way, and useEventSource is mocked so the composable's
// ``events`` map (the SSE handler table) is captured. Tests then drive the
// captured handlers directly with synthetic ``{ data }`` MessageEvents to
// simulate the SSE stream firing a control event.
// ---------------------------------------------------------------------------

vi.mock('../../services/api/grd', () => ({
  grdApi: {
    listSessions: vi.fn(),
    createSession: vi.fn(),
    createRalphSession: vi.fn(),
    createTeamSession: vi.fn(),
    sendInput: vi.fn(),
    stopSession: vi.fn(),
    pauseSession: vi.fn(),
    resumeSession: vi.fn(),
    streamSession: vi.fn(),
  },
}));

// Capture the events map handed to useEventSource so tests can fire SSE
// events at the composable's handlers.
let capturedEvents: Record<string, (event: MessageEvent) => void> = {};

vi.mock('../useEventSource', () => ({
  useEventSource: (opts: { events?: Record<string, (event: MessageEvent) => void> }) => {
    capturedEvents = opts.events ?? {};
    return {
      connect: vi.fn(),
      close: vi.fn(),
      getSource: vi.fn().mockReturnValue(null),
      status: ref('idle'),
    };
  },
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useProjectSession } from '../useProjectSession';

const fire = (type: string, payload: unknown) => {
  capturedEvents[type]?.({ data: JSON.stringify(payload) } as MessageEvent);
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useProjectSession — control SSE events', () => {
  let session: ReturnType<typeof useProjectSession>;
  const projectId = ref('proj-abc');

  beforeEach(() => {
    vi.clearAllMocks();
    capturedEvents = {};
    session = useProjectSession(projectId);
  });

  it('starts with paused/awaitingHuman cleared', () => {
    expect(session.paused.value).toBe(false);
    expect(session.awaitingHuman.value).toBe(false);
    expect(session.gateReason.value).toBeNull();
  });

  it('goal_loop_paused sets the paused ref', () => {
    fire('goal_loop_paused', { iteration: 2 });
    expect(session.paused.value).toBe(true);
  });

  it('goal_loop_resumed clears the paused ref', () => {
    fire('goal_loop_paused', { iteration: 2 });
    fire('goal_loop_resumed', { iteration: 2 });
    expect(session.paused.value).toBe(false);
  });

  it('goal_loop_awaiting_human sets awaitingHuman + gateReason', () => {
    fire('goal_loop_awaiting_human', { iteration: 4, gate_reason: 'every 2 iterations' });
    expect(session.awaitingHuman.value).toBe(true);
    expect(session.gateReason.value).toBe('every 2 iterations');
  });

  it('goal_loop_gate_resolved clears awaitingHuman + gateReason', () => {
    fire('goal_loop_awaiting_human', { iteration: 4, gate_reason: 'every 2 iterations' });
    fire('goal_loop_gate_resolved', { decision: 'continue' });
    expect(session.awaitingHuman.value).toBe(false);
    expect(session.gateReason.value).toBeNull();
  });

  it('goal_loop_intervened forwards an operator note toast via onIntervened', () => {
    const seen: string[] = [];
    session.onIntervened((note) => seen.push(note));
    fire('goal_loop_intervened', { message: 'focus on the parser' });
    expect(seen).toEqual(['focus on the parser']);
  });
});
