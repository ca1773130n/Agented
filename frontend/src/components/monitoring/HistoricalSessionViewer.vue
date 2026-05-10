<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { marked } from 'marked';
import { superAgentSessionApi } from '../../services/api';
import { safeFormatDateTime } from '../../utils/datetime';

interface Props {
  superAgentId: string;
  sessionId: string;
}

const props = defineProps<Props>();
const emit = defineEmits<{ (e: 'close'): void }>();

interface HistoricalMessage {
  role: string;
  content: string;
  timestamp?: string;
  backend?: string;
  token_count?: number;
}

const messages = ref<HistoricalMessage[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

function parseLog(raw: unknown): HistoricalMessage[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw as HistoricalMessage[];
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? (parsed as HistoricalMessage[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await superAgentSessionApi.get(props.superAgentId, props.sessionId);
    // Backend serializes conversation_log as a JSON string on the session row.
    messages.value = parseLog((resp as unknown as { conversation_log?: unknown }).conversation_log);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function formatTime(ts?: string): string {
  return safeFormatDateTime(ts);
}

/**
 * Render a historical message's content as parsed markdown HTML.
 *
 * Before v0.7.36 this view rendered ``{{ msg.content }}`` as plain
 * text, so headings, code fences, lists and links in the assistant's
 * stored reply showed as literal markdown characters — ``## Summary``
 * rendered as the string "## Summary" instead of a heading, code
 * fences leaked their backticks, etc. ``marked.parse`` here mirrors
 * the live AiChatPanel's behavior and the matching dark-theme styles
 * below give headings/blockquotes/tables visible weight inside the
 * read-only viewer.
 *
 * The content comes from our own SuperAgent session log (not from an
 * untrusted source), so v-html on the parsed result is acceptable —
 * same trust model the live chat bubble already operates under.
 */
function renderMarkdown(content: string | undefined | null): string {
  return marked.parse(content || '') as string;
}

onMounted(load);
watch(() => props.sessionId, load);
</script>

<template>
  <div class="historical-viewer">
    <div class="viewer-header">
      <div class="header-text">
        <div class="title">Historical session (read-only)</div>
        <div class="subtitle">{{ sessionId }}</div>
      </div>
      <button class="btn-close" type="button" @click="emit('close')">Close</button>
    </div>

    <div v-if="loading" class="state-row">Loading session...</div>
    <div v-else-if="error" class="state-row error">{{ error }}</div>
    <div v-else-if="messages.length === 0" class="state-row muted">
      No messages recorded in this session.
    </div>
    <div v-else class="messages">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="message"
        :class="msg.role"
      >
        <div class="meta">
          <span class="role">{{ msg.role }}</span>
          <span v-if="msg.backend" class="backend">{{ msg.backend }}</span>
          <span class="time">{{ formatTime(msg.timestamp) }}</span>
        </div>
        <div class="content" v-html="renderMarkdown(msg.content)" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.historical-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--bg-primary);
}

.viewer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.header-text {
  min-width: 0;
}

.title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.subtitle {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-close {
  padding: 5px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
}

.btn-close:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  color: var(--text-primary);
}

.state-row {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.state-row.error {
  color: var(--accent-crimson);
}

.state-row.muted {
  color: var(--text-tertiary);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.message {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
}

.message.user {
  border-left: 3px solid var(--accent-cyan);
}

.message.assistant {
  border-left: 3px solid var(--accent-violet);
}

.message.system {
  border-left: 3px solid var(--accent-amber);
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.role {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.backend {
  padding: 1px 6px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-family: var(--font-mono);
}

.time {
  margin-left: auto;
}

.content {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
  /* ``white-space: pre-wrap`` is dropped: marked.parse turns explicit
     newlines into ``<br>`` / paragraph wraps, so pre-wrap would
     double-space lists and add extra blank rows between rendered
     paragraphs. ``word-break: break-word`` stays so long URLs /
     identifiers wrap inside the viewer column. */
  word-break: break-word;
}

/* Mirror the dark-theme markdown rules from vue-styled's ChatBubble
   so the read-only historical viewer renders headings, lists, code
   fences, blockquotes, tables and links with the same visual weight
   as the live chat bubble. v-html injects marked.parse's output
   directly, so children need ``:deep()`` selectors to be matched
   under scoped CSS. */
.content :deep(p) { margin: 0.25rem 0; }
.content :deep(ul),
.content :deep(ol) { padding-inline-start: 1.5rem; margin: 0.25rem 0; }
.content :deep(li) { margin: 0.125rem 0; }
.content :deep(li > ul),
.content :deep(li > ol) { margin: 0.125rem 0; }
.content :deep(pre) {
  background: var(--bg-tertiary, #0a0a0a);
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  overflow-x: auto;
  margin: 0.5rem 0;
  font-size: 12px;
}
.content :deep(code) {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.content :deep(:not(pre) > code) {
  background: var(--bg-tertiary, #0a0a0a);
  padding: 0.05rem 0.3rem;
  border-radius: 4px;
}
.content :deep(h1),
.content :deep(h2),
.content :deep(h3),
.content :deep(h4),
.content :deep(h5),
.content :deep(h6) {
  font-weight: 700;
  line-height: 1.25;
  margin: 0.75rem 0 0.35rem;
  color: var(--text-primary);
}
.content :deep(h1) { font-size: 1.3rem; }
.content :deep(h2) { font-size: 1.1rem; }
.content :deep(h3) { font-size: 1.0rem; }
.content :deep(h4) {
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}
.content :deep(h5),
.content :deep(h6) { font-size: 0.85rem; color: var(--text-secondary); }
.content :deep(blockquote) {
  border-left: 3px solid var(--border-strong, #3f3f46);
  padding: 0.15rem 0.6rem;
  margin: 0.4rem 0;
  color: var(--text-secondary);
}
.content :deep(table) {
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 0.85rem;
}
.content :deep(th),
.content :deep(td) {
  border: 1px solid var(--border-default);
  padding: 0.3rem 0.55rem;
  text-align: left;
}
.content :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}
.content :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border-default);
  margin: 0.6rem 0;
}
.content :deep(a) {
  color: var(--accent-cyan, #60a5fa);
  text-decoration: underline;
}
.content :deep(a:hover) { text-decoration: none; }
.content :deep(strong) { color: var(--text-primary); }
.content :deep(em) { font-style: italic; }
</style>
