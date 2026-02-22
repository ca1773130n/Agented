<script setup lang="ts">
import { ref, onUnmounted, nextTick } from 'vue';
import { setupApi, ApiError } from '../../services/api';
import type { SetupQuestion } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  projectId: string;
  initialCommand?: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'completed'): void;
}>();

const showToast = useToast();

// State
const executionId = ref<string | null>(null);
const status = ref<'idle' | 'running' | 'waiting_input' | 'complete' | 'error'>('idle');
const logs = ref<string[]>([]);
const currentQuestion = ref<SetupQuestion | null>(null);
const userAnswer = ref('');
const selectedOptions = ref<string[]>([]);
const command = ref(props.initialCommand || '');
const isSubmitting = ref(false);
const isCancelling = ref(false);
const exitCode = ref<number | null>(null);
const errorMessage = ref<string | null>(null);
let eventSource: EventSource | null = null;
let retryCount = 0;
const MAX_RETRIES = 3;
const logContainer = ref<HTMLElement | null>(null);

function scrollToBottom() {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTo(0, logContainer.value.scrollHeight);
    }
  });
}

async function startSetup() {
  if (!command.value.trim()) {
    showToast('Please enter a setup command', 'error');
    return;
  }

  try {
    const result = await setupApi.start(props.projectId, command.value.trim());
    executionId.value = result.execution_id;
    status.value = 'running';
    logs.value = [];
    retryCount = 0;
    connectSSE();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to start setup';
    showToast(message, 'error');
    status.value = 'error';
    errorMessage.value = message;
  }
}

function connectSSE() {
  if (!executionId.value) return;

  eventSource = new EventSource(setupApi.streamUrl(executionId.value));

  eventSource.addEventListener('log', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (data.content) {
        logs.value.push(data.content);
        scrollToBottom();
      }
    } catch {
      // ignore parse errors
    }
  });

  eventSource.addEventListener('question', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      currentQuestion.value = {
        interaction_id: data.interaction_id,
        question_type: data.question_type || 'text',
        prompt: data.prompt || '',
        options: data.options,
      };
      status.value = 'waiting_input';
      userAnswer.value = '';
      selectedOptions.value = [];
      scrollToBottom();
    } catch {
      // ignore parse errors
    }
  });

  eventSource.addEventListener('complete', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      status.value = 'complete';
      exitCode.value = data.exit_code ?? null;
      errorMessage.value = data.error_message ?? null;
    } catch {
      status.value = 'complete';
    }
    closeEventSource();
    if (exitCode.value === 0) {
      emit('completed');
    }
  });

  eventSource.addEventListener('error', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      status.value = 'error';
      errorMessage.value = data.error_message || data.message || 'Setup error';
    } catch {
      status.value = 'error';
      errorMessage.value = 'Setup error';
    }
    closeEventSource();
  });

  eventSource.onerror = () => {
    if (status.value === 'running' || status.value === 'waiting_input') {
      closeEventSource();
      if (retryCount < MAX_RETRIES) {
        retryCount++;
        setTimeout(() => connectSSE(), 2000);
      } else {
        status.value = 'error';
        errorMessage.value = 'Lost connection to setup stream';
      }
    }
  };
}

async function submitAnswer() {
  if (!currentQuestion.value || !executionId.value) return;

  isSubmitting.value = true;
  try {
    let response: Record<string, unknown>;
    if (currentQuestion.value.question_type === 'multiselect') {
      response = { answer: selectedOptions.value };
    } else {
      response = { answer: userAnswer.value };
    }

    await setupApi.respond(
      executionId.value,
      currentQuestion.value.interaction_id,
      response,
    );

    // Add submitted answer to log
    const answerDisplay = currentQuestion.value.question_type === 'multiselect'
      ? selectedOptions.value.join(', ')
      : currentQuestion.value.question_type === 'password'
        ? '***'
        : userAnswer.value;
    logs.value.push(`> ${answerDisplay}`);

    currentQuestion.value = null;
    status.value = 'running';
    userAnswer.value = '';
    selectedOptions.value = [];
    scrollToBottom();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to submit response';
    showToast(message, 'error');
  } finally {
    isSubmitting.value = false;
  }
}

async function cancelSetup() {
  if (!executionId.value) return;

  isCancelling.value = true;
  try {
    await setupApi.cancel(executionId.value);
    closeEventSource();
    status.value = 'error';
    errorMessage.value = 'Setup cancelled by user';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to cancel setup';
    showToast(message, 'error');
  } finally {
    isCancelling.value = false;
  }
}

function resetSetup() {
  closeEventSource();
  executionId.value = null;
  status.value = 'idle';
  logs.value = [];
  currentQuestion.value = null;
  userAnswer.value = '';
  selectedOptions.value = [];
  isSubmitting.value = false;
  isCancelling.value = false;
  exitCode.value = null;
  errorMessage.value = null;
  retryCount = 0;
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

onUnmounted(() => {
  closeEventSource();
});
</script>

<template>
  <div class="interactive-setup">
    <!-- Header -->
    <div class="setup-header">
      <h3>Interactive Setup</h3>
      <div class="setup-header-actions">
        <button
          v-if="status === 'running' || status === 'waiting_input'"
          @click="cancelSetup"
          :disabled="isCancelling"
          class="cancel-btn"
        >
          {{ isCancelling ? 'Cancelling...' : 'Cancel' }}
        </button>
        <button @click="emit('close')" class="close-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Command Input (shown when idle) -->
    <div v-if="status === 'idle'" class="command-input-section">
      <label>Setup Command</label>
      <div class="command-row">
        <input
          v-model="command"
          placeholder="e.g., claude setup-plugin --interactive"
          @keyup.enter="startSetup"
        />
        <button @click="startSetup" :disabled="!command.trim()" class="start-btn">
          Run Setup
        </button>
      </div>
    </div>

    <!-- Log Output -->
    <div v-if="status !== 'idle'" class="log-output" ref="logContainer">
      <div v-for="(line, i) in logs" :key="i" class="log-line">{{ line }}</div>
      <!-- Inline Question Form (appears below logs when waiting) -->
      <div v-if="currentQuestion" class="question-form">
        <div class="question-prompt">{{ currentQuestion.prompt }}</div>

        <!-- Text input -->
        <input
          v-if="currentQuestion.question_type === 'text'"
          v-model="userAnswer"
          type="text"
          class="question-input"
          placeholder="Type your answer..."
          @keyup.enter="submitAnswer"
          autofocus
        />

        <!-- Password input -->
        <input
          v-if="currentQuestion.question_type === 'password'"
          v-model="userAnswer"
          type="password"
          class="question-input"
          placeholder="Enter value..."
          @keyup.enter="submitAnswer"
          autofocus
        />

        <!-- Select dropdown -->
        <select
          v-if="currentQuestion.question_type === 'select'"
          v-model="userAnswer"
          class="question-select"
        >
          <option value="" disabled>Select an option...</option>
          <option v-for="opt in currentQuestion.options" :key="opt" :value="opt">
            {{ opt }}
          </option>
        </select>

        <!-- Multiselect checkboxes -->
        <div v-if="currentQuestion.question_type === 'multiselect'" class="multiselect-options">
          <label v-for="opt in currentQuestion.options" :key="opt" class="checkbox-label">
            <input type="checkbox" :value="opt" v-model="selectedOptions" />
            <span>{{ opt }}</span>
          </label>
        </div>

        <button
          @click="submitAnswer"
          :disabled="isSubmitting || (!userAnswer && selectedOptions.length === 0)"
          class="submit-btn"
        >
          {{ isSubmitting ? 'Submitting...' : 'Submit' }}
        </button>
      </div>
    </div>

    <!-- Status Bar -->
    <div v-if="status !== 'idle'" class="status-bar" :class="status">
      <span v-if="status === 'running'" class="status-dot running"></span>
      <span v-if="status === 'waiting_input'" class="status-dot waiting"></span>
      <span v-if="status === 'complete'" class="status-dot complete"></span>
      <span v-if="status === 'error'" class="status-dot error"></span>
      <span class="status-text">
        {{ status === 'running' ? 'Running...' :
           status === 'waiting_input' ? 'Waiting for input...' :
           status === 'complete' ? (exitCode === 0 ? 'Setup complete' : `Exited with code ${exitCode}`) :
           errorMessage || 'Error' }}
      </span>
      <button
        v-if="status === 'complete' || status === 'error'"
        @click="resetSetup"
        class="reset-btn"
      >
        Run Again
      </button>
    </div>
  </div>
</template>

<style scoped>
.interactive-setup {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.setup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.setup-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.setup-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cancel-btn {
  padding: 6px 12px;
  background: var(--accent-crimson-dim, rgba(255, 64, 129, 0.15));
  color: var(--accent-crimson, #ff4081);
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.cancel-btn:hover:not(:disabled) {
  border-color: var(--accent-crimson, #ff4081);
}

.cancel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.close-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.command-input-section {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.command-input-section label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.command-row {
  display: flex;
  gap: 8px;
}

.command-row input {
  flex: 1;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: var(--font-mono);
}

.command-row input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.command-row input::placeholder {
  color: var(--text-tertiary);
}

.start-btn {
  padding: 10px 20px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.start-btn:hover:not(:disabled) {
  background: #00c4ee;
}

.start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.log-output {
  max-height: 400px;
  overflow-y: auto;
  padding: 16px 20px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  background: var(--bg-primary);
  white-space: pre-wrap;
}

.log-line {
  line-height: 1.5;
  color: var(--text-secondary);
}

.question-form {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border-left: 3px solid var(--accent-cyan);
}

.question-prompt {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
  font-family: var(--font-sans, sans-serif);
  font-size: 0.9rem;
}

.question-input,
.question-select {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.9rem;
  box-sizing: border-box;
}

.question-input:focus,
.question-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.question-input::placeholder {
  color: var(--text-tertiary);
}

.multiselect-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  cursor: pointer;
  font-family: var(--font-sans, sans-serif);
}

.checkbox-label input[type="checkbox"] {
  accent-color: var(--accent-cyan);
}

.submit-btn {
  display: inline-block;
  margin-top: 12px;
  padding: 8px 20px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.submit-btn:hover:not(:disabled) {
  background: #00c4ee;
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-subtle);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.running {
  background: var(--accent-cyan);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot.waiting {
  background: var(--accent-amber, #ffaa00);
}

.status-dot.complete {
  background: var(--accent-emerald, #00ff88);
}

.status-dot.error {
  background: var(--accent-crimson, #ff4081);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-text {
  flex: 1;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.reset-btn {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.reset-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
  border-color: var(--accent-cyan);
}
</style>
