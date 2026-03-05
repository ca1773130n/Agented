<script setup lang="ts">
import { ref } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

interface OnboardingStep {
  id: string;
  order: number;
  name: string;
  description: string;
  type: 'github' | 'slack' | 'jira' | 'email' | 'custom';
  enabled: boolean;
  delayMinutes: number;
}

interface OnboardingRun {
  id: string;
  member: string;
  githubHandle: string;
  startedAt: string;
  completedSteps: number;
  totalSteps: number;
  status: 'running' | 'completed' | 'failed';
}

const triggerEnabled = ref(true);
const triggerEvent = ref('github.member.added');

const steps = ref<OnboardingStep[]>([
  {
    id: 'step-1',
    order: 1,
    name: 'Create Jira account',
    description: 'Provision a new Jira user account with default project access',
    type: 'jira',
    enabled: true,
    delayMinutes: 0,
  },
  {
    id: 'step-2',
    order: 2,
    name: 'Add to Slack channels',
    description: 'Invite new member to #general, #engineering, and team-specific channels',
    type: 'slack',
    enabled: true,
    delayMinutes: 2,
  },
  {
    id: 'step-3',
    order: 3,
    name: 'Assign starter issue',
    description: 'Find and assign a "good first issue" labeled GitHub issue',
    type: 'github',
    enabled: true,
    delayMinutes: 5,
  },
  {
    id: 'step-4',
    order: 4,
    name: 'Send welcome email',
    description: 'Send personalized AI-generated welcome message with team context',
    type: 'email',
    enabled: true,
    delayMinutes: 10,
  },
  {
    id: 'step-5',
    order: 5,
    name: 'Post Slack introduction',
    description: 'Post a welcome message in #introductions with generated bio',
    type: 'slack',
    enabled: false,
    delayMinutes: 15,
  },
]);

const recentRuns = ref<OnboardingRun[]>([
  {
    id: 'run-1',
    member: 'Henry Park',
    githubHandle: 'hpark-dev',
    startedAt: '2026-03-06T09:00:00Z',
    completedSteps: 4,
    totalSteps: 4,
    status: 'completed',
  },
  {
    id: 'run-2',
    member: 'Ines Rodrigues',
    githubHandle: 'ines-r',
    startedAt: '2026-02-28T14:30:00Z',
    completedSteps: 4,
    totalSteps: 4,
    status: 'completed',
  },
  {
    id: 'run-3',
    member: 'James Okafor',
    githubHandle: 'jokafor',
    startedAt: '2026-03-05T11:15:00Z',
    completedSteps: 2,
    totalSteps: 4,
    status: 'failed',
  },
]);

function toggleStep(id: string) {
  const step = steps.value.find((s) => s.id === id);
  if (step) step.enabled = !step.enabled;
}

function saveConfig() {
  showToast('Onboarding automation saved', 'success');
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
    <AppBreadcrumb :items="[{ label: 'Bots' }, { label: 'Onboarding Automation' }]" />
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
            <div class="step-order">{{ step.order }}</div>
            <div class="step-icon" :style="{ color: typeColor(step.type) }">
              {{ typeIcon(step.type) }}
            </div>
            <div class="step-body">
              <div class="step-name">{{ step.name }}</div>
              <div class="step-desc">{{ step.description }}</div>
              <div class="step-meta">
                <span class="type-badge">{{ step.type }}</span>
                <span class="delay">+{{ step.delayMinutes }}m delay</span>
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
        <div class="runs-list">
          <div v-for="run in recentRuns" :key="run.id" class="run-card">
            <div class="run-info">
              <span class="member-name">{{ run.member }}</span>
              <code class="handle">@{{ run.githubHandle }}</code>
              <span class="run-date">{{ formatTime(run.startedAt) }}</span>
            </div>
            <div class="run-progress">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{
                    width: `${(run.completedSteps / run.totalSteps) * 100}%`,
                    background: statusColor(run.status),
                  }"
                />
              </div>
              <span class="progress-label">{{ run.completedSteps }}/{{ run.totalSteps }} steps</span>
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
