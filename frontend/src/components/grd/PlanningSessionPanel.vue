<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue';
import type { PlanningQuestion } from '../../composables/usePlanningSession';
import { renderMarkdown, attachCodeCopyHandlers } from '../../composables/useMarkdown';
import { useAutoScroll } from '../../composables/useAutoScroll';

const props = defineProps<{
  outputLines: string[];
  status: 'idle' | 'running' | 'waiting_input' | 'complete' | 'error';
  currentQuestion: PlanningQuestion | null;
  exitCode: number | null;
}>();

const emit = defineEmits<{
  sendAnswer: [answer: string];
  stop: [];
  clear: [];
}>();

// Answer state
const textAnswer = ref('');
const selectedOptions = ref<string[]>([]);

// Auto-scroll
const outputContainer = ref<HTMLElement | null>(null);
const { forceScrollToBottom } = useAutoScroll(outputContainer);

// Rendered markdown from output lines
const renderedOutput = computed(() => {
  const content = props.outputLines.join('\n');
  if (!content) return '';
  return renderMarkdown(content);
});

// Re-attach code copy handlers when output changes
watch(renderedOutput, () => {
  nextTick(() => {
    if (outputContainer.value) {
      attachCodeCopyHandlers(outputContainer.value);
    }
  });
});

// Scroll to bottom when new output arrives
watch(
  () => props.outputLines.length,
  () => {
    nextTick(() => {
      forceScrollToBottom();
    });
  }
);

// Status display
const statusLabel = computed(() => {
  switch (props.status) {
    case 'running':
      return 'Running...';
    case 'waiting_input':
      return 'Waiting for input...';
    case 'complete':
      return props.exitCode === 0 ? 'Complete' : `Exited with code ${props.exitCode}`;
    case 'error':
      return 'Error';
    default:
      return 'Idle';
  }
});

function handleSendText() {
  const answer = textAnswer.value.trim();
  if (!answer) return;
  emit('sendAnswer', answer);
  textAnswer.value = '';
}

function handleSelectOption(option: string) {
  emit('sendAnswer', option);
}

function handleSendMultiselect() {
  if (selectedOptions.value.length === 0) return;
  emit('sendAnswer', selectedOptions.value.join(','));
  selectedOptions.value = [];
}

function handleTextKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSendText();
  }
}
</script>

<template>
  <div class="session-panel">
    <!-- Status bar -->
    <div class="session-header">
      <div class="session-status">
        <span class="status-dot" :class="status"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </div>
      <div class="session-actions">
        <button
          v-if="status === 'running' || status === 'waiting_input'"
          class="action-btn stop-btn"
          @click="emit('stop')"
        >
          Stop
        </button>
        <button
          v-if="status === 'complete' || status === 'error'"
          class="action-btn clear-btn"
          @click="emit('clear')"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Output -->
    <div ref="outputContainer" class="session-output">
      <div class="output-content">
        <div
          v-if="renderedOutput"
          class="markdown-body"
          v-html="renderedOutput"
        ></div>
        <div v-else-if="status === 'idle'" class="empty-state">
          Select a command to start a planning session.
        </div>
        <div v-else-if="status === 'running' && outputLines.length === 0" class="empty-state">
          Waiting for output...
        </div>

        <!-- Question widget -->
        <div v-if="currentQuestion" class="question-widget">
          <div class="question-prompt">{{ currentQuestion.prompt }}</div>

          <!-- Select: clickable option buttons -->
          <div v-if="currentQuestion.question_type === 'select'" class="select-options">
            <button
              v-for="opt in currentQuestion.options"
              :key="opt"
              class="option-btn"
              @click="handleSelectOption(opt)"
            >
              {{ opt }}
            </button>
          </div>

          <!-- Multiselect: checkboxes + submit -->
          <div v-else-if="currentQuestion.question_type === 'multiselect'" class="multiselect-options">
            <label v-for="opt in currentQuestion.options" :key="opt" class="checkbox-label">
              <input type="checkbox" :value="opt" v-model="selectedOptions" />
              <span>{{ opt }}</span>
            </label>
            <button
              class="submit-btn"
              :disabled="selectedOptions.length === 0"
              @click="handleSendMultiselect"
            >
              Submit
            </button>
          </div>

          <!-- Text / Password input -->
          <div v-else class="text-input-row">
            <input
              v-model="textAnswer"
              :type="currentQuestion.question_type === 'password' ? 'password' : 'text'"
              class="text-input"
              placeholder="Type your answer..."
              @keydown="handleTextKeydown"
              autofocus
            />
            <button
              class="submit-btn"
              :disabled="!textAnswer.trim()"
              @click="handleSendText"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
  height: 100%;
}

.session-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.session-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.idle {
  background: var(--text-muted);
}

.status-dot.running {
  background: var(--accent-cyan);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-dot.waiting_input {
  background: var(--accent-amber, #ffaa00);
}

.status-dot.complete {
  background: var(--accent-emerald, #00ff88);
}

.status-dot.error {
  background: var(--accent-crimson, #ff4081);
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}

.status-text {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.session-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

.stop-btn {
  background: var(--accent-crimson-dim, rgba(255, 64, 129, 0.15));
  color: var(--accent-crimson, #ff4081);
  border: 1px solid transparent;
}

.stop-btn:hover {
  border-color: var(--accent-crimson, #ff4081);
}

.clear-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}

.clear-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
}

.session-output {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.output-content {
  padding: 16px;
}

.empty-state {
  color: var(--text-tertiary);
  font-size: 0.85rem;
  text-align: center;
  padding: 40px 20px;
}

/* Markdown styling */
.markdown-body {
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--text-primary);
  word-wrap: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
}

.markdown-body :deep(h1) {
  font-size: 1.2rem;
}
.markdown-body :deep(h2) {
  font-size: 1.05rem;
}
.markdown-body :deep(h3) {
  font-size: 0.95rem;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 8px;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin-bottom: 4px;
}

.markdown-body :deep(a) {
  color: var(--accent-cyan);
}

.markdown-body :deep(.code-block-wrapper) {
  margin: 8px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}

.markdown-body :deep(.code-block-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  font-size: 0.72rem;
}

.markdown-body :deep(.code-lang) {
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.markdown-body :deep(.code-copy-btn) {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.72rem;
  cursor: pointer;
  font-family: inherit;
}

.markdown-body :deep(.code-copy-btn:hover) {
  color: var(--text-primary);
}

.markdown-body :deep(pre) {
  margin: 0;
  padding: 12px;
  background: var(--bg-primary);
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  font-size: 0.8rem;
  font-family: var(--font-mono);
}

.markdown-body :deep(.inline-code) {
  padding: 1px 5px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  font-size: 0.82em;
  font-family: var(--font-mono);
}

/* Question widget */
.question-widget {
  margin-top: 16px;
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border-left: 3px solid var(--accent-cyan);
}

.question-prompt {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
  font-size: 0.88rem;
}

.select-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.option-btn {
  padding: 8px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
}

.option-btn:hover {
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim, rgba(0, 180, 216, 0.08));
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
  font-size: 0.85rem;
  cursor: pointer;
}

.checkbox-label input[type='checkbox'] {
  accent-color: var(--accent-cyan);
}

.text-input-row {
  display: flex;
  gap: 8px;
}

.text-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.text-input::placeholder {
  color: var(--text-tertiary);
}

.submit-btn {
  padding: 8px 16px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
