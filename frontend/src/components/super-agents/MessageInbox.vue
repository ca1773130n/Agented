<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import type { AgentMessage } from '../../services/api';
import { agentMessageApi, API_BASE } from '../../services/api';
import SendMessageForm from './SendMessageForm.vue';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  superAgentId: string;
}>();

const emit = defineEmits<{
  (e: 'selectThread', fromAgentId: string, toAgentId: string): void;
}>();

const showToast = useToast();

const inbox = ref<AgentMessage[]>([]);
const outbox = ref<AgentMessage[]>([]);
const activeView = ref<'inbox' | 'outbox'>('inbox');
const showSendForm = ref(false);
const sseError = ref(false);
const sseRetryCount = ref(0);
let eventSource: EventSource | null = null;

const currentMessages = computed(() =>
  activeView.value === 'inbox' ? inbox.value : outbox.value,
);

const unreadCount = computed(() =>
  inbox.value.filter((m) => m.status !== 'read').length,
);

async function loadInbox() {
  try {
    const result = await agentMessageApi.listInbox(props.superAgentId);
    inbox.value = result.messages || [];
  } catch {
    // silently fail
  }
}

async function loadOutbox() {
  try {
    const result = await agentMessageApi.listOutbox(props.superAgentId);
    outbox.value = result.messages || [];
  } catch {
    // silently fail
  }
}

async function loadAll() {
  await Promise.all([loadInbox(), loadOutbox()]);
}

async function markRead(messageId: string) {
  try {
    await agentMessageApi.markRead(props.superAgentId, messageId);
    await loadInbox();
  } catch {
    showToast('Failed to mark message as read', 'error');
  }
}

async function deleteMessage(msg: AgentMessage, event: Event) {
  event.stopPropagation();
  try {
    await agentMessageApi.delete(props.superAgentId, msg.id);
    showToast('Message deleted', 'success');
    await loadAll();
  } catch {
    showToast('Failed to delete message', 'error');
  }
}

function connectSSE() {
  closeSSE();
  eventSource = new EventSource(
    `${API_BASE}/admin/super-agents/${props.superAgentId}/messages/stream`,
  );
  eventSource.addEventListener('message', () => {
    sseError.value = false;
    sseRetryCount.value = 0;
    loadInbox();
  });
  eventSource.addEventListener('error', () => {
    sseError.value = true;
    sseRetryCount.value++;
    if (sseRetryCount.value > 3 && eventSource) {
      eventSource.close();
    }
  });
}

function closeSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function openThread(msg: AgentMessage) {
  if (activeView.value === 'inbox') {
    if (msg.status !== 'read') {
      markRead(msg.id);
    }
    emit('selectThread', msg.from_agent_id, props.superAgentId);
  } else {
    emit('selectThread', props.superAgentId, msg.to_agent_id || '');
  }
}

function onSent() {
  showSendForm.value = false;
  loadAll();
}

function priorityClass(priority: string): string {
  if (priority === 'high') return 'priority-high';
  if (priority === 'low') return 'priority-low';
  return 'priority-normal';
}

function statusClass(status: string): string {
  if (status === 'pending') return 'status-pending';
  if (status === 'delivered') return 'status-delivered';
  if (status === 'read') return 'status-read';
  return 'status-expired';
}

function formatTimestamp(ts?: string): string {
  if (!ts) return '';
  return new Date(ts).toLocaleString();
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + '...';
}

onMounted(() => {
  loadAll();
  connectSSE();
});

onUnmounted(() => {
  closeSSE();
});
</script>

<template>
  <div class="message-inbox">
    <!-- Header bar -->
    <div class="inbox-header">
      <div class="view-toggles">
        <button
          :class="['toggle-btn', { active: activeView === 'inbox' }]"
          @click="activeView = 'inbox'"
        >
          Inbox
          <span v-if="unreadCount > 0" class="unread-badge">{{ unreadCount }}</span>
        </button>
        <button
          :class="['toggle-btn', { active: activeView === 'outbox' }]"
          @click="activeView = 'outbox'"
        >
          Outbox
        </button>
      </div>
      <button class="new-message-btn" @click="showSendForm = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14" />
        </svg>
        New Message
      </button>
    </div>

    <!-- SSE error banner -->
    <div v-if="sseError" class="sse-error-banner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>Live updates unavailable</span>
      <button class="reconnect-btn" @click="connectSSE">Reconnect</button>
    </div>

    <!-- Send form overlay -->
    <div v-if="showSendForm" class="send-form-overlay">
      <SendMessageForm
        :superAgentId="superAgentId"
        @sent="onSent"
        @cancel="showSendForm = false"
      />
    </div>

    <!-- Message list -->
    <div v-if="currentMessages.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
      <p>No messages yet</p>
    </div>

    <div v-else class="message-list">
      <div
        v-for="msg in currentMessages"
        :key="msg.id"
        :class="['message-card', { unread: msg.status !== 'read' && activeView === 'inbox' }]"
        @click="openThread(msg)"
      >
        <div class="message-top">
          <span :class="['priority-badge', priorityClass(msg.priority)]">
            {{ msg.priority }}
          </span>
          <span class="message-agent">
            {{ activeView === 'inbox' ? `From: ${msg.from_agent_id}` : `To: ${msg.to_agent_id || 'broadcast'}` }}
          </span>
          <span :class="['status-dot', statusClass(msg.status)]" :title="msg.status"></span>
          <button
            class="delete-msg-btn"
            title="Delete message"
            @click="deleteMessage(msg, $event)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
        <div class="message-subject">
          {{ msg.subject || '(no subject)' }}
        </div>
        <div class="message-preview">
          {{ truncate(msg.content, 100) }}
        </div>
        <div class="message-time">
          {{ formatTimestamp(msg.created_at) }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-inbox {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.inbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-default);
}

.view-toggles {
  display: flex;
  gap: 4px;
}

.toggle-btn {
  position: relative;
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.toggle-btn:hover {
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.toggle-btn.active {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.08);
}

.unread-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 6px;
  background: #ff4d4d;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
}

.new-message-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--accent-violet);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.new-message-btn:hover {
  background: #9966ff;
}

.new-message-btn svg {
  width: 14px;
  height: 14px;
}

.send-form-overlay {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-state svg {
  width: 40px;
  height: 40px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.empty-state p {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.message-card {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.message-card:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  border-color: var(--border-default);
}

.message-card.unread {
  border-left: 3px solid var(--accent-cyan);
}

.message-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.priority-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.priority-high {
  background: rgba(255, 77, 77, 0.15);
  color: #ff4d4d;
}

.priority-normal {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  color: var(--text-tertiary);
}

.priority-low {
  background: transparent;
  color: var(--text-tertiary);
  opacity: 0.7;
}

.message-agent {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-pending {
  background: #ffc107;
}

.status-delivered {
  background: #0088ff;
}

.status-read {
  background: var(--accent-emerald, #00ff88);
}

.status-expired {
  background: var(--text-tertiary);
}

.message-subject {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.message-preview {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.message-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.delete-msg-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
}

.message-card:hover .delete-msg-btn {
  opacity: 1;
}

.delete-msg-btn:hover {
  background: var(--accent-crimson-dim, rgba(255, 51, 102, 0.15));
  color: var(--accent-crimson, #ff3366);
}

.sse-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: rgba(255, 170, 0, 0.1);
  border: 1px solid rgba(255, 170, 0, 0.25);
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--accent-amber, #ffaa00);
}

.sse-error-banner svg {
  flex-shrink: 0;
  color: var(--accent-amber, #ffaa00);
}

.sse-error-banner span {
  flex: 1;
}

.reconnect-btn {
  padding: 3px 10px;
  background: rgba(255, 170, 0, 0.15);
  border: 1px solid rgba(255, 170, 0, 0.3);
  border-radius: 4px;
  color: var(--accent-amber, #ffaa00);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.reconnect-btn:hover {
  background: rgba(255, 170, 0, 0.25);
}
</style>
