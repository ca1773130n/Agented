<script setup lang="ts">
import { ref, onMounted, inject, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import type { MonitoringConfig } from '../../services/api';
import { settingsApi, monitoringApi, listGroupedBackends, getGroupedBackend, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useTourMachine } from '../../composables/useTourMachine';
import DirectoryBrowser from '../base/DirectoryBrowser.vue';
import { SUPPORTED_LOCALES, setLocale } from '../../i18n';

const { t, locale } = useI18n();

// Language — persisted to localStorage by setLocale and applied app-wide,
// independent of the onboarding picker. Same source of truth (SUPPORTED_LOCALES).
function onLocaleChange(e: Event) {
  const lang = (e.target as HTMLSelectElement).value as 'en' | 'ko' | 'ja' | 'zh';
  setLocale(lang);
}
const showToast = useToast();
const setTourGuide = inject<(msg: string | null) => void>('setTourGuide', () => {});
const tourMachine = useTourMachine();
const settingsRouter = useRouter();

function handleRestartTour(): void {
  tourMachine.restartTour();
  settingsRouter.push('/settings#general');
  tourMachine.startTour();
  tourMachine.nextStep(); // welcome -> workspace (skip welcome since user is already authenticated)
}

// General settings
const workspaceRoot = ref('');
const originalWorkspaceRoot = ref('');
const loadingGeneral = ref(false);
const savingGeneral = ref(false);
const showDirectoryBrowser = ref(false);

// Tour guide — update bottom bar when user interacts with workspace settings
watch(showDirectoryBrowser, (open) => {
  if (open) {
    setTourGuide(t('settings.general.tourGuideBrowse'));
  } else if (tourMachine.isActive.value) {
    setTourGuide(workspaceRoot.value
      ? t('settings.general.tourGuideSet')
      : t('settings.general.tourGuideEnter'));
  }
});

// Marketplace auto-update setting
const marketplaceAutoUpdate = ref(true);
const originalAutoUpdate = ref(true);

// YOLO mode for CLI agent runner. When ON (default), sketches and
// agent-driven flows invoke claude/codex/gemini CLIs directly with
// "skip approvals" flags so agents can use tools end-to-end. When
// OFF, those flows fall back to CLIProxyAPI (pure-token chat, no
// tool privileges).
const yoloMode = ref(true);

// Monitoring settings
const monitoringConfig = ref<MonitoringConfig>({
  enabled: false,
  polling_minutes: 5,
  accounts: {},
});
const originalMonitoringConfig = ref<string>('');
const backendAccounts = ref<Array<{ id: string; account_name: string; backend_type: string }>>([]);
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
    showToast(t('settings.general.toastWorkspaceSaved'), 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.general.toastWorkspaceFailed');
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
    showToast(t('settings.general.toastAutoUpdateSaved'), 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.general.toastSettingFailed');
    showToast(message, 'error');
  }
}

async function loadYoloMode() {
  try {
    const data = await settingsApi.get('agent_yolo_mode');
    // Default ON when the setting hasn't been written yet.
    yoloMode.value = !data.value || data.value !== 'false';
  } catch {
    yoloMode.value = true;
  }
}

async function saveYoloMode() {
  try {
    await settingsApi.set('agent_yolo_mode', String(yoloMode.value));
    showToast(
      yoloMode.value
        ? t('settings.general.toastYoloEnabled')
        : t('settings.general.toastYoloDisabled'),
      'success',
    );
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.general.toastYoloFailed');
    showToast(message, 'error');
    // Revert the optimistic flip so the UI reflects the persisted value.
    yoloMode.value = !yoloMode.value;
  }
}

// Per-session "default yolo" for the start-session dialog (v0.7.57).
// Distinct from ``agent_yolo_mode`` above: that one toggles how
// sketches / agent-driven flows invoke the CLIs; this one only
// controls whether the dialog's yolo toggle is pre-checked when the
// user clicks "Start session" on the project Sessions panel.
const sessionDefaultYolo = ref(false);

async function loadSessionDefaultYolo() {
  try {
    const data = await settingsApi.get('session_default_yolo');
    const raw = (data.value || '').trim().toLowerCase();
    sessionDefaultYolo.value =
      raw === 'true' || raw === '1' || raw === 'yes';
  } catch {
    sessionDefaultYolo.value = false;
  }
}

async function saveSessionDefaultYolo() {
  try {
    await settingsApi.set(
      'session_default_yolo',
      String(sessionDefaultYolo.value),
    );
    showToast(
      sessionDefaultYolo.value
        ? t('settings.general.toastSessionYoloOn')
        : t('settings.general.toastSessionYoloOff'),
      'success',
    );
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.general.toastSettingFailed');
    showToast(message, 'error');
    sessionDefaultYolo.value = !sessionDefaultYolo.value;
  }
}

async function loadMonitoringSettings() {
  loadingMonitoring.value = true;
  try {
    const [configData, backendsData] = await Promise.all([
      monitoringApi.getConfig(),
      listGroupedBackends(),
    ]);
    monitoringConfig.value = {
      enabled: configData.enabled ?? false,
      polling_minutes: configData.polling_minutes ?? 5,
      accounts: configData.accounts ?? {},
    };
    originalMonitoringConfig.value = JSON.stringify(monitoringConfig.value);

    // Load accounts for each backend in parallel
    const backendList = backendsData.backends || [];
    const detailResults = await Promise.all(
      backendList.map((b) => getGroupedBackend(b.id).catch(() => null)),
    );
    const allAccounts: Array<{ id: string; account_name: string; backend_type: string }> = [];
    detailResults.forEach((detail, idx) => {
      if (!detail) return;
      for (const acct of (detail.accounts || [])) {
        allAccounts.push({
          id: acct.id,
          account_name: acct.account_name,
          backend_type: backendList[idx].type,
        });
      }
    });
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
    showToast(t('settings.general.toastMonitoringSaved'), 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('settings.general.toastMonitoringFailed');
    showToast(message, 'error');
  } finally {
    savingMonitoring.value = false;
  }
}

function isMonitoringDirty(): boolean {
  return JSON.stringify(monitoringConfig.value) !== originalMonitoringConfig.value;
}

function toggleAccountMonitoring(accountId: string) {
  const key = String(accountId);
  if (!monitoringConfig.value.accounts[key]) {
    monitoringConfig.value.accounts[key] = { enabled: true };
  } else {
    monitoringConfig.value.accounts[key].enabled = !monitoringConfig.value.accounts[key].enabled;
  }
}

function isAccountEnabled(accountId: string): boolean {
  const key = String(accountId);
  return monitoringConfig.value.accounts[key]?.enabled ?? false;
}

onMounted(() => {
  loadGeneralSettings();
  loadAutoUpdateSetting();
  loadYoloMode();
  loadSessionDefaultYolo();
  loadMonitoringSettings();
});
</script>

<template>
  <div class="tab-content">
    <div class="card">
      <div class="card-header">
        <h3>{{ t('settings.general.languageTitle') }}</h3>
      </div>
      <div class="card-body">
        <div class="form-group">
          <label>{{ t('language.label') }}</label>
          <p class="form-help">{{ t('settings.general.languageHelp') }}</p>
          <select :value="locale" class="monitoring-select" @change="onLocaleChange">
            <option v-for="loc in SUPPORTED_LOCALES" :key="loc.code" :value="loc.code">
              {{ loc.nativeName }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem;" data-tour="workspace-root">
      <div class="card-header">
        <h3>{{ t('settings.general.workspaceTitle') }}</h3>
      </div>
      <div class="card-body">
        <div class="form-group">
          <label>{{ t('settings.general.workspaceRootLabel') }}</label>
          <p class="form-help">{{ t('settings.general.workspaceRootHelp') }}</p>
          <div class="input-with-browse">
            <input
              v-model="workspaceRoot"
              type="text"
              class="form-input"
              :placeholder="t('settings.general.workspaceRootPlaceholder')"
            />
            <button
              type="button"
              class="btn btn-secondary browse-btn"
              @click="showDirectoryBrowser = true"
            >
              {{ t('common.browse') }}
            </button>
          </div>
          <p class="form-hint">{{ t('settings.general.cloneHint') }} <code>{{ workspaceRoot || '{workspace_root}' }}/projects/{project_name}/</code></p>
        </div>
        <div class="form-actions">
          <button
            class="btn btn-primary"
            :disabled="savingGeneral || workspaceRoot === originalWorkspaceRoot"
            @click="saveWorkspaceRoot"
          >
            {{ savingGeneral ? t('settings.general.saving') : t('common.save') }}
          </button>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>{{ t('settings.general.marketplaceTitle') }}</h3>
      </div>
      <div class="card-body">
        <div class="form-group toggle-group">
          <label class="toggle-label">
            <span class="toggle-text">
              <strong>{{ t('settings.general.autoRefreshTitle') }}</strong>
              <span class="toggle-description">{{ t('settings.general.autoRefreshDesc') }}</span>
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

    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>{{ t('settings.general.agentExecutionTitle') }}</h3>
      </div>
      <div class="card-body">
        <div class="form-group toggle-group">
          <label class="toggle-label">
            <span class="toggle-text">
              <strong>{{ t('settings.general.yoloTitle') }}</strong>
              <span class="toggle-description">
                <i18n-t keypath="settings.general.yoloDesc" scope="global">
                  <template #claude><code>claude</code></template>
                  <template #codex><code>codex</code></template>
                  <template #gemini><code>gemini</code></template>
                </i18n-t>
              </span>
            </span>
            <button
              :class="['toggle-switch', { active: yoloMode }]"
              @click="yoloMode = !yoloMode; saveYoloMode()"
            >
              <span class="toggle-knob"></span>
            </button>
          </label>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>{{ t('settings.general.interactiveSessionsTitle') }}</h3>
      </div>
      <div class="card-body">
        <div class="form-group toggle-group">
          <label class="toggle-label">
            <span class="toggle-text">
              <strong>{{ t('settings.general.sessionYoloTitle') }}</strong>
              <span class="toggle-description">
                <i18n-t keypath="settings.general.sessionYoloDesc" scope="global">
                  <template #flag><code>--dangerously-skip-permissions</code></template>
                  <template #claude><code>claude</code></template>
                </i18n-t>
              </span>
            </span>
            <button
              :class="['toggle-switch', { active: sessionDefaultYolo }]"
              @click="
                sessionDefaultYolo = !sessionDefaultYolo;
                saveSessionDefaultYolo()
              "
            >
              <span class="toggle-knob"></span>
            </button>
          </label>
        </div>
      </div>
    </div>

    <!-- Token Monitoring Section -->
    <div class="card" style="margin-top: 1.5rem;" data-tour="token-monitoring">
      <div class="card-header">
        <h3>{{ t('settings.general.tokenMonitoringTitle') }}</h3>
      </div>
      <div class="card-body">
        <div v-if="loadingMonitoring" class="loading-state" style="padding: 1.5rem;">
          <div class="spinner"></div>
          <span>{{ t('settings.general.loadingMonitoring') }}</span>
        </div>

        <template v-else>
          <!-- Enable monitoring toggle -->
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>{{ t('settings.general.enableMonitoringTitle') }}</strong>
                <span class="toggle-description">{{ t('settings.general.enableMonitoringDesc') }}</span>
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
            <label>{{ t('settings.general.pollingPeriodLabel') }}</label>
            <select
              v-model.number="monitoringConfig.polling_minutes"
              :disabled="!monitoringConfig.enabled"
              class="monitoring-select"
            >
              <option :value="1">{{ t('settings.general.pollingEvery1') }}</option>
              <option :value="5">{{ t('settings.general.pollingEvery5') }}</option>
              <option :value="15">{{ t('settings.general.pollingEvery15') }}</option>
              <option :value="30">{{ t('settings.general.pollingEvery30') }}</option>
              <option :value="60">{{ t('settings.general.pollingEvery60') }}</option>
            </select>
            <span class="help-text">{{ t('settings.general.pollingHelp') }}</span>
          </div>

          <!-- Per-account toggles -->
          <div class="form-group" style="margin-top: 1rem;">
            <label>{{ t('settings.general.monitoredAccountsLabel') }}</label>
            <div v-if="backendAccounts.length === 0" class="monitoring-no-accounts">
              {{ t('settings.general.noAccounts') }}
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
              {{ savingMonitoring ? t('settings.general.saving') : t('settings.general.saveMonitoring') }}
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- OB-35a: Restart Setup Guide -->
    <div class="card" style="margin-top: 1.5rem;">
      <div class="card-header">
        <h3>{{ t('settings.general.setupGuideTitle') }}</h3>
      </div>
      <div class="card-body">
        <p class="form-help" style="margin-bottom: 1rem;">
          {{ t('settings.general.setupGuideDesc') }}
        </p>
        <button type="button" class="btn btn-secondary restart-tour-btn" @click="handleRestartTour">
          {{ t('settings.general.restartSetupGuide') }}
        </button>
      </div>
    </div>

    <DirectoryBrowser
      v-model="workspaceRoot"
      :visible="showDirectoryBrowser"
      @close="showDirectoryBrowser = false"
    />
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

/* Input with browse button */
.input-with-browse {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.input-with-browse .form-input {
  flex: 1;
}

.browse-btn {
  padding: 0.6rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
}

/* Restart tour button */
.restart-tour-btn {
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
</style>
