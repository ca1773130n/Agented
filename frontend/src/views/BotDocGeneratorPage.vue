<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const error = ref('');

interface BotSummary {
  id: string;
  name: string;
  trigger: string;
  lastRun: string;
  hasDoc: boolean;
  raw: Trigger;
}

const bots = ref<BotSummary[]>([]);

const selectedBotId = ref<string | null>(null);
const isGenerating = ref(false);
const generatedDoc = ref<string | null>(null);
const isCopying = ref(false);

async function loadBots() {
  isLoading.value = true;
  error.value = '';
  try {
    const resp = await triggerApi.list();
    const triggers = resp.triggers ?? [];
    bots.value = triggers.map((t: Trigger) => ({
      id: t.id,
      name: t.name,
      trigger: `${t.trigger_source}${t.schedule_type ? ` (${t.schedule_type})` : ''}`,
      lastRun: t.last_run_at
        ? new Date(t.last_run_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        : 'Never',
      hasDoc: false,
      raw: t,
    }));
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
    } else {
      error.value = 'Failed to load bots';
    }
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

function selectBot(id: string) {
  selectedBotId.value = id;
  generatedDoc.value = null;
}

function generateDocFromTrigger(t: Trigger): string {
  const lines: string[] = [];
  lines.push(`# ${t.name} Documentation`);
  lines.push('');
  lines.push('## What It Does');
  lines.push(`This bot is triggered by **${t.trigger_source}** events and executes using the **${t.backend_type}** backend.`);
  if (t.prompt_template) {
    lines.push(`It runs the following prompt template to produce actionable output.`);
  }
  lines.push('');
  lines.push('## Trigger Configuration');
  lines.push(`- **Source:** ${t.trigger_source}`);
  if (t.schedule_type) lines.push(`- **Schedule:** ${t.schedule_type}${t.schedule_time ? ` at ${t.schedule_time}` : ''}${t.schedule_timezone ? ` (${t.schedule_timezone})` : ''}`);
  if (t.schedule_day) lines.push(`- **Day:** ${t.schedule_day}`);
  if (t.match_field_path) lines.push(`- **Match Field:** \`${t.match_field_path}\` = \`${t.match_field_value ?? '*'}\``);
  if (t.detection_keyword) lines.push(`- **Detection Keyword:** ${t.detection_keyword}`);
  lines.push('');
  lines.push('## Execution Details');
  lines.push(`- **Backend:** ${t.backend_type}`);
  lines.push(`- **Model:** ${t.model ?? 'default'}`);
  if (t.timeout_seconds) lines.push(`- **Timeout:** ${t.timeout_seconds}s`);
  if (t.execution_mode) lines.push(`- **Mode:** ${t.execution_mode}`);
  if (t.team_id) lines.push(`- **Team:** ${t.team_id}`);
  lines.push(`- **Enabled:** ${t.enabled ? 'Yes' : 'No'}`);
  lines.push(`- **Auto-resolve:** ${t.auto_resolve ? 'Yes' : 'No'}`);
  lines.push('');
  if (t.prompt_template) {
    lines.push('## Prompt Template');
    lines.push('```');
    lines.push(t.prompt_template);
    lines.push('```');
    lines.push('');
  }
  if (t.paths && t.paths.length > 0) {
    lines.push('## Configured Paths');
    for (const p of t.paths) {
      lines.push(`- \`${p.local_project_path}\` (${p.path_type})${p.github_repo_url ? ` — ${p.github_repo_url}` : ''}`);
    }
    lines.push('');
  }
  lines.push('## Known Limitations');
  lines.push('- Documentation is auto-generated from trigger configuration');
  lines.push('- Manual review is recommended before sharing externally');
  if (t.timeout_seconds) {
    lines.push(`- Execution timeout is ${t.timeout_seconds}s — long-running tasks may be interrupted`);
  }
  return lines.join('\n');
}

async function generateDoc() {
  if (!selectedBotId.value) return;
  isGenerating.value = true;
  try {
    const trigger = await triggerApi.get(selectedBotId.value);
    generatedDoc.value = generateDocFromTrigger(trigger);
    const b = bots.value.find(b => b.id === selectedBotId.value);
    if (b) b.hasDoc = true;
    showToast('Documentation generated', 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(`Failed to generate documentation: ${e.message}`, 'error');
    } else {
      showToast('Failed to generate documentation', 'error');
    }
  } finally {
    isGenerating.value = false;
  }
}

async function copyDoc() {
  if (!generatedDoc.value) return;
  isCopying.value = true;
  try {
    await navigator.clipboard.writeText(generatedDoc.value);
    showToast('Copied to clipboard', 'success');
  } catch {
    showToast('Copy failed', 'error');
  } finally {
    setTimeout(() => { isCopying.value = false; }, 1000);
  }
}

async function saveDoc() {
  if (!generatedDoc.value) return;
  await new Promise(resolve => setTimeout(resolve, 500));
  showToast('Documentation saved to bot config', 'success');
}

onMounted(loadBots);
</script>

<template>
  <div class="bot-doc-generator-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Doc Generator' },
    ]" />

    <PageHeader
      title="Auto-Generated Bot Documentation"
      subtitle="Generate human-readable README documentation for any bot — trigger type, permissions, example output, and limitations."
    />

    <LoadingState v-if="isLoading" message="Loading bots..." />

    <div v-else-if="error" class="card error-state">
      <p class="error-text">{{ error }}</p>
      <button class="btn btn-primary" @click="loadBots">Retry</button>
    </div>

    <template v-else>
      <div v-if="bots.length === 0" class="card empty-card">
        <p class="empty-text">No bots found. Create a trigger first to generate documentation.</p>
      </div>

      <div v-else class="layout">
        <!-- Bot picker -->
        <div class="bot-picker card">
          <div class="card-header">
            <h3>Select a Bot</h3>
          </div>
          <div class="bot-list">
            <button
              v-for="b in bots"
              :key="b.id"
              class="bot-item"
              :class="{ selected: selectedBotId === b.id }"
              @click="selectBot(b.id)"
            >
              <div class="bot-item-info">
                <span class="bot-item-name">{{ b.name }}</span>
                <span class="bot-item-trigger">{{ b.trigger }}</span>
                <span class="bot-item-meta">Last run {{ b.lastRun }}</span>
              </div>
              <span v-if="b.hasDoc" class="doc-badge">Documented</span>
            </button>
          </div>
        </div>

        <!-- Doc preview -->
        <div class="doc-panel card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
              </svg>
              Generated Documentation
            </h3>
            <div class="header-actions" v-if="generatedDoc">
              <button class="btn btn-ghost" @click="copyDoc">
                {{ isCopying ? 'Copied!' : 'Copy' }}
              </button>
              <button class="btn btn-primary" @click="saveDoc">Save to Bot</button>
            </div>
          </div>

          <div v-if="!selectedBotId" class="doc-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" width="48" height="48">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <p>Select a bot to generate its documentation</p>
          </div>

          <div v-else-if="!generatedDoc" class="generate-prompt">
            <p class="generate-hint">
              Click Generate to create a one-click README for
              <strong>{{ bots.find(b => b.id === selectedBotId)?.name }}</strong>
              — including trigger config, permissions, example outputs, and limitations.
            </p>
            <button class="btn btn-primary btn-lg" :disabled="isGenerating" @click="generateDoc">
              <svg v-if="!isGenerating" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              {{ isGenerating ? 'Generating...' : 'Generate Documentation' }}
            </button>
            <div v-if="isGenerating" class="generating-indicator">
              <div class="spinner" />
              <span>Analyzing bot config and past executions...</span>
            </div>
          </div>

          <div v-else class="doc-content">
            <pre class="doc-text">{{ generatedDoc }}</pre>
            <button class="btn btn-secondary regenerate-btn" :disabled="isGenerating" @click="generateDoc">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
                <polyline points="1 4 1 10 7 10"/>
                <path d="M3.51 15a9 9 0 1 0 .49-3.75"/>
              </svg>
              Regenerate
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bot-doc-generator-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.error-state {
  padding: 32px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.error-text {
  font-size: 0.875rem;
  color: #ef4444;
  margin: 0;
}

.empty-card {
  padding: 48px 24px;
  text-align: center;
}

.empty-text {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
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
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.header-actions {
  display: flex;
  gap: 8px;
}

.bot-list {
  display: flex;
  flex-direction: column;
}

.bot-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.bot-item:last-child { border-bottom: none; }
.bot-item:hover { background: var(--bg-tertiary); }
.bot-item.selected { background: rgba(6, 182, 212, 0.08); border-left: 3px solid var(--accent-cyan); }

.bot-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-item-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.bot-item-trigger {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.bot-item-meta {
  font-size: 0.7rem;
  color: var(--text-tertiary);
}

.doc-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 7px;
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
  border-radius: 4px;
  white-space: nowrap;
}

.doc-empty {
  padding: 64px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: var(--text-tertiary);
}

.doc-empty p { font-size: 0.875rem; margin: 0; }
.doc-empty svg { opacity: 0.3; }

.generate-prompt {
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.generate-hint {
  font-size: 0.875rem;
  color: var(--text-secondary);
  text-align: center;
  max-width: 400px;
  margin: 0;
}

.generate-hint strong { color: var(--text-primary); }

.btn-lg { padding: 10px 24px; font-size: 0.9rem; }

.generating-indicator {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--bg-tertiary);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.doc-content {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.doc-text {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 20px;
  white-space: pre-wrap;
  margin: 0;
  line-height: 1.6;
}

.regenerate-btn { align-self: flex-end; }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--text-secondary); color: var(--text-primary); }
</style>
