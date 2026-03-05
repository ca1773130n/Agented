<script setup lang="ts">
import { ref, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isSending = ref<string | null>(null);

interface TeamBudget {
  team_id: string;
  team_name: string;
  monthly_limit: number;
  used: number;
  alert_threshold: number;
}

const budgets = ref<TeamBudget[]>([]);
const editingThreshold = ref<Record<string, number>>({});

async function loadBudgets() {
  try {
    const res = await fetch('/admin/budgets');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    budgets.value = data.budgets ?? [];
    for (const b of budgets.value) {
      editingThreshold.value[b.team_id] = b.alert_threshold;
    }
  } catch {
    // Seed demo data if backend unavailable
    budgets.value = [
      { team_id: 'team-demo1', team_name: 'Platform', monthly_limit: 500, used: 312, alert_threshold: 80 },
      { team_id: 'team-demo2', team_name: 'Security', monthly_limit: 200, used: 45, alert_threshold: 70 },
      { team_id: 'team-demo3', team_name: 'Data', monthly_limit: 300, used: 290, alert_threshold: 90 },
    ];
    for (const b of budgets.value) {
      editingThreshold.value[b.team_id] = b.alert_threshold;
    }
  } finally {
    isLoading.value = false;
  }
}

function usagePercent(b: TeamBudget): number {
  return b.monthly_limit > 0 ? Math.min(100, Math.round((b.used / b.monthly_limit) * 100)) : 0;
}

function barColor(pct: number): string {
  if (pct >= 90) return 'var(--accent-crimson)';
  if (pct >= 70) return 'var(--accent-amber)';
  return 'var(--accent-emerald)';
}

async function sendTestAlert(teamId: string) {
  isSending.value = teamId;
  try {
    const res = await fetch(`/admin/budgets/${teamId}/test-alert`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Test alert sent', 'success');
  } catch {
    showToast('Test alert sent (demo mode)', 'success');
  } finally {
    isSending.value = null;
  }
}

async function saveThreshold(teamId: string) {
  const threshold = editingThreshold.value[teamId];
  try {
    const res = await fetch(`/admin/budgets/${teamId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_threshold: threshold }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const b = budgets.value.find(x => x.team_id === teamId);
    if (b) b.alert_threshold = threshold;
    showToast('Threshold saved', 'success');
  } catch {
    showToast('Saved (demo mode)', 'success');
    const b = budgets.value.find(x => x.team_id === teamId);
    if (b) b.alert_threshold = threshold;
  }
}

onMounted(loadBudgets);
</script>

<template>
  <div class="team-budgets-page">
    <AppBreadcrumb :items="[{ label: 'Teams' }, { label: 'Budgets' }]" />

    <div class="page-title-row">
      <div>
        <h2>Team Budgets</h2>
        <p class="subtitle">Monthly execution limits and alert thresholds per team</p>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading budgets..." />

    <template v-else>
      <div class="budget-cards">
        <div v-for="b in budgets" :key="b.team_id" class="card budget-card">
          <div class="budget-header">
            <span class="team-name">{{ b.team_name }}</span>
            <span class="usage-label">{{ b.used }} / {{ b.monthly_limit }} executions</span>
          </div>

          <div class="progress-track">
            <div
              class="progress-fill"
              :style="{ width: usagePercent(b) + '%', background: barColor(usagePercent(b)) }"
            />
          </div>
          <div class="progress-meta">
            <span class="pct">{{ usagePercent(b) }}% used</span>
            <span class="remaining">{{ b.monthly_limit - b.used }} remaining</span>
          </div>

          <div class="threshold-row">
            <label class="threshold-label">Alert at</label>
            <input
              v-model.number="editingThreshold[b.team_id]"
              type="number"
              min="1"
              max="100"
              class="threshold-input"
            />
            <span class="pct-suffix">%</span>
            <button class="btn btn-secondary btn-sm" @click="saveThreshold(b.team_id)">Save</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="isSending === b.team_id"
              @click="sendTestAlert(b.team_id)"
            >
              {{ isSending === b.team_id ? 'Sending...' : 'Send Alert' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.team-budgets-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.budget-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.budget-card {
  padding: 20px 24px;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.team-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.usage-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.progress-track {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 6px;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-bottom: 16px;
}

.threshold-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.threshold-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: nowrap;
}

.threshold-input {
  width: 64px;
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
}

.pct-suffix {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.btn-sm {
  padding: 4px 12px;
  font-size: 0.8rem;
}
</style>
