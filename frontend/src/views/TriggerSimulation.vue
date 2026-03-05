<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

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
  botName: string;
  triggerId: string;
  reason: string;
  promptPreview: string;
}

const results = ref<SimulationResult[] | null>(null);

const eventTemplates: Record<EventType, object> = {
  pull_request: { action: 'opened', pull_request: { number: 42, title: 'Add feature', head: { sha: 'abc123' }, changed_files: 3, additions: 50, deletions: 10 }, repository: { full_name: 'org/repo' } },
  push: { ref: 'refs/heads/main', commits: [{ id: 'def456', message: 'Fix auth bug', author: { name: 'Dev' } }], repository: { full_name: 'org/repo' } },
  issue: { action: 'opened', issue: { number: 15, title: 'Bug report: login fails', labels: [{ name: 'bug' }] }, repository: { full_name: 'org/repo' } },
  schedule: { trigger: 'schedule', cron: '0 9 * * 1', timestamp: new Date().toISOString() },
  webhook: { event: 'deployment_complete', environment: 'staging', version: '2.5.0', status: 'success' },
};

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
  isSimulating.value = true;
  results.value = null;
  try {
    await new Promise(r => setTimeout(r, 1200));
    const payload = JSON.parse(customPayload.value);
    const matched: SimulationResult[] = [];
    if (eventType.value === 'pull_request' && payload.action === 'opened') {
      matched.push({
        matched: true,
        botName: 'bot-pr-review',
        triggerId: 'trig-github-pr',
        reason: 'Event type "pull_request" with action "opened" matches trigger condition',
        promptPreview: `Review PR #${payload.pull_request?.number} "${payload.pull_request?.title}" in ${payload.repository?.full_name}...`,
      });
    }
    if (eventType.value === 'schedule') {
      matched.push({
        matched: true,
        botName: 'bot-security',
        triggerId: 'trig-weekly',
        reason: 'Schedule trigger matches weekly cron 0 9 * * 1',
        promptPreview: 'Run weekly security audit on all monitored repositories...',
      });
    }
    if (matched.length === 0) {
      matched.push({ matched: false, botName: '—', triggerId: '—', reason: 'No triggers matched this event', promptPreview: '' });
    }
    results.value = matched;
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
      subtitle="Send mock events from the UI to test trigger matching and bot behavior — no real events required."
    />

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
          <button class="btn btn-primary" :disabled="isSimulating || !!payloadError" @click="simulate">
            {{ isSimulating ? 'Simulating...' : '▶ Simulate Event' }}
          </button>
        </div>
      </div>

      <!-- Results panel -->
      <div class="results-panel">
        <div v-if="!results" class="card results-empty">
          <div class="empty-inner">
            <p>Run a simulation to see which triggers match and what prompt would be generated.</p>
          </div>
        </div>

        <div v-else>
          <div v-for="(res, i) in results" :key="i" class="card result-card" :class="{ 'result-match': res.matched, 'result-nomatch': !res.matched }">
            <div class="result-header">
              <span :class="['match-badge', { 'badge-match': res.matched, 'badge-nomatch': !res.matched }]">
                {{ res.matched ? '✓ MATCHED' : '✗ NO MATCH' }}
              </span>
              <span class="result-bot">{{ res.botName }}</span>
            </div>
            <div class="result-body">
              <div class="result-row">
                <span class="result-label">Trigger</span>
                <span class="result-val">{{ res.triggerId }}</span>
              </div>
              <div class="result-row">
                <span class="result-label">Reason</span>
                <span class="result-val">{{ res.reason }}</span>
              </div>
              <div v-if="res.matched && res.promptPreview" class="result-prompt">
                <div class="prompt-preview-label">Prompt Preview</div>
                <div class="prompt-preview-text">{{ res.promptPreview }}</div>
              </div>
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

.result-prompt { border-top: 1px solid var(--border-subtle); padding-top: 10px; }
.prompt-preview-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 6px; }
.prompt-preview-text { font-size: 0.78rem; color: var(--text-secondary); font-style: italic; line-height: 1.4; }

.btn { display: flex; align-items: center; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-sm { padding: 5px 10px; font-size: 0.75rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
