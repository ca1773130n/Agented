import { ref, onUnmounted, watch, type Ref } from 'vue';
import type { ViewerInfo, InlineComment, AuthenticatedEventSource } from '../services/api';
import { collaborativeApi } from '../services/api';

const HEARTBEAT_INTERVAL_MS = 30_000;

/**
 * Composable for managing collaborative execution viewing.
 *
 * Handles viewer lifecycle (join, heartbeat, leave) and inline comments.
 * Listens for SSE presence and comment events on an existing execution
 * stream EventSource -- does NOT create a separate SSE connection.
 *
 * @param executionId - Reactive execution ID to watch
 * @param viewerName - Display name for the viewer
 * @param getEventSource - Getter for the execution stream's EventSource
 */
export function useCollaborativeViewer(
  executionId: Ref<string>,
  viewerName: string,
  getEventSource: () => AuthenticatedEventSource | null,
) {
  const viewers = ref<ViewerInfo[]>([]);
  const comments = ref<InlineComment[]>([]);
  const isJoined = ref(false);

  // Generate a unique viewer ID per session
  const viewerId = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `viewer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  // SSE event handlers (kept as references for removeEventListener)
  function handlePresenceJoin(event: MessageEvent) {
    try {
      const data = JSON.parse(event.data) as ViewerInfo;
      // Avoid duplicates
      if (!viewers.value.some(v => v.viewer_id === data.viewer_id)) {
        viewers.value.push(data);
      }
    } catch {
      // Ignore malformed events
    }
  }

  function handlePresenceLeave(event: MessageEvent) {
    try {
      const data = JSON.parse(event.data) as { viewer_id: string };
      viewers.value = viewers.value.filter(v => v.viewer_id !== data.viewer_id);
    } catch {
      // Ignore malformed events
    }
  }

  function handleInlineComment(event: MessageEvent) {
    try {
      const data = JSON.parse(event.data) as InlineComment;
      // Avoid duplicates
      if (!comments.value.some(c => c.id === data.id)) {
        comments.value.push(data);
      }
    } catch {
      // Ignore malformed events
    }
  }

  function attachSSEListeners() {
    const source = getEventSource();
    if (!source) return;
    source.addEventListener('presence_join', handlePresenceJoin);
    source.addEventListener('presence_leave', handlePresenceLeave);
    source.addEventListener('inline_comment', handleInlineComment);
  }

  function detachSSEListeners() {
    const source = getEventSource();
    if (!source) return;
    source.removeEventListener('presence_join', handlePresenceJoin);
    source.removeEventListener('presence_leave', handlePresenceLeave);
    source.removeEventListener('inline_comment', handleInlineComment);
  }

  async function join() {
    if (!executionId.value || isJoined.value) return;
    try {
      await collaborativeApi.join(executionId.value, viewerId, viewerName);
      isJoined.value = true;

      // Load existing comments
      const result = await collaborativeApi.getComments(executionId.value);
      comments.value = result?.comments ?? [];

      // Load current viewers
      const viewerResult = await collaborativeApi.getViewers(executionId.value);
      viewers.value = viewerResult?.viewers ?? [];

      // Start heartbeat
      heartbeatTimer = setInterval(() => {
        if (executionId.value) {
          collaborativeApi.heartbeat(executionId.value, viewerId).catch(() => {
            // Silently ignore heartbeat failures
          });
        }
      }, HEARTBEAT_INTERVAL_MS);

      // Attach SSE listeners
      attachSSEListeners();
    } catch {
      // Join failed -- viewer not registered
      isJoined.value = false;
    }
  }

  async function leave() {
    if (!isJoined.value) return;

    // Clear heartbeat
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }

    // Detach SSE listeners
    detachSSEListeners();

    // Notify server
    try {
      if (executionId.value) {
        await collaborativeApi.leave(executionId.value, viewerId);
      }
    } catch {
      // Ignore leave failures
    }

    isJoined.value = false;
    viewers.value = [];
    comments.value = [];
  }

  /** Post an inline comment anchored to a log line number. */
  async function postComment(lineNumber: number, content: string) {
    if (!executionId.value || !content.trim()) return;
    try {
      const comment = await collaborativeApi.postComment(executionId.value, {
        viewer_id: viewerId,
        viewer_name: viewerName,
        line_number: lineNumber,
        content: content.trim(),
      });
      // Add locally (SSE will also broadcast, but we add immediately for responsiveness)
      if (comment && !comments.value.some(c => c.id === comment.id)) {
        comments.value.push(comment);
      }
    } catch (e) {
      console.warn('[useCollaborativeViewer] Failed to post comment:', e);
    }
  }

  // Watch for executionId changes to re-join
  watch(executionId, async (newId, oldId) => {
    if (oldId && isJoined.value) {
      await leave();
    }
    if (newId) {
      await join();
    }
  });

  // Cleanup on unmount
  onUnmounted(() => {
    leave();
  });

  return {
    viewers,
    comments,
    isJoined,
    viewerId,
    join,
    leave,
    postComment,
  };
}
