<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { MonitoringConfig } from '../../services/api';
import { settingsApi, monitoringApi, backendApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const showToast = useToast();

// General settings
const workspaceRoot = ref('');
const originalWorkspaceRoot = ref('');
const loadingGeneral = ref(false);
const savingGeneral = ref(false);

// Marketplace auto-update setting
const marketplaceAutoUpdate = ref(true);
const originalAutoUpdate = ref(true);

// Monitoring settings
const monitoringConfig = ref<MonitoringConfig>({
  enabled: false,
  polling_minutes: 5,
  accounts: {},
});
const originalMonitoringConfig = ref<string>('');
const backendAccounts = ref<Array<{ id: number; account_name: string; backend_type: string }>>([]);
const loadingMonitoring = ref(false);
const savingMonitoring = ref(false);

async function loadGeneralSettings() {
  loadingGeneral.value = true;
  try {
    const data = await settingsApi.get('workspace_root');
    workspaceRoot.value = data.value || '';
    originalWorkspaceRoot.value = workspaceRoot.value;
  } catch {
    // Setting doesn't exist yet, that's fine
    workspaceRoot.value = '';
    originalWorkspaceRoot.value = '';
  } finally {
    loadingGeneral.value = false;
  }
}

async function saveWorkspaceRoot() {
  savingGeneral.value = true;
  try {
    await settingsApi.set('workspace_root', workspaceRoot.value);
    originalWorkspaceRoot.value = workspaceRoot.value;
    showToast('Workspace root saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save workspace root';
    showToast(message, 'error');
  } finally {
    savingGeneral.value = false;
  }
}

async function loadAutoUpdateSetting() {
  try {
    const data = await settingsApi.get('marketplace_auto_update');
    marketplaceAutoUpdate.value = !data.value || data.value !== 'false';
    originalAutoUpdate.value = marketplaceAutoUpdate.value;
  } catch {
    marketplaceAutoUpdate.value = true;
    originalAutoUpdate.value = true;
  }
}

async function saveAutoUpdateSetting() {
  try {
    await settingsApi.set('marketplace_auto_update', String(marketplaceAutoUpdate.value));
    originalAutoUpdate.value = marketplaceAutoUpdate.value;
    showToast('Auto-update setting saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save setting';
    showToast(message, 'error');
  }
}

async function loadMonitoringSettings() {
  loadingMonitoring.value = true;
  try {
    const [configData, backendsData] = await Promise.all([
      monitoringApi.getConfig(),
      backendApi.list(),
    ]);
    monitoringConfig.value = {
      enabled: configData.enabled ?? false,
      polling_minutes: configData.polling_minutes ?? 5,
      accounts: configData.accounts ?? {},
    };
    originalMonitoringConfig.value = JSON.stringify(monitoringConfig.value);

    // Load accounts for each backend
    const allAccounts: Array<{ id: number; account_name: string; backend_type: string }> = [];
    for (const backend of (backendsData.backends || [])) {
      try {
        const detail = await backendApi.get(backend.id);
        for (const acct of (detail.accounts || [])) {
          allAccounts.push({
            id: acct.id,
            account_name: acct.account_name,
            backend_type: backend.type,
          });
        }
      } catch {
        // Skip backends that fail to load
      }
    }
    backendAccounts.value = allAccounts;
  } catch {
    // Config not set yet, use defaults
    monitoringConfig.value = { enabled: false, polling_minutes: 5, accounts: {} };
    originalMonitoringConfig.value = JSON.stringify(monitoringConfig.value);
  } finally {
    loadingMonitoring.value = false;
  }
}

async function saveMonitoringConfig() {
  savingMonitoring.value = true;
  try {
    await monitoringApi.setConfig(monitoringConfig.value);
    originalMonitoringConfig.value = JSON.stringify(monitoringConfig.value);
    showToast('Monitoring settings saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save monitoring settings';
    showToast(message, 'error');
  } finally {
    savingMonitoring.value = false;
  }
}

function isMonitoringDirty(): boolean {
  return JSON.stringify(monitoringConfig.value) !== originalMonitoringConfig.value;
}

function toggleAccountMonitoring(accountId: number) {
  const key = String(accountId);
  if (!monitoringConfig.value.accounts[key]) {
    monitoringConfig.value.accounts[key] = { enabled: true };
  } else {
    monitoringConfig.value.accounts[key].enabled = !monitoringConfig.value.accounts[key].enabled;
  }
}

function isAccountEnabled(accountId: number): boolean {
  const key = String(accountId);
  return monitoringConfig.value.accounts[key]?.enabled ?? false;
}

onMounted(() => {
  loadGeneralSettings();
  loadAutoUpdateSetting();
  loadMonitoringSettings();
});
</script>

<template>
  <div class="tab-content">
    <div class="card">
      <div class="card-header">
        <h3>Project Workspace</h3>
      </div>
      <div class="card-body">
        <div class="form-group">
          <label>Workspace Root</label>
          <p class="form-help">Root directory where GitHub repos are cloned for project team execution.</p>
          <input
            v-model="workspaceRoot"
            type="text"
            class="form-input"
            placeholder="/home/user/workspace"
          />
          <p class="form-hint">Projects will be cloned to: <code>{{ workspaceRoot || '{workspace_root}' }}/projects/{project_name}/</code></p>
        </div>
        <div class="form-actions">
          <button
            class="btn btn-primary"
            :disabled="savingGeneral || workspaceRoot === originalWorkspaceRoot"
            @click="saveWorkspaceRoot"
          >
            {{ savingGeneral ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>Marketplace</h3>
      </div>
      <div class="card-body">
        <div class="form-group toggle-group">
          <label class="toggle-label">
            <span class="toggle-text">
              <strong>Auto-refresh on tab open</strong>
              <span class="toggle-description">Automatically refresh marketplace data when switching to the Marketplaces tab</span>
            </span>
            <button
              :class="['toggle-switch', { active: marketplaceAutoUpdate }]"
              @click="marketplaceAutoUpdate = !marketplaceAutoUpdate; saveAutoUpdateSetting()"
            >
              <span class="toggle-knob"></span>
            </button>
          </label>
        </div>
      </div>
    </div>

    <!-- Token Monitoring Section -->
    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>Token Monitoring</h3>
      </div>
      <div class="card-body">
        <div v-if="loadingMonitoring" class="loading-state" style="padding: 1.5rem;">
          <div class="spinner"></div>
          <span>Loading monitoring settings...</span>
        </div>

        <template v-else>
          <!-- Enable monitoring toggle -->
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>Enable Rate Limit Monitoring</strong>
                <span class="toggle-description">Periodically poll token usage to track rate limit consumption and display gauges on the dashboard</span>
              </span>
              <button
                :class="['toggle-switch', { active: monitoringConfig.enabled }]"
                @click="monitoringConfig.enabled = !monitoringConfig.enabled"
              >
                <span class="toggle-knob"></span>
              </button>
            </label>
          </div>

          <!-- Polling period selector -->
          <div class="form-group" style="margin-top: 1rem;">
            <label>Polling Period</label>
            <select
              v-model.number="monitoringConfig.polling_minutes"
              :disabled="!monitoringConfig.enabled"
              class="monitoring-select"
            >
              <option :value="1">Every 1 minute</option>
              <option :value="5">Every 5 minutes</option>
              <option :value="15">Every 15 minutes</option>
              <option :value="30">Every 30 minutes</option>
              <option :value="60">Every 60 minutes</option>
            </select>
            <span class="help-text">How often to poll token usage data from backend accounts</span>
          </div>

          <!-- Per-account toggles -->
          <div class="form-group" style="margin-top: 1rem;">
            <label>Monitored Accounts</label>
            <div v-if="backendAccounts.length === 0" class="monitoring-no-accounts">
              No AI backend accounts configured. Add accounts in AI Backends to enable per-account monitoring.
            </div>
            <div v-else class="monitoring-accounts-list">
              <div
                v-for="account in backendAccounts"
                :key="account.id"
                class="monitoring-account-row"
              >
                <div class="monitoring-account-info">
                  <span class="monitoring-account-name">{{ account.account_name }}</span>
                  <span class="monitoring-account-type">{{ account.backend_type }}</span>
                </div>
                <button
                  :class="['toggle-switch', 'toggle-switch-sm', { active: isAccountEnabled(account.id) }]"
                  :disabled="!monitoringConfig.enabled"
                  @click="toggleAccountMonitoring(account.id)"
                >
                  <span class="toggle-knob"></span>
                </button>
              </div>
            </div>
          </div>

          <!-- Save button -->
          <div class="form-actions">
            <button
              class="btn btn-primary"
              :disabled="savingMonitoring || !isMonitoringDirty()"
              @click="saveMonitoringConfig"
            >
              {{ savingMonitoring ? 'Saving...' : 'Save Monitoring Settings' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Cards */
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.card-body {
  padding: 1.25rem;
}

/* Form */
.form-group:last-child {
  margin-bottom: 0;
}

.form-input {
  width: 100%;
  padding: 0.6rem 0.8rem;
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary, #e0e0e0);
  font-size: 0.9rem;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent-color, #00d4ff);
}

.form-help {
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
}

.form-hint code {
  background: var(--bg-secondary, #1a1a2e);
  padding: 0.15rem 0.4rem;
  border-radius: 3px;
  font-size: 0.8rem;
}

.help-text {
  font-size: 0.8rem;
  color: var(--text-tertiary, #666);
  margin-top: 0.5rem;
  display: block;
}

/* Toggle switch */
.toggle-group {
  margin-bottom: 0;
}

.toggle-label {
  display: flex !important;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  cursor: pointer;
}

.toggle-text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.toggle-text strong {
  font-size: 0.9rem;
  color: var(--text-primary, #fff);
  font-weight: 500;
}

.toggle-description {
  font-size: 0.8rem;
  color: var(--text-tertiary, #666);
}

.toggle-switch {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  border: none;
  background: var(--bg-tertiary, #1a1a24);
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  padding: 0;
}

.toggle-switch.active {
  background: var(--accent-cyan, #00d4ff);
}

.toggle-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--text-primary, #fff);
  transition: transform 0.2s;
}

.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.loading-state span {
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

/* Monitoring settings */
.monitoring-select {
  width: 100%;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  transition: border-color 0.15s;
}

.monitoring-select:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.monitoring-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.monitoring-no-accounts {
  padding: 1rem;
  text-align: center;
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
}

.monitoring-accounts-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
  overflow: hidden;
}

.monitoring-account-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  transition: background 0.15s;
}

.monitoring-account-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.monitoring-account-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.monitoring-account-name {
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--text-primary, #fff);
}

.monitoring-account-type {
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--bg-secondary, #12121a);
  color: var(--text-tertiary, #666);
}

.toggle-switch-sm {
  width: 36px;
  height: 20px;
  border-radius: 10px;
}

.toggle-switch-sm .toggle-knob {
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
}

.toggle-switch-sm.active .toggle-knob {
  transform: translateX(16px);
}
</style>
