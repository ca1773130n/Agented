<template>
  <div v-if="accounts.length === 0" class="empty-state">
    <p v-if="isOpenCode">{{ t('backendDetail.emptyOpenCode') }}</p>
    <p v-else>{{ t('backendDetail.emptyAccounts') }}</p>
  </div>

  <div v-else class="accounts-list">
    <div v-for="account in accounts" :key="account.id" class="account-card">
      <div class="account-info">
        <div class="account-header">
          <h3>{{ account.account_name }}</h3>
          <span v-if="account.is_default" class="default-badge">{{ t('backendDetail.default') }}</span>
          <!-- Health status badge -->
          <template v-if="getAccountHealth(account.id)">
            <span v-if="getAccountHealth(account.id)!.is_rate_limited" class="health-badge rate-limited">
              <span class="health-dot red"></span>
              {{ t('backendDetail.rateLimited') }} ({{ formatCooldown(getAccountHealth(account.id)!) }})
            </span>
            <span v-else class="health-badge healthy">
              <span class="health-dot green"></span>
              {{ t('backendDetail.healthy') }}
            </span>
          </template>
        </div>
        <div class="account-meta">
          <div v-if="account.email" class="meta-item">
            <span class="meta-label">{{ t('backendDetail.emailLabel') }}</span>
            <span>{{ account.email }}</span>
          </div>
          <div v-if="account.config_path" class="meta-item">
            <span class="meta-label">{{ t('backendDetail.configPathLabel') }}</span>
            <code>{{ account.config_path }}</code>
          </div>
          <div v-if="account.api_key_env" class="meta-item">
            <span class="meta-label">{{ t('backendDetail.apiKeyEnvLabel') }}</span>
            <code>{{ account.api_key_env }}</code>
          </div>
          <div v-if="account.plan" class="meta-item">
            <span class="meta-label">{{ t('backendDetail.planLabel') }}</span>
            <span class="plan-badge">{{ account.plan }}</span>
          </div>
          <!-- Health stats -->
          <template v-if="getAccountHealth(account.id)">
            <div class="meta-item">
              <span class="meta-label">{{ t('backendDetail.executionsLabel') }}</span>
              <span>{{ getAccountHealth(account.id)!.total_executions }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">{{ t('backendDetail.lastUsedLabel') }}</span>
              <span>{{ formatRelativeTime(getAccountHealth(account.id)!.last_used_at) }}</span>
            </div>
          </template>
        </div>
      </div>
      <div class="account-actions">
        <button
          v-if="supportsConnect && isInstalled"
          class="btn btn-sm btn-outline"
          @click="emit('login', { account, proxyOnly: false })"
        >
          {{ t('backendDetail.login') }}
        </button>
        <button
          v-if="supportsConnect"
          class="btn btn-sm btn-outline"
          @click="emit('login', { account, proxyOnly: true })"
        >
          {{ t('backendDetail.proxyLogin') }}
        </button>
        <button
          v-if="backendType !== 'opencode'"
          class="btn btn-sm btn-outline"
          :disabled="rateLimitState[account.id]?.loading"
          @click="emit('check-rate-limits', account.id)"
        >
          {{ rateLimitState[account.id]?.loading ? t('backendDetail.checking') : t('backendDetail.checkRateLimits') }}
        </button>
        <button
          v-if="getAccountHealth(account.id)?.is_rate_limited"
          class="btn btn-sm btn-clear-rl"
          @click="emit('clear-rate-limit', account.id)"
        >
          {{ t('backendDetail.clearRateLimit') }}
        </button>

        <button class="btn btn-sm btn-secondary" @click="emit('edit', account)">{{ t('common.edit') }}</button>
        <button class="btn btn-sm btn-danger" @click="emit('delete', account.id)">{{ t('common.delete') }}</button>
      </div>
      <!-- Rate limit results -->
      <div v-if="rateLimitState[account.id]?.windows?.length" class="rate-limit-results">
        <div v-for="w in rateLimitState[account.id]!.windows" :key="w.window_type" class="rl-mini-gauge">
          <div class="rl-mini-header">
            <span class="rl-mini-label">{{ w.window_type }}</span>
            <span class="rl-mini-pct" :style="{ color: getRateLimitColor(w.percentage) }">{{ Math.round(w.percentage) }}%</span>
          </div>
          <div class="rl-mini-bar">
            <div class="rl-mini-fill" :style="{ width: Math.min(w.percentage, 100) + '%', background: getRateLimitColor(w.percentage) }"></div>
          </div>
          <div v-if="w.resets_at" class="rl-mini-reset">{{ t('backendDetail.resets') }}: {{ new Date(w.resets_at).toLocaleString() }}</div>
        </div>
      </div>
      <div v-else-if="rateLimitState[account.id]?.error" class="rate-limit-error">
        {{ rateLimitState[account.id]!.error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { BackendAccount, AccountHealth, RateLimitWindow } from '../../services/api';

interface RateLimitEntry {
  loading: boolean;
  windows: RateLimitWindow[];
  error: string | null;
}

const props = defineProps<{
  accounts: BackendAccount[];
  isOpenCode: boolean;
  isInstalled: boolean;
  supportsConnect: boolean;
  backendType: string;
  rateLimitState: Record<string, RateLimitEntry>;
  getAccountHealth: (id: string) => AccountHealth | undefined;
  formatCooldown: (h: AccountHealth) => string;
  formatRelativeTime: (s: string | null) => string;
  getRateLimitColor: (pct: number) => string;
}>();

// Reference props to silence unused warning (template uses them).
void props;

const emit = defineEmits<{
  (e: 'login', payload: { account: BackendAccount; proxyOnly: boolean }): void;
  (e: 'edit', account: BackendAccount): void;
  (e: 'delete', accountId: string): void;
  (e: 'check-rate-limits', accountId: string): void;
  (e: 'clear-rate-limit', accountId: string): void;
}>();

const { t } = useI18n();
</script>

<style scoped>
.accounts-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.account-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  padding: 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.account-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.account-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.default-badge {
  padding: 0.125rem 0.5rem;
  background: var(--primary-color);
  color: white;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 500;
}

.account-meta {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
}

.meta-label {
  color: var(--text-secondary);
}

.meta-item code {
  padding: 0.125rem 0.375rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-primary);
}

.plan-badge {
  padding: 0.125rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 10px;
  font-size: 0.75rem;
  text-transform: capitalize;
}

.account-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.btn-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-outline {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
  font-weight: 500;
}

.btn-outline:hover {
  background: var(--bg-elevated);
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}

.btn-outline:active {
  transform: translateY(1px);
}

.btn-danger {
  background: var(--accent-crimson);
  color: white;
  border: none;
}

.btn-danger:hover {
  background: var(--accent-crimson);
  filter: brightness(0.9);
}

/* Health badges */
.health-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.125rem 0.5rem;
  border-radius: 10px;
  font-size: 0.6875rem;
  font-weight: 500;
}

.health-badge.healthy {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.health-badge.rate-limited {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  font-family: var(--font-mono, monospace);
}

.health-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.health-dot.green {
  background: var(--accent-emerald);
  box-shadow: 0 0 4px var(--accent-emerald-dim);
}

.health-dot.red {
  background: var(--accent-crimson);
  box-shadow: 0 0 4px var(--accent-crimson-dim);
}

.btn-clear-rl {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  background: transparent;
  border: 1px solid var(--accent-crimson);
  color: var(--accent-crimson);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-clear-rl:hover {
  background: var(--accent-crimson);
  color: white;
}

/* Rate limit results */
.rate-limit-results {
  width: 100%;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.rl-mini-gauge {
  flex: 1;
  min-width: 140px;
  max-width: 220px;
  padding: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.rl-mini-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.375rem;
}

.rl-mini-label {
  font-size: 0.7rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.rl-mini-pct {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 700;
}

.rl-mini-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.rl-mini-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.rl-mini-reset {
  font-size: 0.65rem;
  color: var(--text-tertiary);
  margin-top: 0.25rem;
}

.rate-limit-error {
  width: 100%;
  margin-top: 0.5rem;
  padding: 0.375rem 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  background: rgba(150, 150, 150, 0.08);
  border-radius: 4px;
}
</style>
