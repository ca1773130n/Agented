<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { settingsApi, triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';
const { t } = useI18n();
const showToast = useToast();

const loading = ref(true);
const error = ref<string | null>(null);
const settings = ref<Record<string, string>>({});
const triggers = ref<Trigger[]>([]);

interface ContextRule {
  id: string;
  name: string;
  enabled: boolean;
  type: 'changed_files' | 'git_history' | 'dependency_graph' | 'file_pattern';
  config: string;
  estimatedTokens: number;
}

const rules = ref<ContextRule[]>([]);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [settingsResp, triggersResp] = await Promise.all([
      settingsApi.getAll(),
      triggerApi.list(),
    ]);
    settings.value = settingsResp.settings ?? {};
    triggers.value = triggersResp.triggers ?? [];

    // Build context rules from settings
    const contextRules: ContextRule[] = [];

    // Map known settings keys to context rules
    const ruleMap: Record<string, { name: string; type: ContextRule['type']; tokens: number }> = {
      'context.changed_files': { name: t('autoContextInjection.rule.changedFiles'), type: 'changed_files', tokens: 8000 },
      'context.git_history': { name: t('autoContextInjection.rule.gitHistory'), type: 'git_history', tokens: 2000 },
      'context.dependency_graph': { name: t('autoContextInjection.rule.dependencyGraph'), type: 'dependency_graph', tokens: 3500 },
      'context.file_pattern': { name: t('autoContextInjection.rule.filePattern'), type: 'file_pattern', tokens: 5000 },
    };

    for (const [key, meta] of Object.entries(ruleMap)) {
      const val = settings.value[key];
      contextRules.push({
        id: key,
        name: meta.name,
        enabled: val === 'true' || val === '1' || val === 'enabled',
        type: meta.type,
        config: val ?? t('autoContextInjection.notConfigured'),
        estimatedTokens: meta.tokens,
      });
    }

    // If no context settings exist, show defaults as disabled
    if (contextRules.every(r => !r.enabled) && Object.keys(settings.value).length > 0) {
      // Keep rules as-is from settings, all disabled
    }

    rules.value = contextRules.length > 0 ? contextRules : [
      { id: 'context.changed_files', name: t('autoContextInjection.rule.changedFiles'), enabled: false, type: 'changed_files', config: t('autoContextInjection.notConfigured'), estimatedTokens: 8000 },
      { id: 'context.git_history', name: t('autoContextInjection.rule.gitHistory'), enabled: false, type: 'git_history', config: t('autoContextInjection.notConfigured'), estimatedTokens: 2000 },
      { id: 'context.dependency_graph', name: t('autoContextInjection.rule.dependencyGraph'), enabled: false, type: 'dependency_graph', config: t('autoContextInjection.notConfigured'), estimatedTokens: 3500 },
      { id: 'context.file_pattern', name: t('autoContextInjection.rule.filePattern'), enabled: false, type: 'file_pattern', config: t('autoContextInjection.notConfigured'), estimatedTokens: 5000 },
    ];

    updateTotals();
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `API Error (${err.status}): ${err.message}`;
    } else {
      error.value = err instanceof Error ? err.message : 'Unknown error';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

const isSaving = ref(false);
const isEditing = ref<ContextRule | null>(null);
const totalTokens = ref(0);

function updateTotals() {
  totalTokens.value = rules.value.filter(r => r.enabled).reduce((s, r) => s + r.estimatedTokens, 0);
}

async function toggleRule(r: ContextRule) {
  r.enabled = !r.enabled;
  updateTotals();
  try {
    await settingsApi.set(r.id, r.enabled ? 'true' : 'false');
  } catch (err) {
    r.enabled = !r.enabled;
    updateTotals();
    showToast(err instanceof ApiError ? err.message : t('autoContextInjection.toast.updateFailed'), 'error');
  }
}

async function handleSave() {
  isSaving.value = true;
  try {
    // Save all rule states as settings
    await Promise.all(
      rules.value.map(r => settingsApi.set(r.id, r.enabled ? 'true' : 'false'))
    );
    showToast(t('autoContextInjection.toast.saved'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('autoContextInjection.toast.saveFailed'), 'error');
  } finally {
    isSaving.value = false;
  }
}

function typeLabel(type: ContextRule['type']): string {
  return {
    changed_files: t('autoContextInjection.type.changedFiles'),
    git_history: t('autoContextInjection.type.gitHistory'),
    dependency_graph: t('autoContextInjection.type.dependencyGraph'),
    file_pattern: t('autoContextInjection.type.filePattern'),
  }[type];
}
</script>

<template>
  <div class="aci-page">

    <PageHeader
      :title="t('autoContextInjection.title')"
      :subtitle="t('autoContextInjection.subtitle')"
    />

    <!-- Loading state -->
    <div v-if="loading" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>{{ t('autoContextInjection.loading') }}</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>{{ error }}</p>
      <button class="btn btn-primary" style="margin-top: 12px" @click="loadData">{{ t('common.retry') }}</button>
    </div>

    <template v-else>
      <div class="layout">
        <div class="main-col">
          <div class="card rules-card">
            <div class="rules-header">
              <span>{{ t('autoContextInjection.contextRules') }}</span>
              <!--
                The "Add Rule" UI hasn't shipped yet. Hide the button
                instead of showing a "coming soon" toast — the toast
                made the button look interactive even though clicking
                it never made progress, which is worse than no button.
                Existing rules still render below; users can manage
                them via the seeded set.
              -->
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
                  <div class="token-label">{{ t('autoContextInjection.tokens') }}</div>
                </div>
                <button class="edit-btn" @click="isEditing = rule">{{ t('common.edit') }}</button>
              </div>
            </div>
          </div>

          <!-- Triggers with context info -->
          <div v-if="triggers.length > 0" class="card">
            <div class="rules-header">
              <span>{{ t('autoContextInjection.triggers', { count: triggers.length }) }}</span>
            </div>
            <div class="rules-list">
              <div v-for="trigger in triggers" :key="trigger.id" class="rule-row">
                <div class="rule-info" style="flex: 1;">
                  <div class="rule-name">{{ trigger.name }}</div>
                  <div class="rule-config">{{ trigger.trigger_source }} · {{ trigger.backend_type }}</div>
                </div>
                <div class="rule-type-badge">{{ trigger.enabled ? t('autoContextInjection.active') : t('autoContextInjection.disabled') }}</div>
              </div>
            </div>
          </div>

          <div class="card preview-card">
            <div class="preview-header">{{ t('autoContextInjection.injectionPreview') }}</div>
            <div class="preview-body">
              <div class="preview-stat">
                <span class="stat-label">{{ t('autoContextInjection.activeRules') }}</span>
                <span class="stat-val">{{ rules.filter(r => r.enabled).length }}</span>
              </div>
              <div class="preview-stat">
                <span class="stat-label">{{ t('autoContextInjection.estTotalTokens') }}</span>
                <span :class="['stat-val', { 'stat-warn': totalTokens > 16000 }]">
                  ~{{ (totalTokens / 1000).toFixed(1) }}k
                </span>
              </div>
              <div v-if="totalTokens > 16000" class="warning-bar">
                {{ t('autoContextInjection.highContextWarning') }}
              </div>
            </div>
          </div>

          <div class="actions">
            <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
              {{ isSaving ? t('autoContextInjection.saving') : t('autoContextInjection.saveRules') }}
            </button>
          </div>
        </div>

        <div class="info-col">
          <div class="card info-card">
            <div class="info-header">{{ t('autoContextInjection.howItWorks') }}</div>
            <div class="info-body">
              <div class="step">
                <div class="step-num">1</div>
                <div class="step-text">{{ t('autoContextInjection.step1') }}</div>
              </div>
              <div class="step">
                <div class="step-num">2</div>
                <div class="step-text">{{ t('autoContextInjection.step2') }}</div>
              </div>
              <div class="step">
                <div class="step-num">3</div>
                <div class="step-text">{{ t('autoContextInjection.step3') }}</div>
              </div>
              <div class="step">
                <div class="step-num">4</div>
                <div class="step-text">{{ t('autoContextInjection.step4') }}</div>
              </div>
            </div>
          </div>

          <div class="card type-info-card">
            <div class="info-header">{{ t('autoContextInjection.ruleTypes') }}</div>
            <div class="type-list">
              <div class="type-item"><span class="type-name">{{ t('autoContextInjection.type.changedFiles') }}</span><span class="type-desc">{{ t('autoContextInjection.typeDesc.changedFiles') }}</span></div>
              <div class="type-item"><span class="type-name">{{ t('autoContextInjection.type.gitHistory') }}</span><span class="type-desc">{{ t('autoContextInjection.typeDesc.gitHistory') }}</span></div>
              <div class="type-item"><span class="type-name">{{ t('autoContextInjection.type.dependencyGraph') }}</span><span class="type-desc">{{ t('autoContextInjection.typeDesc.dependencyGraph') }}</span></div>
              <div class="type-item"><span class="type-name">{{ t('autoContextInjection.type.filePattern') }}</span><span class="type-desc">{{ t('autoContextInjection.typeDesc.filePattern') }}</span></div>
            </div>
          </div>
        </div>
      </div>
    </template>
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

.rules-list { display: flex; flex-direction: column; }

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
