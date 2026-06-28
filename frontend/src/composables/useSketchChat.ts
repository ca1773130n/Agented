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
  // Federated-Tesserae grounding used on the latest ideation turn (provenance).
  const grounding = ref<{ projects: string[]; citations: number } | null>(null);
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
      // Create the sketch ONCE (first message) + classify for the badge.
      // Subsequent turns accumulate onto the SAME sketch — this is a
      // conversation, not one-shot. Routing is deferred to a manual button.
      if (!currentSketch.value) {
        const createResult = await sketchApi.create({
          title: text.slice(0, 100),
          content: text,
          project_id: selectedProjectId.value ?? undefined,
        });
        // Capture the sketch IMMEDIATELY so a later failure can't strand the row
        // or make the next submit create a duplicate.
        currentSketch.value = await sketchApi.get(createResult.sketch_id);
        await loadSketches();
        // Classification is best-effort (drives the badge only) — a failure must
        // not abort the conversation or duplicate the sketch.
        try {
          await sketchApi.classify(createResult.sketch_id);
          if (abortController.signal.aborted) return;
          currentSketch.value = await sketchApi.get(createResult.sketch_id);
        } catch {
          /* keep going — the chat still works without a classification badge */
        }
      }
      if (abortController.signal.aborted) return;

      // Stream a federated-grounded ideation reply. NO routing/execution.
      await ideate();
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

  // One grounded ideation turn: stream a reply from the general-LLM partner,
  // grounded by federated Tesserae knowledge across all projects. No routing.
  async function ideate() {
    const history = messages.value
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role, content: m.content }));

    // The panel renders BOTH `messages` and the live `streamingContent` bubble,
    // so the assistant turn must live in exactly one of them at a time: stream
    // into `streamingContent` only, then commit it to `messages` on completion.
    // (Pushing an assistant message up front + updating streamingContent showed
    // the same text in two duplicate bubbles.)
    streamingContent.value = '';
    isStreaming.value = true;
    grounding.value = null;
    let errorNote = '';
    try {
      await sketchApi.ideateStream(history, {
        onRetrieval: (p) => {
          grounding.value = p;
        },
        onContent: (chunk) => {
          streamingContent.value += chunk;
        },
        onError: (m) => {
          errorNote = `\n\n_⚠ ${m}_`;
        },
        onDone: () => {},
        signal: abortController.signal,
      });
    } finally {
      isStreaming.value = false;
      // Commit the streamed turn as ONE message, then clear the live buffer
      // (same tick → Vue batches into a single render, no duplicate/flash).
      const finalContent = streamingContent.value + errorNote;
      if (finalContent) {
        messages.value.push({
          role: 'assistant',
          content: finalContent,
          timestamp: new Date().toISOString(),
        });
      }
      streamingContent.value = '';
    }
  }

  async function routeSketch(sketchId: string, opts?: { useCliAgent?: boolean }) {
    try {
      isProcessing.value = true;
      error.value = null;

      // Ensure the sketch is classified before routing — classify may have
      // failed/been skipped during ideation, and route requires it. This removes
      // the dead-end where an unclassified sketch can never be routed.
      if (!currentSketch.value?.classification_json) {
        try {
          await sketchApi.classify(sketchId);
          currentSketch.value = await sketchApi.get(sketchId);
        } catch {
          /* route will surface a clear error if it's still unclassified */
        }
      }

      // Route the WHOLE conversation, not just the first message: persist the
      // accumulated transcript as the sketch content so the executor sees the
      // full ideation, not the original one-liner.
      const transcript = messages.value
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
        .join('\n\n');
      if (transcript) {
        try {
          await sketchApi.update(sketchId, { content: transcript });
        } catch {
          /* best-effort — fall back to the stored content */
        }
      }

      const routeResult = await sketchApi.route(sketchId, opts);

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

        // Defensively tear down any prior stream + polling before opening a new
        // one — routing a second sketch in the same component would otherwise
        // leak the previous EventSource (it keeps receiving + mutating state).
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        stopDelegationPolling();

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
              case 'rotation': {
                // Account rate-limited → switched to another. Prefix the
                // streaming turn with an inline notice so the user sees why
                // the replying account/model changed mid-thread.
                const from = (data.data || data).from || '?';
                const to = (data.data || data).to || '?';
                streamingContent.value += `\n\n_↻ ${from} hit its rate limit — switched to ${to}_\n\n`;
                messages.value[msgIndex].content = streamingContent.value;
                break;
              }
              case 'queued': {
                // All accounts rate-limited → turn parked for auto-retry.
                isStreaming.value = false;
                const m = (data.data || data).message || 'All accounts are rate-limited.';
                streamingContent.value += `\n\n_⏳ ${m} Queued — will retry when an account frees._`;
                messages.value[msgIndex].content = streamingContent.value;
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                break;
              }
              case 'finish': {
                isStreaming.value = false;
                // Label the assistant bubble with who actually answered —
                // the resolved backend + model carried on the finish delta.
                const fin = data.data || data;
                const finished = messages.value[msgIndex];
                if (finished) {
                  if (fin.backend) finished.backend = fin.backend;
                  if (fin.model) finished.model = fin.model;
                }
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                // Check for delegations (team collaboration)
                startDelegationPolling(sketchId);
                break;
              }
              case 'error': {
                isStreaming.value = false;
                // Surface the backend reason (e.g. "all accounts
                // rate-limited — soonest reset …") instead of a generic
                // message so the user knows what actually happened.
                const payload = data.data || data;
                error.value =
                  payload.error || 'Streaming error occurred. You can retry by routing again.';
                if (eventSource) {
                  eventSource.close();
                  eventSource = null;
                }
                break;
              }
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

  async function selectSketch(sketch: Sketch) {
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
            role: 'system',
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
            role: 'system',
            content: parts.join(' | '),
            timestamp: sketch.updated_at || new Date().toISOString(),
          });
        }

        // Pull the agent's final response out of the session that
        // executed this sketch. Without this, viewing a completed
        // sketch only showed the user's prompt + the routing system
        // banner — the actual answer was hidden in the SA session log
        // and the user had to navigate to the playground to read it.
        // Append every assistant turn as a bubble so the "what did the
        // agent reply" question is answerable from the sketch list
        // alone.
        const sessionId = (rt.session_id as string | undefined) || undefined;
        const saId = (rt.super_agent_id as string | undefined) || undefined;
        if (sessionId && saId) {
          executionSessionId.value = sessionId;
          executionSuperAgentId.value = saId;
          try {
            const session = await superAgentSessionApi.get(saId, sessionId);
            // ``conversation_log`` is typed as ``string | undefined`` on
            // the session row. ``parseJsonBlock`` expects a string; pass
            // an empty string when the field is missing so we get a
            // clean ``null`` back instead of a TS error.
            const log = parseJsonBlock(session.conversation_log ?? '') as
              | Array<{
                  role?: string;
                  content?: string;
                  timestamp?: string;
                  backend?: string;
                  model?: string;
                }>
              | null;
            if (Array.isArray(log)) {
              for (const turn of log) {
                if (turn?.role === 'assistant' && typeof turn.content === 'string' && turn.content.trim()) {
                  // Carry the persisted backend/model so a resumed sketch
                  // labels the bubble with who answered, not "Assistant".
                  const restored: ConversationMessage = {
                    role: 'assistant',
                    content: turn.content,
                    timestamp: turn.timestamp || sketch.updated_at || new Date().toISOString(),
                  };
                  if (turn.backend) restored.backend = turn.backend;
                  if (turn.model) restored.model = turn.model;
                  messages.value.push(restored);
                }
              }
            }
          } catch {
            // Session fetch failed — fall back to the system summary
            // banner above. Don't surface a toast: completed-sketch
            // browsing should be silent on best-effort lookups.
          }
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
    grounding,
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
