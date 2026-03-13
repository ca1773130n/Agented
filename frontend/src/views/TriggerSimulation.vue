<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger, DryRunResponse } from '../services/api';

const router = useRouter();
const showToast = useToast();

// Trigger selection
const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const isLoadingTriggers = ref(false);
const triggerLoadError = ref('');

type EventType = 'pull_request' | 'push' | 'issue' | 'schedule' | 'webhook';

const eventType = ref<EventType>('pull_request');
const customPayload = ref(JSON.stringify({
  action: 'opened',
  pull_request: {
    number: 42,
    title: 'Add OAuth2 support',
    head: { sha: 'abc1234', ref: 'feature/oauth' },
    base: { ref: 'main' },
    user: { login: 'developer' },
    changed_files: 8,
    additions: 214,
    deletions: 12,
  },
  repository: { full_name: 'org/api' },
}, null, 2));

const payloadError = ref('');
const isSimulating = ref(false);

interface SimulationResult {
  matched: boolean;
  triggerName: string;
  triggerId: string;
  renderedPrompt: string;
  cliCommand: string;
  backendType: string;
  model: string;
  estimatedTokens?: {
    estimated_input_tokens: number;
    estimated_output_tokens: number;
    estimated_cost_usd: number;
    model: string;
    confidence: string;
  };
  error?: string;
}

const results = ref<SimulationResult[] | null>(null);

const eventTemplates: Record<EventType, object> = {
  pull_request: { action: 'opened', pull_request: { number: 42, title: 'Add feature', head: { sha: 'abc123' }, changed_files: 3, additions: 50, deletions: 10 }, repository: { full_name: 'org/repo' } },
  push: { ref: 'refs/heads/main', commits: [{ id: 'def456', message: 'Fix auth bug', author: { name: 'Dev' } }], repository: { full_name: 'org/repo' } },
  issue: { action: 'opened', issue: { number: 15, title: 'Bug report: login fails', labels: [{ name: 'bug' }] }, repository: { full_name: 'org/repo' } },
  schedule: { trigger: 'schedule', cron: '0 9 * * 1', timestamp: new Date().toISOString() },
  webhook: { event: 'deployment_complete', environment: 'staging', version: '2.5.0', status: 'success' },
};

onMounted(async () => {
  await loadTriggers();
});

async function loadTriggers() {
  isLoadingTriggers.value = true;
  triggerLoadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
    if (triggers.value.length > 0) {
      selectedTriggerId.value = triggers.value[0].id;
    }
  } catch (e) {
    triggerLoadError.value = e instanceof ApiError ? e.message : 'Failed to load triggers';
  } finally {
    isLoadingTriggers.value = false;
  }
}

function loadTemplate() {
  customPayload.value = JSON.stringify(eventTemplates[eventType.value], null, 2);
  payloadError.value = '';
}

function validatePayload() {
  try {
    JSON.parse(customPayload.value);
    payloadError.value = '';
    return true;
  } catch (e: unknown) {
    payloadError.value = e instanceof Error ? e.message : 'Invalid JSON';
    return false;
  }
}

async function simulate() {
  if (!validatePayload()) return;
  if (!selectedTriggerId.value) {
    showToast('Select a trigger first', 'info');
    return;
  }

  isSimulating.value = true;
  results.value = null;
  try {
    const payload = JSON.parse(customPayload.value);
    const dryRunResult: DryRunResponse = await triggerApi.dryRun(selectedTriggerId.value, payload);

    const result: SimulationResult = {
      matched: true,
      triggerName: dryRunResult.trigger_name,
      triggerId: dryRunResult.trigger_id,
      renderedPrompt: dryRunResult.rendered_prompt,
      cliCommand: dryRunResult.cli_command,
      backendType: dryRunResult.backend_type,
      model: dryRunResult.model,
      estimatedTokens: dryRunResult.estimated_tokens,
    };

    results.value = [result];
    showToast('Dry run complete', 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      results.value = [{
        matched: false,
        triggerName: triggers.value.find(t => t.id === selectedTriggerId.value)?.name || selectedTriggerId.value,
        triggerId: selectedTriggerId.value,
        renderedPrompt: '',
        cliCommand: '',
        backendType: '',
        model: '',
        error: e.message,
      }];
    } else {
      showToast('Simulation failed', 'error');
    }
  } finally {
    isSimulating.value = false;
  }
}
</script>

<template>
  <div class="trigger-sim">
    <AppBreadcrumb :items="[
      { label: 'Triggers', action: () => router.push({ name: 'triggers' }) },
      { label: 'Simulation & Test Harness' },
    ]" />

    <PageHeader
      title="Trigger Simulation & Test Harness"
      subtitle="Send mock events to test trigger matching and bot behavior via dry run — no real execution required."
    />

    <!-- Trigger selector -->
    <div v-if="isLoadingTriggers" class="loading-msg">Loading triggers...</div>
    <div v-else-if="triggerLoadError" class="error-msg">{{ triggerLoadError }}</div>
    <div v-else class="trigger-selector">
      <label class="selector-label">Trigger:</label>
      <select v-model="selectedTriggerId" class="trigger-select">
        <option value="">Select a trigger...</option>
        <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }} ({{ t.id }})</option>
      </select>
    </div>

    <div class="layout">
      <div class="input-panel">
        <!-- Event type selector -->
        <div class="card event-type-card">
          <div class="card-header">Event Type</div>
          <div class="event-types">
            <button
              v-for="et in (['pull_request', 'push', 'issue', 'schedule', 'webhook'] as EventType[])"
              :key="et"
              :class="['event-type-btn', { active: eventType === et }]"
              @click="eventType = et; loadTemplate()"
            >{{ et.replace('_', ' ') }}</button>
          </div>
        </div>

        <!-- Payload editor -->
        <div class="card payload-card">
          <div class="payload-header">
            <span>Event Payload</span>
            <div class="payload-actions">
              <span v-if="payloadError" class="payload-error">{{ payloadError }}</span>
              <button class="btn btn-ghost btn-sm" @click="loadTemplate">Load Template</button>
            </div>
          </div>
          <textarea
            v-model="customPayload"
            class="payload-textarea"
            spellcheck="false"
            @input="validatePayload"
          ></textarea>
        </div>

        <div class="sim-actions">
          <button class="btn btn-primary" :disabled="isSimulating || !!payloadError || !selectedTriggerId" @click="simulate">
            {{ isSimulating ? 'Simulating...' : 'Simulate Dry Run' }}
          </button>
        </div>
      </div>

      <!-- Results panel -->
      <div class="results-panel">
        <div v-if="!results" class="card results-empty">
          <div class="empty-inner">
            <p>Select a trigger and run a dry-run simulation to see the rendered prompt, CLI command, and cost estimate.</p>
          </div>
        </div>

        <div v-else>
          <div v-for="(res, i) in results" :key="i" class="card result-card" :class="{ 'result-match': res.matched, 'result-nomatch': !res.matched }">
            <div class="result-header">
              <span :class="['match-badge', { 'badge-match': res.matched, 'badge-nomatch': !res.matched }]">
                {{ res.matched ? 'DRY RUN OK' : 'FAILED' }}
              </span>
              <span class="result-bot">{{ res.triggerName }}</span>
            </div>
            <div class="result-body">
              <div class="result-row">
                <span class="result-label">Trigger</span>
                <span class="result-val">{{ res.triggerId }}</span>
              </div>
              <div v-if="res.error" class="result-row">
                <span class="result-label">Error</span>
                <span class="result-val result-error">{{ res.error }}</span>
              </div>
              <template v-if="res.matched">
                <div class="result-row">
                  <span class="result-label">Backend</span>
                  <span class="result-val">{{ res.backendType }} ({{ res.model }})</span>
                </div>
                <div class="result-row">
                  <span class="result-label">CLI</span>
                  <span class="result-val mono">{{ res.cliCommand }}</span>
                </div>
                <div v-if="res.estimatedTokens" class="result-tokens">
                  <div class="tokens-header">Token Estimates</div>
                  <div class="tokens-grid">
                    <div class="token-item">
                      <span class="token-label">Input</span>
                      <span class="token-val">{{ res.estimatedTokens.estimated_input_tokens.toLocaleString() }}</span>
                    </div>
                    <div class="token-item">
                      <span class="token-label">Output</span>
                      <span class="token-val">{{ res.estimatedTokens.estimated_output_tokens.toLocaleString() }}</span>
                    </div>
                    <div class="token-item">
                      <span class="token-label">Est. Cost</span>
                      <span class="token-val">${{ res.estimatedTokens.estimated_cost_usd.toFixed(4) }}</span>
                    </div>
                    <div class="token-item">
                      <span class="token-label">Confidence</span>
                      <span class="token-val">{{ res.estimatedTokens.confidence }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="res.renderedPrompt" class="result-prompt">
                  <div class="prompt-preview-label">Rendered Prompt</div>
                  <div class="prompt-preview-text">{{ res.renderedPrompt }}</div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trigger-sim { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.loading-msg { font-size: 0.82rem; color: var(--text-tertiary); padding: 12px 0; }
.error-msg { font-size: 0.82rem; color: #ef4444; padding: 12px 0; }

.trigger-selector { display: flex; align-items: center; gap: 12px; }
.selector-label { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.trigger-select { flex: 1; max-width: 400px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }

.layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
.input-panel { display: flex; flex-direction: column; gap: 14px; }
.results-panel { display: flex; flex-direction: column; gap: 12px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.card-header { padding: 12px 18px; border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }

.event-types { display: flex; flex-wrap: wrap; gap: 8px; padding: 14px 18px; }
.event-type-btn { padding: 6px 14px; border-radius: 6px; font-size: 0.78rem; font-weight: 500; border: 1px solid var(--border-default); background: var(--bg-tertiary); color: var(--text-secondary); cursor: pointer; text-transform: capitalize; transition: all 0.15s; }
.event-type-btn.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.event-type-btn:hover:not(.active) { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.payload-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 18px; border-bottom: 1px solid var(--border-default); }
.payload-header > span { font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
.payload-actions { display: flex; align-items: center; gap: 10px; }
.payload-error { font-size: 0.7rem; color: #ef4444; }
.payload-textarea { display: block; width: 100%; height: 280px; padding: 14px; background: var(--bg-secondary); border: none; resize: vertical; color: var(--text-primary); font-family: monospace; font-size: 0.78rem; line-height: 1.5; outline: none; box-sizing: border-box; }

.sim-actions { display: flex; justify-content: flex-end; }

.results-empty { padding: 48px 24px; text-align: center; }
.empty-inner p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.result-card { margin-bottom: 0; }
.result-match { border-color: rgba(52,211,153,0.3); }
.result-nomatch { border-color: rgba(239,68,68,0.2); }

.result-header { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-bottom: 1px solid var(--border-subtle); }
.match-badge { font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.04em; }
.badge-match { background: rgba(52,211,153,0.15); color: #34d399; }
.badge-nomatch { background: rgba(239,68,68,0.15); color: #ef4444; }
.result-bot { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }

.result-body { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; }
.result-row { display: flex; gap: 12px; }
.result-label { font-size: 0.72rem; color: var(--text-tertiary); font-weight: 500; width: 60px; flex-shrink: 0; padding-top: 2px; }
.result-val { font-size: 0.8rem; color: var(--text-secondary); flex: 1; line-height: 1.4; }
.result-val.mono { font-family: monospace; font-size: 0.75rem; word-break: break-all; }
.result-error { color: #ef4444; }

.result-tokens { border-top: 1px solid var(--border-subtle); padding-top: 10px; }
.tokens-header { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 8px; }
.tokens-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.token-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: var(--bg-tertiary); border-radius: 6px; }
.token-label { font-size: 0.72rem; color: var(--text-tertiary); }
.token-val { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); font-family: monospace; }

.result-prompt { border-top: 1px solid var(--border-subtle); padding-top: 10px; }
.prompt-preview-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 6px; }
.prompt-preview-text { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; white-space: pre-wrap; max-height: 300px; overflow-y: auto; background: var(--bg-tertiary); padding: 10px; border-radius: 6px; }

.btn { display: flex; align-items: center; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-sm { padding: 5px 10px; font-size: 0.75rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
