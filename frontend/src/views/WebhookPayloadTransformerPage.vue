<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { payloadTransformerApi } from '../services/api/payload-transformers';

const router = useRouter();
const route = useRoute();
const showToast = useToast();

const triggerId = computed(() => (route.query.triggerId as string) || 'global');
const isSaving = ref(false);

type TransformMode = 'jsonpath' | 'jq' | 'rename' | 'extract';

interface TransformRule {
  id: string;
  mode: TransformMode;
  expression: string;
  output_key: string;
  description: string;
}

const rawPayload = ref(JSON.stringify({
  action: 'opened',
  pull_request: {
    number: 42,
    title: 'Fix authentication bug',
    body: 'This PR fixes the login flow issue',
    user: { login: 'dev', email: 'dev@example.com' },
    base: { ref: 'main' },
    head: { ref: 'feature/fix-auth', sha: 'abc1234' },
  },
  repository: {
    full_name: 'org/backend',
    default_branch: 'main',
  },
  sender: { login: 'dev' },
}, null, 2));

const rules = ref<TransformRule[]>([]);

const transformedPayload = ref<Record<string, unknown>>({});
const payloadError = ref('');
const activeRuleId = ref<string | null>(null);

const modeOptions: { value: TransformMode; label: string; icon: string }[] = [
  { value: 'jsonpath', label: 'JSONPath', icon: '$.' },
  { value: 'jq', label: 'jq-style', icon: '|' },
  { value: 'rename', label: 'Rename Key', icon: '→' },
  { value: 'extract', label: 'Extract', icon: '[]' },
];

function newRule(): TransformRule {
  return {
    id: Math.random().toString(36).slice(2, 8),
    mode: 'jsonpath',
    expression: '',
    output_key: '',
    description: '',
  };
}

function addRule() {
  const rule = newRule();
  rules.value.push(rule);
  activeRuleId.value = rule.id;
}

function removeRule(id: string) {
  rules.value = rules.value.filter(r => r.id !== id);
  if (activeRuleId.value === id) activeRuleId.value = null;
}

function getNestedValue(obj: unknown, path: string): unknown {
  // Simplified JSONPath: $.a.b.c
  const parts = path.replace(/^\$\./, '').split('.');
  let cur: unknown = obj;
  for (const p of parts) {
    if (typeof cur !== 'object' || cur === null) return undefined;
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

function runTransform() {
  payloadError.value = '';
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawPayload.value);
  } catch {
    payloadError.value = 'Invalid JSON payload';
    return;
  }

  const result: Record<string, unknown> = {};

  for (const rule of rules.value) {
    if (!rule.expression || !rule.output_key) continue;
    if (rule.mode === 'jsonpath' || rule.mode === 'extract') {
      const val = getNestedValue(parsed, rule.expression);
      result[rule.output_key] = val !== undefined ? val : `(no match: ${rule.expression})`;
    } else if (rule.mode === 'rename') {
      const val = getNestedValue(parsed, rule.expression);
      result[rule.output_key] = val;
    } else if (rule.mode === 'jq') {
      result[rule.output_key] = `[jq: ${rule.expression}]`;
    }
  }

  transformedPayload.value = result;
  showToast('Transform applied', 'success');
}

const hasTransformResult = computed(() => Object.keys(transformedPayload.value).length > 0);

onMounted(async () => {
  try {
    const data = await payloadTransformerApi.get(triggerId.value);
    if (data.rules && data.rules.length > 0) {
      rules.value = data.rules as TransformRule[];
    }
  } catch {
    // No transformer saved yet — start with empty rules
  }
});

async function saveRules() {
  isSaving.value = true;
  try {
    await payloadTransformerApi.save(triggerId.value, {
      name: 'default',
      rules: rules.value,
    });
    showToast('Rules saved', 'success');
  } catch {
    showToast('Failed to save rules', 'error');
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="transformer">
    <AppBreadcrumb :items="[
      { label: 'Webhooks', action: () => router.push({ name: 'webhook-recorder' }) },
      { label: 'Payload Transformer' },
    ]" />

    <PageHeader
      title="Webhook Payload Transformer"
      subtitle="Define JSONPath or jq-style transforms on incoming webhook payloads before they reach your prompt template."
    />

    <div class="layout">
      <!-- Left: payload + transform rules -->
      <div class="left-col">
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
              </svg>
              Raw Webhook Payload
            </h3>
          </div>
          <div class="card-body">
            <textarea
              v-model="rawPayload"
              class="code-editor"
              :class="{ 'error-border': payloadError }"
              rows="16"
              placeholder='{"action": "opened", "pull_request": {...}}'
            />
            <p v-if="payloadError" class="error-msg">{{ payloadError }}</p>
          </div>
        </div>

        <!-- Transform rules -->
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
              </svg>
              Transform Rules
            </h3>
            <button class="btn btn-secondary btn-sm" @click="addRule">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              Add Rule
            </button>
          </div>
          <div class="rules-list">
            <div
              v-for="rule in rules"
              :key="rule.id"
              class="rule-item"
              :class="{ active: activeRuleId === rule.id }"
              @click="activeRuleId = rule.id"
            >
              <div class="rule-mode-badge">{{ rule.mode }}</div>
              <div class="rule-body">
                <div class="rule-top-row">
                  <input
                    v-model="rule.expression"
                    class="rule-input mono"
                    :placeholder="rule.mode === 'jsonpath' ? '$.pull_request.title' : rule.mode === 'jq' ? '.pull_request.title' : 'source_key'"
                    @click.stop
                  />
                  <span class="arrow-icon">→</span>
                  <input
                    v-model="rule.output_key"
                    class="rule-input"
                    placeholder="output_key"
                    @click.stop
                  />
                </div>
                <div class="rule-bottom-row">
                  <select v-model="rule.mode" class="mode-select" @click.stop>
                    <option v-for="m in modeOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
                  </select>
                  <input v-model="rule.description" class="rule-input desc-input" placeholder="Description (optional)" @click.stop />
                </div>
              </div>
              <button class="remove-btn" @click.stop="removeRule(rule.id)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div v-if="rules.length === 0" class="empty-rules">
              No rules defined. Click "Add Rule" to get started.
            </div>
          </div>
          <div class="card-footer">
            <button class="btn btn-secondary btn-sm" :disabled="isSaving" @click="saveRules">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
              </svg>
              {{ isSaving ? 'Saving…' : 'Save Rules' }}
            </button>
            <button class="btn btn-primary" :disabled="rules.length === 0" @click="runTransform">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              Run Transform
            </button>
          </div>
        </div>
      </div>

      <!-- Right: result -->
      <div class="right-col">
        <div class="card output-card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
              Transformed Output
            </h3>
            <span v-if="hasTransformResult" class="card-badge">{{ Object.keys(transformedPayload).length }} keys</span>
          </div>

          <div v-if="!hasTransformResult" class="empty-output">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <p>Define transform rules and click "Run Transform" to see the output.</p>
          </div>

          <pre v-else class="output-pre">{{ JSON.stringify(transformedPayload, null, 2) }}</pre>
        </div>

        <!-- Placeholder hint -->
        <div v-if="hasTransformResult" class="card hint-card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
              </svg>
              Use in Prompt Template
            </h3>
          </div>
          <div class="hint-body">
            <p class="hint-desc">Reference transformed values in your prompt template using these placeholders:</p>
            <div class="placeholder-list">
              <div v-for="(val, key) in transformedPayload" :key="key" class="placeholder-item">
                <code class="placeholder-key">{{ '{' + key + '}' }}</code>
                <span class="placeholder-arrow">→</span>
                <span class="placeholder-val">{{ String(val).slice(0, 60) }}{{ String(val).length > 60 ? '...' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.transformer {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

.left-col, .right-col { display: flex; flex-direction: column; gap: 16px; }

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
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.card-badge {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-weight: 600;
}

.card-body { padding: 16px 18px; }

.code-editor {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}

.code-editor:focus { outline: none; border-color: var(--accent-cyan); }
.error-border { border-color: #ef4444 !important; }
.error-msg { font-size: 0.78rem; color: #ef4444; margin-top: 6px; }

.rules-list { display: flex; flex-direction: column; }

.rule-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
}

.rule-item:last-child { border-bottom: none; }
.rule-item:hover { background: var(--bg-tertiary); }
.rule-item.active { background: rgba(6, 182, 212, 0.05); }

.rule-mode-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 3px 7px;
  background: rgba(6, 182, 212, 0.15);
  color: var(--accent-cyan);
  border-radius: 4px;
  text-transform: uppercase;
  white-space: nowrap;
  margin-top: 2px;
}

.rule-body { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }

.rule-top-row { display: flex; align-items: center; gap: 6px; }
.rule-bottom-row { display: flex; align-items: center; gap: 6px; }

.rule-input {
  flex: 1;
  padding: 5px 9px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.78rem;
  min-width: 0;
}

.rule-input:focus { outline: none; border-color: var(--accent-cyan); }
.mono { font-family: 'Geist Mono', monospace; }
.desc-input { color: var(--text-secondary); }

.arrow-icon { color: var(--text-tertiary); font-size: 0.875rem; flex-shrink: 0; }

.mode-select {
  padding: 5px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-tertiary);
  padding: 4px;
  border-radius: 4px;
  transition: all 0.1s;
  flex-shrink: 0;
  margin-top: 2px;
}

.remove-btn:hover { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

.empty-rules {
  padding: 24px 18px;
  font-size: 0.82rem;
  color: var(--text-tertiary);
  text-align: center;
}

.card-footer {
  padding: 14px 18px;
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 5px 11px; font-size: 0.78rem; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.output-card { min-height: 300px; }

.empty-output {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-output p { font-size: 0.82rem; max-width: 240px; }

.output-pre {
  padding: 18px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  overflow: auto;
  max-height: 500px;
  margin: 0;
}

.hint-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; }

.hint-desc { font-size: 0.8rem; color: var(--text-secondary); margin: 0; }

.placeholder-list { display: flex; flex-direction: column; gap: 6px; }

.placeholder-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 0.78rem;
}

.placeholder-key {
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
  font-size: 0.78rem;
  flex-shrink: 0;
}

.placeholder-arrow { color: var(--text-tertiary); flex-shrink: 0; }

.placeholder-val {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
