import { ref, onUnmounted } from 'vue';
import type { Ref } from 'vue';
import type { Sketch, Project, ConversationMessage, Delegation } from '../services/api/types';
import { sketchApi, projectApi, isAbortError, superAgentSessionApi } from '../services/api';
import type { AuthenticatedEventSource } from '../services/api';

/**
 * Parse a JSON block from a string (e.g. a JSON field value).
 * Returns the parsed value on success, or null on parse failure.
 */
function parseJsonBlock(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function useSketchChat() {
  const sketches: Ref<Sketch[]> = ref([]);
  const currentSketch: Ref<Sketch | null> = ref(null);
  const selectedProjectId: Ref<string | null> = ref(null);
  const projects: Ref<Project[]> = ref([]);
  const isProcessing: Ref<boolean> = ref(false);
  const messages: Ref<ConversationMessage[]> = ref([]);
  const error: Ref<string | null> = ref(null);
  const streamingContent = ref('');
  const isStreaming = ref(false);
  const executionSessionId = ref<string | null>(null);
  const executionSuperAgentId = ref<string | null>(null);
  const delegations = ref<Delegation[]>([]);
  let eventSource: AuthenticatedEventSource | null = null;
  let delegationPollTimer: ReturnType<typeof setInterval> | null = null;

  // AbortController for cancelling pending requests on unmount or re-execute
  let abortController = new AbortController();

  async function loadProjects() {
    try {
      const result = await projectApi.list();
      if (abortController.signal.aborted) return;
      projects.value = result.projects;
    } catch (e: unknown) {
      if (isAbortError(e) || abortController.signal.aborted) return;
      error.value = e instanceof Error ? e.message : 'Failed to load projects';
    }
  }

  async function loadSketches() {
    try {
      const params: { project_id?: string } = {};
      if (selectedProjectId.value) {
        params.project_id = selectedProjectId.value;
      }
      const result = await sketchApi.list(params);
      if (abortController.signal.aborted) return;
      sketches.value = result.sketches;
    } catch (e: unknown) {
      if (isAbortError(e) || abortController.signal.aborted) return;
      error.value = e instanceof Error ? e.message : 'Failed to load sketches';
    }
  }

  async function loadDelegations(sketchId: string) {
    try {
      const result = await sketchApi.getDelegations(sketchId);
      delegations.value = result.delegations;
    } catch (e: unknown) {
      if (isAbortError(e) || abortController.signal.aborted) return;
      // Silently fail — polling will retry
    }
  }

  function stopDelegationPolling() {
    if (delegationPollTimer) {
      clearInterval(delegationPollTimer);
      delegationPollTimer = null;
    }
  }

  function startDelegationPolling(sketchId: string) {
    stopDelegationPolling();
    // Initial load
    loadDelegations(sketchId);
    // Poll every 3 seconds
    delegationPollTimer = setInterval(async () => {
      await loadDelegations(sketchId);
      // Stop when all delegations are completed or errored
      const allDone =
        delegations.value.length > 0 &&
        delegations.value.every(d => d.status === 'completed' || d.status === 'error');
      if (allDone) {
        stopDelegationPolling();
        // Refresh sketch status
        const updated = await sketchApi.get(sketchId);
        currentSketch.value = updated;
      }
    }, 3000);
  }

  async function submitSketch(text: string) {
    isProcessing.value = true;
    error.value = null;

    messages.value.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });

    try {
      const createResult = await sketchApi.create({
        title: text.slice(0, 100),
        content: text,
        project_id: selectedProjectId.value ?? undefined,
      });

      const sketchId = createResult.sketch_id;

      await sketchApi.classify(sketchId);
      if (abortController.signal.aborted) return;

      const fetched = await sketchApi.get(sketchId);
      if (abortController.signal.aborted) return;

      let classificationSummary = 'Sketch created and classified.';
      if (fetched.classification_json) {
        const cls = parseJsonBlock(fetched.classification_json) as Record<string, unknown> | null;
        if (cls) {
          const parts: string[] = [];
          if (cls.phase) parts.push(`Phase: ${cls.phase}`);
          if (cls.domains && (cls.domains as unknown[]).length) parts.push(`Domains: ${(cls.domains as string[]).join(', ')}`);
          if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
          if (cls.confidence != null) parts.push(`Confidence: ${Math.round((cls.confidence as number) * 100)}%`);
          if (parts.length) classificationSummary = parts.join(' | ');
        }
      }

      messages.value.push({
        role: 'assistant',
        content: classificationSummary,
        timestamp: new Date().toISOString(),
      });

      currentSketch.value = fetched;
      await loadSketches();

      // Auto-route after classification
      messages.value.push({
        role: 'system',
        content: 'Routing...',
        timestamp: new Date().toISOString(),
      });
      await routeSketch(sketchId);
    } catch (e: unknown) {
      if (isAbortError(e) || abortController.signal.aborted) return;
      const errMsg = e instanceof Error ? e.message : 'Failed to create or classify sketch';
      error.value = errMsg;
      messages.value.push({
        role: 'assistant',
        content: `Error: ${errMsg}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      if (!abortController.signal.aborted) {
        isProcessing.value = false;
      }
    }
  }

  async function routeSketch(sketchId: string) {
    try {
      isProcessing.value = true;
      error.value = null;

      const routeResult = await sketchApi.route(sketchId);

      // Fetch updated sketch
      const updatedSketch = await sketchApi.get(sketchId);
      currentSketch.value = updatedSketch;

      // Parse routing info
      const routing = routeResult.routing || routeResult;
      const routingMsg: ConversationMessage = {
        role: 'system',
        content: `Routed to: ${routing.target_type} (${routing.target_id || 'none'})\nReason: ${routing.reason || 'N/A'}`,
        timestamp: new Date().toISOString(),
      };
      messages.value.push(routingMsg);

      // If execution started, open SSE stream
      const sessionId = routeResult.session_id;
      const superAgentId = routeResult.super_agent_id;

      if (sessionId && superAgentId) {
        executionSessionId.value = sessionId;
        executionSuperAgentId.value = superAgentId;
        streamingContent.value = '';
        isStreaming.value = true;

        // Add placeholder assistant message
        const assistantMsg: ConversationMessage = {
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
        };
        messages.value.push(assistantMsg);
        const msgIndex = messages.value.length - 1;

        // Open SSE connection (state_delta protocol — same as Playground)
        eventSource = superAgentSessionApi.chatStream(superAgentId, sessionId);

        // All events arrive as 'state_delta' with type in JSON data
        eventSource.addEventListener('state_delta', (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            switch (data.type) {
              case 'content_delta':
                streamingContent.value += data.content || '';
                messages.value[msgIndex].content = streamingContent.value;
                break;
              case 'finish':
                isStreaming.value = false;
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                // Check for delegations (team collaboration)
                startDelegationPolling(sketchId);
                break;
              case 'error':
                isStreaming.value = false;
                error.value = 'Streaming error occurred. You can retry by routing again.';
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                break;
            }
          } catch {
            // Ignore unparseable events
          }
        });

        eventSource.onerror = async () => {
          if (isStreaming.value) {
            // Check if the sketch actually completed before showing an error
            try {
              const sketch = await sketchApi.get(sketchId);
              if (sketch.status === 'completed' || sketch.status === 'collaborating') {
                // Sketch finished — SSE just disconnected after completion
                isStreaming.value = false;
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                startDelegationPolling(sketchId);
                return;
              }
            } catch {
              // If we can't check status, fall through to error
            }
            isStreaming.value = false;
            error.value = 'Connection lost. You can retry by routing again.';
            if (eventSource) {
              eventSource.close();
              eventSource = null;
            }
          }
        };
      } else if (routing.target_type === 'none') {
        messages.value.push({
          role: 'system',
          content: 'No matching agent found. Assign a team with super agents to this project first.',
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Failed to route sketch';
      error.value = errMsg;
    } finally {
      isProcessing.value = false;
    }
  }

  function selectSketch(sketch: Sketch) {
    currentSketch.value = sketch;
    messages.value = [];

    // Rebuild messages from sketch data
    messages.value.push({
      role: 'user',
      content: sketch.content || sketch.title,
      timestamp: sketch.created_at || new Date().toISOString(),
    });

    if (sketch.classification_json) {
      const cls = parseJsonBlock(sketch.classification_json) as Record<string, unknown> | null;
      if (cls) {
        const parts: string[] = [];
        if (cls.phase) parts.push(`Phase: ${cls.phase}`);
        if (cls.domains && (cls.domains as unknown[]).length) parts.push(`Domains: ${(cls.domains as string[]).join(', ')}`);
        if (cls.complexity) parts.push(`Complexity: ${cls.complexity}`);
        if (cls.confidence != null) parts.push(`Confidence: ${Math.round((cls.confidence as number) * 100)}%`);
        if (parts.length) {
          messages.value.push({
            role: 'assistant',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }
      }
    }

    if (sketch.routing_json) {
      const rt = parseJsonBlock(sketch.routing_json) as Record<string, unknown> | null;
      if (rt) {
        const parts: string[] = [];
        if (rt.target_type) parts.push(`Target: ${rt.target_type}`);
        if (rt.target_id) parts.push(`ID: ${rt.target_id}`);
        if (rt.reason) parts.push(`Reason: ${rt.reason}`);
        if (parts.length) {
          messages.value.push({
            role: 'assistant',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }
      }
    }
  }

  function clearChat() {
    currentSketch.value = null;
    messages.value = [];
    error.value = null;
  }

  onUnmounted(() => {
    abortController.abort();
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    stopDelegationPolling();
  });

  return {
    sketches,
    currentSketch,
    selectedProjectId,
    projects,
    isProcessing,
    messages,
    error,
    isStreaming,
    streamingContent,
    executionSessionId,
    executionSuperAgentId,
    delegations,
    loadProjects,
    loadSketches,
    submitSketch,
    routeSketch,
    selectSketch,
    clearChat,
  };
}
