<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { superAgentSessionApi } from '../../services/api';

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
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
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
        <div class="content">{{ msg.content }}</div>
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
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
