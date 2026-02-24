import { ref, onUnmounted, type Ref } from 'vue';
import {
  grdApi,
  type GrdSession,
  type CreateSessionRequest,
  type RalphConfig,
  type TeamConfig,
} from '../services/api/grd';

/**
 * Composable for managing project session lifecycle, SSE streaming,
 * and session CRUD operations.
 *
 * Follows the same patterns as useAiChat.ts but tailored for PTY-based
 * project sessions with output/complete/error SSE events.
 */
export function useProjectSession(projectId: Ref<string>) {
  // Public state
  const sessions = ref<GrdSession[]>([]);
  const activeSessionId = ref<string | null>(null);
  const isStreaming = ref(false);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  // Ralph loop state
  const ralphState = ref<{
    iteration: number;
    maxIterations: number;
    circuitBreakerTriggered: boolean;
  } | null>(null);

  // Team spawn state
  const teamState = ref<{
    teamName: string | null;
    members: Array<{ name: string; agentId: string; agentType: string }>;
    tasks: Array<{ id: string; subject: string; status: string; owner?: string }>;
  } | null>(null);

  // Private state
  let eventSource: EventSource | null = null;
  let errorCount = 0;

  // Callback registrations
  let onOutputCb: ((line: string) => void) | undefined;
  let onCompleteCb: ((status: string, exitCode: number) => void) | undefined;
  let onErrorCb: ((message: string) => void) | undefined;

  /**
   * Load all sessions for the current project.
   */
  async function loadSessions() {
    try {
      const result = await grdApi.listSessions(projectId.value);
      sessions.value = result.sessions || [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load sessions';
    }
  }

  /**
   * Create a new session and connect to its SSE stream.
   */
  async function startSession(request: CreateSessionRequest) {
    isLoading.value = true;
    error.value = null;
    try {
      const result = await grdApi.createSession(projectId.value, request);
      activeSessionId.value = result.session_id;
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to start session';
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Create a new Ralph loop session and connect to its SSE stream.
   */
  async function startRalphSession(config: RalphConfig) {
    isLoading.value = true;
    error.value = null;
    ralphState.value = {
      iteration: 0,
      maxIterations: config.max_iterations,
      circuitBreakerTriggered: false,
    };
    try {
      const result = await grdApi.createRalphSession(projectId.value, {
        ralph_config: config,
      });
      activeSessionId.value = result.session_id;
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start Ralph session';
      ralphState.value = null;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Create a new Team Spawn session and connect to its SSE stream.
   */
  async function startTeamSession(config: TeamConfig) {
    isLoading.value = true;
    error.value = null;
    teamState.value = { teamName: null, members: [], tasks: [] };
    try {
      const result = await grdApi.createTeamSession(projectId.value, {
        team_config: config,
      });
      activeSessionId.value = result.session_id;
      teamState.value = {
        teamName: result.team_name,
        members: [],
        tasks: [],
      };
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start team session';
      teamState.value = null;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Connect to the SSE stream for a session.
   * Always closes any existing stream first to prevent connection leaks.
   */
  function connectStream(sessionId: string) {
    closeStream();
    isStreaming.value = true;
    errorCount = 0;

    eventSource = grdApi.streamSession(projectId.value, sessionId);

    eventSource.addEventListener('output', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        onOutputCb?.(data.line);
      } catch (e) {
        console.warn('[useProjectSession] Failed to parse output event:', e, (event as MessageEvent).data);
      }
    });

    eventSource.addEventListener('complete', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        isStreaming.value = false;
        // Update session status in local list
        const idx = sessions.value.findIndex((s) => s.id === sessionId);
        if (idx !== -1) {
          sessions.value[idx] = { ...sessions.value[idx], status: data.status };
        }
        onCompleteCb?.(data.status, data.exit_code);
      } catch (e) {
        console.warn('[useProjectSession] Failed to parse complete event:', e, (event as MessageEvent).data);
      }
    });

    eventSource.onerror = () => {
      errorCount++;
      if (errorCount >= 3) {
        closeStream();
        error.value = 'Connection lost';
        onErrorCb?.('Connection lost after 3 retries');
      }
    };

    // Ralph iteration progress
    eventSource.addEventListener('ralph_iteration', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        ralphState.value = {
          iteration: data.iteration ?? 0,
          maxIterations: data.max_iterations ?? 0,
          circuitBreakerTriggered: false,
        };
      } catch (e) {
        console.warn('[useProjectSession] Failed to parse ralph_iteration event:', e, (event as MessageEvent).data);
      }
    });

    // Circuit breaker event
    eventSource.addEventListener('circuit_breaker', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (ralphState.value) {
          ralphState.value.circuitBreakerTriggered = true;
        }
        onErrorCb?.(`Circuit breaker: ${data.reason}`);
      } catch (e) {
        console.warn('[useProjectSession] Failed to parse circuit_breaker event:', e, (event as MessageEvent).data);
      }
    });

    // Team update events
    eventSource.addEventListener('team_update', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (data.type === 'config') {
          teamState.value = {
            ...(teamState.value || { teamName: null, members: [], tasks: [] }),
            teamName: data.data?.team_name || teamState.value?.teamName || null,
            members: data.data?.members || teamState.value?.members || [],
          };
        } else if (data.type === 'task') {
          if (!teamState.value) {
            teamState.value = { teamName: null, members: [], tasks: [] };
          }
          // Upsert task in array
          const taskIdx = teamState.value.tasks.findIndex(
            (t) => t.id === data.data?.id,
          );
          if (taskIdx >= 0) {
            teamState.value.tasks[taskIdx] = data.data;
          } else if (data.data) {
            teamState.value.tasks.push(data.data);
          }
        }
      } catch (e) {
        console.warn('[useProjectSession] Failed to parse team_update event:', e, (event as MessageEvent).data);
      }
    });
  }

  /**
   * Send text input to the active session's PTY stdin.
   */
  async function sendInput(text: string) {
    if (!activeSessionId.value) return;
    try {
      await grdApi.sendInput(projectId.value, activeSessionId.value, text);
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to send input';
    }
  }

  /**
   * Stop the active session.
   */
  async function stopSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.stopSession(projectId.value, activeSessionId.value);
      closeStream();
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to stop session';
    }
  }

  /**
   * Pause the active session.
   */
  async function pauseSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.pauseSession(projectId.value, activeSessionId.value);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to pause session';
    }
  }

  /**
   * Resume the active session and re-establish SSE connection.
   */
  async function resumeSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.resumeSession(projectId.value, activeSessionId.value);
      connectStream(activeSessionId.value);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to resume session';
    }
  }

  /**
   * Switch to a different session. Closes existing stream and reconnects
   * if the target session is active or paused.
   */
  function switchSession(sessionId: string) {
    activeSessionId.value = sessionId;
    closeStream();
    ralphState.value = null;
    teamState.value = null;
    const session = sessions.value.find((s) => s.id === sessionId);
    if (session && (session.status === 'active' || session.status === 'paused')) {
      connectStream(sessionId);
    }
  }

  /**
   * Close the current SSE connection.
   */
  function closeStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    isStreaming.value = false;
    ralphState.value = null;
    teamState.value = null;
  }

  // Callback setters
  function onOutput(cb: (line: string) => void) {
    onOutputCb = cb;
  }

  function onComplete(cb: (status: string, exitCode: number) => void) {
    onCompleteCb = cb;
  }

  function onError(cb: (message: string) => void) {
    onErrorCb = cb;
  }

  // Cleanup on unmount
  onUnmounted(closeStream);

  return {
    // State
    sessions,
    activeSessionId,
    isStreaming,
    isLoading,
    error,
    ralphState,
    teamState,
    // Methods
    loadSessions,
    startSession,
    startRalphSession,
    startTeamSession,
    connectStream,
    sendInput,
    stopSession,
    pauseSession,
    resumeSession,
    switchSession,
    closeStream,
    // Callback setters
    onOutput,
    onComplete,
    onError,
  };
}
