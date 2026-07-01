<script setup lang="ts">
/**
 * PolicyEditor (phase 23, 23-05).
 *
 * CRUD for the stackable policy engine: lists policies and creates / edits /
 * deletes them via `policyApi`. Per-kind param fields (cost_budget thresholds,
 * max_tool_calls). All copy via useI18n; dark-theme CSS custom props.
 */
import { reactive, ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { policyApi } from '../../services/api';
import type { Policy, PolicyInput, PolicyScope, PolicyEffect, PolicyKind } from '../../services/api';

const { t } = useI18n();

const SCOPES: PolicyScope[] = ['server', 'team', 'session'];
const EFFECTS: PolicyEffect[] = ['allow', 'deny', 'ask'];
const KINDS: PolicyKind[] = [
  'cost_budget',
  'max_tool_calls_per_session',
  'ask_on_os_tools',
  'enforce_sandbox',
  'custom',
];

const policies = ref<Policy[]>([]);
const loading = ref(false);
const editingId = ref<string | null>(null);

const form = reactive({
  scope: 'session' as PolicyScope,
  scope_id: '',
  kind: 'cost_budget' as PolicyKind,
  effect: 'ask' as PolicyEffect,
  priority: 0,
  max_cost_usd: 0,
  ask_thresholds_usd: '',
  max_tool_calls: 0,
});

async function refresh() {
  loading.value = true;
  try {
    policies.value = (await policyApi.list()).policies;
  } finally {
    loading.value = false;
  }
}

function buildParams(): Record<string, unknown> {
  if (form.kind === 'cost_budget') {
    const thresholds = form.ask_thresholds_usd
      .split(',')
      .map((s) => parseFloat(s.trim()))
      .filter((n) => !Number.isNaN(n));
    return { max_cost_usd: Number(form.max_cost_usd) || 0, ask_thresholds_usd: thresholds };
  }
  if (form.kind === 'max_tool_calls_per_session') {
    return { max_tool_calls: Number(form.max_tool_calls) || 0 };
  }
  return {};
}

async function save() {
  const input: PolicyInput = {
    scope: form.scope,
    scope_id: form.scope === 'server' ? null : form.scope_id || null,
    kind: form.kind,
    effect: form.effect,
    priority: Number(form.priority) || 0,
    params: buildParams(),
  };
  if (editingId.value) input.id = editingId.value;
  await policyApi.upsert(input);
  resetForm();
  await refresh();
}

function edit(p: Policy) {
  editingId.value = p.id;
  form.scope = p.scope;
  form.scope_id = p.scope_id ?? '';
  form.kind = (p.kind as PolicyKind) ?? 'custom';
  form.effect = p.effect;
  form.priority = p.priority;
  const params = p.params || {};
  form.max_cost_usd = Number(params.max_cost_usd) || 0;
  form.ask_thresholds_usd = Array.isArray(params.ask_thresholds_usd)
    ? (params.ask_thresholds_usd as number[]).join(', ')
    : '';
  form.max_tool_calls = Number(params.max_tool_calls) || 0;
}

function resetForm() {
  editingId.value = null;
  form.scope = 'session';
  form.scope_id = '';
  form.kind = 'cost_budget';
  form.effect = 'ask';
  form.priority = 0;
  form.max_cost_usd = 0;
  form.ask_thresholds_usd = '';
  form.max_tool_calls = 0;
}

async function remove(id: string) {
  await policyApi.remove(id);
  if (editingId.value === id) resetForm();
  await refresh();
}

onMounted(refresh);

defineExpose({ refresh, save, edit, remove });
</script>

<template>
  <section class="pe-root">
    <header class="pe-head">
      <h2>{{ t('policy.title') }}</h2>
      <p class="pe-sub">{{ t('policy.subtitle') }}</p>
    </header>

    <ul v-if="policies.length" class="pe-list">
      <li v-for="p in policies" :key="p.id" class="pe-row" :data-policy-id="p.id">
        <span class="pe-badge" :data-effect="p.effect">{{ t(`policy.effects.${p.effect}`) }}</span>
        <span class="pe-scope">{{ t(`policy.scopes.${p.scope}`) }}</span>
        <span class="pe-kind">{{ t(`policy.kinds.${p.kind}`) }}</span>
        <span class="pe-priority">P{{ p.priority }}</span>
        <span class="pe-spacer" />
        <button type="button" class="pe-link" @click="edit(p)">{{ t('policy.edit') }}</button>
        <button type="button" class="pe-link pe-danger" @click="remove(p.id)">
          {{ t('policy.delete') }}
        </button>
      </li>
    </ul>
    <p v-else class="pe-empty">{{ t('policy.empty') }}</p>

    <form class="pe-form" @submit.prevent="save">
      <div class="pe-grid">
        <label class="pe-field">
          <span>{{ t('policy.scope') }}</span>
          <select v-model="form.scope">
            <option v-for="s in SCOPES" :key="s" :value="s">{{ t(`policy.scopes.${s}`) }}</option>
          </select>
        </label>
        <label v-if="form.scope !== 'server'" class="pe-field">
          <span>{{ t('policy.scopeId') }}</span>
          <input v-model="form.scope_id" type="text" />
        </label>
        <label class="pe-field">
          <span>{{ t('policy.kind') }}</span>
          <select v-model="form.kind">
            <option v-for="k in KINDS" :key="k" :value="k">{{ t(`policy.kinds.${k}`) }}</option>
          </select>
        </label>
        <label class="pe-field">
          <span>{{ t('policy.effect') }}</span>
          <select v-model="form.effect">
            <option v-for="e in EFFECTS" :key="e" :value="e">{{ t(`policy.effects.${e}`) }}</option>
          </select>
        </label>
        <label class="pe-field">
          <span>{{ t('policy.priority') }}</span>
          <input v-model.number="form.priority" type="number" />
        </label>

        <label v-if="form.kind === 'cost_budget'" class="pe-field">
          <span>{{ t('policy.maxCostUsd') }}</span>
          <input v-model.number="form.max_cost_usd" type="number" step="0.01" />
        </label>
        <label v-if="form.kind === 'cost_budget'" class="pe-field">
          <span>{{ t('policy.askThresholds') }}</span>
          <input v-model="form.ask_thresholds_usd" type="text" placeholder="1.0, 5.0" />
        </label>
        <label v-if="form.kind === 'max_tool_calls_per_session'" class="pe-field">
          <span>{{ t('policy.maxToolCalls') }}</span>
          <input v-model.number="form.max_tool_calls" type="number" />
        </label>
      </div>

      <div class="pe-form-actions">
        <button v-if="editingId" type="button" class="pe-link" @click="resetForm">
          {{ t('policy.cancel') }}
        </button>
        <button type="submit" class="pe-btn-primary">
          {{ editingId ? t('policy.save') : t('policy.newPolicy') }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.pe-root {
  font-family: var(--font-family, 'Geist', system-ui, sans-serif);
  color: var(--color-text, #e6e6e6);
}
.pe-head h2 {
  margin: 0 0 2px;
  font-size: 1.1rem;
}
.pe-sub {
  margin: 0 0 16px;
  font-size: 0.85rem;
  color: var(--color-text-muted, #9a9a9a);
}
.pe-list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pe-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--color-border, #333);
  border-radius: 6px;
  background: var(--color-surface, #1c1c1e);
  font-size: 0.85rem;
}
.pe-spacer {
  flex: 1;
}
.pe-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-surface-2, #2a2a2d);
}
.pe-badge[data-effect='deny'] {
  color: var(--color-danger, #f08a8a);
}
.pe-badge[data-effect='ask'] {
  color: var(--color-warning, #d9a441);
}
.pe-badge[data-effect='allow'] {
  color: var(--color-success, #6fce9f);
}
.pe-empty {
  font-size: 0.85rem;
  color: var(--color-text-muted, #9a9a9a);
  margin: 0 0 16px;
}
.pe-form {
  border-top: 1px solid var(--color-border, #333);
  padding-top: 14px;
}
.pe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.pe-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--color-text-muted, #9a9a9a);
}
.pe-field input,
.pe-field select {
  padding: 6px 8px;
  border: 1px solid var(--color-border, #333);
  border-radius: 5px;
  background: var(--color-surface, #1c1c1e);
  color: var(--color-text, #e6e6e6);
  font-size: 0.85rem;
}
.pe-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.pe-link {
  background: transparent;
  border: none;
  color: var(--color-accent, #7aa2f7);
  cursor: pointer;
  font-size: 0.8rem;
}
.pe-danger {
  color: var(--color-danger, #f08a8a);
}
.pe-btn-primary {
  padding: 7px 16px;
  border: 1px solid var(--color-accent, #7aa2f7);
  border-radius: 6px;
  background: var(--color-accent, #7aa2f7);
  color: #0b0b0c;
  font-size: 0.85rem;
  cursor: pointer;
}
</style>
