<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { ReplayComparison, OutputDiff } from '../../services/api';
import { replayApi, ApiError } from '../../services/api';
import DiffViewer from './DiffViewer.vue';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  executionId: string;
}>();

const showToast = useToast();

const comparisons = ref<ReplayComparison[]>([]);
const selectedComparison = ref<ReplayComparison | null>(null);
const diffData = ref<OutputDiff | null>(null);
const isReplaying = ref(false);
const isLoadingDiff = ref(false);
const isLoadingComparisons = ref(false);
const replayNotes = ref('');

async function loadComparisons() {
  isLoadingComparisons.value = true;
  try {
    const result = await replayApi.getComparisons(props.executionId);
    comparisons.value = result.comparisons || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load comparisons';
    showToast(message, 'error');
  } finally {
    isLoadingComparisons.value = false;
  }
}

async function handleReplay() {
  if (isReplaying.value) return;
  isReplaying.value = true;
  try {
    const result = await replayApi.create(props.executionId, replayNotes.value || undefined);
    showToast('Replay started successfully', 'success');
    replayNotes.value = '';
    // Reload comparisons to show the new one
    await loadComparisons();
    // Auto-select the new comparison
    const newComparison = comparisons.value.find(c => c.id === result.comparison_id);
    if (newComparison) {
      await viewDiff(newComparison);
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to replay execution';
    showToast(message, 'error');
  } finally {
    isReplaying.value = false;
  }
}

async function viewDiff(comparison: ReplayComparison) {
  selectedComparison.value = comparison;
  isLoadingDiff.value = true;
  diffData.value = null;
  try {
    diffData.value = await replayApi.getDiff(comparison.id);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load diff';
    showToast(message, 'error');
    selectedComparison.value = null;
  } finally {
    isLoadingDiff.value = false;
  }
}

function closeDiff() {
  selectedComparison.value = null;
  diffData.value = null;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

onMounted(loadComparisons);
</script>

<template>
  <div class="replay-comparison">
    <!-- Replay Trigger Section -->
    <div class="replay-trigger">
      <h4 class="section-title">Replay Execution</h4>
      <div class="replay-form">
        <input
          v-model="replayNotes"
          type="text"
          class="replay-notes-input"
          placeholder="Optional notes (e.g., 'testing prompt v2')"
          :disabled="isReplaying"
          @keydown.enter="handleReplay"
        />
        <button
          class="replay-btn"
          :disabled="isReplaying"
          @click="handleReplay"
        >
          <span v-if="isReplaying" class="spinner-small"></span>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5,3 19,12 5,21 5,3" />
          </svg>
          {{ isReplaying ? 'Replaying...' : 'Replay' }}
        </button>
      </div>
    </div>

    <!-- Comparisons List -->
    <div class="comparisons-section">
      <h4 class="section-title">
        Comparisons
        <span v-if="comparisons.length" class="comparison-count">{{ comparisons.length }}</span>
      </h4>

      <div v-if="isLoadingComparisons" class="loading-state">
        <span class="spinner-small"></span>
        Loading comparisons...
      </div>

      <div v-else-if="comparisons.length === 0" class="empty-comparisons">
        No replay comparisons yet. Click "Replay" to create one.
      </div>

      <div v-else class="comparison-list">
        <div
          v-for="comparison in comparisons"
          :key="comparison.id"
          class="comparison-item"
          :class="{ active: selectedComparison?.id === comparison.id }"
        >
          <div class="comparison-info">
            <span class="comparison-date">{{ formatDate(comparison.created_at) }}</span>
            <span v-if="comparison.notes" class="comparison-notes">{{ comparison.notes }}</span>
            <span class="comparison-ids">
              {{ comparison.original_execution_id.slice(0, 8) }} vs {{ comparison.replay_execution_id.slice(0, 8) }}
            </span>
          </div>
          <button
            class="view-diff-btn"
            :class="{ active: selectedComparison?.id === comparison.id }"
            @click="selectedComparison?.id === comparison.id ? closeDiff() : viewDiff(comparison)"
          >
            {{ selectedComparison?.id === comparison.id ? 'Close' : 'View Diff' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Diff View -->
    <div v-if="selectedComparison" class="diff-section">
      <div v-if="isLoadingDiff" class="loading-state">
        <span class="spinner-small"></span>
        Loading diff...
      </div>
      <DiffViewer v-else-if="diffData" :diff-data="diffData" />
    </div>
  </div>
</template>

<style scoped>
.replay-comparison {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.comparison-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.7rem;
  font-weight: 700;
}

/* Replay Trigger */
.replay-trigger {
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.replay-form {
  display: flex;
  gap: 10px;
}

.replay-notes-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
  transition: border-color 0.15s ease;
}

.replay-notes-input::placeholder {
  color: var(--text-muted);
}

.replay-notes-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.replay-notes-input:disabled {
  opacity: 0.5;
}

.replay-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.replay-btn:hover:not(:disabled) {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.replay-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.replay-btn svg {
  width: 14px;
  height: 14px;
}

/* Comparisons List */
.comparisons-section {
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.empty-comparisons {
  padding: 16px;
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
}

.comparison-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comparison-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  transition: border-color 0.15s ease;
}

.comparison-item.active {
  border-color: var(--accent-cyan);
}

.comparison-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.comparison-date {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.comparison-notes {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-style: italic;
}

.comparison-ids {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.view-diff-btn {
  padding: 6px 14px;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.view-diff-btn:hover {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.view-diff-btn.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

/* Diff Section */
.diff-section {
  animation: fadeInSection 0.2s ease;
}

@keyframes fadeInSection {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Shared spinner */
.spinner-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
