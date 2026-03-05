<script setup lang="ts">
import { ref } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

interface OwnershipRule {
  id: string;
  pattern: string;
  team: string;
  reviewers: string[];
  priority: number;
}

interface AssignmentLog {
  id: string;
  prNumber: number;
  prTitle: string;
  assignedTo: string[];
  reason: string;
  confidence: number;
  timestamp: string;
}

const rules = ref<OwnershipRule[]>([
  { id: 'rule-1', pattern: 'backend/**', team: 'Platform', reviewers: ['alice', 'bob'], priority: 1 },
  { id: 'rule-2', pattern: 'frontend/src/**', team: 'Frontend', reviewers: ['carol', 'dave'], priority: 1 },
  { id: 'rule-3', pattern: '**/*.test.ts', team: 'QA', reviewers: ['eve'], priority: 2 },
  { id: 'rule-4', pattern: 'backend/app/db/**', team: 'Data', reviewers: ['frank', 'grace'], priority: 1 },
]);

const recentAssignments = ref<AssignmentLog[]>([
  {
    id: 'asgn-1',
    prNumber: 312,
    prTitle: 'feat: add execution queue with rate limiting',
    assignedTo: ['alice', 'bob'],
    reason: 'Changed files in backend/** match Platform team ownership',
    confidence: 94,
    timestamp: '2026-03-06T14:23:00Z',
  },
  {
    id: 'asgn-2',
    prNumber: 311,
    prTitle: 'fix: resolve SSE streaming memory leak',
    assignedTo: ['carol'],
    reason: 'Changed files in frontend/src/** match Frontend team ownership',
    confidence: 88,
    timestamp: '2026-03-06T11:05:00Z',
  },
  {
    id: 'asgn-3',
    prNumber: 310,
    prTitle: 'refactor: migrate token tracking to new schema',
    assignedTo: ['frank', 'alice'],
    reason: 'Mixed changes in backend/app/db/** and backend/**',
    confidence: 79,
    timestamp: '2026-03-06T09:47:00Z',
  },
]);

const minConfidence = ref(70);
const maxReviewers = ref(2);
const enabled = ref(true);
const newPattern = ref('');
const newTeam = ref('');
const newReviewers = ref('');

function saveSettings() {
  showToast('Settings saved', 'success');
}

function addRule() {
  if (!newPattern.value || !newTeam.value) return;
  rules.value.push({
    id: `rule-${Date.now()}`,
    pattern: newPattern.value,
    team: newTeam.value,
    reviewers: newReviewers.value.split(',').map((r) => r.trim()).filter(Boolean),
    priority: 1,
  });
  newPattern.value = '';
  newTeam.value = '';
  newReviewers.value = '';
  showToast('Ownership rule added', 'success');
}

function deleteRule(id: string) {
  rules.value = rules.value.filter((r) => r.id !== id);
  showToast('Rule removed', 'success');
}

function confidenceColor(score: number) {
  if (score >= 90) return 'var(--color-success)';
  if (score >= 70) return 'var(--color-warning)';
  return 'var(--color-error)';
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleString();
}
</script>

<template>
  <div class="pr-auto-assignment">
    <AppBreadcrumb :items="[{ label: 'Integrations' }, { label: 'PR Auto-Assignment' }]" />
    <PageHeader
      title="AI-Powered PR Auto-Assignment"
      subtitle="Automatically assign reviewers based on file ownership rules and contributor expertise"
    />

    <div class="page-content">
      <div class="top-bar">
        <label class="toggle-row">
          <span>Auto-assignment enabled</span>
          <button
            class="toggle-btn"
            :class="{ active: enabled }"
            @click="enabled = !enabled"
          >
            {{ enabled ? 'ON' : 'OFF' }}
          </button>
        </label>
        <div class="config-row">
          <label>
            Min confidence
            <input v-model.number="minConfidence" type="number" min="0" max="100" class="num-input" />%
          </label>
          <label>
            Max reviewers
            <input v-model.number="maxReviewers" type="number" min="1" max="10" class="num-input" />
          </label>
          <button class="btn-primary" @click="saveSettings">Save Settings</button>
        </div>
      </div>

      <section class="section">
        <h2 class="section-title">Ownership Rules</h2>
        <div class="add-rule-form">
          <input v-model="newPattern" placeholder="File pattern (e.g. backend/**)" class="input" />
          <input v-model="newTeam" placeholder="Team name" class="input" />
          <input v-model="newReviewers" placeholder="Reviewers (comma-separated)" class="input" />
          <button class="btn-primary" @click="addRule">Add Rule</button>
        </div>
        <table class="rules-table">
          <thead>
            <tr>
              <th>Pattern</th>
              <th>Team</th>
              <th>Reviewers</th>
              <th>Priority</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="rule.id">
              <td><code class="pattern">{{ rule.pattern }}</code></td>
              <td>{{ rule.team }}</td>
              <td>
                <span v-for="r in rule.reviewers" :key="r" class="reviewer-tag">@{{ r }}</span>
              </td>
              <td>{{ rule.priority }}</td>
              <td>
                <button class="btn-danger-sm" @click="deleteRule(rule.id)">Remove</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="section">
        <h2 class="section-title">Recent Assignments</h2>
        <div class="assignment-list">
          <div v-for="a in recentAssignments" :key="a.id" class="assignment-card">
            <div class="assignment-header">
              <span class="pr-number">#{{ a.prNumber }}</span>
              <span class="pr-title">{{ a.prTitle }}</span>
              <span
                class="confidence-badge"
                :style="{ color: confidenceColor(a.confidence) }"
              >{{ a.confidence }}% confidence</span>
            </div>
            <div class="assignment-body">
              <div class="assigned-to">
                <span class="label">Assigned to:</span>
                <span v-for="r in a.assignedTo" :key="r" class="reviewer-tag">@{{ r }}</span>
              </div>
              <p class="reason">{{ a.reason }}</p>
              <span class="timestamp">{{ formatTime(a.timestamp) }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.pr-auto-assignment {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1.5rem 3rem;
}

.page-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.top-bar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 0.95rem;
  font-weight: 500;
}

.toggle-btn {
  padding: 0.3rem 0.8rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
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

.config-row {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.config-row label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.num-input {
  width: 60px;
  padding: 0.3rem 0.5rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  font-size: 0.875rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 1rem;
  color: var(--color-text);
}

.add-rule-form {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.input {
  flex: 1;
  min-width: 160px;
  padding: 0.5rem 0.75rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  font-size: 0.875rem;
}

.rules-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.rules-table th,
.rules-table td {
  padding: 0.6rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.rules-table th {
  color: var(--color-text-muted);
  font-weight: 500;
}

.pattern {
  background: var(--color-bg);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8rem;
}

.reviewer-tag {
  display: inline-block;
  background: color-mix(in srgb, var(--color-primary) 15%, transparent);
  color: var(--color-primary);
  padding: 0.15rem 0.5rem;
  border-radius: 12px;
  font-size: 0.75rem;
  margin-right: 0.25rem;
}

.btn-danger-sm {
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  border: 1px solid var(--color-error);
  background: transparent;
  color: var(--color-error);
  cursor: pointer;
  font-size: 0.75rem;
}

.assignment-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.assignment-card {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
}

.assignment-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}

.pr-number {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.pr-title {
  font-weight: 500;
  flex: 1;
}

.confidence-badge {
  font-size: 0.8rem;
  font-weight: 600;
}

.assignment-body {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.assigned-to {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.label {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.reason {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  margin: 0;
}

.timestamp {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  white-space: nowrap;
}

.btn-primary:hover {
  opacity: 0.9;
}

.section {
  display: flex;
  flex-direction: column;
}
</style>
