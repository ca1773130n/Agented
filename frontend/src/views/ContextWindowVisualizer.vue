<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { triggerApi, backendApi } from '../services/api';
import type { Trigger } from '../services/api';

const promptTemplate = ref(`You are a security expert. Analyze the following files:

{paths}

For each file, check for:
1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Authentication bypass possibilities
4. Sensitive data exposure

Return a JSON response with findings.

Payload context: {payload}

Additional context from the repository: {context}
`);

const selectedModel = ref('claude-opus-4-5');
const repoSize = ref<'small' | 'medium' | 'large' | 'xlarge'>('medium');

const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');

interface ModelConfig {
  id: string;
  name: string;
  contextWindow: number;
}

const CONTEXT_WINDOW_BY_BACKEND: Record<string, number> = {
  claude: 200000,
  codex: 128000,
  opencode: 200000,
  gemini: 1000000,
};

const FALLBACK_MODELS: ModelConfig[] = [
  { id: 'claude-haiku-3-5', name: 'Haiku 3.5', contextWindow: 200000 },
  { id: 'claude-sonnet-4-5', name: 'Sonnet 4.5', contextWindow: 200000 },
  { id: 'claude-opus-4-5', name: 'Opus 4.5', contextWindow: 200000 },
];

const models = ref<ModelConfig[]>([...FALLBACK_MODELS]);

async function loadTriggers() {
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
  } catch {
    // silently ignore — trigger selector remains empty
  }
}

async function loadBackends() {
  try {
    const res = await backendApi.list();
    if (res.backends && res.backends.length > 0) {
      const derived: ModelConfig[] = [];
      for (const backend of res.backends) {
        const contextWindow = CONTEXT_WINDOW_BY_BACKEND[backend.type] ?? 200000;
        if (backend.models && backend.models.length > 0) {
          for (const modelId of backend.models) {
            derived.push({ id: modelId, name: modelId, contextWindow });
          }
        } else {
          derived.push({ id: backend.id, name: backend.name, contextWindow });
        }
      }
      if (derived.length > 0) {
        models.value = derived;
      }
    }
  } catch {
    // silently ignore — fall back to hardcoded models
  }
}

async function onTriggerChange(triggerId: string) {
  if (!triggerId) return;
  try {
    const trigger = await triggerApi.get(triggerId);
    if (trigger.prompt_template) {
      promptTemplate.value = trigger.prompt_template;
    }
    if (trigger.model) {
      selectedModel.value = trigger.model;
    }
  } catch {
    // silently ignore
  }
}

onMounted(() => {
  loadTriggers();
  loadBackends();
});

const REPO_TOKENS: Record<string, number> = {
  small: 8000,
  medium: 40000,
  large: 120000,
  xlarge: 160000,
};

const REPO_LABELS: Record<string, string> = {
  small: 'Small (<1k files)',
  medium: 'Medium (1k–10k)',
  large: 'Large (10k–50k)',
  xlarge: 'XL (50k+)',
};

const PLACEHOLDER_TOKENS: Record<string, number> = {
  '{paths}': 500,
  '{payload}': 200,
  '{context}': 2000,
  '{pr_url}': 50,
  '{message}': 100,
};

function countBaseTokens(template: string): number {
  let cleaned = template;
  for (const ph of Object.keys(PLACEHOLDER_TOKENS)) {
    cleaned = cleaned.replace(new RegExp(ph.replace(/[{}]/g, '\\$&'), 'g'), '');
  }
  return Math.ceil(cleaned.length / 4);
}

function countPlaceholderTokens(template: string): number {
  let total = 0;
  for (const [ph, tokens] of Object.entries(PLACEHOLDER_TOKENS)) {
    const regex = new RegExp(ph.replace(/[{}]/g, '\\$&'), 'g');
    const matches = template.match(regex);
    if (matches) total += matches.length * tokens;
  }
  return total;
}

const model = computed(() => models.value.find(m => m.id === selectedModel.value) ?? models.value[1] ?? models.value[0]);
const promptBaseTokens = computed(() => countBaseTokens(promptTemplate.value));
const promptPhTokens = computed(() => countPlaceholderTokens(promptTemplate.value));
const repoContextTokens = computed(() => REPO_TOKENS[repoSize.value]);
const totalTokens = computed(() => promptBaseTokens.value + promptPhTokens.value + repoContextTokens.value);
const contextPct = computed(() => Math.min((totalTokens.value / model.value.contextWindow) * 100, 100));
const remainingTokens = computed(() => Math.max(model.value.contextWindow - totalTokens.value, 0));

const usageStatus = computed(() => {
  if (contextPct.value >= 90) return { label: 'Critical — truncation very likely', color: '#ef4444' };
  if (contextPct.value >= 70) return { label: 'Warning — truncation possible', color: '#f59e0b' };
  if (contextPct.value >= 50) return { label: 'Caution — review prompt length', color: '#eab308' };
  return { label: 'Safe — plenty of context remaining', color: '#34d399' };
});

const segments = computed(() => [
  { label: 'Prompt base', tokens: promptBaseTokens.value, color: '#3b82f6' },
  { label: 'Placeholders (estimated)', tokens: promptPhTokens.value, color: '#8b5cf6' },
  { label: 'Repo context', tokens: repoContextTokens.value, color: '#f59e0b' },
]);

function pct(tokens: number): number {
  return (tokens / model.value.contextWindow) * 100;
}

function formatK(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toString();
}

const detectedPlaceholders = computed(() => {
  const found: string[] = [];
  for (const ph of Object.keys(PLACEHOLDER_TOKENS)) {
    if (promptTemplate.value.includes(ph)) found.push(ph);
  }
  return found;
});
</script>

<template>
  <div class="ctx-visualizer">

    <PageHeader
      title="Context Window Visualizer"
      subtitle="Visualize how your prompt template fills the model's context window."
    />

    <div class="main-layout">
      <div class="card input-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
            </svg>
            Prompt Template
          </h3>
        </div>
        <div class="input-body">
          <div class="field-group">
            <label class="field-label">Load from Trigger</label>
            <select
              v-model="selectedTriggerId"
              class="trigger-select"
              @change="onTriggerChange(selectedTriggerId)"
            >
              <option value="">— select a trigger —</option>
              <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </div>

          <textarea
            v-model="promptTemplate"
            class="text-area"
            rows="16"
            placeholder="Paste your prompt template here..."
            spellcheck="false"
          />

          <div class="field-group">
            <label class="field-label">Model</label>
            <div class="model-pills">
              <button
                v-for="m in models"
                :key="m.id"
                class="model-pill"
                :class="{ active: selectedModel === m.id }"
                @click="selectedModel = m.id"
              >
                {{ m.name }}
                <span class="pill-ctx">{{ formatK(m.contextWindow) }}</span>
              </button>
            </div>
          </div>

          <div class="field-group">
            <label class="field-label">Repo Size</label>
            <div class="size-pills">
              <button
                v-for="(label, key) in REPO_LABELS"
                :key="key"
                class="size-pill"
                :class="{ active: repoSize === key }"
                @click="repoSize = key as typeof repoSize"
              >
                {{ label }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="card viz-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
            </svg>
            Context Window Usage
          </h3>
          <span class="model-badge">{{ model.name }}</span>
        </div>
        <div class="viz-body">
          <div class="usage-summary">
            <div class="usage-pct" :style="{ color: usageStatus.color }">
              {{ contextPct.toFixed(1) }}%
            </div>
            <div class="usage-label">
              {{ formatK(totalTokens) }} / {{ formatK(model.contextWindow) }} tokens used
            </div>
            <div class="usage-status" :style="{ color: usageStatus.color }">
              {{ usageStatus.label }}
            </div>
          </div>

          <!-- Stacked bar visualization -->
          <div class="context-bar-wrap">
            <div class="context-bar">
              <div
                v-for="seg in segments"
                :key="seg.label"
                class="bar-segment"
                :style="{ width: Math.min(pct(seg.tokens), 100 - segments.filter((_s, i) => i < segments.indexOf(seg)).reduce((acc, s) => acc + pct(s.tokens), 0)) + '%', background: seg.color }"
                :title="`${seg.label}: ${formatK(seg.tokens)} tokens`"
              />
              <div class="bar-remaining" :style="{ background: '#ffffff08' }"></div>
            </div>
            <div class="bar-markers">
              <span>0</span>
              <span>50%</span>
              <span>75%</span>
              <span>90%</span>
              <span>100%</span>
            </div>
            <div v-if="contextPct >= 90" class="overflow-warning">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              Template risks truncation! Reduce prompt length or repo context size.
            </div>
          </div>

          <!-- Legend -->
          <div class="legend">
            <div v-for="seg in segments" :key="seg.label" class="legend-row">
              <div class="legend-color" :style="{ background: seg.color }"></div>
              <span class="legend-label">{{ seg.label }}</span>
              <span class="legend-tokens">{{ formatK(seg.tokens) }} tokens</span>
              <span class="legend-pct">{{ pct(seg.tokens).toFixed(1) }}%</span>
            </div>
            <div class="legend-row legend-remaining">
              <div class="legend-color" style="background: var(--bg-tertiary); border: 1px solid var(--border-default)"></div>
              <span class="legend-label">Available</span>
              <span class="legend-tokens">{{ formatK(remainingTokens) }} tokens</span>
              <span class="legend-pct">{{ (100 - contextPct).toFixed(1) }}%</span>
            </div>
          </div>

          <!-- Detected placeholders -->
          <div class="placeholders">
            <div class="ph-label">Detected Placeholders</div>
            <div class="ph-list">
              <div v-if="detectedPlaceholders.length === 0" class="ph-none">No placeholders detected</div>
              <div v-for="ph in detectedPlaceholders" :key="ph" class="ph-row">
                <code class="ph-name">{{ ph }}</code>
                <span class="ph-est">~{{ PLACEHOLDER_TOKENS[ph] }} tokens (estimated)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ctx-visualizer {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.main-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
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
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.model-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
}

.input-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.trigger-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.85rem;
  cursor: pointer;
}

.trigger-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.text-area {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.8rem;
  line-height: 1.6;
  resize: vertical;
  font-family: 'Geist Mono', monospace;
  box-sizing: border-box;
}

.text-area:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 0.83rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.model-pills, .size-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.model-pill, .size-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.model-pill.active, .size-pill.active {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
}

.model-pill:hover:not(.active), .size-pill:hover:not(.active) {
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.pill-ctx {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-family: monospace;
}

.viz-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.usage-summary {
  text-align: center;
}

.usage-pct {
  font-size: 3rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.usage-label {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 6px 0 4px;
}

.usage-status {
  font-size: 0.85rem;
  font-weight: 600;
}

.context-bar-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.context-bar {
  height: 28px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  border: 1px solid var(--border-default);
}

.bar-segment {
  height: 100%;
  transition: width 0.3s ease;
}

.bar-remaining {
  flex: 1;
}

.bar-markers {
  display: flex;
  justify-content: space-between;
  font-size: 0.68rem;
  color: var(--text-muted);
}

.overflow-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 6px;
  font-size: 0.82rem;
  color: #ef4444;
}

.legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.85rem;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}

.legend-label { flex: 1; color: var(--text-secondary); }
.legend-tokens { font-family: monospace; font-size: 0.8rem; color: var(--text-tertiary); min-width: 70px; text-align: right; }
.legend-pct { font-size: 0.78rem; color: var(--text-muted); min-width: 50px; text-align: right; }

.legend-remaining { opacity: 0.6; }

.placeholders {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ph-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ph-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ph-none {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.ph-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.82rem;
}

.ph-name {
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.ph-est {
  color: var(--text-tertiary);
}

@media (max-width: 900px) {
  .main-layout { grid-template-columns: 1fr; }
}
</style>
