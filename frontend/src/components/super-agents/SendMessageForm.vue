<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { SuperAgent, AgentMessagePriority, AgentMessageType } from '../../services/api';
import { agentMessageApi, superAgentApi } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  superAgentId: string;
  allAgents?: Array<{ id: string; name: string }>;
}>();

const emit = defineEmits<{
  (e: 'sent'): void;
  (e: 'cancel'): void;
}>();

const showToast = useToast();

const toAgentId = ref('');
const subject = ref('');
const content = ref('');
const priority = ref<AgentMessagePriority>('normal');
const messageType = ref<AgentMessageType>('message');
const isSending = ref(false);
const agents = ref<Array<{ id: string; name: string }>>([]);

const canSend = computed(() => content.value.trim().length > 0 && !isSending.value);

async function loadAgents() {
  if (props.allAgents && props.allAgents.length > 0) {
    agents.value = props.allAgents.filter((a) => a.id !== props.superAgentId);
    return;
  }
  try {
    const result = await superAgentApi.list();
    agents.value = (result.super_agents || [])
      .filter((sa: SuperAgent) => sa.id !== props.superAgentId)
      .map((sa: SuperAgent) => ({ id: sa.id, name: sa.name }));
  } catch {
    agents.value = [];
  }
}

async function handleSubmit() {
  if (!canSend.value) return;

  isSending.value = true;
  try {
    await agentMessageApi.send(props.superAgentId, {
      to_agent_id: toAgentId.value || undefined,
      message_type: messageType.value,
      priority: priority.value,
      subject: subject.value || undefined,
      content: content.value.trim(),
    });
    showToast('Message sent', 'success');
    emit('sent');
  } catch {
    showToast('Failed to send message', 'error');
  } finally {
    isSending.value = false;
  }
}

onMounted(loadAgents);
</script>

<template>
  <div class="send-message-form">
    <h3 class="form-title">New Message</h3>

    <div class="form-group">
      <label class="form-label">Recipient</label>
      <select v-model="toAgentId" class="form-select">
        <option value="">Broadcast to all</option>
        <option v-for="agent in agents" :key="agent.id" :value="agent.id">
          {{ agent.name }} ({{ agent.id }})
        </option>
      </select>
    </div>

    <div class="form-group">
      <label class="form-label">Subject</label>
      <input
        v-model="subject"
        type="text"
        class="form-input"
        placeholder="Optional subject"
      />
    </div>

    <div class="form-group">
      <label class="form-label">Content <span class="required">*</span></label>
      <textarea
        v-model="content"
        class="form-textarea"
        placeholder="Write your message..."
        rows="4"
      ></textarea>
    </div>

    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Priority</label>
        <select v-model="priority" class="form-select">
          <option value="low">Low</option>
          <option value="normal">Normal</option>
          <option value="high">High</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Type</label>
        <select v-model="messageType" class="form-select">
          <option value="message">Message</option>
          <option value="request">Request</option>
          <option value="artifact">Artifact</option>
        </select>
      </div>
    </div>

    <div class="form-actions">
      <button class="btn-cancel" @click="emit('cancel')">Cancel</button>
      <button class="btn-send" :disabled="!canSend" @click="handleSubmit">
        {{ isSending ? 'Sending...' : 'Send' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.send-message-form {
  padding: 4px 0;
}

.form-title {
  margin: 0 0 12px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.form-group {
  margin-bottom: 10px;
}

.form-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.required {
  color: #ff4d4d;
}

.form-input,
.form-select,
.form-textarea {
  width: 100%;
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  border-color: var(--accent-violet);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

.form-select {
  cursor: pointer;
  appearance: auto;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.btn-cancel {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-cancel:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-send {
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

.btn-send:hover:not(:disabled) {
  background: #9966ff;
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
