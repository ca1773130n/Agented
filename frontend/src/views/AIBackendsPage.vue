<template>
  <PageLayout >
    <PageHeader :title="t('aIBackends.title')" :subtitle="t('aIBackends.subtitle')">
      <template #actions>
        <button
          class="btn btn-ghost upgrade-cliproxy-btn"
          :disabled="isUpgradingCliproxy"
          data-testid="upgrade-cliproxy-btn"
          :title="isUpgradingCliproxy ? t('aIBackends.upgradeInProgress') : t('aIBackends.upgradeCliproxyTooltip')"
          @click="upgradeCliproxy"
        >
          <svg v-if="!isUpgradingCliproxy" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline points="23 4 23 10 17 10"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/>
          </svg>
          <div v-else class="spinner-sm spinner-sm-dark"></div>
          {{ isUpgradingCliproxy ? t('aIBackends.upgrading') : t('aIBackends.upgradeCliproxy') }}
        </button>
        <button
          class="btn btn-secondary detect-btn"
          :disabled="isDetecting"
          data-testid="detect-existing-btn"
          @click="openDetectModal"
        >
          <svg v-if="!isDetecting" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <div v-else class="spinner-sm spinner-sm-dark"></div>
          {{ isDetecting ? t('aIBackends.detecting') : t('aIBackends.detectExisting') }}
        </button>
        <button
          class="btn btn-primary add-account-btn"
          :disabled="isAddingAccount"
          @click="addProxyAccount"
        >
          <svg v-if="!isAddingAccount" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          <div v-else class="spinner-sm"></div>
          {{ isAddingAccount ? t('aIBackends.loggingIn') : t('aIBackends.addAccount') }}
        </button>
      </template>
    </PageHeader>

    <!-- v0.7.93 — flag accounts that have no OAuth token resolvable
         from local keychain/config. Placed OUTSIDE the
         loading/error/empty v-if chain (a v-if sibling between
         v-if and v-else-if would orphan the rest of the chain and
         prevent the grid from ever rendering). The banner self-
         hides when there are no missing credentials. -->
    <CredentialStatusBanner />

    <!-- CLIProxy auth health: warm tokens are silent; only surfaces accounts that
         are expiring/expired/need a re-login (or the proxy being unreachable).
         Re-auth reuses the OAuth proxy-login flow. -->
    <div
      v-if="proxyAuthAttention.length > 0"
      class="proxy-auth-banner"
      :class="proxyAuth?.summary.worst_state"
      role="status"
    >
      <div class="proxy-auth-head">
        <strong>{{ t('aIBackends.proxyAuthTitle') }}</strong>
        <span class="proxy-auth-worst">{{ t(`aIBackends.authState.${proxyAuth?.summary.worst_state}`) }}</span>
      </div>
      <ul class="proxy-auth-list">
        <li v-for="a in proxyAuthAttention" :key="a.type + a.email">
          <span class="proxy-auth-acct">{{ a.type }} · {{ a.email || t('aIBackends.none') }}</span>
          <span class="proxy-auth-state" :class="a.auth_state">{{ t(`aIBackends.authState.${a.auth_state}`) }}</span>
        </li>
      </ul>
      <button
        type="button"
        class="btn btn-sm btn-outline"
        :disabled="isAddingAccount"
        @click="addProxyAccount"
      >
        {{ isAddingAccount ? t('aIBackends.toastOpeningOauth') : t('aIBackends.proxyReauth') }}
      </button>
    </div>

    <LoadingState v-if="isLoading" :message="t('aIBackends.loadingBackends')" />

    <ErrorState v-else-if="error" :message="error" @retry="loadBackends()" />

    <EmptyState
      v-else-if="backends.length === 0"
      :title="t('aIBackends.emptyTitle')"
      :description="t('aIBackends.emptyDescription')"
    >
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09"/>
        </svg>
      </template>
      <template #actions>
        <button
          class="btn btn-primary"
          :disabled="isDetecting"
          data-testid="detect-existing-empty-btn"
          @click="openDetectModal"
        >
          {{ isDetecting ? t('aIBackends.detecting') : t('aIBackends.detectExistingLogins') }}
        </button>
      </template>
    </EmptyState>

    <div v-else class="backends-grid" data-tour="ai-backends">
      <div
        v-for="backend in backends"
        :key="backend.id"
        class="backend-card"
        :class="{ disabled: !backend.is_installed }"
        @click="router.push({ name: 'backend-detail', params: { backendId: backend.id } })"
      >
        <div class="backend-header">
          <div class="backend-icon" :class="backend.type">
            <svg v-if="backend.type === 'claude'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
            </svg>
            <svg v-else-if="backend.type === 'codex'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l9.196 5.308v10.616L12 23.232l-9.196-5.308V7.308z"/>
            </svg>
            <svg v-else-if="backend.type === 'gemini'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l3.09 6.26L22 12l-6.91 3.74L12 22l-3.09-6.26L2 12l6.91-3.74z"/>
            </svg>
            <svg v-else-if="backend.type === 'opencode'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            <span v-else>{{ backend.name[0] }}</span>
          </div>
          <div class="backend-info">
            <h3>{{ backend.name }}</h3>
            <span class="backend-type-label">{{ parseVersion(backend.version) || backend.type }}</span>
          </div>
          <div class="backend-status-area">
            <span class="backend-status" :class="{ installed: backend.is_installed }">
              {{ backend.is_installed ? t('common.installed') : t('common.notInstalled') }}
            </span>
            <button
              v-if="!backend.is_installed"
              class="btn btn-install"
              :disabled="installingBackend === backend.id"
              @click.stop="installBackendCli(backend)"
            >
              <div v-if="installingBackend === backend.id" class="spinner-sm"></div>
              {{ installingBackend === backend.id ? t('aIBackends.installing') : t('aIBackends.install') }}
            </button>
          </div>
        </div>

        <div class="backend-meta">
          <div v-if="backend.models?.length" class="meta-item">
            <span class="meta-label">{{ t('aIBackends.metaModels') }}</span>
            <span class="meta-value">
              <span v-for="model in backend.models" :key="model" class="model-pill">{{ model }}</span>
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">{{ t('aIBackends.metaAccounts') }}</span>
            <span class="meta-value account-badge" :class="{ 'has-accounts': (backend.account_count ?? 0) > 0 }">
              {{ (backend.account_count ?? 0) > 0 ? backend.account_count : t('aIBackends.none') }}
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">{{ t('aIBackends.metaLastUsed') }}</span>
            <span class="meta-value">{{ formatLastUsed(backend.last_used_at) }}</span>
          </div>
          <div v-if="getCapabilityTags(backend.id).length > 0" class="meta-item">
            <span class="meta-label">{{ t('aIBackends.metaCapabilities') }}</span>
            <span class="meta-value">
              <span v-for="tag in getCapabilityTags(backend.id)" :key="tag" class="capability-pill">{{ tag }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="showDetectModal"
        class="modal-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detect-modal-title"
        tabindex="-1"
        data-testid="detect-modal"
        @click.self="closeDetectModal"
        @keydown.escape="closeDetectModal"
      >
        <div class="modal detect-modal">
          <div class="modal-header">
            <h2 id="detect-modal-title">{{ t('aIBackends.detectedLoginsTitle') }}</h2>
            <button
              type="button"
              class="modal-close-btn"
              :aria-label="t('common.close')"
              data-testid="detect-modal-close"
              @click="closeDetectModal"
            >×</button>
          </div>

          <div class="modal-body">
            <div v-if="isDetecting" class="detect-loading">
              <div class="spinner-md"></div>
              <p>{{ t('aIBackends.probingClis') }}</p>
            </div>

            <div
              v-else-if="discoveredItems.length === 0"
              class="detect-empty"
              data-testid="detect-empty"
            >
              <p><strong>{{ t('aIBackends.nothingFound') }}</strong></p>
              <p>{{ t('aIBackends.installCliHintPre') }} <code>claude</code>, <code>codex</code>, <code>gemini</code>, {{ t('aIBackends.installCliHintOr') }} <code>opencode</code> {{ t('aIBackends.installCliHintPost') }}</p>
            </div>

            <ul v-else class="detect-list" data-testid="detect-list">
              <li
                v-for="item in discoveredItems"
                :key="item.kind + ':' + item.path"
                class="detect-row"
                :data-testid="`detect-row-${item.kind}`"
              >
                <div class="detect-row-main">
                  <span class="kind-badge" :class="`kind-${item.kind}`">{{ item.kind }}</span>
                  <div class="detect-row-text">
                    <div class="detect-name">{{ item.suggested_name }}</div>
                    <div class="detect-path" :title="item.path">{{ item.path }}</div>
                  </div>
                </div>
                <div class="detect-row-side">
                  <span
                    class="login-badge"
                    :class="{ ok: item.is_logged_in, bad: !item.is_logged_in }"
                    :title="item.error ?? undefined"
                    :aria-label="item.error ?? undefined"
                  >
                    {{ item.is_logged_in ? t('aIBackends.loggedIn') : t('aIBackends.notLoggedIn') }}
                  </span>
                  <span
                    v-if="item.backend_id"
                    class="already-imported-badge"
                    data-testid="already-imported"
                  >{{ t('aIBackends.alreadyImported') }}</span>
                  <button
                    v-else-if="item.is_logged_in"
                    type="button"
                    class="btn btn-primary btn-sm"
                    :disabled="importingPath === item.path"
                    :data-testid="`detect-import-${item.kind}`"
                    @click="importItem(item)"
                  >
                    <div v-if="importingPath === item.path" class="spinner-sm"></div>
                    {{ importingPath === item.path ? t('aIBackends.importing') : t('aIBackends.import') }}
                  </button>
                  <span v-else class="not-logged-hint">{{ t('aIBackends.loginRequired') }}</span>
                </div>
              </li>
            </ul>
          </div>

          <div class="modal-actions">
            <button
              type="button"
              class="btn btn-secondary"
              :disabled="isDetecting"
              data-testid="detect-rescan"
              @click="rescan"
            >{{ t('aIBackends.rescan') }}</button>
            <button
              type="button"
              class="btn btn-secondary"
              @click="closeDetectModal"
            >{{ t('common.close') }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <div class="test-panel-section">
      <div class="section-header">
        <h2>{{ t('aIBackends.testBackend') }}</h2>
        <p class="subtitle">{{ t('aIBackends.testBackendSubtitle') }}</p>
      </div>
      <div class="test-chat-container">
        <AiChatPanel
          density="detailed"
          :welcome-title="t('aIBackends.testWelcomeTitle')"
          :placeholder="t('aIBackends.testPlaceholder')"
        />
      </div>
    </div>
  </PageLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { backendManagementApi, listGroupedBackends, type AIBackend, type BackendCapabilities } from '../services/api';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import CredentialStatusBanner from '../components/credentials/CredentialStatusBanner.vue';
import { AiChatPanel } from '@ai-accounts/vue-styled';
import { useAiAccounts } from '@ai-accounts/vue-headless';
import { useToast } from '../composables/useToast';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const { client: aiAccountsClient } = useAiAccounts();

/**
 * v0.7.97 — auto-discovery.
 *
 * The sidecar's `/api/v1/discovery/` endpoint probes each candidate
 * CLI by running a real prompt (e.g. `claude -p hello`). That costs
 * upstream tokens and takes up to ~12s per candidate, so this MUST
 * stay user-triggered. Never invoke on mount or in any background
 * effect.
 */
interface DiscoveredItem {
  kind: string;
  path: string;
  suggested_name: string;
  is_logged_in: boolean;
  error: string | null;
  backend_id: string | null;
}

const isDetecting = ref(false);
const showDetectModal = ref(false);
const discoveredItems = ref<DiscoveredItem[]>([]);
const importingPath = ref<string | null>(null);

const router = useRouter();

const showToast = useToast();

/** Extract just the version number (e.g. "2.1.49") from a full version string like "2.1.49 (Claude Code)". */
function parseVersion(version?: string): string {
  if (!version) return '';
  const match = version.match(/\d+\.\d+[\d.]*/);
  return match ? `v${match[0]}` : version;
}

function formatLastUsed(timestamp?: string): string {
  if (!timestamp) return t('aIBackends.never');
  const d = new Date(timestamp);
  if (isNaN(d.getTime())) return t('aIBackends.never');
  const date = d.toLocaleDateString();
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return `${date} ${time}`;
}

// =============================================================================
// Backend List State
// =============================================================================

const backends = ref<AIBackend[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const backendCapabilities = ref<Map<string, BackendCapabilities>>(new Map());
const isAddingAccount = ref(false);
const installingBackend = ref<string | null>(null);

// CLIProxy auth health — per-account expiry state + worst-state summary, so the
// operator sees expired/needs-relogin sessions and can re-authenticate.
type ProxyAuthAccount = { email: string; type: string; auth_state: string; expired: string };
const proxyAuth = ref<{
  available: boolean;
  accounts: ProxyAuthAccount[];
  summary: { worst_state: string; counts: Record<string, number>; total: number };
} | null>(null);

// Accounts that need operator attention (warm tokens are silent).
const proxyAuthAttention = computed(() =>
  (proxyAuth.value?.accounts ?? []).filter((a) =>
    ['expiring', 'expired', 'needs_relogin', 'unreachable'].includes(a.auth_state),
  ),
);

async function loadProxyAuth() {
  try {
    proxyAuth.value = await backendManagementApi.proxyStatus();
  } catch {
    proxyAuth.value = null; // best-effort; the banner just hides
  }
}

async function installBackendCli(backend: AIBackend) {
  if (installingBackend.value) return;
  installingBackend.value = backend.id;
  showToast(t('aIBackends.toastInstalling', { name: backend.name }), 'info');
  try {
    const result = await backendManagementApi.installCli(backend.id);
    showToast(result.message || t('aIBackends.toastInstalled', { name: backend.name }), 'success');
    await loadBackends(true);
  } catch (e: unknown) {
    showToast(e instanceof Error ? e.message : t('aIBackends.toastInstallFailed', { name: backend.name }), 'error');
  } finally {
    installingBackend.value = null;
  }
}

async function addProxyAccount() {
  if (isAddingAccount.value) return;
  isAddingAccount.value = true;
  showToast(t('aIBackends.toastOpeningOauth'), 'info');
  try {
    const result = await backendManagementApi.proxyLogin();
    if (result.status === 'completed') {
      showToast(t('aIBackends.toastAccountAdded'), 'success');
      await loadBackends(true);
      loadProxyAuth();
    } else {
      showToast(result.message || t('aIBackends.toastLoginFailed'), 'error');
    }
  } catch (e: unknown) {
    showToast(e instanceof Error ? e.message : t('aIBackends.toastLoginStartFailed'), 'error');
  } finally {
    isAddingAccount.value = false;
  }
}

const isUpgradingCliproxy = ref(false);

async function upgradeCliproxy() {
  if (isUpgradingCliproxy.value) return;
  isUpgradingCliproxy.value = true;
  showToast(t('aIBackends.toastUpgradingCliproxy'), 'info');
  try {
    const result = await backendManagementApi.upgradeCliproxy();
    const versionSuffix = result.version ? ` (v${result.version})` : '';
    if (result.success) {
      showToast(t('aIBackends.toastCliproxyUpgraded', { version: versionSuffix }), 'success');
    } else {
      showToast(t('aIBackends.toastCliproxyUpgradeFailed', { message: result.message }), 'error');
    }
    await loadBackends(true);
  } catch (e: unknown) {
    showToast(e instanceof Error ? e.message : t('aIBackends.toastCliproxyUpgradeError'), 'error');
  } finally {
    isUpgradingCliproxy.value = false;
  }
}

function closeDetectModal() {
  if (importingPath.value) return; // don't close mid-import
  showDetectModal.value = false;
}

async function runDiscovery() {
  if (isDetecting.value) return;
  isDetecting.value = true;
  try {
    const res = await aiAccountsClient.discoverConfigs();
    discoveredItems.value = res.items;
    if (res.items.length === 0) {
      showToast(t('aIBackends.toastNoLoginsDetected'), 'info');
    }
  } catch (e: unknown) {
    discoveredItems.value = [];
    showToast(e instanceof Error ? e.message : t('aIBackends.toastDiscoveryFailed'), 'error');
  } finally {
    isDetecting.value = false;
  }
}

async function openDetectModal() {
  showDetectModal.value = true;
  await runDiscovery();
}

async function rescan() {
  await runDiscovery();
}

async function importItem(item: DiscoveredItem) {
  if (importingPath.value) return;
  importingPath.value = item.path;
  try {
    await aiAccountsClient.importDiscovered({
      kind: item.kind,
      path: item.path,
      display_name: item.suggested_name,
    });
    showToast(t('aIBackends.toastImported', { name: item.suggested_name }), 'success');
    // Mark locally so the row flips to "Already imported" without
    // a full rescan (which would re-prompt every CLI again).
    item.backend_id = 'imported';
    await loadBackends(true);
  } catch (e: unknown) {
    showToast(
      e instanceof Error ? e.message : t('aIBackends.toastImportFailed', { name: item.suggested_name }),
      'error',
    );
  } finally {
    importingPath.value = null;
  }
}

async function loadBackends(silent = false) {
  if (!silent) {
    isLoading.value = true;
    error.value = null;
  }
  try {
    const response = await listGroupedBackends();
    backends.value = response.backends;
  } catch (err) {
    if (!silent) {
      error.value = t('aIBackends.errorLoadBackends');
    }
  } finally {
    if (!silent) {
      isLoading.value = false;
    }
  }
}

async function autoCheckBackends() {
  if (backends.value.length === 0) return;
  await Promise.allSettled(
    backends.value.map(async (b) => {
      const result = await backendManagementApi.check(b.id);
      if (result.capabilities) {
        backendCapabilities.value.set(b.id, result.capabilities);
      }
      return result;
    })
  );
}

function getCapabilityTags(backendId: string): string[] {
  const caps = backendCapabilities.value.get(backendId);
  if (!caps) return [];
  const tags: string[] = [];
  if (caps.supports_json_output) tags.push(t('aIBackends.capJsonOutput'));
  if (caps.supports_token_usage) tags.push(t('aIBackends.capTokenUsage'));
  if (caps.supports_streaming) tags.push(t('aIBackends.capStreaming'));
  if (caps.supports_non_interactive) tags.push(t('aIBackends.capNonInteractive'));
  return tags;
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(async () => {
  await loadBackends();
  loadProxyAuth();
  autoCheckBackends();
});
</script>

<style scoped>
/* CLIProxy auth banner */
.proxy-auth-banner {
  margin: 0 0 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default);
  border-left: 3px solid var(--accent-amber, #d9a441);
  border-radius: 8px;
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: flex-start;
}
.proxy-auth-banner.needs_relogin,
.proxy-auth-banner.unreachable {
  border-left-color: var(--accent-crimson);
}
.proxy-auth-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.proxy-auth-worst {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-secondary);
}
.proxy-auth-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
}
.proxy-auth-list li {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.8125rem;
}
.proxy-auth-acct {
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}
.proxy-auth-state {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.proxy-auth-state.expired,
.proxy-auth-state.needs_relogin,
.proxy-auth-state.unreachable {
  color: var(--accent-crimson);
}
.proxy-auth-state.expiring {
  color: var(--accent-amber, #d9a441);
}

.add-account-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.backends-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.backend-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.backend-card:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px var(--accent-cyan-dim);
}

.backend-card.disabled {
  opacity: 0.6;
}

.backend-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.backend-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.backend-icon.claude { background: linear-gradient(135deg, #D97757, #bf6344); }
.backend-icon.opencode { background: linear-gradient(135deg, #00B894, #00a07e); }
.backend-icon.gemini { background: linear-gradient(135deg, #4285F4, #3575db); }
.backend-icon.codex { background: linear-gradient(135deg, #10A37F, #0d8a6a); }

.backend-icon svg {
  width: 24px;
  height: 24px;
}

.backend-info {
  flex: 1;
  min-width: 0;
}

.backend-info h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.backend-type-label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.backend-status-area {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
}

.backend-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.backend-status.installed {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.btn-install {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.btn-install:hover:not(:disabled) {
  background: #00c4ee;
}

.btn-install:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.backend-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.meta-label {
  color: var(--text-tertiary);
}

.meta-value {
  color: var(--text-secondary);
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}

.model-pill {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
  border: 1px solid rgba(136, 85, 255, 0.25);
}

.account-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(150, 150, 150, 0.1);
  color: var(--text-tertiary);
}

.account-badge.has-accounts {
  background: rgba(0, 255, 136, 0.12);
  color: var(--accent-emerald);
}

.capability-pill {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent-emerald);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

/* Test Panel Section */
.test-panel-section {
  margin-top: 32px;
}

.test-panel-section .section-header {
  margin-bottom: 16px;
}

.test-panel-section .section-header h2 {
  margin: 0 0 4px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.test-panel-section .section-header .subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.test-chat-container {
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-secondary);
  height: 500px;
  display: flex;
  overflow: hidden;
}

/* Welcome screen override */
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.welcome-icon {
  width: 80px;
  height: 80px;
  background: var(--bg-tertiary);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.welcome-icon svg {
  width: 40px;
  height: 40px;
  color: var(--accent-violet);
}

.chat-welcome h2 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.chat-welcome p {
  margin: 0;
  color: var(--text-secondary);
}

/* --- Detect Existing modal --- */
.detect-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
  margin-right: 8px;
}

.spinner-sm-dark {
  border: 2px solid rgba(0,0,0,0.15);
  border-top-color: var(--text-primary);
}

.spinner-md {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(255,255,255,0.15);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.detect-modal {
  max-width: 640px;
  width: 95%;
}

.modal-close-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  padding: 0 8px;
}

.modal-close-btn:hover { color: var(--text-primary); }

.detect-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  color: var(--text-secondary);
}

.detect-empty {
  padding: 20px 8px;
  color: var(--text-secondary);
  text-align: center;
}

.detect-empty code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
}

.detect-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detect-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
}

.detect-row-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.detect-row-text {
  min-width: 0;
  flex: 1;
}

.detect-name {
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detect-path {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detect-row-side {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.kind-badge {
  text-transform: uppercase;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.kind-claude { background: rgba(217, 119, 87, 0.18); color: #D97757; }
.kind-codex { background: rgba(16, 163, 127, 0.18); color: #10A37F; }
.kind-gemini { background: rgba(66, 133, 244, 0.18); color: #4285F4; }
.kind-opencode { background: rgba(0, 184, 148, 0.18); color: #00B894; }

.login-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
}

.login-badge.ok {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.login-badge.bad {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.already-imported-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(150, 150, 150, 0.15);
  color: var(--text-tertiary);
}

.not-logged-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  font-style: italic;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
}
</style>
