<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

const promptText = ref('');
const codebaseSize = ref<'small' | 'medium' | 'large' | 'xlarge'>('medium');
const selectedModel = ref('claude-opus-4-5');

interface ModelInfo {
  id: string;
  name: string;
  inputPricePer1M: number;
  outputPricePer1M: number;
  contextWindow: number;
  speed: 'fast' | 'medium' | 'slow';
}

const MODELS: ModelInfo[] = [
  { id: 'claude-haiku-3-5', name: 'Claude Haiku 3.5', inputPricePer1M: 0.80, outputPricePer1M: 4.00, contextWindow: 200000, speed: 'fast' },
  { id: 'claude-sonnet-4-5', name: 'Claude Sonnet 4.5', inputPricePer1M: 3.00, outputPricePer1M: 15.00, contextWindow: 200000, speed: 'medium' },
  { id: 'claude-opus-4-5', name: 'Claude Opus 4.5', inputPricePer1M: 15.00, outputPricePer1M: 75.00, contextWindow: 200000, speed: 'slow' },
];

const CODEBASE_TOKENS: Record<string, number> = {
  small: 10000,
  medium: 50000,
  large: 150000,
  xlarge: 400000,
};

const CODEBASE_LABELS: Record<string, string> = {
  small: 'Small (<1k files)',
  medium: 'Medium (1k–10k files)',
  large: 'Large (10k–50k files)',
  xlarge: 'Extra Large (50k+ files)',
};

function countTokens(text: string): number {
  // Rough estimate: ~4 chars per token
  return Math.ceil(text.length / 4);
}

const promptTokens = computed(() => countTokens(promptText.value));
const contextTokens = computed(() => CODEBASE_TOKENS[codebaseSize.value]);
const totalInputTokens = computed(() => promptTokens.value + contextTokens.value);
const estimatedOutputTokens = computed(() => Math.min(totalInputTokens.value * 0.3, 4000));

const selectedModelInfo = computed(() => MODELS.find(m => m.id === selectedModel.value) ?? MODELS[1]);

const estimatedCostLow = computed(() => {
  const m = selectedModelInfo.value;
  return (totalInputTokens.value / 1_000_000) * m.inputPricePer1M +
    (estimatedOutputTokens.value / 1_000_000) * m.outputPricePer1M * 0.7;
});

const estimatedCostHigh = computed(() => {
  const m = selectedModelInfo.value;
  return (totalInputTokens.value / 1_000_000) * m.inputPricePer1M +
    (estimatedOutputTokens.value / 1_000_000) * m.outputPricePer1M * 1.3;
});

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return n.toString();
}

function formatCost(n: number): string {
  if (n < 0.001) return '<$0.001';
  return '$' + n.toFixed(4);
}

function contextFillPct(model: ModelInfo): number {
  return Math.min((totalInputTokens.value / model.contextWindow) * 100, 100);
}

function speedColor(speed: string): string {
  const map: Record<string, string> = { fast: '#34d399', medium: '#f59e0b', slow: '#ef4444' };
  return map[speed] ?? '#6b7280';
}
</script>

<template>
  <div class="cost-estimator">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Cost Estimator' },
    ]" />

    <PageHeader
      title="Execution Cost Estimator"
      subtitle="Estimate token usage and dollar cost before running your bot."
    />

    <div class="estimator-layout">
      <div class="card input-section">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <line x1="12" y1="1" x2="12" y2="23"/>
              <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
            </svg>
            Estimate Parameters
          </h3>
        </div>
        <div class="input-body">
          <div class="field-group">
            <label class="field-label">Prompt Template</label>
            <textarea
              v-model="promptText"
              class="text-area"
              rows="6"
              placeholder="Paste your prompt template here..."
            />
            <div class="field-hint">{{ formatTokens(promptTokens) }} tokens estimated</div>
          </div>

          <div class="field-group">
            <label class="field-label">Typical Codebase Size</label>
            <div class="size-pills">
              <button
                v-for="(label, key) in CODEBASE_LABELS"
                :key="key"
                class="size-pill"
                :class="{ active: codebaseSize === key }"
                @click="codebaseSize = key as typeof codebaseSize"
              >
                {{ label }}
              </button>
            </div>
          </div>

          <div class="field-group">
            <label class="field-label">Model</label>
            <select v-model="selectedModel" class="select-input">
              <option v-for="m in MODELS" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </div>
        </div>
      </div>

      <div class="card estimate-section">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            Cost Estimate
          </h3>
        </div>
        <div class="estimate-body">
          <div class="big-estimate">
            <div class="estimate-range">
              <span class="range-low">{{ formatCost(estimatedCostLow) }}</span>
              <span class="range-sep">–</span>
              <span class="range-high">{{ formatCost(estimatedCostHigh) }}</span>
            </div>
            <div class="estimate-label">estimated per execution</div>
          </div>

          <div class="token-breakdown">
            <div class="token-row">
              <span class="token-label">Prompt tokens</span>
              <span class="token-val">{{ formatTokens(promptTokens) }}</span>
            </div>
            <div class="token-row">
              <span class="token-label">Context (codebase)</span>
              <span class="token-val">{{ formatTokens(contextTokens) }}</span>
            </div>
            <div class="token-row token-total">
              <span class="token-label">Total input</span>
              <span class="token-val">{{ formatTokens(totalInputTokens) }}</span>
            </div>
            <div class="token-row">
              <span class="token-label">Est. output</span>
              <span class="token-val">{{ formatTokens(estimatedOutputTokens) }}</span>
            </div>
          </div>

          <div class="context-bar-wrap">
            <div class="context-bar-label">
              <span>Context window usage</span>
              <span>{{ contextFillPct(selectedModelInfo).toFixed(1) }}%</span>
            </div>
            <div class="context-bar">
              <div
                class="context-fill"
                :style="{
                  width: contextFillPct(selectedModelInfo) + '%',
                  background: contextFillPct(selectedModelInfo) > 80 ? '#ef4444' : contextFillPct(selectedModelInfo) > 50 ? '#f59e0b' : 'var(--accent-cyan)'
                }"
              />
            </div>
            <div v-if="contextFillPct(selectedModelInfo) > 80" class="bar-warning">
              Warning: High context usage risks truncation
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Model comparison table -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <line x1="3" y1="9" x2="21" y2="9"/>
            <line x1="3" y1="15" x2="21" y2="15"/>
            <line x1="9" y1="3" x2="9" y2="21"/>
            <line x1="15" y1="3" x2="15" y2="21"/>
          </svg>
          Model Comparison
        </h3>
      </div>
      <div class="table-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Input / 1M tokens</th>
              <th>Output / 1M tokens</th>
              <th>Est. cost (this request)</th>
              <th>Context window</th>
              <th>Speed</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in MODELS"
              :key="m.id"
              :class="{ 'row-selected': m.id === selectedModel }"
              @click="selectedModel = m.id"
            >
              <td>
                <span class="model-name">{{ m.name }}</span>
              </td>
              <td class="mono">${{ m.inputPricePer1M.toFixed(2) }}</td>
              <td class="mono">${{ m.outputPricePer1M.toFixed(2) }}</td>
              <td class="mono cost-cell">
                {{ formatCost((totalInputTokens / 1_000_000) * m.inputPricePer1M + (estimatedOutputTokens / 1_000_000) * m.outputPricePer1M) }}
              </td>
              <td class="mono">{{ (m.contextWindow / 1000).toFixed(0) }}k</td>
              <td>
                <span class="speed-badge" :style="{ color: speedColor(m.speed), background: speedColor(m.speed) + '20' }">
                  {{ m.speed }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cost-estimator {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.estimator-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
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

.input-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.field-hint {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.text-area {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  line-height: 1.6;
  resize: vertical;
  font-family: 'Geist Mono', monospace;
  box-sizing: border-box;
}

.text-area:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.size-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.size-pill {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.size-pill.active {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
}

.size-pill:hover:not(.active) {
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.estimate-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.big-estimate {
  text-align: center;
  padding: 24px 0;
}

.estimate-range {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: center;
}

.range-low, .range-high {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.range-sep {
  font-size: 1.5rem;
  color: var(--text-tertiary);
}

.estimate-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.token-breakdown {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.token-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
}

.token-label { color: var(--text-secondary); }
.token-val { color: var(--text-primary); font-variant-numeric: tabular-nums; font-family: monospace; }

.token-total {
  border-top: 1px solid var(--border-default);
  padding-top: 8px;
  margin-top: 4px;
}

.token-total .token-label,
.token-total .token-val {
  font-weight: 600;
  color: var(--text-primary);
}

.context-bar-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.context-bar-label {
  display: flex;
  justify-content: space-between;
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.context-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.context-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.bar-warning {
  font-size: 0.75rem;
  color: #ef4444;
}

.table-wrap {
  overflow-x: auto;
}

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.compare-table thead {
  background: var(--bg-tertiary);
}

.compare-table th {
  padding: 12px 20px;
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-default);
}

.compare-table td {
  padding: 12px 20px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.compare-table tr:last-child td { border-bottom: none; }

.compare-table tr { cursor: pointer; transition: background 0.1s; }
.compare-table tr:hover { background: var(--bg-tertiary); }
.compare-table tr.row-selected { background: rgba(6, 182, 212, 0.06); }
.compare-table tr.row-selected td { color: var(--text-primary); }

.model-name { font-weight: 500; color: var(--text-primary); }
.mono { font-family: monospace; }
.cost-cell { color: var(--accent-cyan) !important; font-weight: 600; }

.speed-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
}

@media (max-width: 900px) {
  .estimator-layout { grid-template-columns: 1fr; }
}
</style>
