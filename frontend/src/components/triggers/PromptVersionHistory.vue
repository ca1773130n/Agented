<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { PromptHistoryEntry } from '../../services/api';
import { triggerApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  triggerId: string;
}>();

const showToast = useToast();

const history = ref<PromptHistoryEntry[]>([]);
const isLoading = ref(false);
const error = ref<string | null>(null);
const expandedVersionId = ref<number | null>(null);
const confirmRollbackId = ref<number | null>(null);
const isRollingBack = ref(false);

async function loadHistory() {
  isLoading.value = true;
  error.value = null;
  try {
    const res = await triggerApi.getPromptHistory(props.triggerId);
    history.value = res.history || [];
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Failed to load version history';
  } finally {
    isLoading.value = false;
  }
}

function toggleExpand(id: number) {
  expandedVersionId.value = expandedVersionId.value === id ? null : id;
}

function requestRollback(id: number) {
  confirmRollbackId.value = id;
}

function cancelRollback() {
  confirmRollbackId.value = null;
}

async function confirmRollback(versionId: number) {
  isRollingBack.value = true;
  try {
    await triggerApi.rollbackPrompt(props.triggerId, versionId);
    showToast('Prompt rolled back successfully', 'success');
    confirmRollbackId.value = null;
    await loadHistory();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to rollback prompt';
    showToast(message, 'error');
  } finally {
    isRollingBack.value = false;
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function getDiffLineClass(line: string): string {
  if (line.startsWith('+')) return 'diff-add';
  if (line.startsWith('-')) return 'diff-remove';
  if (line.startsWith('@@')) return 'diff-hunk';
  return 'diff-context';
}

onMounted(loadHistory);
</script>

<template>
  <div class="version-history">
    <div class="section-header">
      <h3>Prompt Version History</h3>
      <span v-if="history.length" class="entry-count">{{ history.length }} versions</span>
    </div>

    <div v-if="isLoading" class="loading-state">
      <span class="spinner"></span>
      Loading version history...
    </div>

    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadHistory">Retry</button>
    </div>

    <div v-else-if="history.length === 0" class="empty-state">
      <div class="empty-icon">&#9671;</div>
      <p>No version history yet</p>
      <span>Edit the prompt template to start tracking changes.</span>
    </div>

    <div v-else class="version-list">
      <div
        v-for="(entry, index) in history"
        :key="entry.id"
        class="version-entry"
      >
        <div class="version-header" @click="toggleExpand(entry.id)">
          <div class="version-info">
            <span class="version-number">v{{ history.length - index }}</span>
            <span class="version-author">{{ entry.author || 'system' }}</span>
            <span class="version-date">{{ formatDate(entry.changed_at) }}</span>
          </div>
          <div class="version-actions">
            <button
              v-if="index > 0"
              class="rollback-btn"
              @click.stop="requestRollback(entry.id)"
              :disabled="isRollingBack"
            >
              Rollback to this version
            </button>
            <span v-else class="current-badge">Current</span>
            <span class="expand-icon" :class="{ expanded: expandedVersionId === entry.id }">
              &#9662;
            </span>
          </div>
        </div>

        <!-- Rollback confirmation -->
        <div v-if="confirmRollbackId === entry.id" class="rollback-confirm">
          <p>Are you sure you want to rollback to v{{ history.length - index }}?</p>
          <div class="confirm-actions">
            <button class="confirm-btn" @click="confirmRollback(entry.id)" :disabled="isRollingBack">
              {{ isRollingBack ? 'Rolling back...' : 'Confirm Rollback' }}
            </button>
            <button class="cancel-btn" @click="cancelRollback">Cancel</button>
          </div>
        </div>

        <!-- Diff view -->
        <div v-if="expandedVersionId === entry.id" class="diff-view">
          <pre v-if="entry.diff_text" class="diff-content"><template
            v-for="(line, lineIdx) in entry.diff_text.split('\n')"
            :key="lineIdx"
          ><span :class="getDiffLineClass(line)">{{ line }}
</span></template></pre>
          <p v-else class="no-diff">No diff available for this version.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.version-history {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.entry-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  padding: 20px 0;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state {
  color: var(--accent-crimson);
  font-size: 0.85rem;
  padding: 20px 0;
}

.retry-btn {
  margin-top: 8px;
  padding: 6px 14px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
}

.retry-btn:hover {
  background: var(--bg-elevated);
}

.empty-state {
  text-align: center;
  padding: 32px 0;
}

.empty-icon {
  font-size: 2.5rem;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-state p {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 4px;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-entry {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}

.version-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.version-header:hover {
  background: var(--bg-secondary);
}

.version-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.version-number {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  padding: 2px 8px;
  border-radius: 4px;
}

.version-author {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.version-date {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.version-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rollback-btn {
  padding: 5px 12px;
  background: var(--bg-tertiary);
  color: var(--accent-amber);
  border: 1px solid var(--accent-amber);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  opacity: 0.8;
  transition: opacity 0.15s ease;
}

.rollback-btn:hover:not(:disabled) {
  opacity: 1;
}

.rollback-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.current-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--accent-emerald);
  background: var(--accent-emerald-dim);
  padding: 3px 8px;
  border-radius: 4px;
}

.expand-icon {
  color: var(--text-muted);
  font-size: 0.8rem;
  transition: transform 0.2s ease;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.rollback-confirm {
  padding: 12px 16px;
  background: var(--accent-amber-dim);
  border-top: 1px solid var(--border-subtle);
}

.rollback-confirm p {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.confirm-actions {
  display: flex;
  gap: 8px;
}

.confirm-btn {
  padding: 6px 14px;
  background: var(--accent-amber);
  color: var(--bg-primary);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 600;
}

.confirm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn {
  padding: 6px 14px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
}

.diff-view {
  border-top: 1px solid var(--border-subtle);
  padding: 12px;
  background: var(--bg-secondary);
}

.diff-content {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.6;
  margin: 0;
  overflow-x: auto;
  white-space: pre;
}

.diff-add {
  color: var(--color-diff-add, #4ade80);
  background: rgba(74, 222, 128, 0.08);
  display: inline;
}

.diff-remove {
  color: var(--color-diff-remove, #f87171);
  background: rgba(248, 113, 113, 0.08);
  display: inline;
}

.diff-hunk {
  color: var(--color-diff-hunk, #67e8f9);
  display: inline;
}

.diff-context {
  color: var(--text-tertiary);
  display: inline;
}

.no-diff {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-style: italic;
}
</style>
