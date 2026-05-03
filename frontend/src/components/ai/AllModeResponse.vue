<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { BackendResponse, SynthesisState } from '../../composables/useAllMode';
import { renderMarkdown } from '../../composables/useMarkdown';

const BACKEND_COLORS: Record<string, string> = {
  claude: '#8855ff',
  codex: '#22c55e',
  gemini: '#3b82f6',
  opencode: '#f59e0b',
};

const props = withDefaults(
  defineProps<{
    responses: Map<string, BackendResponse>;
    synthesisState: SynthesisState | null;
    /** When true, starts collapsed with a toggle to expand (used in compound mode) */
    collapsible?: boolean;
  }>(),
  { collapsible: false },
);

const expanded = ref(false);
const backends = computed(() => Array.from(props.responses.keys()));

/** Summary line for collapsed state */
const collapsedSummary = computed(() => {
  const total = backends.value.length;
  const complete = backends.value.filter(
    (b) => props.responses.get(b)?.status === 'complete',
  ).length;
  const streaming = total - complete;
  if (streaming > 0) {
    return `${complete}/${total} backends responded`;
  }
  return `${total} backend responses`;
});

function backendColor(backend: string): string {
  return BACKEND_COLORS[backend] || '#6b7280';
}

function statusLabel(status: string): string {
  switch (status) {
    case 'streaming': return 'streaming';
    case 'complete': return '';
    case 'error': return 'error';
    case 'timeout': return 'timed out';
    default: return '';
  }
}

watch(
  () => props.collapsible,
  (val) => {
    if (!val) expanded.value = false;
  },
);
</script>

<template>
  <div class="all-mode-responses" v-if="backends.length > 0">
    <!-- Collapsible header for compound mode -->
    <button
      v-if="collapsible"
      class="collapse-toggle"
      @click="expanded = !expanded"
    >
      <svg
        :class="['chevron', { open: expanded }]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
      <span class="collapse-label">Individual Responses</span>
      <span class="collapse-summary">{{ collapsedSummary }}</span>
    </button>

    <!-- Chat bubbles: always visible in all-mode, toggle in compound mode -->
    <template v-if="!collapsible || expanded">
      <div
        v-for="backend in backends"
        :key="backend"
        class="backend-bubble"
      >
        <div class="bubble-avatar" :style="{ background: backendColor(backend) + '22', color: backendColor(backend) }">
          {{ backend.charAt(0).toUpperCase() }}
        </div>
        <div class="bubble-content">
          <div class="bubble-header">
            <span class="bubble-name" :style="{ color: backendColor(backend) }">{{ backend }}</span>
            <span
              v-if="responses.get(backend)?.status === 'streaming'"
              class="bubble-status streaming"
            >
              streaming...
            </span>
            <span
              v-else-if="statusLabel(responses.get(backend)?.status || '')"
              :class="['bubble-status', responses.get(backend)?.status]"
            >
              {{ statusLabel(responses.get(backend)?.status || '') }}
            </span>
          </div>
          <div
            class="bubble-text markdown-body markdown-rendered"
            v-html="renderMarkdown(responses.get(backend)?.content || 'Waiting for response...')"
          />
          <div v-if="responses.get(backend)?.status === 'error'" class="bubble-error">
            {{ responses.get(backend)?.error }}
          </div>
          <div v-if="responses.get(backend)?.status === 'timeout'" class="bubble-timeout">
            Response timed out
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.all-mode-responses {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
}

/* Collapsible toggle header */
.collapse-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  transition: background 0.15s;
}

.collapse-toggle:hover {
  background: rgba(255, 255, 255, 0.04);
}

.chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.chevron.open {
  transform: rotate(90deg);
}

.collapse-label {
  font-weight: 600;
  color: var(--text-primary);
}

.collapse-summary {
  color: var(--text-tertiary);
  font-size: 12px;
}

/* Chat bubble per backend */
.backend-bubble {
  display: flex;
  gap: 10px;
  align-self: flex-start;
  max-width: 90%;
}

.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 700;
}

.bubble-content {
  background: var(--bg-tertiary);
  border-radius: 12px;
  padding: 10px 14px;
  min-width: 120px;
}

.bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.bubble-name {
  font-size: 13px;
  font-weight: 600;
  text-transform: capitalize;
}

.bubble-status {
  font-size: 11px;
  color: var(--text-tertiary);
}

.bubble-status.streaming {
  color: #3b82f6;
  animation: statusPulse 1.5s infinite;
}

.bubble-status.error {
  color: #ef4444;
}

.bubble-status.timeout {
  color: #eab308;
}

@keyframes statusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.bubble-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.bubble-error {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  font-size: 12px;
}

.bubble-timeout {
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(234, 179, 8, 0.1);
  color: #eab308;
  font-size: 12px;
}
</style>
