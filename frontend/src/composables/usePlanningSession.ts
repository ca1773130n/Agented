import { ref, onUnmounted, type Ref } from 'vue';
import { grdApi } from '../services/api/grd';
import type { AuthenticatedEventSource } from '../services/api/client';

export interface PlanningQuestion {
  interaction_id: string;
  question_type: 'text' | 'password' | 'select' | 'multiselect';
  prompt: string;
  options?: string[];
}

/**
 * Composable for managing planning session lifecycle, SSE streaming,
 * input sending, and status tracking.
 *
 * Follows the same PTY/SSE patterns as useProjectSession.ts and
 * InteractiveSetup.vue but tailored for GRD planning commands.
 */
export function usePlanningSession(projectId: Ref<string>) {
  // Public reactive state
  const sessionId = ref<string | null>(null);
  const outputLines = ref<string[]>([]);
  const status = ref<'idle' | 'running' | 'waiting_input' | 'complete' | 'error'>('idle');
  const currentQuestion = ref<PlanningQuestion | null>(null);
  const exitCode = ref<number | null>(null);

  // Private state
  let eventSource: AuthenticatedEventSource | null = null;
  let errorCount = 0;
  const MAX_ERRORS = 3;

  /**
   * Invoke a planning command (e.g., 'init', 'create-milestone').
   * Calls the backend, starts SSE streaming on success.
   */
  async function invokeCommand(command: string, args?: Record<string, string>) {
    try {
      status.value = 'running';
      exitCode.value = null;
      currentQuestion.value = null;

      const result = await grdApi.invokePlanningCommand(projectId.value, command, args);
      sessionId.value = result.session_id;
      connectSSE();
    } catch (e) {
      status.value = 'error';
      const message = e instanceof Error ? e.message : 'Failed to invoke planning command';
      outputLines.value.push(`[error] ${message}`);
    }
  }

  /**
   * Connect to the SSE stream for the active planning session.
   * Handles output, question, complete, and error events.
   */
  function connectSSE() {
    closeEventSource();
    errorCount = 0;

    if (!sessionId.value) return;

    eventSource = grdApi.streamSession(projectId.value, sessionId.value);

    // Default message event: push line content to output
    eventSource.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.line != null) {
          outputLines.value.push(data.line);
        } else if (data.output != null) {
          outputLines.value.push(data.output);
        }
      } catch {
        // Ignore parse errors for non-JSON messages
      }
    };

    // Output event: push line content
    eventSource.addEventListener('output', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (data.line != null) {
          outputLines.value.push(data.line);
        }
      } catch {
        // Ignore parse errors
      }
    });

    // Question event: structured question prompt from the AI session
    eventSource.addEventListener('question', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        if (data.interaction_id && data.prompt) {
          currentQuestion.value = {
            interaction_id: data.interaction_id,
            question_type: data.question_type || 'text',
            prompt: data.prompt,
            options: data.options,
          };
          status.value = 'waiting_input';
        }
      } catch {
        // Ignore parse errors
      }
    });

    // Complete event: session finished
    eventSource.addEventListener('complete', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        exitCode.value = data.exit_code ?? null;
      } catch {
        // Ignore parse errors
      }
      status.value = 'complete';
      closeEventSource();
    });

    // Error event (named SSE event, not EventSource.onerror)
    eventSource.addEventListener('error', (event: Event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data);
        const msg = data.error_message || data.message || 'Session error';
        outputLines.value.push(`[error] ${msg}`);
      } catch {
        // Ignore parse errors
      }
      status.value = 'error';
      closeEventSource();
    });

    // EventSource connection error handler
    eventSource.onerror = () => {
      errorCount++;
      if (errorCount >= MAX_ERRORS) {
        status.value = 'error';
        outputLines.value.push('[error] Connection lost after retries');
        closeEventSource();
      }
      // Otherwise let EventSource auto-reconnect
    };
  }

  /**
   * Send an answer to a pending question in the active session.
   */
  async function sendAnswer(answer: string) {
    if (!sessionId.value) return;
    try {
      await grdApi.sendInput(projectId.value, sessionId.value, answer + '\n');
      currentQuestion.value = null;
      status.value = 'running';
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to send answer';
      outputLines.value.push(`[error] ${message}`);
    }
  }

  /**
   * Stop the active planning session.
   */
  async function stopSession() {
    if (!sessionId.value) return;
    try {
      await grdApi.stopSession(projectId.value, sessionId.value);
    } catch {
      // Best-effort stop
    }
    closeEventSource();
    status.value = 'idle';
  }

  /**
   * Clear all output and reset to idle state.
   */
  function clearOutput() {
    outputLines.value = [];
    status.value = 'idle';
    currentQuestion.value = null;
    exitCode.value = null;
    sessionId.value = null;
  }

  /**
   * Close the EventSource connection.
   */
  function closeEventSource() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  // Cleanup on component unmount to prevent connection leaks
  onUnmounted(closeEventSource);

  return {
    sessionId,
    outputLines,
    status,
    currentQuestion,
    exitCode,
    invokeCommand,
    sendAnswer,
    stopSession,
    clearOutput,
  };
}
