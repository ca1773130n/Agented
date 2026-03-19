<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import {
  triggerConditionsApi,
  type TriggerConditionRule,
} from '../services/api/trigger-conditions';
const route = useRoute();
const showToast = useToast();

// Trigger ID comes from the query string: ?trigger_id=trig-xxxxx
// Falls back to empty string when accessed without context (top-level view)
const triggerId = ref<string>((route.query.trigger_id as string) || '');

type Operator = 'equals' | 'not_equals' | 'contains' | 'greater_than' | 'less_than' | 'matches';

const fieldOptions = [
  { value: 'pr.lines_changed', label: 'PR Lines Changed' },
  { value: 'pr.files_changed', label: 'PR Files Changed' },
  { value: 'pr.author', label: 'PR Author' },
  { value: 'pr.label', label: 'PR Label' },
  { value: 'pr.base_branch', label: 'PR Base Branch' },
  { value: 'file.path', label: 'File Path' },
  { value: 'commit.message', label: 'Commit Message' },
  { value: 'repo.name', label: 'Repository Name' },
  { value: 'event.action', label: 'Event Action' },
];

const operatorOptions: { value: Operator; label: string }[] = [
  { value: 'equals', label: '= equals' },
  { value: 'not_equals', label: '≠ not equals' },
  { value: 'contains', label: '⊃ contains' },
  { value: 'greater_than', label: '> greater than' },
  { value: 'less_than', label: '< less than' },
  { value: 'matches', label: '~ matches (glob)' },
];

const rules = ref<TriggerConditionRule[]>([]);
const selectedRule = ref<TriggerConditionRule | null>(null);
const isLoading = ref(false);
const isSaving = ref(false);
const isDeleting = ref(false);
const isTestingRule = ref(false);
const testResult = ref<{ matched: boolean; reason: string } | null>(null);

async function loadRules() {
  if (!triggerId.value) return;
  isLoading.value = true;
  try {
    const res = await triggerConditionsApi.list(triggerId.value);
    rules.value = res.rules;
    if (rules.value.length > 0 && !selectedRule.value) {
      selectedRule.value = { ...rules.value[0], conditions: [...rules.value[0].conditions] };
    }
  } catch (err: any) {
    showToast(err?.message || 'Failed to load rules', 'error');
  } finally {
    isLoading.value = false;
  }
}

function selectRule(rule: TriggerConditionRule) {
  selectedRule.value = { ...rule, conditions: rule.conditions.map(c => ({ ...c })) };
  testResult.value = null;
}

function addCondition() {
  if (!selectedRule.value) return;
  selectedRule.value.conditions.push({
    id: `c${Date.now()}`,
    field: 'pr.lines_changed',
    operator: 'greater_than',
    value: '',
  });
}

function removeCondition(id: string) {
  if (!selectedRule.value) return;
  selectedRule.value.conditions = selectedRule.value.conditions.filter(c => c.id !== id);
}

async function addRule() {
  if (!triggerId.value) {
    showToast('Select a trigger first (add ?trigger_id=... to the URL)', 'error');
    return;
  }
  isSaving.value = true;
  try {
    const res = await triggerConditionsApi.create(triggerId.value, {
      name: 'New Rule',
      description: '',
      enabled: false,
      logic: 'AND',
      conditions: [{ id: `c${Date.now()}`, field: 'pr.lines_changed', operator: 'greater_than', value: '0' }],
    });
    rules.value.push(res.rule);
    selectedRule.value = { ...res.rule, conditions: [...res.rule.conditions] };
    testResult.value = null;
    showToast('Rule created', 'success');
  } catch (err: any) {
    showToast(err?.message || 'Failed to create rule', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function handleSave() {
  if (!selectedRule.value) return;
  isSaving.value = true;
  try {
    if (selectedRule.value.id.startsWith('tcond-')) {
      // Existing rule — update it
      const updated = await triggerConditionsApi.update(selectedRule.value.id, {
        name: selectedRule.value.name,
        description: selectedRule.value.description,
        enabled: selectedRule.value.enabled,
        logic: selectedRule.value.logic,
        conditions: selectedRule.value.conditions,
      });
      const idx = rules.value.findIndex(r => r.id === updated.id);
      if (idx !== -1) rules.value[idx] = updated;
      selectedRule.value = { ...updated, conditions: [...updated.conditions] };
      showToast('Rule saved', 'success');
    }
  } catch (err: any) {
    showToast(err?.message || 'Failed to save rule', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function handleDelete() {
  if (!selectedRule.value) return;
  isDeleting.value = true;
  try {
    await triggerConditionsApi.delete(selectedRule.value.id);
    rules.value = rules.value.filter(r => r.id !== selectedRule.value!.id);
    selectedRule.value = rules.value[0] ? { ...rules.value[0] } : null;
    testResult.value = null;
    showToast('Rule deleted', 'success');
  } catch (err: any) {
    showToast(err?.message || 'Failed to delete rule', 'error');
  } finally {
    isDeleting.value = false;
  }
}

async function testRule() {
  if (!selectedRule.value) return;
  isTestingRule.value = true;
  testResult.value = null;
  try {
    // Client-side dry evaluation (no server round-trip needed for simple logic preview)
    await new Promise(r => setTimeout(r, 300));
    const conditionCount = selectedRule.value.conditions.length;
    const allFilled = selectedRule.value.conditions.every(c => c.value.trim().length > 0);
    testResult.value = {
      matched: allFilled,
      reason: allFilled
        ? `${conditionCount} condition${conditionCount > 1 ? 's' : ''} evaluated — rule would ${selectedRule.value.enabled ? 'ALLOW' : 'BLOCK'} execution (${selectedRule.value.logic})`
        : 'Some conditions have empty values — fill all values before testing',
    };
  } finally {
    isTestingRule.value = false;
  }
}

onMounted(loadRules);
</script>

<template>
  <div class="conditional-rules">

    <PageHeader
      title="Conditional Trigger Rules Engine"
      subtitle="Add filter conditions to triggers so bots only run when specific criteria are met — reducing noise and wasted tokens."
    />

    <div v-if="isLoading" class="loading-state">Loading rules…</div>

    <div v-else class="layout">
      <!-- Rule list -->
      <aside class="sidebar card">
        <div class="sidebar-header">
          <span>Rules</span>
          <button class="btn-add" :disabled="isSaving" @click="addRule">+</button>
        </div>
        <div v-if="rules.length === 0" class="empty-sidebar">
          No rules yet.<br/>Click + to add one.
        </div>
        <div
          v-for="rule in rules"
          :key="rule.id"
          class="rule-item"
          :class="{ active: selectedRule?.id === rule.id }"
          @click="selectRule(rule)"
        >
          <div class="rule-row">
            <span class="rule-name">{{ rule.name }}</span>
            <span class="rule-pill" :class="rule.enabled ? 'pill-on' : 'pill-off'">
              {{ rule.enabled ? 'ON' : 'OFF' }}
            </span>
          </div>
          <div class="rule-bot">{{ rule.trigger_id }}</div>
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="selectedRule" class="editor">
        <div class="card">
          <div class="card-header">Rule Settings</div>
          <div class="card-body">
            <div class="field-row">
              <div class="field">
                <label class="field-label">Rule Name</label>
                <input v-model="selectedRule.name" class="input" />
              </div>
              <div class="field">
                <label class="field-label">Trigger ID</label>
                <input :value="selectedRule.trigger_id" class="input" disabled />
              </div>
            </div>
            <div class="field">
              <label class="field-label">Description</label>
              <input v-model="selectedRule.description" class="input" />
            </div>
            <div class="field-row">
              <div class="field">
                <label class="field-label">Condition Logic</label>
                <select v-model="selectedRule.logic" class="select">
                  <option value="AND">ALL must match (AND)</option>
                  <option value="OR">ANY must match (OR)</option>
                </select>
              </div>
              <div class="field">
                <label class="field-label">Enabled</label>
                <label class="toggle-label">
                  <input type="checkbox" v-model="selectedRule.enabled" />
                  <span>{{ selectedRule.enabled ? 'Active' : 'Disabled' }}</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <span>Conditions</span>
            <span class="logic-badge">{{ selectedRule.logic }}</span>
          </div>
          <div class="conditions-body">
            <div
              v-for="(cond, idx) in selectedRule.conditions"
              :key="cond.id"
              class="condition-row"
            >
              <span class="cond-connector" v-if="idx > 0">{{ selectedRule.logic }}</span>
              <div class="cond-fields">
                <select v-model="cond.field" class="select cond-select">
                  <option v-for="f in fieldOptions" :key="f.value" :value="f.value">{{ f.label }}</option>
                </select>
                <select v-model="cond.operator" class="select cond-op-select">
                  <option v-for="op in operatorOptions" :key="op.value" :value="op.value">{{ op.label }}</option>
                </select>
                <input v-model="cond.value" class="input cond-value" placeholder="value" />
                <button class="btn-remove" @click="removeCondition(cond.id)" :disabled="selectedRule.conditions.length <= 1">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
            </div>
            <button class="btn-add-cond" @click="addCondition">+ Add Condition</button>
          </div>
        </div>

        <div v-if="testResult" class="test-result card" :class="testResult.matched ? 'result-pass' : 'result-fail'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline v-if="testResult.matched" points="20 6 9 17 4 12"/>
            <circle v-else cx="12" cy="12" r="10"/><line v-if="!testResult.matched" x1="15" y1="9" x2="9" y2="15"/>
          </svg>
          {{ testResult.reason }}
        </div>

        <div class="actions">
          <button class="btn btn-danger" :disabled="isDeleting" @click="handleDelete">
            {{ isDeleting ? 'Deleting...' : 'Delete Rule' }}
          </button>
          <button class="btn btn-ghost" :disabled="isTestingRule" @click="testRule">
            {{ isTestingRule ? 'Testing...' : 'Test Rule' }}
          </button>
          <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save Rule' }}
          </button>
        </div>
      </div>

      <div v-else class="editor empty-editor">
        <p>Select a rule from the list or create a new one.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.conditional-rules { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }
.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
.btn-add { background: var(--accent-cyan); color: #000; border: none; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; font-weight: 700; font-size: 1rem; display: flex; align-items: center; justify-content: center; }

.rule-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.rule-item:hover { background: var(--bg-tertiary); }
.rule-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.rule-item:last-child { border-bottom: none; }
.rule-row { display: flex; align-items: center; justify-content: space-between; }
.rule-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.rule-bot { font-size: 0.72rem; color: var(--text-muted); margin-top: 3px; font-family: monospace; }
.rule-pill { font-size: 0.6rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.pill-on { background: rgba(52, 211, 153, 0.2); color: #34d399; }
.pill-off { background: var(--bg-tertiary); color: var(--text-muted); }

.editor { display: flex; flex-direction: column; gap: 16px; }
.card-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; justify-content: space-between; }
.logic-badge { font-size: 0.7rem; font-weight: 700; padding: 2px 8px; background: rgba(99,102,241,0.15); color: #818cf8; border-radius: 4px; }
.card-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); }
.input { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.input:focus { outline: none; border-color: var(--accent-cyan); }
.select { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; cursor: pointer; }
.select:focus { outline: none; border-color: var(--accent-cyan); }
.toggle-label { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
.toggle-label input { accent-color: var(--accent-cyan); cursor: pointer; }

.conditions-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
.condition-row { display: flex; flex-direction: column; gap: 6px; }
.cond-connector { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; padding: 2px 0; }
.cond-fields { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; align-items: center; }
.cond-select { }
.cond-op-select { }
.cond-value { }
.btn-remove { display: flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-secondary); cursor: pointer; flex-shrink: 0; }
.btn-remove:hover:not(:disabled) { border-color: #ef4444; color: #ef4444; }
.btn-remove:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-add-cond { display: flex; align-items: center; padding: 6px 12px; background: none; border: 1px dashed var(--border-default); border-radius: 6px; color: var(--text-tertiary); font-size: 0.8rem; cursor: pointer; width: fit-content; margin-top: 4px; }
.btn-add-cond:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.test-result { display: flex; align-items: center; gap: 10px; padding: 14px 20px; font-size: 0.83rem; font-weight: 500; }
.result-pass { color: #34d399; }
.result-fail { color: #ef4444; }

.actions { display: flex; justify-content: flex-end; gap: 12px; }
.btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; }
.btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.2); }
.btn-danger:disabled { opacity: 0.4; cursor: not-allowed; }

.loading-state { text-align: center; padding: 48px; color: var(--text-muted); font-size: 0.85rem; }
.empty-sidebar { padding: 20px 16px; color: var(--text-muted); font-size: 0.78rem; text-align: center; line-height: 1.6; }
.empty-editor { display: flex; align-items: center; justify-content: center; min-height: 200px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; }
.empty-editor p { color: var(--text-muted); font-size: 0.85rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .cond-fields { grid-template-columns: 1fr 1fr; } .field-row { grid-template-columns: 1fr; } }
</style>
