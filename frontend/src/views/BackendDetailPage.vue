<template>
  <EntityLayout :load-entity="loadBackend" entity-label="backend">
    <template #default="{ reload: _reload }">
  <div class="backend-detail-page">
    <AppBreadcrumb :items="[{ label: 'AI Backends', action: () => router.push({ name: 'ai-backends' }) }, { label: backend?.name || 'Backend' }]" />

    <template v-if="backend">
      <PageHeader :title="backend.name" :subtitle="backend.description">
        <template #actions>
          <div class="backend-badges">
            <span class="type-badge">{{ backend.type }}</span>
            <span v-if="backend.version" class="version-badge">v{{ backend.version }}</span>
            <span v-if="backend.is_installed" class="status-badge installed">Installed</span>
            <span v-else class="status-badge not-installed">Not Installed</span>
          </div>
          <button v-if="supportsConnect && backend.is_installed" class="btn btn-primary" @click="showConnect = !showConnect">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
              <polyline points="10 17 15 12 10 7"/>
              <line x1="15" y1="12" x2="3" y2="12"/>
            </svg>
            {{ showConnect ? 'Hide Login' : 'Connect' }}
          </button>
          <a v-if="backend.documentation_url" :href="backend.documentation_url" target="_blank" class="btn btn-outline">
            Documentation
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

      <div class="backend-info-section">
        <div class="info-grid">
          <div class="info-card">
            <h3>Available Models</h3>
            <div class="model-tags">
              <span v-for="model in backend.models" :key="model" class="model-tag">
                {{ model }}
              </span>
            </div>
          </div>
          <div class="info-card capabilities-card" v-if="capabilityList.length > 0">
            <h3>Capabilities</h3>
            <div class="capabilities-list">
              <div v-for="cap in capabilityList" :key="cap.label" class="capability-item">
                <span class="capability-dot" :class="{ active: cap.supported }"></span>
                <span class="capability-label">{{ cap.label }}</span>
                <span v-if="cap.flag" class="capability-flag">{{ cap.flag }}</span>
              </div>
            </div>
          </div>
          <div class="info-card" v-if="cliPath">
            <h3>CLI Path</h3>
            <code class="cli-path-value">{{ cliPath }}</code>
          </div>
        </div>
      </div>

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
      <div v-if="isOpenCode" class="opencode-section">
        <div class="opencode-note">
          <span class="note-icon">i</span>
          <span>OpenCode routes through other AI backends. Register accounts on those backends.</span>
        </div>
        <div class="section-header">
          <h2>Available Backend Accounts</h2>
        </div>
        <div v-if="otherBackendAccounts.length === 0" class="empty-state">
          <p>No accounts found on other backends. Add accounts to Claude, Codex, or Gemini backends first.</p>
        </div>
        <div v-else class="accounts-list">
          <div v-for="group in otherBackendAccounts" :key="group.backend_type" class="cross-backend-group">
            <div class="cross-backend-header">
              <span class="cross-backend-name">{{ group.backend_name }}</span>
              <span class="type-badge">{{ group.backend_type }}</span>
            </div>
            <div v-for="account in group.accounts" :key="account.id" class="account-card cross-backend-card">
              <div class="account-info">
                <div class="account-header">
                  <h3>{{ account.account_name }}</h3>
                  <span v-if="account.is_default" class="default-badge">Default</span>
                </div>
                <div class="account-meta">
                  <div v-if="account.email" class="meta-item">
                    <span class="meta-label">Email:</span>
                    <span>{{ account.email }}</span>
                  </div>
                  <div v-if="account.plan" class="meta-item">
                    <span class="meta-label">Plan:</span>
                    <span class="plan-badge">{{ account.plan }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="accounts-section">
        <div class="section-header">
          <h2>{{ isOpenCode ? 'OpenCode Accounts' : 'Accounts' }}</h2>
          <button v-if="!isOpenCode" class="btn btn-primary" @click="showAddModal = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Account
          </button>
        </div>

        <!-- Inline Add/Edit Account Form -->
        <div v-if="showAddModal || editingAccount" class="inline-account-form">
          <div class="inline-form-header">
            <h3>{{ editingAccount ? 'Edit Account' : 'Add Account' }}</h3>
            <button class="btn-close" @click="closeModal">&times;</button>
          </div>
          <form @submit.prevent="saveAccount">
            <div v-if="!editingAccount && loginInfo" class="login-banner">
              <span class="banner-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="16" x2="12" y2="12"/>
                  <line x1="12" y1="8" x2="12.01" y2="8"/>
                </svg>
              </span>
              <span v-if="loginInfo.loginCommand">Need to authenticate? Use the Connect button or run <code>{{ loginInfo.loginCommand }}</code></span>
              <span v-else>Need to set up? Visit <a :href="loginInfo.url" target="_blank">{{ loginInfo.label }}</a></span>
            </div>
            <div class="form-group">
              <label for="account_name">Account Name *</label>
              <input
                id="account_name"
                v-model="accountForm.account_name"
                type="text"
                required
                placeholder="e.g., Personal, Work"
              />
            </div>
            <div class="form-group">
              <label for="email">Email</label>
              <input
                id="email"
                v-model="accountForm.email"
                type="email"
                placeholder="e.g., user@example.com"
              />
              <small>Login email for this account</small>
            </div>
            <div class="form-group">
              <label for="config_path">Config Path</label>
              <input
                id="config_path"
                v-model="accountForm.config_path"
                type="text"
                placeholder="e.g., ~/.claude-work"
              />
              <small>Path to the backend's config directory for this account</small>
            </div>
            <div class="form-group">
              <label for="api_key_env">API Key Environment Variable</label>
              <input
                id="api_key_env"
                v-model="accountForm.api_key_env"
                type="text"
                placeholder="e.g., ANTHROPIC_API_KEY_WORK"
              />
              <small>Name of the environment variable containing the API key</small>
            </div>
            <div v-if="planOptions.length > 0" class="form-group">
              <label for="plan">Plan</label>
              <select id="plan" v-model="accountForm.plan">
                <option value="">Select plan...</option>
                <option v-for="opt in planOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <template v-if="backend?.type === 'codex'">
              <div class="form-group">
                <label for="reasoning_level">Reasoning Level</label>
                <select id="reasoning_level" v-model="codexSettings.reasoning_level">
                  <option value="">Default</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
                <small>Controls how much reasoning the model performs</small>
              </div>
              <div class="form-group">
                <label for="summary_level">Summary Level</label>
                <select id="summary_level" v-model="codexSettings.summary_level">
                  <option value="">Default</option>
                  <option value="concise">Concise</option>
                  <option value="detailed">Detailed</option>
                </select>
                <small>Controls output verbosity</small>
              </div>
            </template>
            <div class="form-group checkbox">
              <label>
                <input type="checkbox" v-model="accountForm.is_default" />
                Set as default account
              </label>
            </div>
            <div class="inline-form-actions">
              <button type="button" class="btn btn-secondary" @click="closeModal">Cancel</button>
              <button type="submit" class="btn btn-primary" :disabled="isSaving">
                {{ isSaving ? 'Saving...' : (editingAccount ? 'Update' : 'Add Account') }}
              </button>
            </div>
          </form>
        </div>

        <div v-if="backend.accounts?.length === 0" class="empty-state">
          <p v-if="isOpenCode">OpenCode uses other backends' accounts. No separate accounts needed.</p>
          <p v-else>No accounts configured. Add an account to use this backend.</p>
        </div>

        <div v-else class="accounts-list">
          <div v-for="account in backend.accounts" :key="account.id" class="account-card">
            <div class="account-info">
              <div class="account-header">
                <h3>{{ account.account_name }}</h3>
                <span v-if="account.is_default" class="default-badge">Default</span>
                <!-- Health status badge -->
                <template v-if="getAccountHealth(account.id)">
                  <span v-if="getAccountHealth(account.id)!.is_rate_limited" class="health-badge rate-limited">
                    <span class="health-dot red"></span>
                    Rate Limited ({{ formatCooldown(getAccountHealth(account.id)!) }})
                  </span>
                  <span v-else class="health-badge healthy">
                    <span class="health-dot green"></span>
                    Healthy
                  </span>
                </template>
              </div>
              <div class="account-meta">
                <div v-if="account.email" class="meta-item">
                  <span class="meta-label">Email:</span>
                  <span>{{ account.email }}</span>
                </div>
                <div v-if="account.config_path" class="meta-item">
                  <span class="meta-label">Config Path:</span>
                  <code>{{ account.config_path }}</code>
                </div>
                <div v-if="account.api_key_env" class="meta-item">
                  <span class="meta-label">API Key Env:</span>
                  <code>{{ account.api_key_env }}</code>
                </div>
                <div v-if="account.plan" class="meta-item">
                  <span class="meta-label">Plan:</span>
                  <span class="plan-badge">{{ account.plan }}</span>
                </div>
                <!-- Health stats -->
                <template v-if="getAccountHealth(account.id)">
                  <div class="meta-item">
                    <span class="meta-label">Executions:</span>
                    <span>{{ getAccountHealth(account.id)!.total_executions }}</span>
                  </div>
                  <div class="meta-item">
                    <span class="meta-label">Last Used:</span>
                    <span>{{ formatRelativeTime(getAccountHealth(account.id)!.last_used_at) }}</span>
                  </div>
                </template>
              </div>
            </div>
            <div class="account-actions">
              <button
                v-if="backend.type !== 'opencode'"
                class="btn btn-sm btn-outline"
                :disabled="rateLimitState[account.id]?.loading"
                @click="checkAccountRateLimits(account.id)"
              >
                {{ rateLimitState[account.id]?.loading ? 'Checking...' : 'Check Rate Limits' }}
              </button>
              <button
                v-if="getAccountHealth(account.id)?.is_rate_limited"
                class="btn btn-sm btn-clear-rl"
                @click="clearRateLimit(account.id)"
              >
                Clear Rate Limit
              </button>
              <button class="btn btn-sm btn-secondary" @click="editAccount(account)">Edit</button>
              <button class="btn btn-sm btn-danger" @click="deleteAccount(account.id)">Delete</button>
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
                <div v-if="w.resets_at" class="rl-mini-reset">Resets: {{ new Date(w.resets_at).toLocaleString() }}</div>
              </div>
            </div>
            <div v-else-if="rateLimitState[account.id]?.error" class="rate-limit-error">
              {{ rateLimitState[account.id]!.error }}
            </div>
          </div>
        </div>
      </div>
    </template>

    <ConfirmModal
      :open="showDeleteAccountConfirm"
      title="Delete Account"
      message="Are you sure you want to delete this account?"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDeleteAccount"
      @cancel="showDeleteAccountConfirm = false"
    />
  </div>
    </template>
  </EntityLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { backendApi, orchestrationApi, BACKEND_PLAN_OPTIONS, BACKEND_LOGIN_INFO, type AIBackendWithAccounts, type BackendAccount, type AccountHealth, type BackendCapabilities, type RateLimitWindow } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import BackendConnect from '../components/monitoring/BackendConnect.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const route = useRoute();
const backendId = computed(() => route.params.backendId as string);

const backend = ref<AIBackendWithAccounts | null>(null);

const showAddModal = ref(false);
const editingAccount = ref<BackendAccount | null>(null);
const isSaving = ref(false);

const showToast = useToast();

// Account health state
const healthMap = ref<Map<number, AccountHealth>>(new Map());
const now = ref(Date.now());
let clockTimer: ReturnType<typeof setInterval> | null = null;

// Connect state
const showConnect = ref(false);

// Rate limit state per account
const rateLimitState = ref<Record<number, { loading: boolean; windows: RateLimitWindow[]; error: string | null }>>({});

// Capabilities state
const capabilities = ref<BackendCapabilities | null>(null);
const cliPath = ref<string | null>(null);

// Confirm delete account state
const showDeleteAccountConfirm = ref(false);
const pendingDeleteAccountId = ref<number | null>(null);

const capabilityList = computed(() => {
  const caps = capabilities.value;
  if (!caps) return [];
  return [
    { label: 'JSON Output', supported: caps.supports_json_output, flag: caps.json_output_flag || null },
    { label: 'Token Usage', supported: caps.supports_token_usage, flag: null },
    { label: 'Streaming', supported: caps.supports_streaming, flag: null },
    { label: 'Non-Interactive', supported: caps.supports_non_interactive, flag: caps.non_interactive_flag || null },
  ];
});

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

const planOptions = computed(() => {
  if (!backend.value) return [];
  return BACKEND_PLAN_OPTIONS[backend.value.type] || [];
});

async function loadBackend() {
  const data = await backendApi.get(backendId.value);
  backend.value = data;
  // Fire-and-forget: load supplementary data
  loadHealth();
  if (data?.type === 'opencode') {
    loadOtherBackendAccounts();
  }
  return data;
}


function editAccount(account: BackendAccount) {
  editingAccount.value = account;
  accountForm.value = {
    account_name: account.account_name,
    email: account.email || '',
    config_path: account.config_path || '',
    api_key_env: account.api_key_env || '',
    plan: account.plan || '',
    is_default: !!account.is_default,
  };
  const ud = account.usage_data || {};
  codexSettings.value = {
    reasoning_level: (ud as Record<string, string>).reasoning_level || '',
    summary_level: (ud as Record<string, string>).summary_level || '',
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

async function saveAccount() {
  isSaving.value = true;
  try {
    const usageData: Record<string, string> = {};
    if (backend.value?.type === 'codex') {
      if (codexSettings.value.reasoning_level) usageData.reasoning_level = codexSettings.value.reasoning_level;
      if (codexSettings.value.summary_level) usageData.summary_level = codexSettings.value.summary_level;
    }
    const data = {
      account_name: accountForm.value.account_name,
      email: accountForm.value.email || undefined,
      config_path: accountForm.value.config_path || undefined,
      api_key_env: accountForm.value.api_key_env || undefined,
      plan: accountForm.value.plan || undefined,
      is_default: accountForm.value.is_default ? 1 : 0,
      usage_data: Object.keys(usageData).length > 0 ? usageData : undefined,
    };

    if (editingAccount.value) {
      await backendApi.updateAccount(backendId.value, editingAccount.value.id, data);
    } else {
      await backendApi.addAccount(backendId.value, data);
    }

    closeModal();
    showToast?.('Account saved successfully', 'success');
    await loadBackend();
  } catch (err) {
    showToast?.('Failed to save account', 'error');
  } finally {
    isSaving.value = false;
  }
}

function deleteAccount(accountId: number) {
  pendingDeleteAccountId.value = accountId;
  showDeleteAccountConfirm.value = true;
}

async function confirmDeleteAccount() {
  const accountId = pendingDeleteAccountId.value;
  showDeleteAccountConfirm.value = false;
  pendingDeleteAccountId.value = null;
  if (accountId === null) return;
  try {
    await backendApi.deleteAccount(backendId.value, accountId);
    await loadBackend();
  } catch (err) {
    showToast?.('Failed to delete account', 'error');
  }
}

async function loadHealth() {
  try {
    const data = await orchestrationApi.getHealth();
    const map = new Map<number, AccountHealth>();
    for (const acct of (data.accounts || [])) {
      map.set(acct.account_id, acct);
    }
    healthMap.value = map;
  } catch {
    // Health data is supplementary -- don't block on failure
  }
}

function getAccountHealth(accountId: number): AccountHealth | undefined {
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

async function clearRateLimit(accountId: number) {
  try {
    await orchestrationApi.clearRateLimit(accountId);
    showToast?.('Rate limit cleared', 'success');
    await loadHealth();
  } catch {
    showToast?.('Failed to clear rate limit', 'error');
  }
}

const supportsConnect = computed(() => {
  if (!backend.value) return false;
  return !!BACKEND_LOGIN_INFO[backend.value.type]?.loginCommand;
});

function onConnected() {
  showConnect.value = false;
  showToast?.('Login completed successfully', 'success');
  loadBackend();
}

async function checkAccountRateLimits(accountId: number) {
  rateLimitState.value[accountId] = { loading: true, windows: [], error: null };
  try {
    const result = await backendApi.checkRateLimits(backendId.value, accountId);
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
    const { backends } = await backendApi.list();
    const results: typeof otherBackendAccounts.value = [];
    for (const b of backends) {
      if (b.type === 'opencode') continue;
      const detail = await backendApi.get(b.id);
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

.backend-info-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.backend-badges {
  display: flex;
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

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.info-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 1rem;
}

.info-card h3 {
  margin: 0 0 0.5rem 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.info-card p {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.model-tag {
  padding: 0.25rem 0.75rem;
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
  border: 1px solid rgba(136, 85, 255, 0.25);
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  font-family: var(--font-mono);
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

/* Capabilities */
.capabilities-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.capability-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  flex-shrink: 0;
}

.capability-dot.active {
  background: var(--accent-emerald);
  box-shadow: 0 0 4px var(--accent-emerald-dim);
}

.capability-label {
  color: var(--text-primary);
}

.capability-flag {
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.cli-path-value {
  display: block;
  padding: 0.375rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8125rem;
  color: var(--text-primary);
  word-break: break-all;
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
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-outline:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
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

/* OpenCode section */
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

/* Connect section */
.connect-section {
  margin-bottom: 1rem;
  animation: fadeIn 0.3s ease;
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
