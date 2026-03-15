<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import {
  triggerConditionsApi,
  type TriggerConditionRule,
  type ConditionItem,
} from '../services/api/trigger-conditions';
import type { Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

// Trigger selection
const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const isLoadingTriggers = ref(false);
const triggerLoadError = ref('');

// Saved rules from API
const savedRules = ref<TriggerConditionRule[]>([]);
const isLoadingRules = ref(false);

interface CompiledRule {
  field: string;
  operator: string;
  value: string | number;
}

const naturalLanguageInput = ref('');
const isCompiling = ref(false);
const compiledRule = ref<CompiledRule[] | null>(null);
const compiledJson = ref('');
const isSaving = ref(false);

const examples = [
  'run when a PR touches the auth directory and has more than 100 lines changed',
  'fire when commit message contains "fix" and the branch is main',
  'trigger when PR title includes "security" or any file in src/db/ is modified',
];

onMounted(async () => {
  await loadTriggers();
});

async function loadTriggers() {
  isLoadingTriggers.value = true;
  triggerLoadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
  } catch (e) {
    triggerLoadError.value = e instanceof ApiError ? e.message : 'Failed to load triggers';
  } finally {
    isLoadingTriggers.value = false;
  }
}

async function loadConditions() {
  if (!selectedTriggerId.value) return;
  isLoadingRules.value = true;
  try {
    const res = await triggerConditionsApi.list(selectedTriggerId.value);
    savedRules.value = res.rules || [];
  } catch (e) {
    if (e instanceof ApiError && e.status !== 404) {
      showToast(e.message, 'error');
    }
    savedRules.value = [];
  } finally {
    isLoadingRules.value = false;
  }
}

async function onTriggerChange() {
  savedRules.value = [];
  compiledRule.value = null;
  compiledJson.value = '';
  if (selectedTriggerId.value) {
    await loadConditions();
  }
}

function compileNaturalLanguage(input: string): CompiledRule[] {
  const text = input.toLowerCase();
  const conditions: CompiledRule[] = [];
  if (text.includes('auth')) conditions.push({ field: 'changed_files', operator: 'includes_path', value: 'auth/' });
  if (/\d+ lines/.test(text)) {
    const match = text.match(/(\d+)\s+lines/);
    if (match) conditions.push({ field: 'lines_changed', operator: 'gt', value: parseInt(match[1]) });
  }
  if (text.includes('fix')) conditions.push({ field: 'head_commit.message', operator: 'contains', value: 'fix' });
  if (text.includes('main')) conditions.push({ field: 'ref', operator: 'eq', value: 'refs/heads/main' });
  if (text.includes('security')) conditions.push({ field: 'pull_request.title', operator: 'contains', value: 'security' });
  if (/src\/\w+/.test(text)) {
    const pathMatch = text.match(/src\/[\w/]+/);
    if (pathMatch) conditions.push({ field: 'changed_files', operator: 'includes_path', value: pathMatch[0] });
  }
  if (conditions.length === 0) conditions.push({ field: 'event', operator: 'equals', value: 'push' });
  return conditions;
}

async function handleCompile() {
  if (!naturalLanguageInput.value.trim()) return;
  isCompiling.value = true;
  compiledRule.value = null;
  try {
    const conditions = compileNaturalLanguage(naturalLanguageInput.value);
    compiledRule.value = conditions;
    const logic = naturalLanguageInput.value.toLowerCase().includes(' or ') ? 'OR' : 'AND';
    compiledJson.value = JSON.stringify({ conditions, logic: logic.toLowerCase() }, null, 2);
    showToast('Rule compiled successfully', 'success');
  } finally {
    isCompiling.value = false;
  }
}

async function handleSave() {
  if (!compiledRule.value || !selectedTriggerId.value) {
    showToast('Select a trigger and compile a rule first', 'info');
    return;
  }
  isSaving.value = true;
  try {
    const logic = naturalLanguageInput.value.toLowerCase().includes(' or ') ? 'OR' : 'AND';
    const conditionItems: ConditionItem[] = compiledRule.value.map((c, i) => ({
      id: `cond-${i}`,
      field: c.field,
      operator: mapOperator(c.operator),
      value: String(c.value),
    }));

    const res = await triggerConditionsApi.create(selectedTriggerId.value, {
      name: naturalLanguageInput.value.substring(0, 80),
      description: naturalLanguageInput.value,
      enabled: true,
      logic: logic as 'AND' | 'OR',
      conditions: conditionItems,
    });

    if (res.rule) {
      savedRules.value.unshift(res.rule);
    }
    showToast('Rule saved', 'success');
    naturalLanguageInput.value = '';
    compiledRule.value = null;
    compiledJson.value = '';
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to save rule', 'error');
  } finally {
    isSaving.value = false;
  }
}

function mapOperator(op: string): ConditionItem['operator'] {
  const mapping: Record<string, ConditionItem['operator']> = {
    eq: 'equals',
    equals: 'equals',
    ne: 'not_equals',
    not_equals: 'not_equals',
    contains: 'contains',
    includes_path: 'contains',
    gt: 'greater_than',
    greater_than: 'greater_than',
    lt: 'less_than',
    less_than: 'less_than',
    matches: 'matches',
  };
  return mapping[op] || 'equals';
}

async function deleteRule(ruleId: string) {
  try {
    await triggerConditionsApi.delete(ruleId);
    savedRules.value = savedRules.value.filter(r => r.id !== ruleId);
    showToast('Rule deleted', 'success');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to delete rule', 'error');
  }
}

function useExample(ex: string) {
  naturalLanguageInput.value = ex;
}
</script>

<template>
  <div class="nl-trigger">

    <PageHeader
      title="Natural Language Trigger Rule Editor"
      subtitle="Write trigger conditions in plain English — the platform compiles them to structured filter rules."
    />

    <!-- Trigger selector -->
    <div v-if="isLoadingTriggers" class="loading-msg">Loading triggers...</div>
    <div v-else-if="triggerLoadError" class="error-msg">{{ triggerLoadError }}</div>
    <div v-else class="trigger-selector">
      <label class="selector-label">Trigger:</label>
      <select v-model="selectedTriggerId" class="trigger-select" @change="onTriggerChange">
        <option value="">Select a trigger...</option>
        <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }} ({{ t.id }})</option>
      </select>
    </div>

    <div class="layout">
      <div class="editor-col">
        <div class="card compose-card">
          <div class="compose-header">Describe your trigger condition</div>
          <div class="compose-body">
            <textarea
              v-model="naturalLanguageInput"
              class="nl-input"
              placeholder="e.g. run when a PR touches the auth directory and has more than 100 lines changed"
              rows="4"
            ></textarea>

            <div class="examples-row">
              <span class="examples-label">Examples:</span>
              <button
                v-for="ex in examples"
                :key="ex"
                class="example-chip"
                @click="useExample(ex)"
              >{{ ex }}</button>
            </div>

            <div class="compose-actions">
              <button
                class="btn btn-primary"
                :disabled="isCompiling || !naturalLanguageInput.trim()"
                @click="handleCompile"
              >
                {{ isCompiling ? 'Compiling...' : 'Compile Rule' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="compiledRule" class="card compiled-card">
          <div class="compiled-header">
            <span>Compiled Rule</span>
            <button
              class="btn btn-primary btn-sm"
              :disabled="isSaving || !selectedTriggerId"
              @click="handleSave"
            >{{ isSaving ? 'Saving...' : 'Save Rule' }}</button>
          </div>
          <div class="conditions-list">
            <div v-for="(c, i) in compiledRule" :key="i" class="condition-row">
              <span class="cond-field">{{ c.field }}</span>
              <span class="cond-op">{{ c.operator }}</span>
              <span class="cond-val">{{ c.value }}</span>
            </div>
          </div>
          <div class="compiled-json-section">
            <div class="json-label">JSON Output</div>
            <pre class="json-pre">{{ compiledJson }}</pre>
          </div>
        </div>
      </div>

      <aside class="saved-col card">
        <div class="saved-header">
          Saved Rules
          <span v-if="isLoadingRules" class="loading-hint">loading...</span>
        </div>
        <div v-if="!selectedTriggerId" class="saved-empty">Select a trigger to see its rules.</div>
        <div v-else-if="savedRules.length === 0 && !isLoadingRules" class="saved-empty">No rules yet for this trigger.</div>
        <div v-for="r in savedRules" :key="r.id" class="saved-rule">
          <div class="saved-desc">{{ r.description || r.name }}</div>
          <div class="saved-meta">
            <span class="saved-conditions">{{ r.conditions.length }} condition{{ r.conditions.length !== 1 ? 's' : '' }} · {{ r.logic }}</span>
            <button class="delete-btn" @click="deleteRule(r.id)" title="Delete rule">x</button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.nl-trigger { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.loading-msg { font-size: 0.82rem; color: var(--text-tertiary); padding: 12px 0; }
.error-msg { font-size: 0.82rem; color: #ef4444; padding: 12px 0; }

.trigger-selector { display: flex; align-items: center; gap: 12px; }
.selector-label { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.trigger-select { flex: 1; max-width: 400px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }

.layout { display: grid; grid-template-columns: 1fr 280px; gap: 20px; align-items: start; }
.editor-col { display: flex; flex-direction: column; gap: 16px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.compose-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }

.compose-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }

.nl-input {
  width: 100%; padding: 12px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-default);
  border-radius: 8px; color: var(--text-primary); font-size: 0.88rem; font-family: inherit;
  resize: vertical; line-height: 1.5; box-sizing: border-box;
}
.nl-input:focus { outline: none; border-color: var(--accent-cyan); }
.nl-input::placeholder { color: var(--text-muted); }

.examples-row { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; }
.examples-label { font-size: 0.72rem; color: var(--text-tertiary); line-height: 26px; flex-shrink: 0; }
.example-chip {
  background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary);
  padding: 4px 10px; border-radius: 5px; font-size: 0.72rem; cursor: pointer; text-align: left;
  transition: all 0.15s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px;
}
.example-chip:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.compose-actions { display: flex; justify-content: flex-end; }

.compiled-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }

.conditions-list { padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: 8px; }
.condition-row { display: flex; align-items: center; gap: 10px; }
.cond-field { font-family: monospace; font-size: 0.78rem; color: var(--text-primary); }
.cond-op { font-size: 0.75rem; color: var(--accent-cyan); font-weight: 600; }
.cond-val { font-family: monospace; font-size: 0.78rem; color: #fbbf24; }

.compiled-json-section { padding: 16px 20px; }
.json-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 8px; }
.json-pre { background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 0.75rem; color: var(--text-secondary); margin: 0; overflow: auto; max-height: 200px; }

.saved-header { padding: 14px 16px; border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; justify-content: space-between; }
.loading-hint { font-size: 0.7rem; color: var(--text-muted); font-weight: 400; }
.saved-empty { padding: 16px; font-size: 0.78rem; color: var(--text-muted); text-align: center; }
.saved-rule { padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); }
.saved-rule:last-child { border-bottom: none; }
.saved-desc { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; margin-bottom: 4px; }
.saved-meta { display: flex; align-items: center; justify-content: space-between; }
.saved-conditions { font-size: 0.7rem; color: var(--text-muted); }
.delete-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; }
.delete-btn:hover { color: #ef4444; background: rgba(239,68,68,0.1); }

.btn { display: flex; align-items: center; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm { padding: 5px 12px; font-size: 0.75rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
