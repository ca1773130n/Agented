<script setup lang="ts">
import { ref, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { onboardingApi } from '../services/api/onboarding';
import type { OnboardingStep, OnboardingRun } from '../services/api/onboarding';

const showToast = useToast();

const ONBOARDING_TRIGGER_ID = 'bot-onboarding';

const triggerEnabled = ref(true);
const triggerEvent = ref('github.member.added');
const loading = ref(false);
const saving = ref(false);

const steps = ref<OnboardingStep[]>([]);
const recentRuns = ref<OnboardingRun[]>([]);

onMounted(async () => {
  loading.value = true;
  try {
    const [config, runs] = await Promise.all([
      onboardingApi.getConfig(ONBOARDING_TRIGGER_ID),
      onboardingApi.getRuns(ONBOARDING_TRIGGER_ID),
    ]);
    if (config.trigger) {
      triggerEnabled.value = Boolean(config.trigger.enabled);
      triggerEvent.value = config.trigger.trigger_source || 'github.member.added';
    }
    steps.value = config.steps;
    recentRuns.value = runs.runs;
  } catch {
    // Trigger may not exist yet — leave defaults
  } finally {
    loading.value = false;
  }
});

function toggleStep(id: string) {
  const step = steps.value.find((s) => s.id === id);
  if (step) step.enabled = !step.enabled;
}

async function saveConfig() {
  saving.value = true;
  try {
    await onboardingApi.saveConfig({
      trigger_id: ONBOARDING_TRIGGER_ID,
      trigger_event: triggerEvent.value,
      enabled: triggerEnabled.value,
      steps: steps.value.map((s, idx) => ({
        id: s.id,
        step_order: s.step_order ?? idx + 1,
        name: s.name,
        description: s.description,
        type: s.type,
        enabled: s.enabled,
        delay_minutes: s.delay_minutes,
      })),
    });
    showToast('Onboarding automation saved', 'success');
  } catch {
    showToast('Failed to save onboarding config', 'error');
  } finally {
    saving.value = false;
  }
}

function typeIcon(type: string) {
  const icons: Record<string, string> = {
    github: '⬡',
    slack: '#',
    jira: '⊟',
    email: '✉',
    custom: '⚙',
  };
  return icons[type] ?? '⚙';
}

function typeColor(type: string) {
  const colors: Record<string, string> = {
    github: '#e2e8f0',
    slack: '#4ade80',
    jira: '#60a5fa',
    email: '#f0a500',
    custom: '#a78bfa',
  };
  return colors[type] ?? '#94a3b8';
}

function statusColor(status: string) {
  if (status === 'completed') return 'var(--color-success)';
  if (status === 'running') return 'var(--color-warning)';
  return 'var(--color-error)';
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
</script>

<template>
  <div class="onboarding-page">
    <PageHeader
      title="New Engineer Onboarding Automation"
      subtitle="Automatically run onboarding tasks when a new GitHub org member is added"
    />

    <div class="page-content">
      <section class="section trigger-config">
        <h2 class="section-title">Trigger Configuration</h2>
        <div class="config-row">
          <label class="config-label">
            Trigger event
            <select v-model="triggerEvent" class="select">
              <option value="github.member.added">GitHub — org member added</option>
              <option value="github.team.member.added">GitHub — team member added</option>
              <option value="manual">Manual only</option>
            </select>
          </label>
          <label class="toggle-label">
            Enabled
            <button
              class="toggle-btn"
              :class="{ active: triggerEnabled }"
              @click="triggerEnabled = !triggerEnabled"
            >
              {{ triggerEnabled ? 'ON' : 'OFF' }}
            </button>
          </label>
          <button class="btn-primary" @click="saveConfig">Save</button>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">Onboarding Steps</h2>
        <p class="section-hint">Steps execute in order. Disabled steps are skipped.</p>
        <div class="steps-list">
          <div v-for="step in steps" :key="step.id" class="step-card" :class="{ disabled: !step.enabled }">
            <div class="step-order">{{ step.step_order }}</div>
            <div class="step-icon" :style="{ color: typeColor(step.type) }">
              {{ typeIcon(step.type) }}
            </div>
            <div class="step-body">
              <div class="step-name">{{ step.name }}</div>
              <div class="step-desc">{{ step.description }}</div>
              <div class="step-meta">
                <span class="type-badge">{{ step.type }}</span>
                <span class="delay">+{{ step.delay_minutes }}m delay</span>
              </div>
            </div>
            <button
              class="step-toggle"
              :class="{ active: step.enabled }"
              @click="toggleStep(step.id)"
            >
              {{ step.enabled ? 'Enabled' : 'Disabled' }}
            </button>
          </div>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">Recent Onboarding Runs</h2>
        <div v-if="recentRuns.length === 0" class="empty-runs">No runs yet.</div>
        <div v-else class="runs-list">
          <div v-for="run in recentRuns" :key="run.execution_id" class="run-card">
            <div class="run-info">
              <code class="handle">{{ run.execution_id }}</code>
              <span class="run-date">{{ formatTime(run.started_at) }}</span>
            </div>
            <span class="run-status" :style="{ color: statusColor(run.status) }">
              {{ run.status }}
            </span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.onboarding-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 0 1.5rem 3rem;
}

.page-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.section {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1.25rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
}

.section-hint {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0 0 1rem;
}

.config-row {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.config-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.select {
  padding: 0.4rem 0.6rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font-size: 0.875rem;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.toggle-btn {
  padding: 0.3rem 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 600;
}

.toggle-btn.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
}

.btn-primary:hover { opacity: 0.9; }

.steps-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.step-card {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.875rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  transition: opacity 0.2s;
}

.step-card.disabled {
  opacity: 0.5;
}

.step-order {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--color-border);
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
}

.step-icon {
  font-size: 1rem;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

.step-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.step-name {
  font-size: 0.875rem;
  font-weight: 500;
}

.step-desc {
  font-size: 0.78rem;
  color: var(--color-text-muted);
}

.step-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.type-badge {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  background: var(--color-border);
  color: var(--color-text-muted);
  text-transform: uppercase;
}

.delay {
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.step-toggle {
  padding: 0.25rem 0.65rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 0.75rem;
  flex-shrink: 0;
}

.step-toggle.active {
  background: color-mix(in srgb, var(--color-success) 15%, transparent);
  color: var(--color-success);
  border-color: var(--color-success);
}

.runs-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.run-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  flex-wrap: wrap;
}

.run-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 200px;
}

.member-name {
  font-weight: 500;
  font-size: 0.875rem;
}

.handle {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-family: monospace;
}

.run-date {
  font-size: 0.78rem;
  color: var(--color-text-muted);
  margin-left: auto;
}

.run-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 160px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--color-border);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.progress-label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.run-status {
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: capitalize;
}

.trigger-config .config-row {
  margin-top: 0.75rem;
}
</style>
