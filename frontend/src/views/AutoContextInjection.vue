<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface ContextRule {
  id: string;
  name: string;
  enabled: boolean;
  type: 'changed_files' | 'git_history' | 'dependency_graph' | 'file_pattern';
  config: string;
  estimatedTokens: number;
}

const rules = ref<ContextRule[]>([
  { id: 'r1', name: 'Changed files from PR', enabled: true, type: 'changed_files', config: 'max_files=20, max_lines=500', estimatedTokens: 8000 },
  { id: 'r2', name: 'Recent git history (7 days)', enabled: true, type: 'git_history', config: 'days=7, limit=50', estimatedTokens: 2000 },
  { id: 'r3', name: 'Import dependency graph', enabled: false, type: 'dependency_graph', config: 'depth=2, format=json', estimatedTokens: 3500 },
  { id: 'r4', name: 'Auth directory files', enabled: false, type: 'file_pattern', config: 'pattern=src/auth/**', estimatedTokens: 5000 },
]);

const isSaving = ref(false);
const isEditing = ref<ContextRule | null>(null);

const totalTokens = ref(rules.value.filter(r => r.enabled).reduce((s, r) => s + r.estimatedTokens, 0));

function updateTotals() {
  totalTokens.value = rules.value.filter(r => r.enabled).reduce((s, r) => s + r.estimatedTokens, 0);
}

function toggleRule(r: ContextRule) {
  r.enabled = !r.enabled;
  updateTotals();
}

async function handleSave() {
  isSaving.value = true;
  try {
    await new Promise(res => setTimeout(res, 700));
    showToast('Context rules saved', 'success');
  } finally {
    isSaving.value = false;
  }
}

function typeLabel(t: ContextRule['type']): string {
  return { changed_files: 'Changed Files', git_history: 'Git History', dependency_graph: 'Dependency Graph', file_pattern: 'File Pattern' }[t];
}

</script>

<template>
  <div class="aci-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'triggers' }) },
      { label: 'Auto Context Injection' },
    ]" />

    <PageHeader
      title="Automatic Codebase Context Injection"
      subtitle="Configure rules to automatically inject relevant file contents, git history, or dependency graphs into bot prompts."
    />

    <div class="layout">
      <div class="main-col">
        <div class="card rules-card">
          <div class="rules-header">
            <span>Context Rules</span>
            <button class="btn-add" @click="showToast('Add rule coming soon', 'info')">+ Add Rule</button>
          </div>
          <div class="rules-list">
            <div v-for="rule in rules" :key="rule.id" class="rule-row">
              <div class="rule-toggle-area">
                <button :class="['toggle-btn', { active: rule.enabled }]" @click="toggleRule(rule)">
                  <span class="toggle-knob"></span>
                </button>
              </div>
              <div class="rule-info">
                <div class="rule-name">{{ rule.name }}</div>
                <div class="rule-type-badge">{{ typeLabel(rule.type) }}</div>
                <div class="rule-config">{{ rule.config }}</div>
              </div>
              <div class="rule-tokens">
                <div class="token-val">~{{ (rule.estimatedTokens / 1000).toFixed(1) }}k</div>
                <div class="token-label">tokens</div>
              </div>
              <button class="edit-btn" @click="isEditing = rule">Edit</button>
            </div>
          </div>
        </div>

        <div class="card preview-card">
          <div class="preview-header">Injection Preview</div>
          <div class="preview-body">
            <div class="preview-stat">
              <span class="stat-label">Active rules</span>
              <span class="stat-val">{{ rules.filter(r => r.enabled).length }}</span>
            </div>
            <div class="preview-stat">
              <span class="stat-label">Estimated total context tokens</span>
              <span :class="['stat-val', { 'stat-warn': totalTokens > 16000 }]">
                ~{{ (totalTokens / 1000).toFixed(1) }}k
              </span>
            </div>
            <div v-if="totalTokens > 16000" class="warning-bar">
              ⚠️ High context size may increase costs and reduce response quality. Consider disabling some rules.
            </div>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save Rules' }}
          </button>
        </div>
      </div>

      <div class="info-col">
        <div class="card info-card">
          <div class="info-header">How It Works</div>
          <div class="info-body">
            <div class="step">
              <div class="step-num">1</div>
              <div class="step-text">A trigger fires (PR opened, webhook received, etc.)</div>
            </div>
            <div class="step">
              <div class="step-num">2</div>
              <div class="step-text">Active context rules are evaluated against the payload</div>
            </div>
            <div class="step">
              <div class="step-num">3</div>
              <div class="step-text">Matching files/history/graphs are fetched and formatted</div>
            </div>
            <div class="step">
              <div class="step-num">4</div>
              <div class="step-text">Context is injected into the bot prompt before execution</div>
            </div>
          </div>
        </div>

        <div class="card type-info-card">
          <div class="info-header">Rule Types</div>
          <div class="type-list">
            <div class="type-item"><span class="type-name">Changed Files</span><span class="type-desc">Files modified in the triggering PR or commit</span></div>
            <div class="type-item"><span class="type-name">Git History</span><span class="type-desc">Recent commit messages and authors</span></div>
            <div class="type-item"><span class="type-name">Dependency Graph</span><span class="type-desc">Import/dependency relationships between modules</span></div>
            <div class="type-item"><span class="type-name">File Pattern</span><span class="type-desc">Any files matching a glob pattern</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.aci-page { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 1fr 280px; gap: 20px; align-items: start; }
.main-col { display: flex; flex-direction: column; gap: 16px; }
.info-col { display: flex; flex-direction: column; gap: 16px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.rules-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.btn-add { background: none; border: 1px solid var(--border-default); color: var(--accent-cyan); padding: 5px 12px; border-radius: 6px; font-size: 0.78rem; cursor: pointer; transition: all 0.15s; }
.btn-add:hover { background: rgba(6,182,212,0.08); }

.rule-row { display: flex; align-items: center; gap: 16px; padding: 14px 20px; border-bottom: 1px solid var(--border-subtle); }
.rule-row:last-child { border-bottom: none; }

.toggle-btn { width: 36px; height: 20px; border-radius: 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); cursor: pointer; position: relative; transition: background 0.2s; flex-shrink: 0; padding: 0; }
.toggle-btn.active { background: var(--accent-cyan); border-color: var(--accent-cyan); }
.toggle-knob { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: left 0.2s; }
.toggle-btn.active .toggle-knob { left: 18px; }

.rule-info { flex: 1; }
.rule-name { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.rule-type-badge { display: inline-block; font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 3px; background: rgba(6,182,212,0.1); color: var(--accent-cyan); margin-bottom: 4px; }
.rule-config { font-size: 0.72rem; color: var(--text-muted); font-family: monospace; }

.rule-tokens { text-align: right; }
.token-val { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.token-label { font-size: 0.68rem; color: var(--text-muted); }

.edit-btn { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-tertiary); padding: 5px 10px; border-radius: 5px; font-size: 0.75rem; cursor: pointer; transition: all 0.15s; }
.edit-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.preview-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.preview-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.preview-stat { display: flex; align-items: center; justify-content: space-between; }
.stat-label { font-size: 0.78rem; color: var(--text-tertiary); }
.stat-val { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.stat-warn { color: #fbbf24; }
.warning-bar { background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.2); border-radius: 6px; padding: 10px 14px; font-size: 0.78rem; color: #fbbf24; }

.actions { display: flex; justify-content: flex-end; }
.btn { padding: 8px 20px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.info-header { padding: 12px 16px; border-bottom: 1px solid var(--border-default); font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }

.info-body { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.step { display: flex; align-items: flex-start; gap: 10px; }
.step-num { width: 22px; height: 22px; border-radius: 50%; background: rgba(6,182,212,0.15); color: var(--accent-cyan); font-size: 0.72rem; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
.step-text { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; }

.type-list { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.type-item { display: flex; flex-direction: column; gap: 2px; }
.type-name { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); }
.type-desc { font-size: 0.72rem; color: var(--text-muted); }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
