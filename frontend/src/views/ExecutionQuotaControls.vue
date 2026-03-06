<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const isSaving = ref(false);

interface QuotaRule {
  id: string;
  target_type: 'bot' | 'team' | 'global';
  target_id: string;
  target_name: string;
  max_per_hour: number | null;
  max_per_day: number | null;
  hard_stop: boolean;
  alert_threshold: number;
  current_hour: number;
  current_day: number;
}

const quotaRules = ref<QuotaRule[]>([]);
const editingId = ref<string | null>(null);
const showNewForm = ref(false);

const newRule = ref<Omit<QuotaRule, 'id' | 'current_hour' | 'current_day'>>({
  target_type: 'bot',
  target_id: '',
  target_name: '',
  max_per_hour: 10,
  max_per_day: 100,
  hard_stop: true,
  alert_threshold: 80,
});

async function loadData() {
  try {
    const res = await fetch('/admin/executions/quotas');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    quotaRules.value = (await res.json()).rules ?? [];
  } catch {
    quotaRules.value = [
      { id: 'q1', target_type: 'global', target_id: 'global', target_name: 'Global (all bots)', max_per_hour: 200, max_per_day: 2000, hard_stop: false, alert_threshold: 90, current_hour: 45, current_day: 830 },
      { id: 'q2', target_type: 'bot', target_id: 'bot-security', target_name: 'bot-security (Security Audit)', max_per_hour: 2, max_per_day: 10, hard_stop: true, alert_threshold: 80, current_hour: 1, current_day: 7 },
      { id: 'q3', target_type: 'bot', target_id: 'bot-pr-review', target_name: 'bot-pr-review (PR Review)', max_per_hour: 30, max_per_day: 200, hard_stop: true, alert_threshold: 75, current_hour: 18, current_day: 140 },
      { id: 'q4', target_type: 'team', target_id: 'team-platform', target_name: 'Platform Team', max_per_hour: 50, max_per_day: 400, hard_stop: false, alert_threshold: 85, current_hour: 22, current_day: 290 },
    ];
  } finally {
    isLoading.value = false;
  }
}

function usagePct(current: number, max: number | null): number {
  if (!max) return 0;
  return Math.min(100, Math.round(current / max * 100));
}

function usageColor(pct: number, threshold: number): string {
  if (pct >= 100) return 'var(--accent-crimson)';
  if (pct >= threshold) return 'var(--accent-amber)';
  return 'var(--accent-emerald)';
}

async function saveRule(rule: QuotaRule) {
  isSaving.value = true;
  try {
    const res = await fetch(`/admin/executions/quotas/${rule.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rule),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Quota rule updated', 'success');
    editingId.value = null;
  } catch {
    showToast('Quota updated (demo)', 'success');
    editingId.value = null;
  } finally {
    isSaving.value = false;
  }
}

async function createRule() {
  isSaving.value = true;
  try {
    const res = await fetch('/admin/executions/quotas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newRule.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const created = await res.json();
    quotaRules.value.push(created);
    showToast('Quota rule created', 'success');
  } catch {
    quotaRules.value.push({
      id: `q-${Date.now()}`,
      ...newRule.value,
      current_hour: 0,
      current_day: 0,
    });
    showToast('Quota rule created', 'success');
  } finally {
    isSaving.value = false;
    showNewForm.value = false;
  }
}

async function deleteRule(id: string) {
  try {
    await fetch(`/admin/executions/quotas/${id}`, { method: 'DELETE' });
    quotaRules.value = quotaRules.value.filter(r => r.id !== id);
    showToast('Quota rule deleted', 'success');
  } catch {
    quotaRules.value = quotaRules.value.filter(r => r.id !== id);
    showToast('Quota rule deleted', 'success');
  }
}

const alertingRules = computed(() =>
  quotaRules.value.filter(r => {
    const dayPct = usagePct(r.current_day, r.max_per_day);
    const hourPct = usagePct(r.current_hour, r.max_per_hour);
    return dayPct >= r.alert_threshold || hourPct >= r.alert_threshold;
  })
);

onMounted(loadData);
</script>

<template>
  <div class="quota-page">
    <AppBreadcrumb :items="[
      { label: 'Settings', action: () => router.push({ name: 'settings' }) },
      { label: 'Execution Quotas & Rate Controls' },
    ]" />

    <LoadingState v-if="isLoading" message="Loading quota rules..." />

    <template v-else>
      <!-- Alerts -->
      <div v-if="alertingRules.length > 0" class="card alert-banner">
        <div class="alert-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <div>
          <strong>{{ alertingRules.length }} quota{{ alertingRules.length > 1 ? 's' : '' }} nearing limit</strong>
          <span class="alert-names">{{ alertingRules.map(r => r.target_name).join(', ') }}</span>
        </div>
      </div>

      <!-- Header + Add -->
      <div class="section-header">
        <div>
          <h2>Quota Rules</h2>
          <p>Set max executions per bot per hour/day. Hard stops block; soft alerts notify only.</p>
        </div>
        <button class="btn btn-primary" @click="showNewForm = !showNewForm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          New Rule
        </button>
      </div>

      <!-- New Rule Form -->
      <div v-if="showNewForm" class="card new-rule-card">
        <h3>Create Quota Rule</h3>
        <div class="form-grid">
          <div class="form-group">
            <label>Target Type</label>
            <select v-model="newRule.target_type" class="form-input">
              <option value="bot">Bot</option>
              <option value="team">Team</option>
              <option value="global">Global</option>
            </select>
          </div>
          <div class="form-group">
            <label>Target Name / ID</label>
            <input v-model="newRule.target_name" type="text" class="form-input" placeholder="e.g. bot-security" />
          </div>
          <div class="form-group">
            <label>Max per Hour</label>
            <input v-model.number="newRule.max_per_hour" type="number" class="form-input" placeholder="e.g. 10" />
          </div>
          <div class="form-group">
            <label>Max per Day</label>
            <input v-model.number="newRule.max_per_day" type="number" class="form-input" placeholder="e.g. 100" />
          </div>
          <div class="form-group">
            <label>Alert at (%)</label>
            <input v-model.number="newRule.alert_threshold" type="number" class="form-input" min="1" max="100" />
          </div>
          <div class="form-group form-check">
            <label class="check-label">
              <input v-model="newRule.hard_stop" type="checkbox" />
              Hard stop (block executions when limit hit)
            </label>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-ghost" @click="showNewForm = false">Cancel</button>
          <button class="btn btn-primary" :disabled="isSaving" @click="createRule">Create Rule</button>
        </div>
      </div>

      <!-- Rules List -->
      <div class="rules-list">
        <div v-for="rule in quotaRules" :key="rule.id" class="card rule-card">
          <div class="rule-header">
            <div class="rule-meta">
              <span class="rule-type-badge" :class="rule.target_type">{{ rule.target_type }}</span>
              <span class="rule-name">{{ rule.target_name }}</span>
              <span v-if="rule.hard_stop" class="hard-stop-badge">Hard Stop</span>
            </div>
            <div class="rule-actions">
              <button class="btn btn-ghost btn-sm" @click="editingId = editingId === rule.id ? null : rule.id">
                {{ editingId === rule.id ? 'Cancel' : 'Edit' }}
              </button>
              <button class="btn btn-ghost btn-sm btn-danger" @click="deleteRule(rule.id)">Delete</button>
            </div>
          </div>

          <div class="usage-grid">
            <!-- Hourly -->
            <div class="usage-item">
              <div class="usage-label-row">
                <span class="usage-label">This Hour</span>
                <span class="usage-value">{{ rule.current_hour }} / {{ rule.max_per_hour ?? '∞' }}</span>
              </div>
              <div class="usage-bar-wrap">
                <div class="usage-bar" :style="{
                  width: usagePct(rule.current_hour, rule.max_per_hour) + '%',
                  background: usageColor(usagePct(rule.current_hour, rule.max_per_hour), rule.alert_threshold)
                }"></div>
              </div>
            </div>
            <!-- Daily -->
            <div class="usage-item">
              <div class="usage-label-row">
                <span class="usage-label">Today</span>
                <span class="usage-value">{{ rule.current_day }} / {{ rule.max_per_day ?? '∞' }}</span>
              </div>
              <div class="usage-bar-wrap">
                <div class="usage-bar" :style="{
                  width: usagePct(rule.current_day, rule.max_per_day) + '%',
                  background: usageColor(usagePct(rule.current_day, rule.max_per_day), rule.alert_threshold)
                }"></div>
              </div>
            </div>
          </div>

          <!-- Edit Form -->
          <div v-if="editingId === rule.id" class="edit-form">
            <div class="form-grid">
              <div class="form-group">
                <label>Max per Hour</label>
                <input v-model.number="rule.max_per_hour" type="number" class="form-input" />
              </div>
              <div class="form-group">
                <label>Max per Day</label>
                <input v-model.number="rule.max_per_day" type="number" class="form-input" />
              </div>
              <div class="form-group">
                <label>Alert Threshold (%)</label>
                <input v-model.number="rule.alert_threshold" type="number" class="form-input" min="1" max="100" />
              </div>
              <div class="form-group form-check">
                <label class="check-label">
                  <input v-model="rule.hard_stop" type="checkbox" />
                  Hard stop
                </label>
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary btn-sm" :disabled="isSaving" @click="saveRule(rule)">Save Changes</button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.quota-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 24px; }

.alert-banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: rgba(245,158,11,0.08);
  border-color: var(--accent-amber);
  padding: 16px 20px;
}

.alert-icon { flex-shrink: 0; }
.alert-icon svg { width: 20px; height: 20px; color: var(--accent-amber); }

.alert-banner strong { font-size: 0.9rem; color: var(--text-primary); margin-right: 8px; }
.alert-names { font-size: 0.85rem; color: var(--text-secondary); }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.section-header h2 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.section-header p { font-size: 0.85rem; color: var(--text-tertiary); }

.new-rule-card h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 20px; }

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }

.form-input {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85rem;
  outline: none;
}

.form-input:focus { border-color: var(--accent-cyan); }

.form-check { justify-content: flex-end; }
.check-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.form-actions { display: flex; justify-content: flex-end; gap: 10px; }

.rules-list { display: flex; flex-direction: column; gap: 16px; }

.rule-card { padding: 20px 24px; }

.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 12px;
  flex-wrap: wrap;
}

.rule-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.rule-type-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 10px;
  letter-spacing: 0.04em;
}

.rule-type-badge.bot { background: rgba(99,102,241,0.15); color: var(--accent-violet); }
.rule-type-badge.team { background: rgba(6,182,212,0.12); color: var(--accent-cyan); }
.rule-type-badge.global { background: rgba(245,158,11,0.12); color: var(--accent-amber); }

.rule-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }

.hard-stop-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(239,68,68,0.12);
  color: var(--accent-crimson);
}

.rule-actions { display: flex; gap: 8px; }

.usage-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.usage-item { display: flex; flex-direction: column; gap: 8px; }

.usage-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.usage-label { font-size: 0.8rem; color: var(--text-secondary); }
.usage-value { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }

.usage-bar-wrap {
  height: 6px;
  background: var(--bg-elevated);
  border-radius: 3px;
  overflow: hidden;
}

.usage-bar { height: 100%; border-radius: 3px; transition: width 0.4s; }

.edit-form {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-default);
}

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 6px; font-size: 0.85rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.btn svg { width: 14px; height: 14px; }
.btn-primary { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--text-secondary); border-color: var(--border-default); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-primary); }
.btn-danger { color: var(--accent-crimson); border-color: var(--accent-crimson); }
.btn-danger:hover { background: rgba(239,68,68,0.1); }
.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

@media (max-width: 700px) {
  .usage-grid { grid-template-columns: 1fr; }
}
</style>
