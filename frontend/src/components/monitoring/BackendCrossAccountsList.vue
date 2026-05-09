<template>
  <div class="opencode-section">
    <div class="opencode-note" data-tour="opencode-info">
      <span class="note-icon">i</span>
      <span>{{ t('backendDetail.openCodeNote') }}</span>
    </div>
    <div class="section-header">
      <h2>{{ t('backendDetail.availableBackendAccounts') }}</h2>
    </div>
    <div v-if="groups.length === 0" class="empty-state">
      <p>{{ t('backendDetail.noOtherBackendAccounts') }}</p>
    </div>
    <div v-else class="accounts-list">
      <div v-for="group in groups" :key="group.backend_type" class="cross-backend-group">
        <div class="cross-backend-header">
          <span class="cross-backend-name">{{ group.backend_name }}</span>
          <span class="type-badge">{{ group.backend_type }}</span>
        </div>
        <div v-for="account in group.accounts" :key="account.id" class="account-card cross-backend-card">
          <div class="account-info">
            <div class="account-header">
              <h3>{{ account.account_name }}</h3>
              <span v-if="account.is_default" class="default-badge">{{ t('backendDetail.default') }}</span>
            </div>
            <div class="account-meta">
              <div v-if="account.email" class="meta-item">
                <span class="meta-label">{{ t('backendDetail.emailLabel') }}</span>
                <span>{{ account.email }}</span>
              </div>
              <div v-if="account.plan" class="meta-item">
                <span class="meta-label">{{ t('backendDetail.planLabel') }}</span>
                <span class="plan-badge">{{ account.plan }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { BackendAccount } from '../../services/api';

interface CrossBackendGroup {
  backend_name: string;
  backend_type: string;
  accounts: BackendAccount[];
}

defineProps<{
  groups: CrossBackendGroup[];
}>();

const { t } = useI18n();
</script>

<style scoped>
.opencode-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.opencode-note {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--accent-emerald);
  border-radius: 8px;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.note-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
  font-size: 0.7rem;
  font-weight: 700;
  flex-shrink: 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h2 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

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

.plan-badge {
  padding: 0.125rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 10px;
  font-size: 0.75rem;
  text-transform: capitalize;
}

.type-badge {
  padding: 0.25rem 0.75rem;
  background: var(--bg-tertiary);
  border-radius: 20px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.cross-backend-group {
  margin-bottom: 1rem;
}

.cross-backend-group:last-child {
  margin-bottom: 0;
}

.cross-backend-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  padding: 0.25rem 0;
}

.cross-backend-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.cross-backend-card {
  opacity: 0.85;
  border-style: dashed;
}
</style>
