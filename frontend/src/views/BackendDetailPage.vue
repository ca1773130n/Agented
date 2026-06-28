<template>
  <EntityLayout :load-entity="loadBackend" entity-label="backend">
    <template #default="{ reload: _reload }">
  <div class="backend-detail-page">

    <template v-if="backend">
      <PageHeader :title="backend.name" :subtitle="backend.description">
        <template #actions>
          <div class="backend-badges">
            <span class="type-badge">{{ backend.type }}</span>
            <span v-if="backend.version" class="version-badge">v{{ backend.version }}</span>
            <span v-if="backend.is_installed" class="status-badge installed">{{ t('common.installed') }}</span>
            <span v-else class="status-badge not-installed">{{ t('common.notInstalled') }}</span>
          </div>
          <button
            v-if="!backend.is_installed"
            class="btn btn-primary"
            :disabled="isInstalling"
            @click="installCli"
          >
            <div v-if="isInstalling" class="spinner-sm"></div>
            {{ isInstalling ? t('accountWizard.installing') : t('accountWizard.installCli') }}
          </button>
          <button v-if="supportsConnect && backend.is_installed" class="btn btn-primary" @click="loginConfigPath = undefined; proxyOnlyLogin = false; showLoginModal = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
              <polyline points="10 17 15 12 10 7"/>
              <line x1="15" y1="12" x2="3" y2="12"/>
            </svg>
            {{ t('backendDetail.login') }}
          </button>
          <button v-if="supportsConnect" class="btn btn-outline" @click="loginConfigPath = undefined; proxyOnlyLogin = true; showLoginModal = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            {{ t('backendDetail.proxyLogin') }}
          </button>
          <a v-if="backend.documentation_url" :href="backend.documentation_url" target="_blank" class="btn btn-outline">
            {{ t('backendDetail.documentation') }}
          </a>
          <a v-if="loginInfo" :href="loginInfo.url" target="_blank" class="btn btn-outline">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            {{ loginInfo.label }}
          </a>
        </template>
      </PageHeader>

      <BackendInfoSection
        :models="backend.models || []"
        :capability-list="capabilityList"
        :cli-path="cliPath"
        :backend-kind="backend.type"
      />

      <!-- Inline Connect Terminal -->
      <div v-if="showConnect && backend" class="connect-section">
        <BackendConnect
          :backend-id="backend.id"
          :backend-type="backend.type"
          @close="showConnect = false"
          @connected="onConnected"
        />
      </div>

      <!-- OpenCode cross-backend accounts -->
      <BackendCrossAccountsList v-if="isOpenCode" :groups="otherBackendAccounts" />

      <div class="accounts-section">
        <div class="section-header">
          <h2>{{ isOpenCode ? t('backendDetail.openCodeAccounts') : t('backendDetail.accounts') }}</h2>
          <button v-if="!isOpenCode" class="btn btn-primary" data-tour="add-account-btn" @click="showAddModal = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            {{ t('backendDetail.addAccount') }}
          </button>
        </div>

        <!-- Account Wizard (for adding new accounts) -->
        <!-- Sourced from @ai-accounts/vue-styled 0.3.0-alpha.1. -->
        <AccountWizard
          v-if="showAddModal && !editingAccount && backend"
          :initial-backend-kind="legacyIdToKind(backend.type)"
          :backend-name="backend.name"
          :translate="wizardTranslate"
          @close="closeModal"
          @saved="onWizardSaved"
          @skip="onWizardSkip"
          @done="onWizardDone"
          @add-another="onWizardAddAnother"
        />

        <!-- Inline Edit Account Form (editing existing accounts) -->
        <div v-if="editingAccount" class="inline-account-form">
          <div class="inline-form-header">
            <h3>{{ t('backendDetail.editForm.title') }}</h3>
            <button class="btn-close" :aria-label="t('common.close')" @click="closeModal">&times;</button>
          </div>
          <form @submit.prevent="saveAccount">
            <div class="form-group">
              <label for="edit_account_name">{{ t('backendDetail.editForm.accountNameLabel') }}</label>
              <input
                id="edit_account_name"
                v-model="accountForm.account_name"
                type="text"
                required
                :placeholder="t('backendDetail.editForm.accountNamePlaceholder')"
              />
            </div>
            <div class="form-group">
              <label for="edit_email">{{ t('backendDetail.editForm.emailLabel') }}</label>
              <input
                id="edit_email"
                v-model="accountForm.email"
                type="email"
                :placeholder="t('backendDetail.editForm.emailPlaceholder')"
              />
              <small>{{ t('backendDetail.editForm.emailHint') }}</small>
            </div>
            <div class="form-group">
              <label for="edit_config_path">{{ t('backendDetail.editForm.configPathLabel') }}</label>
              <input
                id="edit_config_path"
                v-model="accountForm.config_path"
                type="text"
                :placeholder="t('backendDetail.editForm.configPathPlaceholder')"
              />
              <small>{{ t('backendDetail.editForm.configPathHint') }}</small>
            </div>
            <div class="form-group">
              <label for="edit_api_key_env">{{ t('backendDetail.editForm.apiKeyEnvLabel') }}</label>
              <input
                id="edit_api_key_env"
                v-model="accountForm.api_key_env"
                type="text"
                :placeholder="t('backendDetail.editForm.apiKeyEnvPlaceholder')"
              />
              <small>{{ t('backendDetail.editForm.apiKeyEnvHint') }}</small>
            </div>
            <div v-if="planOptions.length > 0" class="form-group">
              <label for="edit_plan">{{ t('backendDetail.editForm.planLabel') }}</label>
              <select id="edit_plan" v-model="accountForm.plan">
                <option value="">{{ t('backendDetail.editForm.selectPlan') }}</option>
                <option v-for="opt in planOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <template v-if="backend?.type === 'codex'">
              <div class="form-group">
                <label for="edit_reasoning_level">{{ t('backendDetail.editForm.reasoningLabel') }}</label>
                <select id="edit_reasoning_level" v-model="codexSettings.reasoning_level">
                  <option value="">{{ t('backendDetail.editForm.levelDefault') }}</option>
                  <option value="low">{{ t('backendDetail.editForm.levelLow') }}</option>
                  <option value="medium">{{ t('backendDetail.editForm.levelMedium') }}</option>
                  <option value="high">{{ t('backendDetail.editForm.levelHigh') }}</option>
                </select>
                <small>{{ t('backendDetail.editForm.reasoningHint') }}</small>
              </div>
              <div class="form-group">
                <label for="edit_summary_level">{{ t('backendDetail.editForm.summaryLabel') }}</label>
                <select id="edit_summary_level" v-model="codexSettings.summary_level">
                  <option value="">{{ t('backendDetail.editForm.levelDefault') }}</option>
                  <option value="concise">{{ t('backendDetail.editForm.summaryConcise') }}</option>
                  <option value="detailed">{{ t('backendDetail.editForm.summaryDetailed') }}</option>
                </select>
                <small>{{ t('backendDetail.editForm.summaryHint') }}</small>
              </div>
            </template>
            <div class="form-group checkbox">
              <label>
                <input type="checkbox" v-model="accountForm.is_default" />
                {{ t('backendDetail.editForm.setDefault') }}
              </label>
            </div>
            <div class="inline-form-actions">
              <button type="button" class="btn btn-secondary" @click="closeModal">{{ t('common.cancel') }}</button>
              <button type="submit" class="btn btn-primary" :disabled="isSaving">
                {{ isSaving ? t('backendDetail.editForm.saving') : t('backendDetail.editForm.update') }}
              </button>
            </div>
          </form>
        </div>

        <BackendAccountList
          :accounts="backend.accounts || []"
          :is-open-code="isOpenCode"
          :is-installed="!!backend.is_installed"
          :supports-connect="supportsConnect"
          :backend-type="backend.type"
          :rate-limit-state="rateLimitState"
          :get-account-health="getAccountHealth"
          :format-cooldown="formatCooldown"
          :format-relative-time="formatRelativeTime"
          :get-rate-limit-color="getRateLimitColor"
          @login="onAccountLogin"
          @edit="editAccount"
          @delete="deleteAccount"
          @check-rate-limits="checkAccountRateLimits"
          @clear-rate-limit="clearRateLimit"
        />
      </div>
    </template>

    <ConfirmModal
      :open="showDeleteAccountConfirm"
      :title="t('backendDetail.deleteAccount')"
      :message="t('backendDetail.confirmDeleteAccount')"
      :confirm-label="t('common.delete')"
      variant="danger"
      @confirm="confirmDeleteAccount"
      @cancel="showDeleteAccountConfirm = false"
    />

    <AccountLoginModal
      v-if="backend"
      :open="showLoginModal"
      :backend-id="backend.id"
      :backend-type="backend.type"
      :backend-name="backend.name"
      :config-path="loginConfigPath"
      :proxy-only="proxyOnlyLogin"
      @close="showLoginModal = false"
      @success="onLoginModalSuccess"
    />

    <!-- v0.6.4: blocking overlay between "Move on to next backend" click
         and the next-page navigation. Without this, the page sits on the
         current backend's view (with the wizard's data-tour markers still
         attached) for a perceptible moment after the click — operators
         think the click was lost and click again. -->
    <div v-if="isAdvancing" class="advancing-overlay" data-tour="advancing-overlay">
      <div class="advancing-overlay__card">
        <div class="advancing-overlay__spinner"></div>
        <div class="advancing-overlay__text">{{ t('backendDetail.movingToNext', 'Moving to the next backend…') }}</div>
      </div>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, inject } from 'vue';
import { useRoute } from 'vue-router';
import { backendManagementApi, legacyIdToKind, listGroupedBackends, getGroupedBackend, orchestrationApi, BACKEND_LOGIN_INFO, BACKEND_PLAN_OPTIONS, type AIBackendWithAccounts, type BackendAccount, type AccountHealth, type BackendCapabilities, type RateLimitWindow } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import BackendConnect from '../components/monitoring/BackendConnect.vue';
import AccountLoginModal from '../components/monitoring/AccountLoginModal.vue';
import BackendInfoSection from '../components/monitoring/BackendInfoSection.vue';
import BackendCrossAccountsList from '../components/monitoring/BackendCrossAccountsList.vue';
import BackendAccountList from '../components/monitoring/BackendAccountList.vue';
import { AccountWizard } from '@ai-accounts/vue-styled';
import { useAiAccounts } from '@ai-accounts/vue-headless';
import { useI18n } from 'vue-i18n';
import { useTourMachine } from '../composables/useTourMachine';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { handleApiError } from '../services/api/error-handler';
import { useWebMcpTool } from '../composables/useWebMcpTool';

// Use the plugin-provided client (wired with the API token in main.ts) so
// inline updateBackend / deleteBackend calls don't 401 against the sidecar's
// ApiKeyAuth guard.
const aiAccountsClient = useAiAccounts().client;

// Bridge ai-accounts AccountWizard's translator to vue-i18n. Falls back to
// the English stub baked into the wizard when a key is missing.
const { t, te } = useI18n();
function wizardTranslate(key: string, params?: Record<string, unknown>): string {
  if (te(key)) return t(key, params ?? {});
  return '';
}

const route = useRoute();
const backendId = computed(() => route.params.backendId as string);

const backend = ref<AIBackendWithAccounts | null>(null);

const tourMachine = useTourMachine();

const showAddModal = ref(false);
const editingAccount = ref<BackendAccount | null>(null);
const isSaving = ref(false);
// v0.6.4: blocking overlay shown while the tour advances to the next
// backend. Cleared automatically by the route-change watch below;
// also has a 4s safety timeout in case the tour finishes (no more
// backends) and never navigates.
const isAdvancing = ref(false);
let advancingTimeout: ReturnType<typeof setTimeout> | null = null;

// OB-44: Signal tour overlay when any account form/modal is open
const setTourModalOpen = inject<(open: boolean) => void>('setTourModalOpen', () => {});
watch([showAddModal, editingAccount], ([addOpen, editing]) => {
  setTourModalOpen(addOpen || editing !== null);
});

// Account edit form state
const accountForm = ref({
  account_name: '',
  email: '',
  config_path: '',
  api_key_env: '',
  plan: '',
  is_default: false,
});
const codexSettings = ref({
  reasoning_level: '',
  summary_level: '',
});

const planOptions = computed(() => {
  if (!backend.value) return [];
  return BACKEND_PLAN_OPTIONS[backend.value.type] || [];
});

const showToast = useToast();

// Account health state (keyed by ai-accounts bkd-* id)
const healthMap = ref<Map<string, AccountHealth>>(new Map());
const now = ref(Date.now());
let clockTimer: ReturnType<typeof setInterval> | null = null;

// Login modal state
const showLoginModal = ref(false);
const loginConfigPath = ref<string | undefined>(undefined);
const proxyOnlyLogin = ref(false);

// Install state
const isInstalling = ref(false);

async function installCli() {
  if (isInstalling.value || !backend.value) return;
  isInstalling.value = true;
  showToast?.(t('backendDetail.toast.installing', { name: backend.value.name }), 'info');
  try {
    const result = await backendManagementApi.installCli(backendId.value);
    showToast?.(result.message || t('backendDetail.toast.installed'), 'success');
    await loadBackend();
  } catch (e: unknown) {
    showToast?.(e instanceof Error ? e.message : t('backendDetail.toast.installFailed'), 'error');
  } finally {
    isInstalling.value = false;
  }
}

// Connect state
const showConnect = ref(false);

// Rate limit state per account (keyed by ai-accounts bkd-* id)
const rateLimitState = ref<Record<string, { loading: boolean; windows: RateLimitWindow[]; error: string | null }>>({});

// Capabilities state
const capabilities = ref<BackendCapabilities | null>(null);
const cliPath = ref<string | null>(null);

// Confirm delete account state (account id is an ai-accounts bkd-* string)
const showDeleteAccountConfirm = ref(false);
const pendingDeleteAccountId = ref<string | null>(null);

const capabilityList = computed(() => {
  const caps = capabilities.value;
  if (!caps) return [];
  return [
    { label: t('aIBackends.capJsonOutput'), supported: caps.supports_json_output, flag: caps.json_output_flag || null },
    { label: t('aIBackends.capTokenUsage'), supported: caps.supports_token_usage, flag: null },
    { label: t('aIBackends.capStreaming'), supported: caps.supports_streaming, flag: null },
    { label: t('aIBackends.capNonInteractive'), supported: caps.supports_non_interactive, flag: caps.non_interactive_flag || null },
  ];
});

// OpenCode cross-backend accounts
const otherBackendAccounts = ref<{ backend_name: string; backend_type: string; accounts: BackendAccount[] }[]>([]);

useWebMcpTool({
  name: 'agented_backend_detail_get_state',
  description: 'Returns the current state of the BackendDetailPage',
  page: 'BackendDetailPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'BackendDetailPage',
        backendId: backend.value?.id ?? null,
        backendName: backend.value?.name ?? null,
        backendType: backend.value?.type ?? null,
        isSaving: isSaving.value,
        isInstalled: backend.value?.is_installed ?? null,
        accountCount: backend.value?.accounts?.length ?? 0,
        showConnect: showConnect.value,
        showAddModal: showAddModal.value,
      }),
    }],
  }),
  deps: [backend, isSaving, showConnect, showAddModal],
});

const isOpenCode = computed(() => backend.value?.type === 'opencode');

const loginInfo = computed(() => {
  if (!backend.value) return null;
  return BACKEND_LOGIN_INFO[backend.value.type] || null;
});


async function loadBackend() {
  try {
    const data = await getGroupedBackend(backendId.value);
    backend.value = data;
    // Fire-and-forget: load supplementary data (models, health, cross-backend accounts)
    loadHealth();
    if (data?.type === 'opencode') {
      loadOtherBackendAccounts();
    }
    // getGroupedBackend now skips model discovery (spawns CLI subprocess).
    // Fetch models in the background so the page renders without blocking
    // on a potentially slow CLI call — matters for onboarding tour timing.
    if (data && data.type !== 'opencode') {
      backendManagementApi
        .discoverModels(backendId.value)
        .then((result) => {
          if (backend.value && result.models?.length) {
            backend.value = { ...backend.value, models: result.models };
          }
        })
        .catch(() => { /* model discovery is optional */ });
    }
    return data;
  } catch (err) {
    handleApiError(err, showToast, t('backendDetail.toast.loadFailed'));
    throw err;
  }
}


function editAccount(account: BackendAccount) {
  editingAccount.value = account;
  const ud = (account.usage_data || {}) as Record<string, string>;
  accountForm.value = {
    account_name: account.account_name,
    email: account.email || '',
    config_path: account.config_path || '',
    api_key_env: account.api_key_env || '',
    plan: account.plan || '',
    is_default: !!account.is_default,
  };
  codexSettings.value = {
    reasoning_level: ud.reasoning_level || '',
    summary_level: ud.summary_level || '',
  };
}

function closeModal() {
  showAddModal.value = false;
  editingAccount.value = null;
  accountForm.value = {
    account_name: '',
    email: '',
    config_path: '',
    api_key_env: '',
    plan: '',
    is_default: false,
  };
  codexSettings.value = { reasoning_level: '', summary_level: '' };
}

async function onWizardSaved() {
  showToast?.(t('backendDetail.toast.saved'), 'success');
  await loadBackend();
}

// Route-param snapshot at click time. We hold the overlay until BOTH
// the URL has moved off this id AND backend.value has caught up to
// the new URL. Watching backend.value.id alone failed: it could flip
// before route.params settled, or the user could see the previous
// page's content briefly under the overlay before the new content
// rendered.
const advancingFromId = ref<string | null>(null);

function startAdvancingOverlay() {
  isAdvancing.value = true;
  advancingFromId.value = backendId.value ?? backend.value?.id ?? null;
  if (advancingTimeout) clearTimeout(advancingTimeout);
  // Safety timeout — covers tour-ended (no more backends, navigation
  // never happens) and network stalls. 15s comfortably exceeds the
  // worst-case sidecar+backend round-trip plus the model-discovery
  // background task that follows loadBackend().
  advancingTimeout = setTimeout(() => {
    isAdvancing.value = false;
    advancingFromId.value = null;
    advancingTimeout = null;
  }, 15000);
}

function onWizardSkip() {
  showAddModal.value = false;
  showToast?.(t('backendDetail.toast.skipped'), 'info');
  startAdvancingOverlay();
  tourMachine.nextStep();
}

function onWizardDone() {
  closeModal();
  startAdvancingOverlay();
  tourMachine.nextStep();
}

// Hold the overlay up until the new backend's page is FULLY visible.
// Three preconditions must ALL hold before we begin the release:
//   a) route.params.backendId differs from the snapshotted from-id
//      → the URL has moved to the next backend
//   b) backend.value !== null
//      → loadBackend() has resolved (not still awaiting the network)
//   c) backend.value.id === backendId.value
//      → the loaded data matches the current route (not the stale
//         previous backend's data still sitting in the ref)
//
// Once all three hold, wait for: Vue's DOM patch (flush:'post'),
// double requestAnimationFrame (browser paint), and a 600ms settle
// for subscoped reactive updates (account list, health badges,
// model-discovery follow-up). 600ms is intentionally generous —
// operators reported the previous 250ms releasing before they
// perceived the new page.
function _waitForPaint(): Promise<void> {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  });
}

const _readyForRelease = computed(() => {
  if (!isAdvancing.value) return false;
  if (!advancingFromId.value) return false;
  const routeId = backendId.value;
  if (!routeId || routeId === advancingFromId.value) return false;
  const data = backend.value;
  if (!data || !data.id) return false;
  return data.id === routeId;
});

watch(
  _readyForRelease,
  async (ready) => {
    if (!ready) return;
    await _waitForPaint();
    await new Promise((r) => setTimeout(r, 600));
    // Re-check after the long wait — advancing may have been cancelled
    // (e.g. user navigated away) or the route may have changed again.
    if (!isAdvancing.value) return;
    if (!_readyForRelease.value) return;
    isAdvancing.value = false;
    advancingFromId.value = null;
    if (advancingTimeout) {
      clearTimeout(advancingTimeout);
      advancingTimeout = null;
    }
  },
  { flush: 'post' },
);

onUnmounted(() => {
  if (advancingTimeout) clearTimeout(advancingTimeout);
});

function onWizardAddAnother() {
  // Wizard handles its own reset; just reload backend data
  loadBackend();
}

async function saveAccount() {
  if (!editingAccount.value) return;
  isSaving.value = true;
  try {
    const config: Record<string, unknown> = {};
    if (accountForm.value.email) config.email = accountForm.value.email;
    if (accountForm.value.config_path) config.config_path = accountForm.value.config_path;
    if (accountForm.value.api_key_env) config.api_key_env = accountForm.value.api_key_env;
    if (accountForm.value.plan) config.plan = accountForm.value.plan;
    config.is_default = !!accountForm.value.is_default;
    if (backend.value?.type === 'codex') {
      const usage: Record<string, string> = {};
      if (codexSettings.value.reasoning_level) usage.reasoning_level = codexSettings.value.reasoning_level;
      if (codexSettings.value.summary_level) usage.summary_level = codexSettings.value.summary_level;
      if (Object.keys(usage).length > 0) config.usage_data = usage;
    }
    await aiAccountsClient.updateBackend(editingAccount.value.id, {
      display_name: accountForm.value.account_name,
      config,
    });
    showToast?.(t('backendDetail.toast.updated'), 'success');
    closeModal();
    await loadBackend();
  } catch (err) {
    showToast?.(err instanceof Error ? err.message : t('backendDetail.toast.saveFailed'), 'error');
  } finally {
    isSaving.value = false;
  }
}

function deleteAccount(accountId: string) {
  pendingDeleteAccountId.value = accountId;
  showDeleteAccountConfirm.value = true;
}

async function confirmDeleteAccount() {
  const accountId = pendingDeleteAccountId.value;
  showDeleteAccountConfirm.value = false;
  pendingDeleteAccountId.value = null;
  if (accountId === null) return;
  try {
    await aiAccountsClient.deleteBackend(accountId);
    await loadBackend();
  } catch (err) {
    showToast?.(t('backendDetail.toast.deleteFailed'), 'error');
  }
}

async function loadHealth() {
  try {
    const data = await orchestrationApi.getHealth();
    const map = new Map<string, AccountHealth>();
    for (const acct of (data.accounts || [])) {
      map.set(acct.account_id, acct);
    }
    healthMap.value = map;
  } catch {
    // Health data is supplementary -- don't block on failure
  }
}

function getAccountHealth(accountId: string): AccountHealth | undefined {
  return healthMap.value.get(accountId);
}

function formatCooldown(health: AccountHealth): string {
  if (!health.rate_limited_until) return 'Unknown';
  const until = new Date(health.rate_limited_until).getTime();
  const remaining = Math.max(0, Math.floor((until - now.value) / 1000));
  if (remaining <= 0) return 'Expiring...';
  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
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

async function clearRateLimit(accountId: string) {
  try {
    await orchestrationApi.clearRateLimit(accountId);
    showToast?.(t('backendDetail.toast.rateLimitCleared'), 'success');
    await loadHealth();
  } catch {
    showToast?.(t('backendDetail.toast.rateLimitClearFailed'), 'error');
  }
}

const supportsConnect = computed(() => {
  if (!backend.value) return false;
  return !!BACKEND_LOGIN_INFO[backend.value.type]?.loginCommand;
});

function onConnected() {
  showConnect.value = false;
  showToast?.(t('backendDetail.toast.loginSuccess'), 'success');
  loadBackend();
}

function onLoginModalSuccess() {
  showLoginModal.value = false;
  showToast?.(t('backendDetail.toast.loginSuccess'), 'success');
  loadBackend();
}

function onAccountLogin(payload: { account: BackendAccount; proxyOnly: boolean }) {
  loginConfigPath.value = payload.account.config_path || undefined;
  proxyOnlyLogin.value = payload.proxyOnly;
  showLoginModal.value = true;
}

async function checkAccountRateLimits(accountId: string) {
  rateLimitState.value[accountId] = { loading: true, windows: [], error: null };
  try {
    const result = await backendManagementApi.checkRateLimits(backendId.value, accountId);
    if (result.needs_login && supportsConnect.value && backend.value?.is_installed) {
      // Auto-trigger login for this account
      const account = backend.value?.accounts?.find((a: BackendAccount) => a.id === accountId);
      if (account) {
        loginConfigPath.value = account.config_path || undefined;
        showLoginModal.value = true;
      }
      rateLimitState.value[accountId] = { loading: false, windows: [], error: null };
      return;
    }
    rateLimitState.value[accountId] = {
      loading: false,
      windows: result.windows || [],
      error: result.windows?.length ? null : (result.message || 'No rate limit data'),
    };
  } catch {
    rateLimitState.value[accountId] = {
      loading: false,
      windows: [],
      error: 'Failed to check rate limits',
    };
  }
}

function getRateLimitColor(pct: number): string {
  if (pct >= 90) return 'var(--accent-crimson)';
  if (pct >= 75) return 'var(--accent-amber)';
  if (pct >= 50) return 'var(--accent-cyan)';
  return 'var(--accent-emerald)';
}

async function loadOtherBackendAccounts() {
  try {
    const { backends } = await listGroupedBackends();
    const results: typeof otherBackendAccounts.value = [];
    for (const b of backends) {
      if (b.type === 'opencode') continue;
      const detail = await getGroupedBackend(b.id);
      if (detail.accounts?.length) {
        results.push({
          backend_name: b.name,
          backend_type: b.type,
          accounts: detail.accounts,
        });
      }
    }
    otherBackendAccounts.value = results;
  } catch {
    // Non-critical — don't block the page
  }
}

onMounted(() => {
  clockTimer = setInterval(() => { now.value = Date.now(); }, 1000);
});

onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
});
</script>

<style scoped>
.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.backend-detail-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.backend-badges {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.type-badge {
  padding: 0.25rem 0.75rem;
  background: var(--bg-tertiary);
  border-radius: 20px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.version-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-badge.installed {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.not-installed {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.accounts-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
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

/* Inline Account Form */
.inline-account-form {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.inline-form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.inline-form-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.btn-close:hover {
  color: var(--text-primary);
}

.inline-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

.form-group input[type="text"],
.form-group input[type="email"] {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--primary-color);
}

.form-group small {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.form-group.checkbox label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.form-group.checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

/* Buttons */

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

/* Login banner in inline form */
.login-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  margin-bottom: 1rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--primary-color);
  border-radius: 6px;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.login-banner a {
  color: var(--primary-color);
  text-decoration: none;
  font-weight: 500;
}

.login-banner a:hover {
  text-decoration: underline;
}

.banner-icon {
  display: flex;
  align-items: center;
  color: var(--primary-color);
  flex-shrink: 0;
}

.login-banner code {
  padding: 0.125rem 0.375rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.75rem;
}

/* Advanced toggle link */
.advanced-toggle {
  text-align: right;
  margin-top: -0.75rem;
  margin-bottom: 1rem;
}

.btn-link {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  font-family: inherit;
}

.btn-link:hover {
  color: var(--text-secondary);
}

/* Connect section */
.connect-section {
  margin-bottom: 1rem;
  animation: fadeIn 0.3s ease;
}

/* v0.6.4: blocking overlay during tour transitions. */
.advancing-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  /* Block clicks below. */
  pointer-events: auto;
  backdrop-filter: blur(2px);
}
.advancing-overlay__card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem 1.75rem;
  background: var(--surface-1, #1f1f1f);
  border: 1px solid var(--border, #333);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.advancing-overlay__spinner {
  width: 24px;
  height: 24px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: var(--accent, #4a9eff);
  border-radius: 50%;
  animation: aia-advance-spin 0.8s linear infinite;
}
@keyframes aia-advance-spin {
  to { transform: rotate(360deg); }
}
.advancing-overlay__text {
  color: var(--text, #fff);
  font-weight: 500;
  font-size: 0.95rem;
}

</style>
