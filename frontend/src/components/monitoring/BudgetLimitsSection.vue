<script setup lang="ts">
import { ref } from 'vue';
import type { BudgetLimit } from '../../services/api';
import { useTokenFormatting } from '../../composables/useTokenFormatting';
import ConfirmModal from '../base/ConfirmModal.vue';

const { formatCurrency } = useTokenFormatting();

defineProps<{
  budgetLimits: BudgetLimit[];
  agents: { id: string; name: string }[];
  teams: { id: string; name: string }[];
  triggers: { id: string; name: string }[];
}>();

const emit = defineEmits<{
  (e: 'open-add-limit'): void;
  (e: 'open-edit-limit', limit: BudgetLimit): void;
  (e: 'delete-limit', limit: BudgetLimit): void;
}>();

// Delete confirmation state
const showDeleteConfirm = ref(false);
const pendingDeleteLimit = ref<BudgetLimit | null>(null);

function requestDelete(limit: BudgetLimit) {
  pendingDeleteLimit.value = limit;
  showDeleteConfirm.value = true;
}

function confirmDelete() {
  if (pendingDeleteLimit.value) {
    emit('delete-limit', pendingDeleteLimit.value);
  }
  showDeleteConfirm.value = false;
  pendingDeleteLimit.value = null;
}

function cancelDelete() {
  showDeleteConfirm.value = false;
  pendingDeleteLimit.value = null;
}

function getLimitStatus(limit: BudgetLimit): { label: string; color: string; bgColor: string } {
  const spend = limit.current_spend_usd || 0;
  if (limit.hard_limit_usd != null && spend >= limit.hard_limit_usd) {
    return { label: 'Exceeded', color: '#ff3366', bgColor: 'rgba(255, 51, 102, 0.15)' };
  }
  if (limit.soft_limit_usd != null && spend >= limit.soft_limit_usd) {
    return { label: 'Warning', color: '#ffaa00', bgColor: 'rgba(255, 170, 0, 0.15)' };
  }
  return { label: 'Within Budget', color: '#00ff88', bgColor: 'rgba(0, 255, 136, 0.15)' };
}

function getBudgetProgress(limit: BudgetLimit): number {
  const spend = limit.current_spend_usd || 0;
  const cap = limit.hard_limit_usd ?? limit.soft_limit_usd ?? 0;
  if (cap <= 0) return 0;
  return Math.min((spend / cap) * 100, 100);
}

function getBudgetProgressColor(limit: BudgetLimit): string {
  return getLimitStatus(limit).color;
}

function getEntityName(limit: BudgetLimit, agents: { id: string; name: string }[], teams: { id: string; name: string }[], triggers: { id: string; name: string }[]): string {
  if (limit.entity_type === 'agent') {
    const agent = agents.find(a => a.id === limit.entity_id);
    return agent?.name ?? limit.entity_id;
  }
  if (limit.entity_type === 'team') {
    const team = teams.find(t => t.id === limit.entity_id);
    return team?.name ?? limit.entity_id;
  }
  if (limit.entity_type === 'trigger' || limit.entity_type === 'bot') {
    const trigger = triggers.find(t => t.id === limit.entity_id);
    return trigger?.name ?? limit.entity_id;
  }
  return limit.entity_id;
}
</script>

<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">Budget Limits</h2>
      <button class="add-limit-btn" @click="emit('open-add-limit')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/>
          <line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Add Limit
      </button>
    </div>

    <div v-if="budgetLimits.length === 0" class="empty-state">
      No budget limits configured. Click "Add Limit" to set spending guardrails.
    </div>

    <div v-else class="limits-table-wrapper">
      <table class="limits-table">
        <thead>
          <tr>
            <th>Entity</th>
            <th>Type</th>
            <th>Period</th>
            <th>Soft Limit</th>
            <th>Hard Limit</th>
            <th>Current Spend</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="limit in budgetLimits" :key="limit.id">
            <td class="entity-cell">{{ getEntityName(limit, agents, teams, triggers) }}</td>
            <td><span class="type-badge">{{ limit.entity_type }}</span></td>
            <td>{{ limit.period }}</td>
            <td>{{ limit.soft_limit_usd != null ? formatCurrency(limit.soft_limit_usd) : '--' }}</td>
            <td>{{ limit.hard_limit_usd != null ? formatCurrency(limit.hard_limit_usd) : '--' }}</td>
            <td>
              <div class="spend-cell">
                <span>{{ formatCurrency(limit.current_spend_usd || 0) }}</span>
                <div class="budget-progress-track">
                  <div
                    class="budget-progress-fill"
                    :style="{
                      width: getBudgetProgress(limit) + '%',
                      backgroundColor: getBudgetProgressColor(limit),
                    }"
                  ></div>
                </div>
              </div>
            </td>
            <td>
              <span
                class="status-badge"
                :style="{
                  color: getLimitStatus(limit).color,
                  backgroundColor: getLimitStatus(limit).bgColor,
                }"
              >
                {{ getLimitStatus(limit).label }}
              </span>
            </td>
            <td>
              <div class="action-btns">
                <button class="action-btn" title="Edit" @click="emit('open-edit-limit', limit)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
                <button class="action-btn danger" title="Delete" @click="requestDelete(limit)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Budget Limit"
      :message="`Are you sure you want to delete the budget limit for \u201C${pendingDeleteLimit ? getEntityName(pendingDeleteLimit, agents, teams, triggers) : ''}\u201D?`"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>

<style scoped>
.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.add-limit-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.add-limit-btn:hover {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.add-limit-btn svg {
  width: 14px;
  height: 14px;
}

.limits-table-wrapper {
  overflow-x: auto;
}

.limits-table {
  width: 100%;
  border-collapse: collapse;
}

.limits-table th {
  text-align: left;
  padding: 10px 12px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-subtle);
}

.limits-table td {
  padding: 12px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.limits-table tbody tr:last-child td {
  border-bottom: none;
}

.limits-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.entity-cell {
  font-weight: 600;
  color: var(--text-primary) !important;
}

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.spend-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.budget-progress-track {
  height: 4px;
  background: var(--bg-primary);
  border-radius: 2px;
  overflow: hidden;
  min-width: 80px;
}

.budget-progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
}

.action-btns {
  display: flex;
  gap: 4px;
}

.action-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border-color: var(--border-default);
}

.action-btn.danger:hover {
  color: #ff3366;
  background: rgba(255, 51, 102, 0.1);
  border-color: rgba(255, 51, 102, 0.3);
}

.action-btn svg {
  width: 14px;
  height: 14px;
}
</style>
