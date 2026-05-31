<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { workflowExecutionApi, ApiError } from '../services/api';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const showToast = useToast();

interface PendingApproval {
  execution_id: string;
  node_id: string;
  status: string;
  requested_at: string;
  timeout_seconds: number;
}

const pending = ref<PendingApproval[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const processingKey = ref<string | null>(null);
const rejectingKey = ref<string | null>(null);
const rejectReason = ref('');

function approvalKey(pa: PendingApproval): string {
  return `${pa.execution_id}:${pa.node_id}`;
}

async function loadPendingApprovals() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await workflowExecutionApi.listPendingApprovals();
    pending.value = data.pending_approvals ?? [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('humanApprovalGates.toast.loadFailed');
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function handleApprove(pa: PendingApproval) {
  const key = approvalKey(pa);
  processingKey.value = key;
  try {
    await workflowExecutionApi.approveNode(pa.execution_id, pa.node_id);
    pending.value = pending.value.filter(p => approvalKey(p) !== key);
    showToast(t('humanApprovalGates.toast.granted'), 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('humanApprovalGates.toast.approveFailed');
    showToast(message, 'error');
  } finally {
    processingKey.value = null;
  }
}

async function handleReject(pa: PendingApproval) {
  const key = approvalKey(pa);
  processingKey.value = key;
  try {
    await workflowExecutionApi.rejectNode(pa.execution_id, pa.node_id, rejectReason.value || undefined);
    pending.value = pending.value.filter(p => approvalKey(p) !== key);
    rejectingKey.value = null;
    rejectReason.value = '';
    showToast(t('humanApprovalGates.toast.rejected'), 'info');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('humanApprovalGates.toast.rejectFailed');
    showToast(message, 'error');
  } finally {
    processingKey.value = null;
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function isExpired(pa: PendingApproval): boolean {
  if (!pa.timeout_seconds) return false;
  const expiresAt = new Date(pa.requested_at).getTime() + pa.timeout_seconds * 1000;
  return expiresAt - Date.now() <= 0;
}

function timeRemaining(pa: PendingApproval): string {
  if (!pa.timeout_seconds) return '';
  const requestedAt = new Date(pa.requested_at).getTime();
  const expiresAt = requestedAt + pa.timeout_seconds * 1000;
  const remaining = expiresAt - Date.now();
  if (remaining <= 0) return t('humanApprovalGates.expired');
  const minutes = Math.floor(remaining / 60000);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) return t('humanApprovalGates.remainingHours', { hours, minutes: minutes % 60 });
  return t('humanApprovalGates.remainingMinutes', { minutes });
}

const pendingCount = computed(() => pending.value.length);

onMounted(loadPendingApprovals);
</script>

<template>
  <div class="approval-gates">

    <PageHeader
      :title="t('humanApprovalGates.title')"
      :subtitle="t('humanApprovalGates.subtitle')"
    >
      <template #actions>
        <button class="btn btn-ghost" @click="loadPendingApprovals">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          {{ t('humanApprovalGates.refresh') }}
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" :message="t('humanApprovalGates.loading')" />

    <div v-else-if="loadError" class="card error-card">
      <div class="error-inner">
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="loadPendingApprovals">{{ t('common.retry') }}</button>
      </div>
    </div>

    <template v-else>
      <!-- Pending Approvals -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            {{ t('humanApprovalGates.pendingApprovals') }}
          </h3>
          <span v-if="pendingCount > 0" class="badge-warn">{{ t('humanApprovalGates.pendingCount', { count: pendingCount }) }}</span>
        </div>
        <div class="pending-list">
          <div
            v-for="pa in pending"
            :key="approvalKey(pa)"
            class="pending-row"
          >
            <div class="pending-info">
              <div class="pending-ids">
                <span class="id-label">{{ t('humanApprovalGates.execution') }}</span>
                <code class="id-value">{{ pa.execution_id }}</code>
                <span class="id-label">{{ t('humanApprovalGates.node') }}</span>
                <code class="id-value">{{ pa.node_id }}</code>
              </div>
              <div class="pending-meta">
                <span class="meta-item">{{ t('humanApprovalGates.requested') }}: {{ formatDate(pa.requested_at) }}</span>
                <template v-if="pa.timeout_seconds">
                  <span class="meta-sep">&middot;</span>
                  <span class="meta-item" :class="{ 'text-warn': isExpired(pa) }">
                    {{ timeRemaining(pa) }}
                  </span>
                </template>
                <span class="meta-sep">&middot;</span>
                <span class="meta-item">{{ t('humanApprovalGates.statusLabel') }}: {{ pa.status }}</span>
              </div>
            </div>
            <div class="pending-actions">
              <button
                class="btn btn-approve"
                :disabled="processingKey === approvalKey(pa)"
                @click="handleApprove(pa)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ processingKey === approvalKey(pa) ? '...' : t('humanApprovalGates.approve') }}
              </button>
              <button
                class="btn btn-reject"
                :disabled="processingKey === approvalKey(pa)"
                @click="rejectingKey = rejectingKey === approvalKey(pa) ? null : approvalKey(pa)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                {{ t('humanApprovalGates.reject') }}
              </button>
            </div>
            <div v-if="rejectingKey === approvalKey(pa)" class="reject-form">
              <input v-model="rejectReason" type="text" class="text-input" :placeholder="t('humanApprovalGates.rejectReasonPlaceholder')" />
              <div class="reject-actions">
                <button class="btn btn-ghost-sm" @click="rejectingKey = null">{{ t('common.cancel') }}</button>
                <button class="btn btn-reject-confirm" :disabled="processingKey === approvalKey(pa)" @click="handleReject(pa)">
                  {{ t('humanApprovalGates.confirmReject') }}
                </button>
              </div>
            </div>
          </div>
          <div v-if="pending.length === 0" class="list-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="opacity: 0.3; color: var(--text-tertiary)">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <p>{{ t('humanApprovalGates.noPending') }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.approval-gates {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.badge-warn {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 10px;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border-radius: 4px;
}

.error-card { padding: 48px; }

.error-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.error-inner p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.pending-list {
  display: flex;
  flex-direction: column;
}

.pending-row {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: background 0.1s;
}

.pending-row:hover { background: var(--bg-tertiary); }
.pending-row:last-child { border-bottom: none; }

.pending-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pending-ids {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.id-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.id-value {
  font-family: 'Geist Mono', monospace;
  font-size: 0.82rem;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}

.pending-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.meta-sep { opacity: 0.5; }
.text-warn { color: #ef4444; }

.pending-actions {
  display: flex;
  gap: 10px;
}

.reject-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.reject-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.text-input {
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.list-empty {
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.list-empty p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-ghost {
  padding: 8px 14px;
  font-size: 0.875rem;
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
}

.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-approve {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.btn-approve:hover:not(:disabled) { background: rgba(52, 211, 153, 0.25); }
.btn-approve:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-reject {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.btn-reject:hover:not(:disabled) { background: rgba(239, 68, 68, 0.2); }
.btn-reject:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-reject-confirm {
  background: #ef4444;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.8rem;
  cursor: pointer;
}

.btn-reject-confirm:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost-sm {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 6px 8px;
}

.btn-ghost-sm:hover { color: var(--text-primary); }
</style>
