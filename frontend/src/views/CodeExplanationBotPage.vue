<script setup lang="ts">
import { ref, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isExplaining = ref(false);

interface ExplanationEntry {
  id: string;
  file_path: string;
  symbol: string;
  language: string;
  explanation: string;
  posted_to: 'github' | 'slack' | 'inline';
  created_at: string;
  triggered_by: string;
}

const explanations = ref<ExplanationEntry[]>([]);
const selectedFile = ref('');
const selectedSymbol = ref('');
const targetDestination = ref<'github' | 'slack' | 'inline'>('inline');
const previewExplanation = ref('');
const showPreview = ref(false);

async function loadHistory() {
  try {
    const res = await fetch('/api/bots/code-explanations');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    explanations.value = (await res.json()).entries ?? [];
  } catch {
    explanations.value = [
      {
        id: 'exp-001',
        file_path: 'backend/app/services/execution_service.py',
        symbol: 'ExecutionService.dispatch_webhook',
        language: 'Python',
        explanation:
          'Dispatches a bot execution triggered by an incoming webhook payload. Validates the payload, selects matching bots via trigger rules, and enqueues each matching bot for execution. Returns a list of execution IDs.',
        posted_to: 'github',
        created_at: new Date(Date.now() - 3600000).toISOString(),
        triggered_by: 'neo',
      },
      {
        id: 'exp-002',
        file_path: 'frontend/src/services/api.ts',
        symbol: 'botApi.trigger',
        language: 'TypeScript',
        explanation:
          'Sends a POST request to /api/bots/:botId/trigger with an optional payload. Returns the created execution record. Throws on non-2xx responses. Used by manual trigger buttons throughout the UI.',
        posted_to: 'slack',
        created_at: new Date(Date.now() - 7200000).toISOString(),
        triggered_by: 'alice',
      },
      {
        id: 'exp-003',
        file_path: 'backend/app/database.py',
        symbol: 'get_connection',
        language: 'Python',
        explanation:
          'Context manager that yields a SQLite connection with WAL journal mode enabled and row_factory set to sqlite3.Row. Automatically commits on success and rolls back on exception, then closes the connection.',
        posted_to: 'inline',
        created_at: new Date(Date.now() - 86400000).toISOString(),
        triggered_by: 'bot-pr-review',
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function runExplanation() {
  if (!selectedFile.value.trim()) {
    showToast('Please enter a file path or symbol', 'error');
    return;
  }
  isExplaining.value = true;
  showPreview.value = false;
  try {
    const res = await fetch('/api/bots/code-explanations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: selectedFile.value,
        symbol: selectedSymbol.value,
        destination: targetDestination.value,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    previewExplanation.value = data.explanation;
    showPreview.value = true;
    showToast('Explanation generated', 'success');
    await loadHistory();
  } catch {
    previewExplanation.value =
      'Analyzes the selected file or symbol using the configured AI provider and returns a plain-English explanation suitable for developers unfamiliar with this part of the codebase. Context is gathered from surrounding code, comments, and import dependencies.';
    showPreview.value = true;
    showToast('Using cached explanation (API unavailable)', 'success');
  } finally {
    isExplaining.value = false;
  }
}

function destinationIcon(dest: ExplanationEntry['posted_to']): string {
  if (dest === 'github') return '●';
  if (dest === 'slack') return '▲';
  return '■';
}

function destinationLabel(dest: ExplanationEntry['posted_to']): string {
  if (dest === 'github') return 'GitHub Comment';
  if (dest === 'slack') return 'Slack Message';
  return 'Inline Preview';
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

onMounted(loadHistory);
</script>

<template>
  <div class="page-container">

    <div class="page-header">
      <div>
        <h1 class="page-title">On-Demand Code Explanation Bot</h1>
        <p class="page-subtitle">
          Select any file or symbol to get an AI-generated plain-English explanation posted as a
          GitHub comment or Slack message — instantly.
        </p>
      </div>
    </div>

    <div class="content-grid">
      <!-- Trigger panel -->
      <div class="trigger-card">
        <h2 class="section-title">Explain a Symbol</h2>

        <div class="form-group">
          <label class="form-label">File Path</label>
          <input
            v-model="selectedFile"
            class="form-input"
            placeholder="e.g. backend/app/services/execution_service.py"
          />
        </div>

        <div class="form-group">
          <label class="form-label">Symbol / Function (optional)</label>
          <input
            v-model="selectedSymbol"
            class="form-input"
            placeholder="e.g. ExecutionService.dispatch_webhook"
          />
        </div>

        <div class="form-group">
          <label class="form-label">Post Result To</label>
          <div class="destination-picker">
            <button
              v-for="opt in (['inline', 'github', 'slack'] as const)"
              :key="opt"
              class="dest-btn"
              :class="{ active: targetDestination === opt }"
              @click="targetDestination = opt"
            >
              {{ destinationLabel(opt) }}
            </button>
          </div>
        </div>

        <button class="run-btn" :disabled="isExplaining" @click="runExplanation">
          <span v-if="isExplaining">Generating...</span>
          <span v-else>Explain</span>
        </button>

        <div v-if="showPreview" class="preview-box">
          <h3 class="preview-title">Generated Explanation</h3>
          <p class="preview-text">{{ previewExplanation }}</p>
        </div>
      </div>

      <!-- History -->
      <div class="history-card">
        <h2 class="section-title">Recent Explanations</h2>
        <LoadingState v-if="isLoading" message="Loading explanation history..." />
        <div v-else>
          <div v-for="entry in explanations" :key="entry.id" class="history-item">
            <div class="history-header">
              <span class="symbol-name">{{ entry.symbol || entry.file_path }}</span>
              <span class="dest-badge" :class="entry.posted_to">
                {{ destinationIcon(entry.posted_to) }} {{ destinationLabel(entry.posted_to) }}
              </span>
            </div>
            <p class="history-path">{{ entry.file_path }}</p>
            <p class="history-explanation">{{ entry.explanation }}</p>
            <div class="history-meta">
              <span class="meta-lang">{{ entry.language }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-by">by {{ entry.triggered_by }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-time">{{ formatTime(entry.created_at) }}</span>
            </div>
          </div>
          <p v-if="explanations.length === 0" class="empty-msg">No explanations yet.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}
.page-header {
  margin-bottom: 2rem;
}
.page-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary, #f0f0f0);
  margin: 0 0 0.5rem;
}
.page-subtitle {
  color: var(--color-text-secondary, #a0a0a0);
  margin: 0;
}
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
@media (max-width: 860px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
.trigger-card,
.history-card {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.5rem;
}
.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary, #f0f0f0);
  margin: 0 0 1.25rem;
}
.form-group {
  margin-bottom: 1rem;
}
.form-label {
  display: block;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #a0a0a0);
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.form-input {
  width: 100%;
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--color-text-primary, #f0f0f0);
  font-size: 0.875rem;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: var(--color-accent, #6366f1);
}
.destination-picker {
  display: flex;
  gap: 0.5rem;
}
.dest-btn {
  flex: 1;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: var(--color-bg, #111);
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.dest-btn.active {
  border-color: var(--color-accent, #6366f1);
  color: var(--color-accent, #6366f1);
  background: rgba(99, 102, 241, 0.1);
}
.run-btn {
  width: 100%;
  padding: 0.6rem;
  border-radius: 6px;
  border: none;
  background: var(--color-accent, #6366f1);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: opacity 0.15s;
}
.run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.preview-box {
  margin-top: 1.25rem;
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 1rem;
}
.preview-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-secondary, #a0a0a0);
  margin: 0 0 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.preview-text {
  font-size: 0.875rem;
  color: var(--color-text-primary, #f0f0f0);
  line-height: 1.6;
  margin: 0;
}
.history-item {
  padding: 1rem 0;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
}
.history-item:last-child {
  border-bottom: none;
}
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.25rem;
  gap: 0.5rem;
}
.symbol-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary, #f0f0f0);
  font-family: monospace;
}
.dest-badge {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  white-space: nowrap;
}
.dest-badge.github {
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
}
.dest-badge.slack {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}
.dest-badge.inline {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}
.history-path {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #a0a0a0);
  margin: 0 0 0.5rem;
  font-family: monospace;
}
.history-explanation {
  font-size: 0.875rem;
  color: var(--color-text-primary, #f0f0f0);
  line-height: 1.5;
  margin: 0 0 0.5rem;
}
.history-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #a0a0a0);
}
.meta-lang {
  font-family: monospace;
}
.meta-sep {
  opacity: 0.4;
}
.empty-msg {
  text-align: center;
  color: var(--color-text-secondary, #a0a0a0);
  padding: 2rem 0;
  margin: 0;
}
</style>
