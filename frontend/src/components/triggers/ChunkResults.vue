<script setup lang="ts">
import { ref } from 'vue';
import type { MergedChunkResults } from '../../services/api';

defineProps<{
  results: MergedChunkResults;
}>();

const expandedChunks = ref<Set<number>>(new Set());

function toggleChunk(index: number) {
  if (expandedChunks.value.has(index)) {
    expandedChunks.value.delete(index);
  } else {
    expandedChunks.value.add(index);
  }
  // Trigger reactivity
  expandedChunks.value = new Set(expandedChunks.value);
}
</script>

<template>
  <div class="chunk-results">
    <!-- Summary Header -->
    <div class="summary-header">
      <div class="summary-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
          <rect x="3" y="3" width="7" height="7" rx="1"/>
          <rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/>
          <rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
      </div>
      <div class="summary-text">
        <span class="summary-title">
          Processed <strong>{{ results.total_chunks }}</strong> chunks
        </span>
        <span class="summary-detail">
          {{ results.unique_findings.length }} unique findings
          <span v-if="results.duplicate_count > 0" class="dedup-badge">
            {{ results.duplicate_count }} duplicates removed
          </span>
        </span>
      </div>
    </div>

    <!-- Merged Findings -->
    <div v-if="results.unique_findings.length > 0" class="findings-section">
      <h4 class="section-title">Merged Findings</h4>
      <ul class="findings-list">
        <li v-for="(finding, i) in results.unique_findings" :key="i" class="finding-item">
          {{ finding }}
        </li>
      </ul>
    </div>

    <!-- Merged Output (if different from findings list) -->
    <div v-if="results.merged_output" class="merged-output-section">
      <h4 class="section-title">Merged Output</h4>
      <pre class="merged-output">{{ results.merged_output }}</pre>
    </div>

    <!-- Empty state -->
    <div v-if="results.unique_findings.length === 0 && !results.merged_output" class="empty-findings">
      No findings produced from chunked execution.
    </div>

    <!-- Per-Chunk Details Accordion -->
    <div v-if="results.chunk_results && results.chunk_results.length > 0" class="chunks-accordion">
      <h4 class="section-title accordion-header">
        <button class="accordion-toggle" @click="expandedChunks.size === results.chunk_results.length ? (expandedChunks = new Set()) : (expandedChunks = new Set(results.chunk_results.map((_, i) => i)))">
          Per-Chunk Details
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M6 9l6 6 6-6"/>
          </svg>
        </button>
      </h4>

      <div v-for="(chunk, index) in results.chunk_results" :key="index" class="chunk-item">
        <button class="chunk-header" @click="toggleChunk(index)">
          <span class="chunk-index">Chunk {{ chunk.chunk_index + 1 }}</span>
          <span class="chunk-meta">{{ chunk.token_count }} tokens</span>
          <svg
            class="chunk-chevron"
            :class="{ expanded: expandedChunks.has(index) }"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"
          >
            <path d="M6 9l6 6 6-6"/>
          </svg>
        </button>
        <div v-if="expandedChunks.has(index)" class="chunk-body">
          <pre class="chunk-output">{{ chunk.bot_output }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chunk-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.summary-icon {
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.summary-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-title {
  font-size: 0.9rem;
  color: var(--text-primary);
}

.summary-title strong {
  color: var(--accent-cyan);
}

.summary-detail {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.dedup-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 600;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.findings-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.findings-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.finding-item {
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.finding-item::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--accent-cyan);
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
}

.merged-output-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.merged-output {
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}

.empty-findings {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.chunks-accordion {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.accordion-header {
  margin-bottom: 4px;
}

.accordion-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  padding: 0;
}

.accordion-toggle:hover {
  color: var(--text-primary);
}

.chunk-item {
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  overflow: hidden;
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
  transition: background 0.15s ease;
}

.chunk-header:hover {
  background: var(--bg-tertiary);
}

.chunk-index {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.chunk-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-left: auto;
}

.chunk-chevron {
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.chunk-chevron.expanded {
  transform: rotate(180deg);
}

.chunk-body {
  padding: 12px;
  background: var(--bg-primary);
  border-top: 1px solid var(--border-subtle);
  animation: chunkExpand 0.2s ease;
}

@keyframes chunkExpand {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 500px; }
}

.chunk-output {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}
</style>
