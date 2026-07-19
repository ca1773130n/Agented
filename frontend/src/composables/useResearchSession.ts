import { ref, onUnmounted, type Ref } from 'vue';
import { researchApi } from '../services/api/research';
import type { StartResearchOptions } from '../services/api/research';
import type { AuthenticatedEventSource } from '../services/api/client';

export type ResearchStatus = 'idle' | 'running' | 'waiting_input' | 'complete' | 'error';

export interface ResearchQuestion {
  interaction_id: string;
  question_type: 'text' | 'password' | 'select' | 'multiselect';
  prompt: string;
  options?: string[];
}

/**
 * Composable for managing a GRD autoresearch session lifecycle: spawning the
 * ``gd research`` loop, SSE-streaming its live output, surfacing interactive
 * questions, and tracking status.
 *
 * Mirrors usePlanningSession.ts (the createAuthenticatedEventSource +
 * .addEventListener 'output'|'question'|'complete'|'error' + cleanup pattern).
 * A research session is a normal PSM session, so its live output streams over
 * the generic ``/sessions/{id}/stream`` SSE via ``researchApi.streamResearch``.
 */
export function useResearchSession(projectId: Ref<string>) {
  // Public reactive state
  const sessionId = ref<string | null>(null);
  const threadId = ref<string | null>(null);
  const outputLines = ref<string[]>([]);
  const status = ref<ResearchStatus>('idle');
  const currentQuestion = ref<ResearchQuestion | null>(null);
  const exitCode = ref<number | null>(null);
  const error = ref<string | null>(null);

  // Private state
  let eventSource: AuthenticatedEventSource | null = null;
  let errorCount = 0;
  const MAX_ERRORS = 3;

  /**
   * Start a research run for ``question``. Calls researchApi.startResearch,
   * then subscribes to the resulting session's SSE stream.
   */
  async function start(question: string, opts?: StartResearchOptions) {
    try {
      status.value = 'running';
      error.value = null;
      exitCode.value = null;
      currentQuestion.value = null;

      const result = await researchApi.startResearch(projectId.value, question, opts);
      sessionId.value = result.session_id;
      connectSSE();
    } catch (e) {
      status.value = 'error';
      const message = e instanceof Error ? e.message : 'Failed to start research';
      error.value = message;
      outputLines.value.push(`[error] ${message}`);
    }
  }

  /**
   * Resume an existing research thread (the thread carries its own question).
   * ``opts.answers`` (GRD 0.5.0) resolves a pending checkpoint — one entry per
   * checkpoint question — and is forwarded to ``researchApi.resumeThread``.
   */
  async function resume(thread: string, opts?: StartResearchOptions) {
    try {
      status.value = 'running';
      error.value = null;
      exitCode.value = null;
      currentQuestion.value = null;
      threadId.value = thread;

      const result = await researchApi.resumeThread(projectId.value, thread, opts);
      sessionId.value = result.session_id;
      connectSSE();
    } catch (e) {
      status.value = 'error';
      const message = e instanceof Error ? e.message : 'Failed to resume research';
      error.value = message;
      outputLines.value.push(`[error] ${message}`);
    }
  }

  /**
   * Connect to the SSE stream for the active research session.
   * Handles output, question, complete, and error events.
   */
  function connectSSE() {
    closeEventSource();
    errorCount = 0;

    if (!sessionId.value) return;

    eventSource = researchApi.streamResearch(projectId.value, sessionId.value);

    // Default message event: push line/output content to the buffer
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

    // Question event: structured question prompt from the research session
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
        error.value = msg;
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
        error.value = 'Connection lost after retries';
        outputLines.value.push('[error] Connection lost after retries');
        closeEventSource();
      }
      // Otherwise let EventSource auto-reconnect
    };
  }

  /**
   * Clear all output and reset to idle state.
   */
  function clearOutput() {
    outputLines.value = [];
    status.value = 'idle';
    currentQuestion.value = null;
    exitCode.value = null;
    error.value = null;
    sessionId.value = null;
    threadId.value = null;
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
    threadId,
    outputLines,
    status,
    currentQuestion,
    exitCode,
    error,
    start,
    resume,
    clearOutput,
  };
}
