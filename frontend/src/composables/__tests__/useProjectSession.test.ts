import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

const mockListSessions = vi.fn();
const mockCreateSession = vi.fn();
const mockCreateRalphSession = vi.fn();
const mockCreateTeamSession = vi.fn();
const mockSendInput = vi.fn();
const mockStopSession = vi.fn();
const mockPauseSession = vi.fn();
const mockResumeSession = vi.fn();
const mockStreamSession = vi.fn();

vi.mock('../../services/api/grd', () => ({
  grdApi: {
    listSessions: (...a: unknown[]) => mockListSessions(...a),
    createSession: (...a: unknown[]) => mockCreateSession(...a),
    createRalphSession: (...a: unknown[]) => mockCreateRalphSession(...a),
    createTeamSession: (...a: unknown[]) => mockCreateTeamSession(...a),
    sendInput: (...a: unknown[]) => mockSendInput(...a),
    stopSession: (...a: unknown[]) => mockStopSession(...a),
    pauseSession: (...a: unknown[]) => mockPauseSession(...a),
    resumeSession: (...a: unknown[]) => mockResumeSession(...a),
    streamSession: (...a: unknown[]) => mockStreamSession(...a),
  },
}));

const mockSseConnect = vi.fn();
const mockSseClose = vi.fn();

vi.mock('../useEventSource', () => ({
  useEventSource: () => ({
    connect: mockSseConnect,
    close: mockSseClose,
    getSource: vi.fn().mockReturnValue(null),
    status: ref('idle'),
  }),
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useProjectSession } from '../useProjectSession';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useProjectSession', () => {
  let session: ReturnType<typeof useProjectSession>;
  const projectId = ref('proj-abc');

  beforeEach(() => {
    vi.clearAllMocks();
    session = useProjectSession(projectId);
  });

  // -----------------------------------------------------------------------
  // Initial state
  // -----------------------------------------------------------------------
  describe('initial state', () => {
    it('has empty sessions list', () => {
      expect(session.sessions.value).toEqual([]);
    });

    it('has no active session', () => {
      expect(session.activeSessionId.value).toBeNull();
    });

    it('is not streaming', () => {
      expect(session.isStreaming.value).toBe(false);
    });

    it('has no error', () => {
      expect(session.error.value).toBeNull();
    });

    it('has null ralph and team state', () => {
      expect(session.ralphState.value).toBeNull();
      expect(session.teamState.value).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // loadSessions
  // -----------------------------------------------------------------------
  describe('loadSessions', () => {
    it('populates sessions list on success', async () => {
      const sessions = [{ id: 'sess-1', status: 'active' }];
      mockListSessions.mockResolvedValue({ sessions });

      await session.loadSessions();

      expect(session.sessions.value).toEqual(sessions);
      expect(mockListSessions).toHaveBeenCalledWith('proj-abc');
    });

    it('defaults to empty array when sessions key is missing', async () => {
      mockListSessions.mockResolvedValue({});

      await session.loadSessions();

      expect(session.sessions.value).toEqual([]);
    });

    it('sets error on failure', async () => {
      mockListSessions.mockRejectedValue(new Error('Network error'));

      await session.loadSessions();

      expect(session.error.value).toBe('Network error');
    });

    it('sets generic error for non-Error throws', async () => {
      mockListSessions.mockRejectedValue('boom');

      await session.loadSessions();

      expect(session.error.value).toBe('Failed to load sessions');
    });
  });

  // -----------------------------------------------------------------------
  // startSession
  // -----------------------------------------------------------------------
  describe('startSession', () => {
    it('creates session, sets active id, and connects stream', async () => {
      mockCreateSession.mockResolvedValue({ session_id: 'sess-new' });
      mockListSessions.mockResolvedValue({ sessions: [] });

      await session.startSession({ cmd: ['claude'] });

      expect(session.activeSessionId.value).toBe('sess-new');
      expect(mockSseConnect).toHaveBeenCalled();
      expect(session.isLoading.value).toBe(false);
    });

    it('sets error on failure', async () => {
      mockCreateSession.mockRejectedValue(new Error('Create failed'));

      await session.startSession({ cmd: ['claude'] });

      expect(session.error.value).toBe('Create failed');
      expect(session.isLoading.value).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // startRalphSession
  // -----------------------------------------------------------------------
  describe('startRalphSession', () => {
    const ralphConfig = {
      max_iterations: 5,
      completion_promise: 'done',
      task_description: 'test',
      no_progress_threshold: 3,
    };

    it('creates ralph session and sets active session id', async () => {
      mockCreateRalphSession.mockResolvedValue({ session_id: 'sess-ralph' });
      mockListSessions.mockResolvedValue({ sessions: [] });

      await session.startRalphSession(ralphConfig);

      expect(session.activeSessionId.value).toBe('sess-ralph');
      expect(mockSseConnect).toHaveBeenCalled();
      expect(session.isLoading.value).toBe(false);
    });

    it('clears ralph state on failure', async () => {
      mockCreateRalphSession.mockRejectedValue(new Error('Ralph failed'));

      await session.startRalphSession(ralphConfig);

      expect(session.error.value).toBe('Ralph failed');
      expect(session.ralphState.value).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // startTeamSession
  // -----------------------------------------------------------------------
  describe('startTeamSession', () => {
    const teamConfig = {
      team_size: 3,
      task_description: 'build feature',
      roles: ['developer', 'reviewer'],
    };

    it('creates team session and sets active session id', async () => {
      mockCreateTeamSession.mockResolvedValue({
        session_id: 'sess-team',
        team_name: 'Alpha',
      });
      mockListSessions.mockResolvedValue({ sessions: [] });

      await session.startTeamSession(teamConfig);

      expect(session.activeSessionId.value).toBe('sess-team');
      expect(mockSseConnect).toHaveBeenCalled();
      expect(session.isLoading.value).toBe(false);
    });

    it('clears team state on failure', async () => {
      mockCreateTeamSession.mockRejectedValue(new Error('Team failed'));

      await session.startTeamSession(teamConfig);

      expect(session.error.value).toBe('Team failed');
      expect(session.teamState.value).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // sendInput
  // -----------------------------------------------------------------------
  describe('sendInput', () => {
    it('does nothing when no active session', async () => {
      await session.sendInput('hello');

      expect(mockSendInput).not.toHaveBeenCalled();
    });

    it('sends input to active session', async () => {
      session.activeSessionId.value = 'sess-1';
      mockSendInput.mockResolvedValue({});

      await session.sendInput('hello');

      expect(mockSendInput).toHaveBeenCalledWith('proj-abc', 'sess-1', 'hello');
    });

    it('sets error on failure', async () => {
      session.activeSessionId.value = 'sess-1';
      mockSendInput.mockRejectedValue(new Error('Send failed'));

      await session.sendInput('hello');

      expect(session.error.value).toBe('Send failed');
    });
  });

  // -----------------------------------------------------------------------
  // stopSession
  // -----------------------------------------------------------------------
  describe('stopSession', () => {
    it('does nothing when no active session', async () => {
      await session.stopSession();

      expect(mockStopSession).not.toHaveBeenCalled();
    });

    it('stops session and closes stream', async () => {
      session.activeSessionId.value = 'sess-1';
      mockStopSession.mockResolvedValue({});
      mockListSessions.mockResolvedValue({ sessions: [] });

      await session.stopSession();

      expect(mockStopSession).toHaveBeenCalledWith('proj-abc', 'sess-1');
      expect(mockSseClose).toHaveBeenCalled();
    });

    it('sets error on failure', async () => {
      session.activeSessionId.value = 'sess-1';
      mockStopSession.mockRejectedValue(new Error('Stop failed'));

      await session.stopSession();

      expect(session.error.value).toBe('Stop failed');
    });
  });

  // -----------------------------------------------------------------------
  // pauseSession / resumeSession
  // -----------------------------------------------------------------------
  describe('pauseSession', () => {
    it('sets error on failure', async () => {
      session.activeSessionId.value = 'sess-1';
      mockPauseSession.mockRejectedValue(new Error('Pause failed'));

      await session.pauseSession();

      expect(session.error.value).toBe('Pause failed');
    });
  });

  describe('resumeSession', () => {
    it('resumes session and reconnects stream', async () => {
      session.activeSessionId.value = 'sess-1';
      mockResumeSession.mockResolvedValue({});
      mockListSessions.mockResolvedValue({ sessions: [] });

      await session.resumeSession();

      expect(mockResumeSession).toHaveBeenCalledWith('proj-abc', 'sess-1');
      expect(mockSseConnect).toHaveBeenCalled();
    });

    it('sets error on failure', async () => {
      session.activeSessionId.value = 'sess-1';
      mockResumeSession.mockRejectedValue(new Error('Resume failed'));

      await session.resumeSession();

      expect(session.error.value).toBe('Resume failed');
    });
  });

  // -----------------------------------------------------------------------
  // switchSession
  // -----------------------------------------------------------------------
  describe('switchSession', () => {
    it('switches to session and connects if session is active', () => {
      session.sessions.value = [
        { id: 'sess-1', status: 'active' } as any,
        { id: 'sess-2', status: 'completed' } as any,
      ];

      session.switchSession('sess-1');

      expect(session.activeSessionId.value).toBe('sess-1');
      expect(mockSseConnect).toHaveBeenCalled();
    });

    it('does not connect stream for completed session', () => {
      session.sessions.value = [{ id: 'sess-2', status: 'completed' } as any];

      session.switchSession('sess-2');

      expect(session.activeSessionId.value).toBe('sess-2');
      // Close is called (to close previous), but connect should not be called
      // after the close from switchSession's initial closeStream()
      expect(mockSseConnect).not.toHaveBeenCalled();
    });

    it('resets ralph and team state', () => {
      session.ralphState.value = { iteration: 1, maxIterations: 5, circuitBreakerTriggered: false };
      session.teamState.value = { teamName: 'A', members: [], tasks: [] };

      session.switchSession('sess-3');

      expect(session.ralphState.value).toBeNull();
      expect(session.teamState.value).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // closeStream
  // -----------------------------------------------------------------------
  describe('closeStream', () => {
    it('closes SSE and resets streaming state', () => {
      session.isStreaming.value = true;
      session.ralphState.value = { iteration: 1, maxIterations: 5, circuitBreakerTriggered: false };

      session.closeStream();

      expect(mockSseClose).toHaveBeenCalled();
      expect(session.isStreaming.value).toBe(false);
      expect(session.ralphState.value).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // Callback setters
  // -----------------------------------------------------------------------
  describe('callback setters', () => {
    it('registers onOutput, onComplete, and onError callbacks', () => {
      // These should not throw
      session.onOutput(() => {});
      session.onComplete(() => {});
      session.onError(() => {});
    });
  });
});
