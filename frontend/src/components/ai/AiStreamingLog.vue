<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';

interface LogEntry {
  type: string;
  text: string;
}

const props = withDefaults(
  defineProps<{
    log: LogEntry[];
    isStreaming: boolean;
    phase?: string;
    hint?: string;
    assistantName?: string;
  }>(),
  {
    assistantName: 'AI',
  },
);

const logContainer = ref<HTMLElement | null>(null);

watch(() => props.log.length, () => {
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight;
    }
  });
});
</script>

<template>
  <div class="ai-streaming-log">
    <div class="streaming-header">
      <div class="streaming-spinner"></div>
      <span>{{ phase || 'Processing...' }}</span>
    </div>
    <div class="streaming-log-container" ref="logContainer">
      <div v-for="(entry, i) in log" :key="i" class="log-line" :class="'log-' + entry.type">
        <span class="log-prefix" v-if="entry.type === 'phase'">SYSTEM</span>
        <span class="log-prefix" v-else-if="entry.type === 'thinking'">{{ assistantName.toUpperCase() }}</span>
        <span class="log-prefix" v-else-if="entry.type === 'output'">OUTPUT</span>
        <span class="log-prefix" v-else-if="entry.type === 'error'">ERROR</span>
        <span class="log-text">{{ entry.text }}</span>
      </div>
    </div>
    <p v-if="hint" class="streaming-hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.ai-streaming-log {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.streaming-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--accent-cyan, #00d4ff);
  font-weight: 500;
  font-size: 0.9rem;
}

.streaming-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(0, 212, 255, 0.2);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.streaming-log-container {
  background: #0a0a12;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 0.75rem;
  max-height: 280px;
  overflow-y: auto;
  font-family: 'Geist Mono', 'SF Mono', 'Fira Code', monospace;
  font-size: 0.75rem;
  line-height: 1.7;
}

.log-line {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 1px 0;
}

.log-prefix {
  display: inline-block;
  min-width: 52px;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 1px 5px;
  border-radius: 3px;
  text-align: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.log-text {
  white-space: pre-wrap;
  word-break: break-all;
}

.log-phase .log-prefix {
  background: rgba(0, 212, 255, 0.2);
  color: #00d4ff;
}
.log-phase .log-text {
  color: #00d4ff;
  font-weight: 500;
}

.log-thinking .log-prefix {
  background: rgba(168, 85, 247, 0.2);
  color: #c084fc;
}
.log-thinking .log-text {
  color: #a0a0b8;
}

.log-output .log-prefix {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}
.log-output .log-text {
  color: #e0e0e8;
}

.log-error .log-prefix {
  background: rgba(255, 77, 77, 0.2);
  color: #ff4d4d;
}
.log-error .log-text {
  color: #ff4d4d;
}

.streaming-hint {
  font-size: 0.75rem;
  color: var(--text-muted, #404050);
  font-weight: 400;
  text-align: center;
}
</style>
