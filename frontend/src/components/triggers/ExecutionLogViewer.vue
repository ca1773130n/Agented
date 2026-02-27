<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import type { Execution, LogLine, AuthenticatedEventSource } from '../../services/api';
import { executionApi } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  executionId: string;
  isLive?: boolean;
  maxHeight?: string;
  showHeader?: boolean;
}>();

const emit = defineEmits<{
  (e: 'complete', status: string): void;
  (e: 'close'): void;
}>();

const showToast = useToast();

const logLines = ref<LogLine[]>([]);
const execution = ref<Execution | null>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);
const autoScroll = ref(true);
const eventSource = ref<AuthenticatedEventSource | null>(null);
const logContainer = ref<HTMLElement | null>(null);
const elapsedTime = ref(0);
const elapsedInterval = ref<number | null>(null);
const queueOverflowWarning = ref(false);

const formattedDuration = computed(() => {
  const ms = execution.value?.duration_ms || elapsedTime.value;
  if (!ms) return '0s';
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
});

const statusClass = computed(() => {
  switch (execution.value?.status) {
    case 'running': return 'status-running';
    case 'success': return 'status-success';
    case 'failed': return 'status-failed';
    case 'timeout': return 'status-timeout';
    case 'cancelled': return 'status-cancelled';
    case 'interrupted': return 'status-interrupted';
    default: return '';
  }
});

async function loadExecution() {
  try {
    isLoading.value = true;
    error.value = null;
    execution.value = await executionApi.get(props.executionId);

    // Parse existing logs if available
    if (execution.value.stdout_log || execution.value.stderr_log) {
      parseExistingLogs();
    }

    // Start SSE if execution is still running
    if (props.isLive && execution.value.status === 'running') {
      startStreaming();
      startElapsedTimer();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load execution';
  } finally {
    isLoading.value = false;
  }
}

function parseExistingLogs() {
  if (!execution.value) return;

  const lines: LogLine[] = [];
  const timestamp = execution.value.started_at || new Date().toISOString();

  if (execution.value.stdout_log) {
    execution.value.stdout_log.split('\n').forEach((content) => {
      if (content) {
        lines.push({ timestamp, stream: 'stdout', content });
      }
    });
  }

  if (execution.value.stderr_log) {
    execution.value.stderr_log.split('\n').forEach((content) => {
      if (content) {
        lines.push({ timestamp, stream: 'stderr', content });
      }
    });
  }

  logLines.value = lines;
}

function startStreaming() {
  if (eventSource.value) {
    eventSource.value.close();
  }

  queueOverflowWarning.value = false;
  eventSource.value = executionApi.streamLogs(props.executionId, {
    onQueueOverflow: () => { queueOverflowWarning.value = true; },
  });

  eventSource.value.addEventListener('log', (event) => {
    const data = JSON.parse(event.data) as LogLine;
    logLines.value.push(data);
    scrollToBottom();
  });

  eventSource.value.addEventListener('status', (event) => {
    const data = JSON.parse(event.data);
    if (execution.value) {
      execution.value.status = data.status;
    }
  });

  eventSource.value.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    if (execution.value) {
      execution.value.status = data.status;
      execution.value.exit_code = data.exit_code;
      execution.value.error_message = data.error_message;
      execution.value.duration_ms = data.duration_ms;
      execution.value.finished_at = data.finished_at;
    }
    stopStreaming();
    emit('complete', data.status);
  });

  eventSource.value.onerror = () => {
    // Connection lost, reload execution data
    loadExecution();
  };
}

function stopStreaming() {
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
  if (elapsedInterval.value) {
    clearInterval(elapsedInterval.value);
    elapsedInterval.value = null;
  }
}

function startElapsedTimer() {
  if (execution.value?.started_at) {
    const startTime = new Date(execution.value.started_at).getTime();
    elapsedInterval.value = window.setInterval(() => {
      elapsedTime.value = Date.now() - startTime;
    }, 1000);
  }
}

function scrollToBottom() {
  if (autoScroll.value && logContainer.value) {
    nextTick(() => {
      logContainer.value!.scrollTop = logContainer.value!.scrollHeight;
    });
  }
}

function handleScroll() {
  if (!logContainer.value) return;
  const { scrollTop, scrollHeight, clientHeight } = logContainer.value;
  // Auto-scroll is disabled if user scrolls up more than 100px from bottom
  autoScroll.value = scrollHeight - scrollTop - clientHeight < 100;
}

function copyLogs() {
  const text = logLines.value.map(l => `[${l.stream}] ${l.content}`).join('\n');
  navigator.clipboard.writeText(text);
}

const cancelling = ref(false);

async function handleCancel() {
  if (cancelling.value) return;
  cancelling.value = true;
  try {
    await executionApi.cancel(props.executionId);
    showToast('Execution cancelled', 'success');
  } catch (error: any) {
    showToast(error.message || 'Failed to cancel execution', 'error');
  } finally {
    cancelling.value = false;
  }
}

onMounted(() => {
  loadExecution();
});

onUnmounted(() => {
  stopStreaming();
});

watch(() => props.executionId, () => {
  stopStreaming();
  logLines.value = [];
  loadExecution();
});
</script>

<template>
  <div class="log-viewer" :style="{ maxHeight: maxHeight || '500px' }">
    <!-- Header -->
    <div v-if="showHeader !== false" class="log-header">
      <div class="header-left">
        <div class="status-badge" :class="statusClass">
          <span class="status-dot"></span>
          {{ execution?.status || 'loading' }}
        </div>
        <span class="duration">{{ formattedDuration }}</span>
        <button
          v-if="execution?.status === 'running'"
          class="cancel-btn"
          :disabled="cancelling"
          @click="handleCancel"
          title="Cancel execution"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
          {{ cancelling ? 'Cancelling...' : 'Cancel' }}
        </button>
      </div>
      <div class="header-actions">
        <button class="icon-btn" @click="autoScroll = !autoScroll" :title="autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'">
          <svg v-if="autoScroll" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12l7 7 7-7"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 15l-6-6-6 6"/>
          </svg>
        </button>
        <button class="icon-btn" @click="copyLogs" title="Copy logs">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
        </button>
        <button v-if="$emit" class="icon-btn" @click="emit('close')" title="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="isLoading" class="log-loading">
      <div class="spinner"></div>
      <span>Loading execution logs...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="log-error">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M15 9l-6 6M9 9l6 6"/>
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- Log content -->
    <div
      v-else
      class="log-content-wrapper"
    >
      <!-- Queue overflow warning -->
      <div v-if="queueOverflowWarning" class="queue-overflow-banner">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        Some log lines were dropped — output may be incomplete.
      </div>
    <div
      ref="logContainer"
      class="log-content"
      @scroll="handleScroll"
    >
      <div v-if="logLines.length === 0" class="log-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
        </svg>
        <span>{{ execution?.status === 'running' ? 'Waiting for output...' : 'No output recorded' }}</span>
      </div>

      <div v-for="(line, index) in logLines" :key="index" class="log-line" :class="line.stream">
        <span class="line-number">{{ index + 1 }}</span>
        <span class="line-stream">{{ line.stream === 'stderr' ? 'ERR' : 'OUT' }}</span>
        <span class="line-content">{{ line.content }}</span>
      </div>

      <!-- Running indicator -->
      <div v-if="execution?.status === 'running'" class="log-line running-indicator">
        <span class="line-number"></span>
        <span class="line-stream"></span>
        <span class="cursor-blink">_</span>
      </div>
    </div>

    <!-- Footer with error message if failed -->
    <div v-if="execution?.error_message" class="log-footer error">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 8v4M12 16h.01"/>
      </svg>
      <span>{{ execution.error_message }}</span>
    </div>
    </div>
  </div>
</template>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  overflow: hidden;
  font-family: var(--font-mono);
}

.log-content-wrapper {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.queue-overflow-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: rgba(245, 158, 11, 0.1);
  border-bottom: 1px solid rgba(245, 158, 11, 0.3);
  color: #f59e0b;
  font-size: 0.78rem;
  font-family: var(--font-sans, sans-serif);
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-running {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-running .status-dot {
  background: var(--accent-cyan);
  animation: pulse 1.5s infinite;
}

.status-success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-success .status-dot {
  background: var(--accent-emerald);
}

.status-failed, .status-timeout {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.status-failed .status-dot, .status-timeout .status-dot {
  background: var(--accent-crimson);
}

.status-cancelled {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.status-cancelled .status-dot {
  background: #f59e0b;
}

.status-interrupted {
  background: rgba(107, 114, 128, 0.15);
  color: #9ca3af;
}

.status-interrupted .status-dot {
  background: #9ca3af;
}

.cancel-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cancel-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

.cancel-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn svg {
  width: 12px;
  height: 12px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.duration {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.icon-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.icon-btn svg {
  width: 14px;
  height: 14px;
}

.log-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 0;
  min-height: 200px;
}

.log-loading, .log-error, .log-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.log-loading svg, .log-error svg, .log-empty svg {
  width: 32px;
  height: 32px;
  opacity: 0.5;
}

.log-error {
  color: var(--accent-crimson);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.log-line {
  display: flex;
  align-items: flex-start;
  padding: 2px 16px;
  font-size: 0.8rem;
  line-height: 1.5;
}

.log-line:hover {
  background: var(--bg-elevated);
}

.line-number {
  width: 40px;
  color: var(--text-muted);
  text-align: right;
  padding-right: 12px;
  flex-shrink: 0;
  user-select: none;
}

.line-stream {
  width: 36px;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 4px;
  border-radius: 3px;
  margin-right: 12px;
  text-align: center;
  flex-shrink: 0;
}

.log-line.stdout .line-stream {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.log-line.stderr .line-stream {
  background: var(--accent-amber-dim, rgba(255, 170, 0, 0.15));
  color: var(--accent-amber, #ffaa00);
}

.line-content {
  flex: 1;
  color: var(--text-secondary);
  word-break: break-all;
  white-space: pre-wrap;
}

.log-line.stderr .line-content {
  color: var(--accent-amber, #ffaa00);
}

.running-indicator {
  opacity: 0.7;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--accent-cyan);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.log-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
  font-size: 0.8rem;
}

.log-footer.error {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.log-footer svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}
</style>
