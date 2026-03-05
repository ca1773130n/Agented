<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface CompiledRule {
  field: string;
  operator: string;
  value: string | number;
}

const naturalLanguageInput = ref('');
const isCompiling = ref(false);
const compiledRule = ref<CompiledRule[] | null>(null);
const compiledJson = ref('');
const savedRules = ref([
  { id: 'r1', description: 'run when a PR touches the auth directory and has more than 100 lines changed', compiled: { event: 'pull_request', conditions: [{ field: 'changed_files', operator: 'includes_path', value: 'auth/' }, { field: 'lines_changed', operator: 'gt', value: 100 }] } },
  { id: 'r2', description: 'fire when commit message contains "fix" and the branch is main', compiled: { event: 'push', conditions: [{ field: 'head_commit.message', operator: 'contains', value: 'fix' }, { field: 'ref', operator: 'eq', value: 'refs/heads/main' }] } },
]);

const examples = [
  'run when a PR touches the auth directory and has more than 100 lines changed',
  'fire when commit message contains "fix" and the branch is main',
  'trigger when PR title includes "security" or any file in src/db/ is modified',
];

async function handleCompile() {
  if (!naturalLanguageInput.value.trim()) return;
  isCompiling.value = true;
  compiledRule.value = null;
  try {
    await new Promise(r => setTimeout(r, 1000));
    const input = naturalLanguageInput.value.toLowerCase();
    const conditions: CompiledRule[] = [];
    if (input.includes('auth')) conditions.push({ field: 'changed_files', operator: 'includes_path', value: 'auth/' });
    if (input.includes('100 lines')) conditions.push({ field: 'lines_changed', operator: 'gt', value: 100 });
    if (input.includes('fix')) conditions.push({ field: 'head_commit.message', operator: 'contains', value: 'fix' });
    if (input.includes('main')) conditions.push({ field: 'ref', operator: 'eq', value: 'refs/heads/main' });
    if (conditions.length === 0) conditions.push({ field: 'event', operator: 'eq', value: 'push' });
    compiledRule.value = conditions;
    compiledJson.value = JSON.stringify({ conditions, logic: 'and' }, null, 2);
    showToast('Rule compiled successfully', 'success');
  } finally {
    isCompiling.value = false;
  }
}

async function handleSave() {
  if (!compiledRule.value) return;
  savedRules.value.unshift({
    id: `r${Date.now()}`,
    description: naturalLanguageInput.value,
    compiled: { event: 'github', conditions: compiledRule.value as any },
  });
  showToast('Rule saved', 'success');
  naturalLanguageInput.value = '';
  compiledRule.value = null;
}

function useExample(ex: string) {
  naturalLanguageInput.value = ex;
}
</script>

<template>
  <div class="nl-trigger">
    <AppBreadcrumb :items="[
      { label: 'Triggers', action: () => router.push({ name: 'triggers' }) },
      { label: 'Natural Language Rule Editor' },
    ]" />

    <PageHeader
      title="Natural Language Trigger Rule Editor"
      subtitle="Write trigger conditions in plain English — the platform compiles them to structured filter rules."
    />

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
                {{ isCompiling ? 'Compiling...' : '⚡ Compile Rule' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="compiledRule" class="card compiled-card">
          <div class="compiled-header">
            <span>Compiled Rule</span>
            <button class="btn btn-primary btn-sm" @click="handleSave">Save Rule</button>
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
        <div class="saved-header">Saved Rules</div>
        <div v-for="r in savedRules" :key="r.id" class="saved-rule">
          <div class="saved-desc">{{ r.description }}</div>
          <div class="saved-conditions">{{ r.compiled.conditions.length }} condition{{ r.compiled.conditions.length !== 1 ? 's' : '' }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.nl-trigger { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

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

.saved-header { padding: 14px 16px; border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
.saved-rule { padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); }
.saved-rule:last-child { border-bottom: none; }
.saved-desc { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; margin-bottom: 4px; }
.saved-conditions { font-size: 0.7rem; color: var(--text-muted); }

.btn { display: flex; align-items: center; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm { padding: 5px 12px; font-size: 0.75rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
