<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { AgentMessage } from '../../services/api';
import { agentMessageApi } from '../../services/api';

const props = defineProps<{
  superAgentId: string;
  peerAgentId: string;
}>();

const emit = defineEmits<{
  (e: 'back'): void;
}>();

const inbox = ref<AgentMessage[]>([]);
const outbox = ref<AgentMessage[]>([]);

const threadMessages = computed(() => {
  const fromPeer = inbox.value.filter((m) => m.from_agent_id === props.peerAgentId);
  const toPeer = outbox.value.filter((m) => m.to_agent_id === props.peerAgentId);
  const merged = [...fromPeer, ...toPeer];
  merged.sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
    return ta - tb;
  });
  return merged;
});

function isOwnMessage(msg: AgentMessage): boolean {
  return msg.from_agent_id === props.superAgentId;
}

function formatTimestamp(ts?: string): string {
  if (!ts) return '';
  return new Date(ts).toLocaleString();
}

async function loadMessages() {
  try {
    const [inboxResult, outboxResult] = await Promise.all([
      agentMessageApi.listInbox(props.superAgentId),
      agentMessageApi.listOutbox(props.superAgentId),
    ]);
    inbox.value = inboxResult.messages || [];
    outbox.value = outboxResult.messages || [];
  } catch {
    // silently fail
  }
}

onMounted(loadMessages);
</script>

<template>
  <div class="message-thread">
    <div class="thread-header">
      <button class="btn-back" @click="emit('back')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <span class="peer-label">Conversation with {{ peerAgentId }}</span>
    </div>

    <div v-if="threadMessages.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
      </svg>
      <p>No messages with this agent</p>
    </div>

    <div v-else class="thread-list">
      <div
        v-for="msg in threadMessages"
        :key="msg.id"
        :class="['thread-bubble', { own: isOwnMessage(msg), peer: !isOwnMessage(msg) }]"
      >
        <div class="bubble-content">
          <div v-if="msg.priority === 'high'" class="bubble-priority">HIGH</div>
          <div class="bubble-text">{{ msg.content }}</div>
          <div class="bubble-meta">
            <span :class="['bubble-status', `status-${msg.status}`]">{{ msg.status }}</span>
            <span class="bubble-time">{{ formatTimestamp(msg.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-thread {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.thread-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-default);
}

.btn-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

.peer-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
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

.thread-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
  padding: 4px 0;
}

.thread-bubble {
  display: flex;
  max-width: 80%;
}

.thread-bubble.own {
  align-self: flex-end;
}

.thread-bubble.peer {
  align-self: flex-start;
}

.bubble-content {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
}

.own .bubble-content {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  border-bottom-right-radius: 2px;
}

.peer .bubble-content {
  background: var(--bg-tertiary);
  border-bottom-left-radius: 2px;
}

.bubble-priority {
  font-size: 10px;
  font-weight: 700;
  color: #ff4d4d;
  text-transform: uppercase;
  margin-bottom: 2px;
}

.bubble-text {
  color: var(--text-primary);
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.bubble-status {
  font-size: 10px;
  font-weight: 500;
  text-transform: capitalize;
}

.bubble-status.status-pending {
  color: #ffc107;
}

.bubble-status.status-delivered {
  color: #0088ff;
}

.bubble-status.status-read {
  color: var(--accent-emerald, #00ff88);
}

.bubble-status.status-expired {
  color: var(--text-tertiary);
}

.bubble-time {
  font-size: 10px;
  color: var(--text-tertiary);
}
</style>
