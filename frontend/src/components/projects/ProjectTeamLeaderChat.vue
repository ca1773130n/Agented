<!--
  Ask the team leader — single-pane chat panel for a project.

  Resolves the project's manager super-agent + leader session via the
  /admin/projects/{id}/team-leader/chat/session endpoint, then drives
  the existing super-agent chat surface (POST + SSE) directly.

  When the project has Tesserae enabled, a "grounded by Tesserae"
  badge is shown — the leader's runtime context already has the
  tesserae_* MCP tools available, so the synthesized answers can pull
  from the compiled project graph automatically.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  teamLeaderChatApi,
  type TeamLeaderChatSession,
} from '../../services/api/team-leader-chat';
import { apiFetch, ApiError } from '../../services/api/client';
import { useToast } from '../../composables/useToast';
import LoadingState from '../base/LoadingState.vue';
import ErrorState from '../base/ErrorState.vue';

const props = defineProps<{ projectId: string }>();
const showToast = useToast();
const { t } = useI18n();

const isResolving = ref(true);
const resolveError = ref<string | null>(null);
const chatSession = ref<TeamLeaderChatSession | null>(null);

type CitationKind = 'file' | 'kg_entity' | 'session' | 'takeaway';

interface Citation {
  kind: CitationKind;
  value: string;
}

interface ToolUseRecord {
  name: string;
  input: unknown;
  id?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  message_id?: string;
  timestamp?: string;
  citations?: Citation[];
  tool_uses?: ToolUseRecord[];
}

const messages = ref<ChatMessage[]>([]);
const draft = ref('');
const isSending = ref(false);
const isStreaming = ref(false);

const sseSource = ref<EventSource | null>(null);
const scrollContainer = ref<HTMLDivElement | null>(null);

const tesseraeBadge = computed(() =>
  chatSession.value?.tesserae_enabled ? t('projectTeamLeaderChat.groundedBadge') : null,
);

async function resolveAndConnect() {
  isResolving.value = true;
  resolveError.value = null;
  try {
    const session = await teamLeaderChatApi.openSession(props.projectId);
    chatSession.value = session;
    connectStream(session);
  } catch (err) {
    resolveError.value =
      err instanceof ApiError ? err.message : t('projectTeamLeaderChat.openFailed');
  } finally {
    isResolving.value = false;
  }
}

function connectStream(session: TeamLeaderChatSession) {
  // The chat SSE path lives on the existing super-agent surface.
  // Use template SA id (matches what _resolve_chat_session expects).
  const url =
    `/admin/super-agents/${encodeURIComponent(session.super_agent_id)}` +
    `/sessions/${encodeURIComponent(session.session_id)}/chat/stream`;

  closeStream();

  // EventSource doesn't accept custom headers — auth flows via cookie
  // when the dev server is set up properly.
  const es = new EventSource(url, { withCredentials: true });
  sseSource.value = es;

  let activeAssistant: ChatMessage | null = null;

  es.onmessage = (ev) => {
    let payload: any;
    try {
      payload = JSON.parse(ev.data);
    } catch {
      return;
    }
    const deltaType = payload.type || payload.delta_type;
    const data = payload.data || payload;

    if (deltaType === 'message') {
      if (data.role === 'user' && data.content) {
        // De-dup against optimistic local push by message_id.
        if (
          data.message_id &&
          !messages.value.some((m) => m.message_id === data.message_id)
        ) {
          messages.value.push({
            role: 'user',
            content: data.content,
            message_id: data.message_id,
          });
        }
      }
    } else if (deltaType === 'content_delta') {
      if (!activeAssistant) {
        activeAssistant = { role: 'assistant', content: '' };
        messages.value.push(activeAssistant);
      }
      activeAssistant.content += data.content || '';
      scrollToBottom();
    } else if (deltaType === 'tool_use') {
      // Real tool-use event surfaced by the backend stream — Anthropic
      // tool_use blocks or OpenAI tool_calls deltas, dispatched by
      // run_streaming_response. Attach to the active assistant turn.
      if (!activeAssistant) {
        activeAssistant = { role: 'assistant', content: '' };
        messages.value.push(activeAssistant);
      }
      const tu: ToolUseRecord = {
        name: data.name || 'unknown',
        input: data.input,
        id: data.id,
      };
      activeAssistant.tool_uses = activeAssistant.tool_uses
        ? [...activeAssistant.tool_uses, tu]
        : [tu];
      scrollToBottom();
    } else if (deltaType === 'finish') {
      if (activeAssistant) {
        activeAssistant.citations = extractCitations(activeAssistant.content);
        activeAssistant = null;
      }
      isStreaming.value = false;
    } else if (deltaType === 'status_change') {
      isStreaming.value = data.status === 'streaming';
    }
  };

  es.onerror = (err) => {
    console.warn('[TeamLeaderChat] SSE error', err);
    isStreaming.value = false;
  };
}

function closeStream() {
  if (sseSource.value) {
    sseSource.value.close();
    sseSource.value = null;
  }
}

// Citation kinds we recognize in the assistant's synthesized text.
// File paths are caught by backtick + extension; entity / session /
// takeaway IDs use Agented's prefix conventions:
//   kge-*   knowledge graph entity (Tesserae node id pattern)
//   sess-*  super-agent / project session
//   tk*     takeaway id
// Each chip carries a kind for typed rendering. The list is best-
// effort — actual tool_use citations would need plumbing through the
// CLI proxy's tool-call stream (see harness_evolver.py and
// conversation_streaming.py — both currently yield plain text only;
// tool_use events surface only in the Anthropic stream-json fallback
// and the proxy's OpenAI chat-completions surface drops them).
const CITATION_PATTERNS: { kind: CitationKind; re: RegExp }[] = [
  { kind: 'file', re: /`([A-Za-z0-9_./\-]+\.[a-zA-Z0-9]{1,8})`/g },
  { kind: 'kg_entity', re: /\b(kge-[a-z0-9]{4,})\b/g },
  { kind: 'session', re: /\b(sess-[a-z0-9]{4,}|psa-[a-z0-9]{4,})\b/g },
  { kind: 'takeaway', re: /\b(tk[a-z0-9]{6,})\b/g },
];

function extractCitations(text: string): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  for (const { kind, re } of CITATION_PATTERNS) {
    for (const m of text.matchAll(re)) {
      const value = m[1];
      if (!value) continue;
      const key = `${kind}:${value}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ kind, value });
      if (out.length >= 12) return out;
    }
  }
  return out;
}

async function send() {
  if (!chatSession.value || !draft.value.trim()) return;
  const content = draft.value.trim();
  draft.value = '';
  isSending.value = true;
  isStreaming.value = true;

  messages.value.push({ role: 'user', content });
  scrollToBottom();

  try {
    const session = chatSession.value;
    await apiFetch(
      `/admin/super-agents/${encodeURIComponent(session.super_agent_id)}` +
        `/sessions/${encodeURIComponent(session.session_id)}/chat`,
      {
        method: 'POST',
        body: JSON.stringify({ content }),
      },
    );
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : t('projectTeamLeaderChat.sendFailed');
    showToast(msg, 'error');
    isStreaming.value = false;
  } finally {
    isSending.value = false;
  }
}

function formatToolInput(tu: ToolUseRecord): string {
  // Full args as JSON for the badge hover tooltip.
  try {
    return JSON.stringify(tu.input, null, 2).slice(0, 600);
  } catch {
    return String(tu.input);
  }
}

function formatToolPreview(tu: ToolUseRecord): string {
  // One-line summary for inline display next to the tool name.
  // For tesserae_ask / search_* the first arg is the operative one;
  // pick a sensible primary field.
  if (typeof tu.input === 'string') {
    const s = tu.input.trim();
    return s.length > 60 ? s.slice(0, 57) + '…' : s;
  }
  if (tu.input && typeof tu.input === 'object') {
    const obj = tu.input as Record<string, unknown>;
    const primary =
      obj.question || obj.query || obj.q || obj.path ||
      obj.symbol || obj.seed_nodes || obj.session_id || obj.name;
    if (primary == null) return '';
    const s = typeof primary === 'string' ? primary : JSON.stringify(primary);
    return s.length > 60 ? s.slice(0, 57) + '…' : s;
  }
  return '';
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight;
    }
  });
}

onMounted(resolveAndConnect);
onUnmounted(closeStream);
</script>

<template>
  <section class="team-leader-chat" data-testid="project-team-leader-chat">
    <header class="head">
      <div>
        <h3>{{ t('projectTeamLeaderChat.title') }}</h3>
        <p class="muted">
          <span v-if="chatSession">
            {{ t('projectTeamLeaderChat.conversationWith') }}
            <strong>{{ chatSession.leader_name }}</strong>
            <span v-if="tesseraeBadge" class="badge ok">
              {{ tesseraeBadge }}
            </span>
          </span>
          <span v-else-if="isResolving">{{ t('projectTeamLeaderChat.resolving') }}</span>
        </p>
        <p v-if="chatSession" class="muted tiny">
          {{ t('projectTeamLeaderChat.persistsNote') }}
          <code>super_agent_sessions.conversation_log</code>.
        </p>
      </div>
    </header>

    <LoadingState v-if="isResolving" :message="t('projectTeamLeaderChat.openingSession')" />
    <ErrorState
      v-else-if="resolveError"
      :message="resolveError"
      @retry="resolveAndConnect"
    />
    <template v-else-if="chatSession">
      <div
        ref="scrollContainer"
        class="messages"
        data-testid="team-leader-chat-messages"
      >
        <p v-if="!messages.length" class="empty muted">
          {{ t('projectTeamLeaderChat.emptyHint') }}
        </p>
        <article
          v-for="(m, i) in messages"
          :key="i"
          :class="['msg', `msg--${m.role}`]"
          :data-role="m.role"
        >
          <div class="msg__role">{{ m.role }}</div>
          <div
            v-if="m.role === 'assistant' && m.tool_uses?.length"
            class="msg__tools"
            data-testid="msg-tool-uses"
          >
            <span class="tool-label">{{ t('projectTeamLeaderChat.queriedLabel') }}</span>
            <span
              v-for="(tu, ti) in m.tool_uses"
              :key="(tu.id || tu.name) + ':' + ti"
              class="tool-badge"
              :data-tool="tu.name"
              :title="formatToolInput(tu)"
            >
              <code>{{ tu.name }}</code>
              <span v-if="formatToolPreview(tu)" class="tool-preview">
                {{ formatToolPreview(tu) }}
              </span>
            </span>
          </div>
          <div class="msg__content">{{ m.content }}</div>
          <div
            v-if="m.role === 'assistant' && m.citations?.length"
            class="msg__cites"
          >
            <span class="cite-label">{{ t('projectTeamLeaderChat.citedLabel') }}</span>
            <code
              v-for="c in m.citations"
              :key="c.kind + ':' + c.value"
              class="cite-chip"
              :data-kind="c.kind"
              :title="t('projectTeamLeaderChat.citationKind', { kind: c.kind })"
            >{{ c.value }}</code>
          </div>
        </article>
        <div v-if="isStreaming" class="streaming">…</div>
      </div>

      <footer class="composer">
        <textarea
          v-model="draft"
          :placeholder="t('projectTeamLeaderChat.inputPlaceholder')"
          :disabled="isSending"
          rows="2"
          data-testid="team-leader-chat-input"
          @keydown.enter.exact.prevent="send"
        />
        <button
          class="btn-send"
          :disabled="!draft.trim() || isSending"
          data-testid="team-leader-chat-send"
          @click="send"
        >
          {{ t('projectTeamLeaderChat.askButton') }}
        </button>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.team-leader-chat {
  display: flex; flex-direction: column;
  border: 1px solid var(--border-default, rgba(255,255,255,0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255,255,255,0.02));
  padding: 16px 18px;
  gap: 12px;
  min-height: 400px;
  max-height: 600px;
}
.head h3 { margin: 0; font-size: 14px; }
.muted { color: var(--text-tertiary); font-size: 12px; margin: 4px 0 0; }
.muted.tiny { font-size: 10px; margin-top: 2px; }
.muted.tiny code { font-size: 10px; }
.badge.ok {
  margin-left: 8px; padding: 1px 6px; border-radius: 3px;
  font-size: 10px; letter-spacing: 0.04em; text-transform: uppercase;
  background: var(--accent-green, #10b981); color: white;
}

.messages {
  flex: 1; overflow-y: auto;
  display: flex; flex-direction: column; gap: 10px;
  padding: 6px 0;
}
.empty { padding: 24px 4px; text-align: center; font-size: 12px; }

.msg {
  padding: 10px 12px; border-radius: 8px;
  display: flex; flex-direction: column; gap: 4px;
}
.msg--user {
  background: var(--bg-tertiary, rgba(99, 102, 241, 0.08));
  border: 1px solid rgba(99, 102, 241, 0.2);
  align-self: flex-end; max-width: 80%;
}
.msg--assistant {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  align-self: flex-start; max-width: 90%;
}
.msg__role {
  font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-tertiary);
}
.msg__content { font-size: 13px; white-space: pre-wrap; line-height: 1.5; }
.msg__cites {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-top: 4px;
}
.cite-label { font-size: 10px; color: var(--text-tertiary); }
.cite-chip {
  font-size: 10px; padding: 1px 5px; border-radius: 3px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan, #06b6d4);
  font-family: var(--font-mono, monospace);
}
.cite-chip[data-kind="kg_entity"] {
  background: rgba(139, 92, 246, 0.1);
  border-color: rgba(139, 92, 246, 0.3);
  color: var(--accent-purple, #8b5cf6);
}
.cite-chip[data-kind="session"] {
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.3);
  color: var(--accent-green, #10b981);
}
.cite-chip[data-kind="takeaway"] {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.3);
  color: var(--accent-amber, #f59e0b);
}
.msg__tools {
  display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  margin-bottom: 2px;
}
.tool-label { font-size: 10px; color: var(--text-tertiary); }
.tool-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; padding: 2px 6px; border-radius: 3px;
  background: rgba(139, 92, 246, 0.12);
  border: 1px solid rgba(139, 92, 246, 0.35);
  color: var(--accent-purple, #8b5cf6);
  font-family: var(--font-mono, monospace);
  cursor: help;
}
.tool-badge[data-tool^="tesserae_"] {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.35);
  color: var(--accent-green, #10b981);
}
.tool-badge code { font-family: inherit; font-size: 10px; }
.tool-preview {
  font-family: var(--font-sans, sans-serif);
  font-size: 10px;
  opacity: 0.8;
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.streaming { font-size: 14px; color: var(--text-tertiary); padding: 6px 12px; }

.composer {
  display: flex; gap: 8px; align-items: stretch;
}
.composer textarea {
  flex: 1; resize: none;
  font-size: 13px; padding: 8px 10px; border-radius: 6px;
  background: var(--bg-primary, rgba(0,0,0,0.2));
  border: 1px solid var(--border-default, rgba(255,255,255,0.12));
  color: var(--text-primary); font-family: inherit;
}
.btn-send {
  padding: 6px 16px; border-radius: 6px;
  border: 1px solid var(--accent-cyan, #06b6d4);
  background: transparent; color: var(--accent-cyan, #06b6d4);
  cursor: pointer; font-size: 13px;
}
.btn-send:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
