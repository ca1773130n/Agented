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
import { superAgentSessionApi } from '../../services/api/super-agents';
import { apiFetch, ApiError, type AuthenticatedEventSource } from '../../services/api/client';
import { useToast } from '../../composables/useToast';
import LoadingState from '../base/LoadingState.vue';
import ErrorState from '../base/ErrorState.vue';
import MarkdownContent from '../base/MarkdownContent.vue';
import { authorName, modelDisplayName } from '../../utils/assistantLabel';

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
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_id?: string;
  timestamp?: string;
  /** Backend that produced an assistant turn (claude/codex/gemini/opencode). */
  backend?: string;
  /** Model that produced an assistant turn (shown as a pill beside the name). */
  model?: string;
  citations?: Citation[];
  tool_uses?: ToolUseRecord[];
  // Phase 19 (REQ-13) — when this turn ran on the ``grd`` driver, the
  // bridge surfaces the spawned PSM session id on the finish/status
  // delta. We render a "View GRD session" link to that session.
  grdSessionId?: string;
  /** Extended-thinking / reasoning text, shown folded above the answer. */
  thinking?: string;
  // System notices: account rotation / queued-for-retry / terminal errors.
  variant?: 'rotation' | 'queued' | 'error' | 'rag_progress';
  /** RAG progress hint (planning/retrieval). Only for variant === 'rag_progress'. */
  ragProgressKind?: 'planning' | 'retrieval';
  ragProgressData?: { chunks?: number; iterations?: number; sufficient?: boolean };
}

const messages = ref<ChatMessage[]>([]);
const draft = ref('');
const isSending = ref(false);
const isStreaming = ref(false);

const sseSource = ref<AuthenticatedEventSource | null>(null);
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
  closeStream();

  // Use the SAME authenticated SSE wrapper every other chat panel uses
  // (superAgentSessionApi.chatStream → createAuthenticatedEventSource). A
  // raw `new EventSource` can't send the X-API-Key header the API client
  // signs every request with, so the /admin/.../chat/stream request was
  // rejected 401 on any host without a cookie session (e.g. remote/DDNS).
  // The backend emits NAMED `state_delta` events, so we must listen via
  // addEventListener('state_delta') — `onmessage` only fires for unnamed
  // events and never received these.
  const es = superAgentSessionApi.chatStream(session.super_agent_id, session.session_id);
  sseSource.value = es;

  let activeAssistant: ChatMessage | null = null;

  const handleDelta = (ev: MessageEvent) => {
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
        // send() optimistically pushes the user's message (no message_id) so
        // it shows instantly. The backend then echoes it WITH a message_id.
        // Reconcile the two — adopt the id onto the optimistic bubble instead
        // of pushing a second copy (the bug: every line showed twice).
        const optimistic = messages.value.find(
          (m) => m.role === 'user' && m.content === data.content && !m.message_id,
        );
        if (optimistic) {
          optimistic.message_id = data.message_id;
          if (data.timestamp) optimistic.timestamp = data.timestamp;
        } else if (
          data.message_id &&
          !messages.value.some((m) => m.message_id === data.message_id)
        ) {
          messages.value.push({
            role: 'user',
            content: data.content,
            message_id: data.message_id,
            timestamp: data.timestamp || new Date().toISOString(),
          });
        }
      }
    } else if (deltaType === 'content_delta') {
      if (!activeAssistant) {
        activeAssistant = { role: 'assistant', content: '', timestamp: new Date().toISOString() };
        messages.value.push(activeAssistant);
      }
      activeAssistant.content += data.content || '';
      scrollToBottom();
    } else if (deltaType === 'thinking') {
      // Reasoning tokens — accumulate into the active turn, shown folded.
      if (!activeAssistant) {
        activeAssistant = { role: 'assistant', content: '', timestamp: new Date().toISOString() };
        messages.value.push(activeAssistant);
      }
      activeAssistant.thinking = (activeAssistant.thinking || '') + (data.text || '');
      scrollToBottom();
    } else if (deltaType === 'tool_use') {
      // Real tool-use event surfaced by the backend stream — Anthropic
      // tool_use blocks or OpenAI tool_calls deltas, dispatched by
      // run_streaming_response. Attach to the active assistant turn.
      if (!activeAssistant) {
        activeAssistant = { role: 'assistant', content: '', timestamp: new Date().toISOString() };
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
    } else if (deltaType === 'rotation') {
      // The backend hit a rate limit on one account and switched to
      // another (same backend, then other backends). Close the current
      // turn and drop in a system notice so the user understands why the
      // replying account/model changed mid-thread.
      activeAssistant = null;
      messages.value.push({
        role: 'system',
        variant: 'rotation',
        content: t('projectTeamLeaderChat.rotatedNotice', {
          from: data.from || '?',
          to: data.to || '?',
        }),
      });
      scrollToBottom();
    } else if (deltaType === 'queued') {
      // Phase 2: every account is rate-limited, so the turn is parked and
      // will auto-resume when one frees up (scheduler retries every ~20s).
      activeAssistant = null;
      messages.value.push({
        role: 'system',
        variant: 'queued',
        content: t('projectTeamLeaderChat.queuedNotice', { detail: data.message || '' }),
      });
      isStreaming.value = false;
      scrollToBottom();
    } else if (deltaType === 'retry_dispatch') {
      // A queued turn is being re-dispatched onto a freed account.
      messages.value.push({
        role: 'system',
        variant: 'rotation',
        content: t('projectTeamLeaderChat.retrying'),
      });
      isStreaming.value = true;
      scrollToBottom();
    } else if (deltaType === 'error') {
      // Terminal stream error — most importantly "all accounts
      // rate-limited". Previously dropped silently (the chat just went
      // quiet); surface it as a system notice.
      activeAssistant = null;
      messages.value.push({
        role: 'system',
        variant: 'error',
        content:
          data.kind === 'rate_limited'
            ? t('projectTeamLeaderChat.allRateLimited', { detail: data.error || '' })
            : data.error || t('projectTeamLeaderChat.streamError'),
      });
      isStreaming.value = false;
      scrollToBottom();
    } else if (deltaType === 'finish') {
      if (activeAssistant) {
        activeAssistant.citations = extractCitations(activeAssistant.content);
        // Label the bubble with who actually answered — the resolved
        // backend + model are carried on the finish delta.
        if (data.backend) activeAssistant.backend = data.backend;
        if (data.model) activeAssistant.model = data.model;
        // Phase 19 (REQ-13) — a grd-driver turn carries the spawned PSM
        // session id on the finish delta (any of these field names —
        // 19-RESEARCH §7/risk 2; bind defensively). When present, render
        // a link to the GRD session.
        const gid = extractGrdSessionId(data);
        if (gid) activeAssistant.grdSessionId = gid;
        activeAssistant = null;
      }
      isStreaming.value = false;
    } else if (deltaType === 'status_change') {
      isStreaming.value = data.status === 'streaming';
    } else if (deltaType === 'planning') {
      // RAG pipeline: planner sub-step started — show inline progress line
      // beside the thinking fold so the user sees retrieval is in progress.
      messages.value.push({
        role: 'system',
        variant: 'rag_progress',
        content: t('projectTeamLeaderChat.planningProgress'),
        ragProgressKind: 'planning',
      });
      scrollToBottom();
    } else if (deltaType === 'retrieval') {
      // RAG pipeline: fanout finished — report chunk / iteration counts.
      messages.value.push({
        role: 'system',
        variant: 'rag_progress',
        content: t('projectTeamLeaderChat.retrievalProgress', {
          chunks: data.chunks ?? 0,
          iterations: data.iterations ?? 1,
        }),
        ragProgressKind: 'retrieval',
        ragProgressData: {
          chunks: data.chunks,
          iterations: data.iterations,
          sufficient: data.sufficient,
        },
      });
      scrollToBottom();
    } else if (deltaType === 'citations') {
      // RAG pipeline: backend-extracted citations arrive AFTER finish has
      // already cleared activeAssistant. Attach them to the LAST assistant
      // message, replacing the regex-derived fallback citations.
      // data.citations is already mapped to {kind, value} by the backend
      // (Task 3), so we consume it directly without re-running extractCitations.
      if (data.message_scope === 'last_assistant') {
        const lastAssistant = [...messages.value].reverse().find((m) => m.role === 'assistant');
        if (lastAssistant && Array.isArray(data.citations)) {
          lastAssistant.citations = data.citations as Citation[];
        }
      }
    }
  };

  // Backend deltas (content/tool_use/rotation/queued/error/finish) all
  // arrive on the named `state_delta` channel.
  es.addEventListener('state_delta', handleDelta);

  // Backend in-band terminal error (e.g. "Session not found"), distinct
  // from a transport error — carries a JSON body.
  es.addEventListener('error', (ev: MessageEvent) => {
    try {
      const payload = JSON.parse(ev.data);
      activeAssistant = null;
      messages.value.push({
        role: 'system',
        variant: 'error',
        content: payload.error || t('projectTeamLeaderChat.streamError'),
      });
      isStreaming.value = false;
      scrollToBottom();
    } catch {
      /* transport 'error' events have no JSON body — handled by onerror */
    }
  });

  es.onerror = () => {
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

// Phase 19 (REQ-13) — pull the GRD/PSM session id off a finish/status
// delta. The bridge may name it any of these; accept all and require a
// plausible session-id shape so a stray ``finish_reason`` never matches.
function extractGrdSessionId(data: Record<string, unknown>): string | null {
  if (!data || typeof data !== 'object') return null;
  for (const key of ['grd_session_id', 'psm_session_id', 'session_id']) {
    const val = data[key];
    if (typeof val === 'string' && val.trim()) return val.trim();
  }
  return null;
}

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

  messages.value.push({ role: 'user', content, timestamp: new Date().toISOString() });
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

function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
        <template v-for="(m, i) in messages" :key="i">
        <!-- System notices: rate-limit account rotation / terminal errors. -->
        <div
          v-if="m.role === 'system'"
          :class="['msg-notice', `msg-notice--${m.variant || 'rotation'}`]"
          data-role="system"
          :data-variant="m.variant"
          data-testid="chat-system-notice"
        >
          <span class="msg-notice__icon" aria-hidden="true">{{
            m.variant === 'error' ? '⚠'
            : m.variant === 'queued' ? '⏳'
            : m.variant === 'rag_progress' ? (m.ragProgressKind === 'retrieval' ? '⬇' : '⟳')
            : '↻'
          }}</span>
          <span class="msg-notice__text">{{ m.content }}</span>
        </div>
        <article
          v-else
          :class="['msg', `msg--${m.role}`]"
          :data-role="m.role"
        >
          <div class="msg__head">
            <span class="msg__role">{{ authorName(m.role, m.backend) }}</span>
            <span
              v-if="m.role === 'assistant' && modelDisplayName(m.model)"
              class="msg__model"
              >{{ modelDisplayName(m.model) }}</span
            >
            <span v-if="m.timestamp" class="msg__time">{{ formatTime(m.timestamp) }}</span>
          </div>
          <!-- Reasoning — folded by default; expand to read the thinking. -->
          <details
            v-if="m.role === 'assistant' && m.thinking"
            class="msg__fold msg__fold--thinking"
            data-testid="msg-thinking"
          >
            <summary>{{ t('projectTeamLeaderChat.thinkingLabel') }}</summary>
            <div class="msg__fold-body">{{ m.thinking }}</div>
          </details>
          <!-- Tool executions — folded; expand to see each call + its args. -->
          <details
            v-if="m.role === 'assistant' && m.tool_uses?.length"
            class="msg__fold msg__fold--tools"
            data-testid="msg-tool-uses"
          >
            <summary>
              {{ t('projectTeamLeaderChat.toolsLabel', { count: m.tool_uses.length }) }}
            </summary>
            <div class="msg__fold-body">
              <div
                v-for="(tu, ti) in m.tool_uses"
                :key="(tu.id || tu.name) + ':' + ti"
                class="tool-row"
                :data-tool="tu.name"
              >
                <code class="tool-row__name">{{ tu.name }}</code>
                <span v-if="formatToolPreview(tu)" class="tool-row__args">{{
                  formatToolPreview(tu)
                }}</span>
              </div>
            </div>
          </details>
          <!-- Assistant replies render markdown; user input stays literal so
               accidental markdown in a question isn't reinterpreted. -->
          <MarkdownContent
            v-if="m.role === 'assistant'"
            class="msg__content"
            :content="m.content"
            :breaks="true"
          />
          <div v-else class="msg__content">{{ m.content }}</div>
          <!-- Phase 19 (REQ-13) — GRD-session linkage for grd-driver turns. -->
          <router-link
            v-if="m.role === 'assistant' && m.grdSessionId"
            class="grd-session-link"
            data-testid="grd-session-link"
            :data-session-id="m.grdSessionId"
            :to="{
              name: 'project-management',
              params: { projectId: props.projectId },
              query: { session: m.grdSessionId },
            }"
          >
            <span class="grd-session-link__icon" aria-hidden="true">⚡</span>
            {{ t('driver.viewGrdSession') }}
          </router-link>
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
        </template>
        <div v-if="isStreaming" class="typing" data-testid="chat-typing" aria-label="assistant is typing">
          <span class="typing__dot" />
          <span class="typing__dot" />
          <span class="typing__dot" />
        </div>
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
.msg__head {
  display: flex; align-items: baseline; gap: 8px;
}
.msg__role {
  font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-tertiary);
}
.msg__model {
  font-size: 10px; padding: 1px 6px; border-radius: 4px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.06));
  color: var(--text-tertiary); font-variant-numeric: tabular-nums;
}
.msg__time {
  font-size: 10px; color: var(--text-quaternary, var(--text-tertiary));
  opacity: 0.7; font-variant-numeric: tabular-nums;
}
/* Inline system notices (rate-limit rotation + terminal errors) —
   centered, full-width, visually distinct from user/assistant bubbles. */
.msg-notice {
  align-self: center;
  display: flex; align-items: center; gap: 8px;
  max-width: 92%;
  padding: 6px 12px; border-radius: 8px;
  font-size: 12px; line-height: 1.4;
}
.msg-notice__icon { flex: 0 0 auto; font-size: 13px; }
.msg-notice__text { white-space: pre-wrap; }
.msg-notice--rotation {
  background: rgba(234, 179, 8, 0.08);
  border: 1px solid rgba(234, 179, 8, 0.28);
  color: var(--accent-amber, #eab308);
}
.msg-notice--queued {
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.28);
  color: var(--accent-blue, #3b82f6);
}
.msg-notice--error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--accent-red, #ef4444);
}
.msg__content { font-size: 13px; white-space: pre-wrap; line-height: 1.5; }
.msg__cites {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-top: 4px;
}
.grd-session-link {
  display: inline-flex; align-items: center; gap: 4px;
  margin-top: 6px; align-self: flex-start;
  font-size: 11px; padding: 3px 8px; border-radius: 4px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: var(--accent-green, #10b981);
  text-decoration: none;
}
.grd-session-link:hover { background: rgba(16, 185, 129, 0.18); }
.grd-session-link__icon { font-size: 11px; }
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

/* Collapsible folds — reasoning + tool executions, closed by default. */
.msg__fold {
  margin: 2px 0 4px;
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.08));
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  font-size: 11px;
}
.msg__fold > summary {
  cursor: pointer; list-style: none;
  padding: 4px 8px;
  color: var(--text-tertiary);
  user-select: none;
  display: flex; align-items: center; gap: 6px;
}
.msg__fold > summary::-webkit-details-marker { display: none; }
.msg__fold > summary::before {
  content: '▸'; font-size: 9px; transition: transform 0.15s ease;
}
.msg__fold[open] > summary::before { transform: rotate(90deg); }
.msg__fold--thinking > summary { color: var(--accent-purple, #8b5cf6); }
.msg__fold-body {
  padding: 6px 10px 8px;
  border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  white-space: pre-wrap; line-height: 1.5;
  color: var(--text-secondary, var(--text-tertiary));
  font-size: 12px;
  max-height: 320px; overflow: auto;
}
.tool-row {
  display: flex; align-items: baseline; gap: 8px;
  padding: 2px 0;
}
.tool-row__name {
  font-family: var(--font-mono, monospace);
  color: var(--accent-green, #10b981);
  font-size: 11px;
}
.tool-row__args {
  font-size: 11px; opacity: 0.8;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* Typing indicator — three pulsing dots while the assistant streams. */
.typing {
  display: inline-flex; align-items: center; gap: 4px;
  align-self: flex-start;
  padding: 8px 12px;
}
.typing__dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-tertiary, #888);
  animation: typing-bounce 1.2s ease-in-out infinite;
}
.typing__dot:nth-child(2) { animation-delay: 0.18s; }
.typing__dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes typing-bounce {
  0%, 80%, 100% { opacity: 0.3; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-3px); }
}
@media (prefers-reduced-motion: reduce) {
  .typing__dot { animation: none; opacity: 0.6; }
}

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
