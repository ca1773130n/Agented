<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger, DryRunResponse } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const payloadJson = ref(JSON.stringify({
  action: 'opened',
  pull_request: { number: 42, title: 'Add new feature', head: { sha: 'abc123' } },
  repository: { full_name: 'org/repo' },
}, null, 2));
const isRunning = ref(false);
const dryRunResult = ref<DryRunResponse | null>(null);
const payloadError = ref('');

interface DryRunDisplay {
  steps: string[];
  output: string;
  warnings: string[];
}

const displayResult = ref<DryRunDisplay | null>(null);

async function loadTriggers() {
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers ?? [];
    if (triggers.value.length > 0) {
      selectedTriggerId.value = triggers.value[0].id;
    }
  } catch {
    // Non-critical
  }
}

function validateJson(): boolean {
  try {
    JSON.parse(payloadJson.value);
    payloadError.value = '';
    return true;
  } catch (e: unknown) {
    payloadError.value = e instanceof Error ? e.message : 'Invalid JSON';
    return false;
  }
}

async function handleDryRun() {
  if (!validateJson()) return;
  if (!selectedTriggerId.value) {
    showToast('Select a trigger to dry-run', 'info');
    return;
  }

  isRunning.value = true;
  dryRunResult.value = null;
  displayResult.value = null;

  try {
    const payload = JSON.parse(payloadJson.value);
    const result = await triggerApi.dryRun(selectedTriggerId.value, payload);
    dryRunResult.value = result;

    // Build display from real response
    const trigger = triggers.value.find(t => t.id === selectedTriggerId.value);
    const steps: string[] = [
      'Payload received and validated',
      `Matched trigger: ${result.trigger_name}`,
      `Prompt template rendered (backend: ${result.backend_type})`,
      `CLI command built: ${result.cli_command.substring(0, 80)}${result.cli_command.length > 80 ? '...' : ''}`,
      `Cost estimated (model: ${result.model})`,
      'DRY RUN complete -- no subprocess spawned',
    ];

    const est = result.estimated_tokens;
    const output = [
      `[DRY RUN] Trigger "${result.trigger_name}" (${result.trigger_id})`,
      '',
      `Backend: ${result.backend_type}`,
      `Model: ${result.model}`,
      '',
      `--- CLI Command ---`,
      result.cli_command,
      '',
      `--- Token Estimate (confidence: ${est.confidence}) ---`,
      `Input tokens:  ~${est.estimated_input_tokens.toLocaleString()}`,
      `Output tokens: ~${est.estimated_output_tokens.toLocaleString()}`,
      `Estimated cost: $${est.estimated_cost_usd.toFixed(4)}`,
      '',
      `--- Rendered Prompt (${result.rendered_prompt.length} chars) ---`,
      result.rendered_prompt.substring(0, 500) + (result.rendered_prompt.length > 500 ? '\n...(truncated)' : ''),
      '',
      'No actual execution occurred. No side effects.',
    ].join('\n');

    const warnings: string[] = [];
    if (trigger?.trigger_source === 'github') {
      warnings.push('GitHub webhook would be processed (suppressed in dry run)');
    }
    if (trigger?.auto_resolve) {
      warnings.push('Auto-resolve would run after execution (suppressed in dry run)');
    }

    displayResult.value = { steps, output, warnings };
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Dry run failed';
    showToast(message, 'error');
  } finally {
    isRunning.value = false;
  }
}

onMounted(loadTriggers);
</script>

<template>
  <div class="bot-dry-run">

    <PageHeader
      title="Bot Dry Run"
      subtitle="Test your bot against a payload without any real side effects."
    />

    <div class="dry-run-layout">
      <div class="card input-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            Dry Run Configuration
          </h3>
          <div class="no-effects-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            No side effects
          </div>
        </div>
        <div class="input-body">
          <div class="field-group">
            <label class="field-label">Select Trigger / Bot</label>
            <select v-model="selectedTriggerId" class="select-input">
              <option value="">-- Select trigger --</option>
              <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </div>

          <div class="field-group">
            <label class="field-label">Payload JSON</label>
            <textarea
              v-model="payloadJson"
              class="text-area code-area"
              rows="14"
              spellcheck="false"
              @input="validateJson"
            />
            <div v-if="payloadError" class="error-hint">{{ payloadError }}</div>
          </div>

          <div class="actions">
            <button
              class="btn btn-primary"
              :disabled="isRunning || !!payloadError"
              @click="handleDryRun"
            >
              <svg v-if="isRunning" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              {{ isRunning ? 'Running dry run...' : 'Run Dry Run' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="displayResult" class="card output-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="9" x2="15" y2="9"/>
              <line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
            Dry Run Output
          </h3>
          <div class="no-effects-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Safe -- no side effects
          </div>
        </div>
        <div class="output-body">
          <div class="steps-section">
            <div class="steps-label">Execution Steps</div>
            <div class="steps-list">
              <div v-for="(step, i) in displayResult.steps" :key="i" class="step-row">
                <span class="step-num">{{ i + 1 }}</span>
                <span class="step-text">{{ step }}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="color: #34d399; flex-shrink: 0">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
            </div>
          </div>

          <div class="output-section">
            <div class="steps-label">Dry Run Output</div>
            <pre class="output-pre">{{ displayResult.output }}</pre>
          </div>

          <div v-if="displayResult.warnings.length > 0" class="would-send-section">
            <div class="steps-label">Would Have Triggered (suppressed)</div>
            <div v-for="s in displayResult.warnings" :key="s" class="would-row">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="color: #f59e0b">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <span>{{ s }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-dry-run {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.dry-run-layout {
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

.no-effects-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 4px 10px;
  background: rgba(52, 211, 153, 0.1);
  color: #34d399;
  border-radius: 4px;
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.input-body, .output-body {
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
  font-family: inherit;
  box-sizing: border-box;
}

.text-area:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.code-area {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
}

.error-hint {
  font-size: 0.78rem;
  color: #ef4444;
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.steps-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 10px;
}

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.step-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.step-num {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.step-text { flex: 1; }

.output-pre {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  line-height: 1.6;
  margin: 0;
}

.would-send-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.would-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-tertiary);
  padding: 8px 12px;
  background: rgba(245, 158, 11, 0.06);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 6px;
}

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .dry-run-layout { grid-template-columns: 1fr; }
}
</style>
