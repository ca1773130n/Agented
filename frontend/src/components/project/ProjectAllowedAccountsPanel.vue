<script setup lang="ts">
/**
 * Manage the per-project AI backend account whitelist (v0.7.58).
 *
 * Sessions started with ``yolo_mode=false`` must pick an account that
 * appears here. Yolo mode bypasses the check.
 *
 * Lists the whitelist's current entries (resolved to friendly account
 * names by cross-referencing the sidecar's account list) and offers a
 * picker to add more. Removal is one-click with confirmation in a
 * toast.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdApi, listGroupedBackends, getGroupedBackend, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const { t } = useI18n();

const props = defineProps<{ projectId: string }>();

interface AllowedEntry {
  account_id: string;
  created_at: string;
}

interface AccountOption {
  id: string;
  account_name: string;
  backend_type: string;
}

const allowed = ref<AllowedEntry[]>([]);
const allAccounts = ref<AccountOption[]>([]);
const selectedAccountId = ref('');
const isLoading = ref(false);
const isSubmitting = ref(false);

const showToast = useToast();

const accountById = computed(() => {
  const map = new Map<string, AccountOption>();
  for (const a of allAccounts.value) map.set(a.id, a);
  return map;
});

const addableAccounts = computed(() => {
  const taken = new Set(allowed.value.map((e) => e.account_id));
  return allAccounts.value.filter((a) => !taken.has(a.id));
});

async function reload() {
  isLoading.value = true;
  try {
    const [allowedRes, backendsRes] = await Promise.all([
      grdApi.listAllowedAccounts(props.projectId),
      listGroupedBackends(),
    ]);
    allowed.value = allowedRes.allowed_accounts ?? [];

    // Fan out one ``getGroupedBackend`` per backend kind to assemble
    // a flat list of accounts (id + name + backend type). Failures
    // on individual kinds are swallowed — partial discovery is
    // better than refusing to render.
    const detailResults = await Promise.all(
      (backendsRes.backends || []).map((b) => getGroupedBackend(b.id).catch(() => null)),
    );
    const flat: AccountOption[] = [];
    detailResults.forEach((detail, idx) => {
      if (!detail) return;
      for (const acct of detail.accounts || []) {
        flat.push({
          id: acct.id,
          account_name: acct.account_name,
          backend_type: backendsRes.backends[idx].type,
        });
      }
    });
    allAccounts.value = flat;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectAllowedAccountsPanel.toast.loadFailed');
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function onAdd() {
  if (!selectedAccountId.value) return;
  isSubmitting.value = true;
  try {
    const res = await grdApi.addAllowedAccount(props.projectId, selectedAccountId.value);
    if (res.inserted) {
      showToast(t('projectAllowedAccountsPanel.toast.added'), 'success');
    } else {
      showToast(t('projectAllowedAccountsPanel.toast.alreadyWhitelisted'), 'info');
    }
    selectedAccountId.value = '';
    await reload();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectAllowedAccountsPanel.toast.addFailed');
    showToast(message, 'error');
  } finally {
    isSubmitting.value = false;
  }
}

async function onRemove(accountId: string) {
  try {
    await grdApi.removeAllowedAccount(props.projectId, accountId);
    showToast(t('projectAllowedAccountsPanel.toast.removed'), 'info');
    await reload();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectAllowedAccountsPanel.toast.removeFailed');
    showToast(message, 'error');
  }
}

function displayName(accountId: string): string {
  const a = accountById.value.get(accountId);
  return a ? a.account_name : accountId;
}

function displayType(accountId: string): string {
  return accountById.value.get(accountId)?.backend_type ?? t('projectAllowedAccountsPanel.unknown');
}

onMounted(reload);
</script>

<template>
  <div class="allowed-accounts">
    <p class="hint">
      {{ t('projectAllowedAccountsPanel.hintPrefix') }}<strong>{{ t('projectAllowedAccountsPanel.yoloMode') }}</strong>{{ t('projectAllowedAccountsPanel.hintSuffix') }}
    </p>

    <div v-if="isLoading" class="loading-state">{{ t('projectAllowedAccountsPanel.loading') }}</div>

    <template v-else>
      <div v-if="allowed.length === 0" class="empty-state">
        {{ t('projectAllowedAccountsPanel.empty') }}
      </div>

      <ul v-else class="allowed-list">
        <li v-for="entry in allowed" :key="entry.account_id" class="allowed-row">
          <div class="row-main">
            <span class="account-name">{{ displayName(entry.account_id) }}</span>
            <span class="account-type">{{ displayType(entry.account_id) }}</span>
            <code class="account-id">{{ entry.account_id }}</code>
          </div>
          <button
            type="button"
            class="btn btn-danger btn-sm"
            @click="onRemove(entry.account_id)"
          >
            {{ t('common.remove') }}
          </button>
        </li>
      </ul>

      <div class="add-row">
        <select v-model="selectedAccountId" :disabled="addableAccounts.length === 0">
          <option value="" disabled>
            {{
              addableAccounts.length === 0
                ? t('projectAllowedAccountsPanel.allWhitelisted')
                : t('projectAllowedAccountsPanel.pickAccount')
            }}
          </option>
          <option v-for="a in addableAccounts" :key="a.id" :value="a.id">
            {{ a.account_name }} ({{ a.backend_type }})
          </option>
        </select>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!selectedAccountId || isSubmitting"
          @click="onAdd"
        >
          {{ isSubmitting ? t('projectAllowedAccountsPanel.adding') : t('common.add') }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.allowed-accounts {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.loading-state,
.empty-state {
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
}

.allowed-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.allowed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.row-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.account-name {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
}

.account-type {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: rgba(0, 188, 212, 0.12);
  color: var(--accent-cyan, #00bcd4);
  padding: 2px 6px;
  border-radius: 4px;
}

.account-id {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.add-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: 4px;
}
.add-row select {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.add-row select:focus {
  border-color: var(--accent-cyan);
}
.add-row select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent-cyan);
  color: #002;
  border-color: var(--accent-cyan);
  font-weight: 600;
}
.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn-danger {
  background: transparent;
  border-color: rgba(255, 100, 100, 0.4);
  color: var(--accent-red, #ff6464);
}
.btn-danger:hover {
  background: rgba(255, 100, 100, 0.1);
}
.btn-sm {
  font-size: 12px;
  padding: 4px 10px;
}
</style>
