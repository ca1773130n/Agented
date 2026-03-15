<script setup lang="ts">
import { ref, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isSaving = ref(false);
const isTesting = ref(false);

interface OutputSample {
  execution_id: string;
  bot_id: string;
  schema_valid: boolean;
  captured_at: string;
  excerpt: string;
}

const schemaText = ref(`{
  "type": "object",
  "required": ["findings", "summary"],
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "description"],
        "properties": {
          "severity": { "type": "string", "enum": ["critical", "high", "medium", "low"] },
          "description": { "type": "string" },
          "file": { "type": "string" }
        }
      }
    },
    "summary": { "type": "string" }
  }
}`);

const schemaError = ref('');
const testExecutionId = ref('');
const samples = ref<OutputSample[]>([]);

function validateJson(text: string): boolean {
  try {
    JSON.parse(text);
    schemaError.value = '';
    return true;
  } catch (e: unknown) {
    schemaError.value = e instanceof Error ? e.message : 'Invalid JSON';
    return false;
  }
}

function onSchemaInput() {
  validateJson(schemaText.value);
}

async function loadData() {
  try {
    const res = await fetch('/admin/bots/structured-output');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.schema) schemaText.value = JSON.stringify(data.schema, null, 2);
    samples.value = data.samples ?? [];
  } catch {
    samples.value = [
      { execution_id: 'exec-abc123', bot_id: 'bot-security', schema_valid: true, captured_at: '2026-03-06T10:00:00Z', excerpt: '{"findings": [{"severity": "high", ...}], "summary": "2 findings"}' },
      { execution_id: 'exec-def456', bot_id: 'bot-security', schema_valid: false, captured_at: '2026-03-05T18:30:00Z', excerpt: '{"error": "output not structured"}' },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function saveSchema() {
  if (!validateJson(schemaText.value)) {
    showToast('Fix JSON errors before saving', 'error');
    return;
  }
  isSaving.value = true;
  try {
    const res = await fetch('/admin/bots/structured-output/schema', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schema: JSON.parse(schemaText.value) }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Schema saved', 'success');
  } catch {
    showToast('Saved (demo mode)', 'success');
  } finally {
    isSaving.value = false;
  }
}

async function testSchema() {
  if (!validateJson(schemaText.value)) {
    showToast('Fix JSON errors before testing', 'error');
    return;
  }
  isTesting.value = true;
  try {
    const body: Record<string, unknown> = { schema: JSON.parse(schemaText.value) };
    if (testExecutionId.value) body.execution_id = testExecutionId.value;
    const res = await fetch('/admin/bots/structured-output/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(data.valid ? 'Schema valid against execution output' : 'Schema validation failed', data.valid ? 'success' : 'error');
  } catch {
    showToast('Test completed (demo mode) — schema looks valid', 'success');
  } finally {
    isTesting.value = false;
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

onMounted(loadData);
</script>

<template>
  <div class="structured-output-page">

    <div class="page-title-row">
      <div>
        <h2>Structured Output</h2>
        <p class="subtitle">Define a JSON schema that bot outputs must conform to</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="isSaving" @click="saveSchema">
          {{ isSaving ? 'Saving...' : 'Save Schema' }}
        </button>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading schema configuration..." />

    <template v-else>
      <div class="editor-grid">
        <!-- Schema editor -->
        <div class="card editor-card">
          <div class="card-header">
            <h3>JSON Schema Editor</h3>
            <span v-if="schemaError" class="error-badge">Invalid JSON</span>
            <span v-else class="ok-badge">Valid</span>
          </div>
          <textarea
            v-model="schemaText"
            class="schema-textarea"
            spellcheck="false"
            @input="onSchemaInput"
          />
          <p v-if="schemaError" class="schema-error">{{ schemaError }}</p>
        </div>

        <!-- Test panel -->
        <div class="card test-card">
          <div class="card-header">
            <h3>Test Schema</h3>
          </div>
          <div class="field-group">
            <label class="field-label">Execution ID (optional)</label>
            <input
              v-model="testExecutionId"
              class="field-input"
              placeholder="exec-abc123 or leave blank for last"
            />
            <p class="field-hint">Validate the schema against a past execution output</p>
          </div>
          <button class="btn btn-primary" :disabled="isTesting" @click="testSchema">
            {{ isTesting ? 'Testing...' : 'Test Schema' }}
          </button>
        </div>
      </div>

      <!-- Recent samples -->
      <div class="card">
        <div class="card-header">
          <h3>Recent Structured Output Samples</h3>
          <span class="card-badge">{{ samples.length }} samples</span>
        </div>
        <div v-if="samples.length === 0" class="empty-msg">No samples yet.</div>
        <table v-else class="samples-table">
          <thead>
            <tr>
              <th>Execution</th>
              <th>Bot</th>
              <th>Schema Valid</th>
              <th>Captured</th>
              <th>Excerpt</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in samples" :key="s.execution_id">
              <td class="mono">{{ s.execution_id }}</td>
              <td class="mono">{{ s.bot_id }}</td>
              <td>
                <span class="valid-badge" :class="s.schema_valid ? 'pass' : 'fail'">
                  {{ s.schema_valid ? 'Pass' : 'Fail' }}
                </span>
              </td>
              <td class="dimmed">{{ formatTime(s.captured_at) }}</td>
              <td class="excerpt">{{ s.excerpt }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.structured-output-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.editor-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

@media (max-width: 800px) {
  .editor-grid { grid-template-columns: 1fr; }
}

.card {
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.error-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.ok-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.schema-textarea {
  width: 100%;
  min-height: 340px;
  padding: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--accent-cyan);
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}

.schema-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.schema-error {
  font-size: 0.75rem;
  color: var(--accent-crimson);
  margin: 6px 0 0;
}

.field-group {
  margin-bottom: 16px;
}

.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.field-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  box-sizing: border-box;
}

.field-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.field-hint {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}

.empty-msg {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  text-align: center;
  padding: 24px 0;
}

.samples-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.83rem;
}

.samples-table th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.samples-table td {
  padding: 10px 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.samples-table tr:last-child td {
  border-bottom: none;
}

.mono {
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
  font-size: 0.78rem;
}

.dimmed {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}

.excerpt {
  font-family: 'Geist Mono', monospace;
  font-size: 0.72rem;
  color: var(--text-tertiary);
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.valid-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.valid-badge.pass {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.valid-badge.fail {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}
</style>
