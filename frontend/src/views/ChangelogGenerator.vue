<script setup lang="ts">
import { ref, computed } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { executionApi, analyticsApi, ApiError } from '../services/api';
import type { Execution } from '../services/api';
const showToast = useToast();

const dateFrom = ref('2026-02-01');
const dateTo = ref('2026-03-13');
const milestone = ref('');
const isGenerating = ref(false);
const generated = ref<string | null>(null);
const isCopied = ref(false);
const loadError = ref<string | null>(null);

async function handleGenerate() {
  if (!dateFrom.value || !dateTo.value) {
    showToast('Please select a date range', 'info');
    return;
  }
  isGenerating.value = true;
  generated.value = null;
  loadError.value = null;

  try {
    // Fetch executions and analytics for the date range
    const [execResp, analyticsResp] = await Promise.all([
      executionApi.listAll({ limit: 100 }),
      analyticsApi.fetchExecutionAnalytics({
        start_date: dateFrom.value,
        end_date: dateTo.value,
      }),
    ]);

    const executions: Execution[] = execResp.executions || [];

    // Filter executions by date range
    const from = new Date(dateFrom.value).getTime();
    const to = new Date(dateTo.value).getTime() + 86400000; // include end date
    const filteredExecs = executions.filter((e) => {
      const ts = new Date(e.started_at || '').getTime();
      return ts >= from && ts <= to;
    });

    // Build changelog from execution results
    const completedExecs = filteredExecs.filter((e) => e.status === 'success');
    const failedExecs = filteredExecs.filter((e) => e.status === 'failed');

    const title = milestone.value || `${dateFrom.value} to ${dateTo.value}`;

    let changelog = `# Changelog — ${title}\n\n`;

    if (completedExecs.length > 0) {
      changelog += `## Completed Executions (${completedExecs.length})\n`;
      for (const exec of completedExecs) {
        const name = exec.trigger_name || exec.trigger_id || 'Unknown trigger';
        const date = exec.started_at ? new Date(exec.started_at).toLocaleDateString() : '';
        changelog += `- **${name}** — ${exec.status} (${date})`;
        if (exec.execution_id) changelog += ` [${exec.execution_id}]`;
        changelog += '\n';
      }
      changelog += '\n';
    }

    if (failedExecs.length > 0) {
      changelog += `## Failed Executions (${failedExecs.length})\n`;
      for (const exec of failedExecs) {
        const name = exec.trigger_name || exec.trigger_id || 'Unknown trigger';
        const date = exec.started_at ? new Date(exec.started_at).toLocaleDateString() : '';
        changelog += `- **${name}** — ${exec.status} (${date})\n`;
      }
      changelog += '\n';
    }

    // Add analytics summary if available
    const analytics = analyticsResp;
    if (analytics && analytics.data && analytics.data.length > 0) {
      changelog += `## Execution Analytics\n`;
      changelog += `- Total data points: ${analytics.data.length}\n`;
      const totalExecs = analytics.data.reduce((sum, dp) => sum + (dp.total_executions || 0), 0);
      const successExecs = analytics.data.reduce((sum, dp) => sum + (dp.success_count || 0), 0);
      changelog += `- Total executions in range: ${totalExecs}\n`;
      changelog += `- Successful: ${successExecs}\n`;
      if (totalExecs > 0) {
        changelog += `- Success rate: ${((successExecs / totalExecs) * 100).toFixed(1)}%\n`;
      }
      changelog += '\n';
    }

    changelog += `---\n*Generated from execution data on ${new Date().toISOString().split('T')[0]}*`;

    if (filteredExecs.length === 0 && (!analytics?.data || analytics.data.length === 0)) {
      changelog = `# Changelog — ${title}\n\nNo executions found in the selected date range (${dateFrom.value} to ${dateTo.value}).`;
    }

    generated.value = changelog;
    showToast('Changelog generated from execution data', 'success');
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = err.message;
      showToast(`Failed to generate changelog: ${err.message}`, 'error');
    } else {
      showToast('Failed to generate changelog', 'error');
    }
  } finally {
    isGenerating.value = false;
  }
}

async function handleCopy() {
  if (!generated.value) return;
  try {
    await navigator.clipboard.writeText(generated.value);
    isCopied.value = true;
    showToast('Changelog copied to clipboard', 'success');
    setTimeout(() => { isCopied.value = false; }, 2000);
  } catch {
    showToast('Failed to copy', 'error');
  }
}

function handleDownload() {
  if (!generated.value) return;
  const blob = new Blob([generated.value], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'CHANGELOG.md';
  a.click();
  URL.revokeObjectURL(url);
  showToast('CHANGELOG.md downloaded', 'success');
}

const lineCount = computed(() => generated.value?.split('\n').length ?? 0);
const wordCount = computed(() => generated.value?.split(/\s+/).filter(Boolean).length ?? 0);
</script>

<template>
  <div class="changelog-generator">

    <PageHeader
      title="Changelog Generator"
      subtitle="Generate changelogs from execution history and analytics data."
    />

    <div class="main-layout">
      <div class="card config-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            Configuration
          </h3>
        </div>
        <div class="config-body">
          <div class="field-group">
            <label class="field-label">Date Range</label>
            <div class="date-row">
              <input v-model="dateFrom" type="date" class="date-input" />
              <span class="date-sep">to</span>
              <input v-model="dateTo" type="date" class="date-input" />
            </div>
          </div>

          <div class="field-group">
            <label class="field-label">Milestone (optional)</label>
            <input v-model="milestone" type="text" class="text-input" placeholder="e.g. v0.4.0 or Sprint 24" />
          </div>

          <div class="field-group">
            <label class="field-label">Include Categories</label>
            <div class="category-checks">
              <label class="check-item"><input type="checkbox" checked /> Features</label>
              <label class="check-item"><input type="checkbox" checked /> Bug Fixes</label>
              <label class="check-item"><input type="checkbox" checked /> Improvements</label>
              <label class="check-item"><input type="checkbox" checked /> Security</label>
              <label class="check-item"><input type="checkbox" /> Breaking Changes</label>
            </div>
          </div>

          <div v-if="loadError" style="color: #ef4444; font-size: 0.82rem; padding: 8px 0;">
            {{ loadError }}
          </div>

          <button
            class="btn btn-primary btn-full"
            :disabled="isGenerating"
            @click="handleGenerate"
          >
            <svg v-if="isGenerating" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            {{ isGenerating ? 'Generating...' : 'Generate Changelog' }}
          </button>
        </div>
      </div>

      <div class="card preview-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            Preview
          </h3>
          <div v-if="generated" class="preview-actions">
            <span class="meta-info">{{ lineCount }} lines · {{ wordCount }} words</span>
            <button class="btn btn-sm btn-secondary" :class="{ copied: isCopied }" @click="handleCopy">
              <svg v-if="!isCopied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ isCopied ? 'Copied!' : 'Copy' }}
            </button>
            <button class="btn btn-sm btn-secondary" @click="handleDownload">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download .md
            </button>
          </div>
        </div>
        <div class="preview-body">
          <div v-if="!generated" class="preview-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="opacity: 0.3; color: var(--text-tertiary)">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <p>Configure parameters and click "Generate Changelog"</p>
          </div>
          <pre v-else class="preview-content">{{ generated }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.changelog-generator {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.main-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 24px;
  align-items: start;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.preview-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-info {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.config-body {
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 0.83rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.date-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.date-input {
  flex: 1;
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8rem;
}

.date-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.date-sep {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.text-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.category-checks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.check-item input {
  width: 15px;
  height: 15px;
  accent-color: var(--accent-cyan);
}

.preview-body {
  padding: 0;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 64px 24px;
  text-align: center;
}

.preview-empty p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.preview-content {
  display: block;
  padding: 24px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.7;
  white-space: pre-wrap;
  overflow: auto;
  max-height: 600px;
  margin: 0;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 7px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  padding: 10px 16px;
  font-size: 0.875rem;
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-full { width: 100%; justify-content: center; }

.btn-sm { padding: 5px 10px; font-size: 0.78rem; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary.copied { background: rgba(52, 211, 153, 0.1); border-color: #34d399; color: #34d399; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .main-layout { grid-template-columns: 1fr; }
}
</style>
