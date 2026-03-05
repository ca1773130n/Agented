<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const isAnalyzing = ref(false);
const isApplying = ref(false);
const hasAnalyzed = ref(false);

interface Suggestion {
  id: string;
  type: 'truncation' | 'failure' | 'inefficiency' | 'clarity';
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  before: string;
  after: string;
  selected: boolean;
}

const suggestions = ref<Suggestion[]>([]);

const MOCK_SUGGESTIONS: Suggestion[] = [
  {
    id: '1',
    type: 'truncation',
    severity: 'high',
    title: 'Output truncation detected',
    description: 'Analysis shows 34% of executions hit the output limit. The prompt requests too much detail at once.',
    before: 'Analyze the entire codebase and list all potential issues with full explanations.',
    after: 'Analyze the top 10 most critical issues with brief explanations. Focus on severity: critical > high > medium.',
    selected: true,
  },
  {
    id: '2',
    type: 'failure',
    severity: 'high',
    title: 'Path placeholder missing fallback',
    description: '12% of failures occur when {paths} is empty. Add a graceful fallback.',
    before: 'Review files at {paths} for security issues.',
    after: 'Review files at {paths|default:"the root directory"} for security issues.',
    selected: true,
  },
  {
    id: '3',
    type: 'inefficiency',
    severity: 'medium',
    title: 'Redundant context instructions',
    description: 'The prompt repeats role instructions 3 times, consuming ~400 tokens unnecessarily.',
    before: 'You are a security expert. As a security expert, analyze... Remember you are a security expert...',
    after: 'You are a security expert. Analyze the following and report findings:',
    selected: false,
  },
  {
    id: '4',
    type: 'clarity',
    severity: 'low',
    title: 'Ambiguous output format',
    description: 'Executions produce inconsistent JSON vs markdown output. Specify format explicitly.',
    before: 'Report your findings.',
    after: 'Report findings as JSON: { "issues": [{ "severity": "...", "file": "...", "description": "..." }] }',
    selected: false,
  },
];

async function handleAnalyze() {
  isAnalyzing.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 1800));
    suggestions.value = MOCK_SUGGESTIONS.map(s => ({ ...s }));
    hasAnalyzed.value = true;
    showToast('Log analysis complete — 4 improvements found', 'success');
  } catch {
    showToast('Analysis failed', 'error');
  } finally {
    isAnalyzing.value = false;
  }
}

async function handleApply() {
  const selected = suggestions.value.filter(s => s.selected);
  if (selected.length === 0) {
    showToast('Select at least one suggestion to apply', 'info');
    return;
  }
  isApplying.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 1000));
    showToast(`Applied ${selected.length} suggestion${selected.length > 1 ? 's' : ''} successfully`, 'success');
    suggestions.value = suggestions.value.filter(s => !s.selected);
  } catch {
    showToast('Failed to apply suggestions', 'error');
  } finally {
    isApplying.value = false;
  }
}

function severityColor(sev: string): string {
  const map: Record<string, string> = { high: '#ef4444', medium: '#f59e0b', low: '#6b7280' };
  return map[sev] ?? '#6b7280';
}

function typeIcon(type: string): string {
  const map: Record<string, string> = {
    truncation: 'M18 8h1a4 4 0 0 1 0 8h-1M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8zM6 1v3M10 1v3M14 1v3',
    failure: 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01',
    inefficiency: 'M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4',
    clarity: 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  };
  return map[type] ?? '';
}
</script>

<template>
  <div class="prompt-optimizer">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Prompt Optimizer' },
    ]" />

    <PageHeader title="Prompt Optimizer" subtitle="Analyze execution logs to identify patterns and improve your bot prompts.">
      <template #actions>
        <button class="btn btn-primary" :disabled="isAnalyzing" @click="handleAnalyze">
          <svg v-if="isAnalyzing" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          {{ isAnalyzing ? 'Analyzing...' : 'Analyze Logs' }}
        </button>
        <button
          v-if="hasAnalyzed"
          class="btn btn-accent"
          :disabled="isApplying || suggestions.filter(s => s.selected).length === 0"
          @click="handleApply"
        >
          <svg v-if="isApplying" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          {{ isApplying ? 'Applying...' : `Apply ${suggestions.filter(s => s.selected).length} Selected` }}
        </button>
      </template>
    </PageHeader>

    <div v-if="!hasAnalyzed" class="card empty-prompt">
      <div class="empty-inner">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48" class="empty-icon">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        <p class="empty-title">No analysis yet</p>
        <p class="empty-sub">Click "Analyze Logs" to scan recent execution logs for optimization opportunities.</p>
        <button class="btn btn-primary" :disabled="isAnalyzing" @click="handleAnalyze">
          <svg v-if="isAnalyzing" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          {{ isAnalyzing ? 'Analyzing...' : 'Analyze Logs' }}
        </button>
      </div>
    </div>

    <template v-else>
      <div class="stats-row">
        <div class="stat-pill">
          <span class="stat-num" style="color: #ef4444">{{ suggestions.filter(s => s.severity === 'high').length }}</span>
          <span class="stat-lbl">High Priority</span>
        </div>
        <div class="stat-pill">
          <span class="stat-num" style="color: #f59e0b">{{ suggestions.filter(s => s.severity === 'medium').length }}</span>
          <span class="stat-lbl">Medium Priority</span>
        </div>
        <div class="stat-pill">
          <span class="stat-num" style="color: var(--accent-cyan)">{{ suggestions.filter(s => s.selected).length }}</span>
          <span class="stat-lbl">Selected</span>
        </div>
      </div>

      <div v-if="suggestions.length === 0" class="card empty-prompt">
        <div class="empty-inner">
          <p class="empty-title" style="color: var(--accent-emerald)">All improvements applied!</p>
          <p class="empty-sub">Your prompts are optimized. Run another analysis to check for new issues.</p>
        </div>
      </div>

      <div v-for="s in suggestions" :key="s.id" class="card suggestion-card" :class="{ 'is-selected': s.selected }">
        <div class="sug-header">
          <label class="sug-checkbox-wrap">
            <input type="checkbox" v-model="s.selected" class="sug-checkbox" />
          </label>
          <div class="sug-icon" :style="{ color: severityColor(s.severity) }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path :d="typeIcon(s.type)"/>
            </svg>
          </div>
          <div class="sug-title-area">
            <span class="sug-title">{{ s.title }}</span>
            <span class="sug-type">{{ s.type }}</span>
          </div>
          <div class="sug-severity" :style="{ color: severityColor(s.severity) }">
            {{ s.severity }}
          </div>
        </div>
        <div class="sug-body">
          <p class="sug-desc">{{ s.description }}</p>
          <div class="diff-row">
            <div class="diff-block diff-before">
              <div class="diff-label">Before</div>
              <pre class="diff-code">{{ s.before }}</pre>
            </div>
            <div class="diff-arrow">→</div>
            <div class="diff-block diff-after">
              <div class="diff-label">After</div>
              <pre class="diff-code">{{ s.after }}</pre>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.prompt-optimizer {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.suggestion-card {
  transition: border-color 0.15s;
}

.suggestion-card.is-selected {
  border-color: var(--accent-cyan);
}

.empty-prompt {
  padding: 48px 24px;
}

.empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.empty-icon {
  color: var(--text-tertiary);
  opacity: 0.5;
}

.empty-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.empty-sub {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  max-width: 480px;
  margin: 0;
}

.stats-row {
  display: flex;
  gap: 16px;
}

.stat-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.stat-num {
  font-size: 1.25rem;
  font-weight: 700;
}

.stat-lbl {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.sug-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.sug-checkbox {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent-cyan);
}

.sug-title-area {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.sug-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.sug-type {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sug-severity {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sug-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sug-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.diff-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: start;
}

.diff-arrow {
  padding-top: 28px;
  color: var(--text-tertiary);
  font-size: 1.2rem;
}

.diff-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.diff-label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.diff-before .diff-label { color: #ef4444; }
.diff-after .diff-label { color: var(--accent-emerald); }

.diff-code {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 10px 12px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.diff-before .diff-code { border-color: rgba(239, 68, 68, 0.3); }
.diff-after .diff-code { border-color: rgba(52, 211, 153, 0.3); }

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-accent {
  background: var(--accent-emerald);
  color: #000;
}

.btn-accent:hover:not(:disabled) { opacity: 0.85; }
.btn-accent:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .diff-row { grid-template-columns: 1fr; }
  .diff-arrow { display: none; }
}
</style>
