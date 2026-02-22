<template>
  <div class="service-health-grid">
    <div v-if="loading" class="grid-skeleton">
      <div v-for="i in 3" :key="i" class="skeleton-card">
        <div class="skeleton-line wide"></div>
        <div class="skeleton-line medium"></div>
        <div class="skeleton-line narrow"></div>
      </div>
    </div>
    <div v-else-if="accounts.length === 0" class="grid-empty">
      <p>No accounts in this group.</p>
    </div>
    <div v-else class="grid-cards">
      <div v-for="account in accounts" :key="account.account_id" class="health-card">
        <div class="card-header">
          <div class="header-left">
            <span class="status-dot" :class="statusClass(account)"></span>
            <span class="account-name">{{ account.account_name }}</span>
          </div>
          <span class="backend-type-badge" :class="account.backend_type">
            {{ account.backend_type }}
          </span>
        </div>

        <div class="card-status">
          <span v-if="account.is_rate_limited" class="status-badge rate-limited">Rate Limited</span>
          <span v-else class="status-badge healthy">Healthy</span>
          <span v-if="account.is_default" class="default-badge">Default</span>
          <span v-if="account.plan" class="plan-badge">{{ account.plan }}</span>
        </div>

        <div v-if="account.is_rate_limited" class="rate-limit-info">
          <div class="cooldown-timer">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
            <span>Cooldown: {{ formatCooldown(account) }}</span>
          </div>
          <p v-if="account.rate_limit_reason" class="rate-limit-reason">
            {{ account.rate_limit_reason }}
          </p>
          <button class="clear-rate-limit-btn" @click="$emit('clear-rate-limit', account.account_id)">
            Clear Rate Limit
          </button>
        </div>

        <div class="card-stats">
          <div class="stat-item">
            <span class="stat-label">Executions</span>
            <span class="stat-value">{{ account.total_executions }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Last Used</span>
            <span class="stat-value">{{ formatRelativeTime(account.last_used_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import type { AccountHealth } from '../../services/api';

defineProps<{
  accounts: AccountHealth[];
  loading: boolean;
}>();

defineEmits<{
  (e: 'clear-rate-limit', accountId: number): void;
}>();

// Reactive clock for countdown timers
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  timer = setInterval(() => { now.value = Date.now(); }, 1000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});

function statusClass(account: AccountHealth): string {
  if (account.is_rate_limited) return 'red';
  return 'green';
}

function formatCooldown(account: AccountHealth): string {
  if (!account.rate_limited_until) return 'Unknown';
  const until = new Date(account.rate_limited_until).getTime();
  const remaining = Math.max(0, Math.floor((until - now.value) / 1000));
  if (remaining <= 0) return 'Expiring...';
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s remaining`;
  return `${seconds}s remaining`;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const diff = Math.floor((now.value - new Date(dateStr).getTime()) / 1000);
  if (diff < 0) return 'Just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
</script>

<style scoped>
.grid-skeleton {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.skeleton-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1.25rem;
}

.skeleton-line {
  height: 14px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  margin-bottom: 0.75rem;
}

.skeleton-line.wide { width: 80%; }
.skeleton-line.medium { width: 60%; }
.skeleton-line.narrow { width: 40%; }

.grid-empty {
  text-align: center;
  padding: 2rem;
  color: var(--text-tertiary);
}

.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

@media (min-width: 1200px) {
  .grid-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .grid-cards {
    grid-template-columns: 1fr;
  }
}

.health-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1.25rem;
  transition: border-color var(--transition-fast);
}

.health-card:hover {
  border-color: var(--border-default);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.green {
  background: var(--accent-emerald);
  box-shadow: 0 0 6px rgba(0, 255, 136, 0.4);
}

.status-dot.red {
  background: var(--accent-crimson);
  box-shadow: 0 0 6px rgba(255, 51, 102, 0.4);
}

.account-name {
  font-weight: 600;
  font-size: 0.9375rem;
  color: var(--text-primary);
}

.backend-type-badge {
  padding: 0.15rem 0.5rem;
  border-radius: 12px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.backend-type-badge.claude {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.backend-type-badge.opencode {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.card-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.status-badge {
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 600;
}

.status-badge.healthy {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.rate-limited {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.default-badge {
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 600;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.plan-badge {
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 600;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.rate-limit-info {
  background: rgba(255, 51, 102, 0.06);
  border: 1px solid rgba(255, 51, 102, 0.15);
  border-radius: 8px;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
}

.cooldown-timer {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--accent-crimson);
  font-family: var(--font-mono);
}

.cooldown-timer svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.rate-limit-reason {
  margin: 0.5rem 0 0;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.clear-rate-limit-btn {
  margin-top: 0.5rem;
  padding: 0.35rem 0.75rem;
  background: transparent;
  border: 1px solid var(--accent-crimson);
  color: var(--accent-crimson);
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.clear-rate-limit-btn:hover {
  background: var(--accent-crimson);
  color: white;
}

.card-stats {
  display: flex;
  gap: 1.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.stat-label {
  font-size: 0.6875rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 0.8125rem;
  color: var(--text-primary);
  font-weight: 500;
}
</style>
