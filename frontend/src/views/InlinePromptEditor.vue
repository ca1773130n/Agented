<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';
const showToast = useToast();

const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const isLoadingTriggers = ref(false);
const isLoadingPrompt = ref(false);
const loadError = ref('');

const prompt = ref('');

const testPayload = ref(JSON.stringify({
  diff: '--- a/src/auth.ts\n+++ b/src/auth.ts\n@@ -5,4 +5,6 @@\n+const token = req.query.token;',
  repo: 'org/api',
  author: 'john.doe',
  file_count: 3,
}, null, 2));

const isSaving = ref(false);
const payloadError = ref('');

const variables = computed(() => {
  const matches = prompt.value.match(/\{([^}]+)\}/g) || [];
  return matches.map(m => m.slice(1, -1));
});

const renderedPrompt = computed(() => {
  try {
    const payload = JSON.parse(testPayload.value);
    let rendered = prompt.value;
    for (const [key, val] of Object.entries(payload)) {
      rendered = rendered.split(`{${key}}`).join(String(val));
    }
    return rendered;
  } catch {
    return prompt.value;
  }
});

const unresolvedVars = computed(() => {
  try {
    const payload = JSON.parse(testPayload.value);
    return variables.value.filter(v => !(v in payload));
  } catch {
    return variables.value;
  }
});

function validatePayload() {
  try {
    JSON.parse(testPayload.value);
    payloadError.value = '';
    return true;
  } catch (e: unknown) {
    payloadError.value = e instanceof Error ? e.message : 'Invalid JSON';
    return false;
  }
}

watch(testPayload, () => { if (testPayload.value) validatePayload(); });

onMounted(async () => {
  await loadTriggers();
});

async function loadTriggers() {
  isLoadingTriggers.value = true;
  loadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
    if (triggers.value.length > 0 && !selectedTriggerId.value) {
      selectedTriggerId.value = triggers.value[0].id;
      await loadTriggerPrompt(triggers.value[0].id);
    }
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load triggers';
  } finally {
    isLoadingTriggers.value = false;
  }
}

async function loadTriggerPrompt(triggerId: string) {
  isLoadingPrompt.value = true;
  try {
    const trigger = await triggerApi.get(triggerId);
    prompt.value = trigger.prompt_template || '';
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to load prompt', 'error');
  } finally {
    isLoadingPrompt.value = false;
  }
}

watch(selectedTriggerId, async (newId) => {
  if (newId) {
    await loadTriggerPrompt(newId);
  }
});

async function handleSave() {
  if (!selectedTriggerId.value) {
    showToast('Select a trigger first', 'info');
    return;
  }
  isSaving.value = true;
  try {
    await triggerApi.update(selectedTriggerId.value, { prompt_template: prompt.value });
    showToast('Prompt template saved', 'success');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to save prompt', 'error');
  } finally {
    isSaving.value = false;
  }
}

function highlightPrompt(text: string) {
  return text
    .replace(/\{([^}]+)\}/g, '<mark class="var-highlight">{$1}</mark>')
    .replace(/\n/g, '<br>');
}
</script>

<template>
  <div class="prompt-editor">

    <PageHeader
      title="Inline Prompt Editor with Live Preview"
      subtitle="Split-pane editor with template variable highlighting, test payload injector, and rendered preview."
    />

    <!-- Trigger selector -->
    <div v-if="isLoadingTriggers" class="loading-bar">Loading triggers...</div>
    <div v-else-if="loadError" class="error-bar">{{ loadError }}</div>
    <div v-else-if="triggers.length === 0" class="empty-bar">No triggers found. Create a trigger first.</div>
    <div v-else class="trigger-selector">
      <label class="selector-label">Trigger:</label>
      <select v-model="selectedTriggerId" class="trigger-select">
        <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }} ({{ t.id }})</option>
      </select>
    </div>

    <div v-if="isLoadingPrompt" class="loading-bar">Loading prompt...</div>

    <div class="variables-bar" v-if="variables.length > 0">
      <span class="vars-label">Variables:</span>
      <span
        v-for="v in variables"
        :key="v"
        :class="['var-chip', { 'var-unresolved': unresolvedVars.includes(v) }]"
      >{{ v }}</span>
    </div>

    <div class="editor-grid">
      <!-- Left: Prompt editor -->
      <div class="pane">
        <div class="pane-header">
          <span>Prompt Template</span>
          <button class="btn btn-primary btn-sm" :disabled="isSaving || !selectedTriggerId" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save' }}
          </button>
        </div>
        <textarea v-model="prompt" class="prompt-textarea" spellcheck="false"></textarea>
      </div>

      <!-- Middle: Test payload -->
      <div class="pane">
        <div class="pane-header">
          <span>Test Payload (JSON)</span>
          <span v-if="payloadError" class="payload-error">{{ payloadError }}</span>
        </div>
        <textarea
          v-model="testPayload"
          class="payload-textarea"
          spellcheck="false"
          @input="validatePayload"
        ></textarea>
      </div>

      <!-- Right: Rendered preview -->
      <div class="pane">
        <div class="pane-header">
          <span>Rendered Preview</span>
          <span v-if="unresolvedVars.length > 0" class="unresolved-warning">
            {{ unresolvedVars.length }} unresolved
          </span>
        </div>
        <div class="rendered-preview" v-html="highlightPrompt(renderedPrompt)"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prompt-editor { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.trigger-selector { display: flex; align-items: center; gap: 12px; }
.selector-label { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.trigger-select { flex: 1; max-width: 400px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }

.loading-bar { font-size: 0.82rem; color: var(--text-tertiary); padding: 12px 0; }
.error-bar { font-size: 0.82rem; color: #ef4444; padding: 12px 0; }
.empty-bar { font-size: 0.82rem; color: var(--text-muted); padding: 12px 0; }

.variables-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.vars-label { font-size: 0.75rem; color: var(--text-tertiary); font-weight: 500; }
.var-chip { font-size: 0.72rem; font-family: monospace; padding: 3px 8px; border-radius: 4px; background: rgba(6,182,212,0.1); color: var(--accent-cyan); border: 1px solid rgba(6,182,212,0.2); }
.var-unresolved { background: rgba(251,191,36,0.1); color: #fbbf24; border-color: rgba(251,191,36,0.2); }

.editor-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; height: 600px; }

.pane { display: flex; flex-direction: column; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.pane-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--border-default); font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); background: var(--bg-tertiary); flex-shrink: 0; }

.payload-error { font-size: 0.7rem; color: #ef4444; font-weight: normal; }
.unresolved-warning { font-size: 0.7rem; color: #fbbf24; font-weight: normal; }

.prompt-textarea, .payload-textarea {
  flex: 1; padding: 14px; background: var(--bg-secondary); border: none; resize: none;
  color: var(--text-primary); font-family: 'Geist Mono', monospace; font-size: 0.78rem; line-height: 1.6;
  outline: none;
}

.rendered-preview {
  flex: 1; padding: 14px; overflow: auto; font-family: inherit; font-size: 0.8rem;
  color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap;
}

.btn { display: flex; align-items: center; padding: 5px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm { padding: 4px 10px; font-size: 0.72rem; }

@media (max-width: 1100px) { .editor-grid { grid-template-columns: 1fr; height: auto; } .pane { height: 300px; } }
</style>

<style>
/* Non-scoped for v-html content */
.var-highlight { background: rgba(6,182,212,0.15); color: var(--accent-cyan); border-radius: 3px; padding: 1px 3px; font-weight: 600; }
</style>
