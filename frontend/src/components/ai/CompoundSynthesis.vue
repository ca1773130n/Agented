<script setup lang="ts">
import type { SynthesisState } from '../../composables/useAllMode';
import { renderMarkdown } from '../../composables/useMarkdown';

defineProps<{
  synthesis: SynthesisState;
}>();
</script>

<template>
  <div class="compound-synthesis" v-if="synthesis">
    <div class="synthesis-badge">
      <span class="badge-icon">&#x2728;</span>
      Compound Synthesis
      <span class="badge-backend">via {{ synthesis.primaryBackend }}</span>
    </div>
    <div class="synthesis-sources" v-if="synthesis.backendsCollected.length > 0">
      Sources: {{ synthesis.backendsCollected.join(', ') }}
    </div>
    <div
      class="synthesis-body markdown-body markdown-rendered"
      v-if="synthesis.content"
      v-html="renderMarkdown(synthesis.content)"
    />
    <div v-else-if="synthesis.status === 'streaming'" class="synthesis-loading">
      Generating synthesis...
    </div>
    <div v-else-if="synthesis.status === 'waiting'" class="synthesis-loading">
      Waiting for backend responses...
    </div>
    <div v-if="synthesis.status === 'error'" class="synthesis-error">
      {{ synthesis.error || 'Synthesis failed' }}
    </div>
  </div>
</template>

<style scoped>
.compound-synthesis {
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
  flex-shrink: 0;
}

.synthesis-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--accent-violet);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 12px;
  margin-bottom: 8px;
}

.badge-icon {
  font-size: 14px;
}

.badge-backend {
  color: rgba(255, 255, 255, 0.7);
  font-weight: 400;
}

.synthesis-sources {
  font-size: 12px;
  font-style: italic;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.synthesis-body {
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.synthesis-loading {
  color: var(--text-tertiary);
  font-style: italic;
  font-size: 14px;
  animation: synthPulse 1.5s infinite;
}

@keyframes synthPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.synthesis-error {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  font-size: 13px;
}
</style>
