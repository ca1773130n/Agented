<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface ApprovalGate {
  id: string;
  name: string;
  bot: string;
  condition: string;
  approvers: string[];
  enabled: boolean;
}

interface PendingApproval {
  id: string;
  gateId: string;
  gateName: string;
  bot: string;
  action: string;
  requestedBy: string;
  requestedAt: string;
  context: string;
  status: 'pending' | 'approved' | 'rejected';
}

interface AuditEntry {
  id: string;
  action: 'approved' | 'rejected';
  gate: string;
  approver: string;
  timestamp: string;
  reason: string;
}

const gates = ref<ApprovalGate[]>([
  { id: 'gate-1', name: 'Production Deploy Approval', bot: 'bot-deploy', condition: 'trigger.type === "deploy" && env === "production"', approvers: ['alice@example.com', 'bob@example.com'], enabled: true },
  { id: 'gate-2', name: 'Security Critical Finding', bot: 'bot-security', condition: 'finding.severity === "critical"', approvers: ['security@example.com'], enabled: true },
]);

const pending = ref<PendingApproval[]>([
  { id: 'pa-1', gateId: 'gate-2', gateName: 'Security Critical Finding', bot: 'bot-security', action: 'Create Jira ticket for SQL injection', requestedBy: 'bot-security', requestedAt: '5 minutes ago', context: 'Found SQL injection vulnerability in /api/users endpoint. Severity: CRITICAL.', status: 'pending' },
  { id: 'pa-2', gateId: 'gate-1', gateName: 'Production Deploy Approval', bot: 'bot-deploy', action: 'Deploy v2.5.0 to production', requestedBy: 'bot-deploy', requestedAt: '12 minutes ago', context: 'Deployment pipeline triggered. 4 services affected. 0 failing tests.', status: 'pending' },
]);

const audit = ref<AuditEntry[]>([
  { id: 'a-1', action: 'approved', gate: 'Production Deploy Approval', approver: 'alice@example.com', timestamp: '2 hours ago', reason: 'Verified tests pass' },
  { id: 'a-2', action: 'rejected', gate: 'Security Critical Finding', approver: 'security@example.com', timestamp: '1 day ago', reason: 'False positive — already patched' },
]);

const processingId = ref<string | null>(null);
const rejectReason = ref('');
const rejectingId = ref<string | null>(null);

async function handleApprove(pa: PendingApproval) {
  processingId.value = pa.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 800));
    pa.status = 'approved';
    audit.value.unshift({ id: 'a-' + Date.now(), action: 'approved', gate: pa.gateName, approver: 'you@example.com', timestamp: 'just now', reason: 'Approved' });
    showToast('Approval granted', 'success');
    setTimeout(() => {
      pending.value = pending.value.filter(p => p.id !== pa.id);
    }, 800);
  } catch {
    showToast('Failed to approve', 'error');
  } finally {
    processingId.value = null;
  }
}

async function handleReject(pa: PendingApproval) {
  processingId.value = pa.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 800));
    pa.status = 'rejected';
    audit.value.unshift({ id: 'a-' + Date.now(), action: 'rejected', gate: pa.gateName, approver: 'you@example.com', timestamp: 'just now', reason: rejectReason.value || 'No reason given' });
    showToast('Approval rejected', 'info');
    setTimeout(() => {
      pending.value = pending.value.filter(p => p.id !== pa.id);
      rejectingId.value = null;
    }, 800);
  } catch {
    showToast('Failed to reject', 'error');
  } finally {
    processingId.value = null;
  }
}
</script>

<template>
  <div class="approval-gates">
    <AppBreadcrumb :items="[
      { label: 'Workflows', action: () => router.push({ name: 'workflows' }) },
      { label: 'Approval Gates' },
    ]" />

    <PageHeader
      title="Human Approval Gates"
      subtitle="Configure approval requirements and process pending approvals."
    />

    <!-- Pending Approvals -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          Pending Approvals
        </h3>
        <span class="badge-warn">{{ pending.filter(p => p.status === 'pending').length }} pending</span>
      </div>
      <div class="pending-list">
        <div
          v-for="pa in pending"
          :key="pa.id"
          class="pending-row"
          :class="{ 'is-approved': pa.status === 'approved', 'is-rejected': pa.status === 'rejected' }"
        >
          <div class="pending-info">
            <div class="pending-gate">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--accent-cyan)">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              </svg>
              {{ pa.gateName }}
            </div>
            <div class="pending-action">{{ pa.action }}</div>
            <div class="pending-context">{{ pa.context }}</div>
            <div class="pending-meta">
              <span class="meta-item">Requested by {{ pa.requestedBy }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">{{ pa.requestedAt }}</span>
            </div>
          </div>
          <div class="pending-actions">
            <template v-if="pa.status === 'pending'">
              <button
                class="btn btn-approve"
                :disabled="processingId === pa.id"
                @click="handleApprove(pa)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                Approve
              </button>
              <button
                class="btn btn-reject"
                :disabled="processingId === pa.id"
                @click="rejectingId = rejectingId === pa.id ? null : pa.id"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                Reject
              </button>
            </template>
            <span v-else-if="pa.status === 'approved'" class="status-badge approved">Approved</span>
            <span v-else class="status-badge rejected">Rejected</span>
          </div>
          <div v-if="rejectingId === pa.id" class="reject-form">
            <input v-model="rejectReason" type="text" class="text-input" placeholder="Reason for rejection (optional)..." />
            <div class="reject-actions">
              <button class="btn btn-ghost-sm" @click="rejectingId = null">Cancel</button>
              <button class="btn btn-reject-confirm" @click="handleReject(pa)">Confirm Reject</button>
            </div>
          </div>
        </div>
        <div v-if="pending.length === 0" class="list-empty">
          No pending approvals
        </div>
      </div>
    </div>

    <!-- Gate configs -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          Approval Gate Configurations
        </h3>
        <button class="btn btn-primary">+ New Gate</button>
      </div>
      <div class="gates-list">
        <div v-for="g in gates" :key="g.id" class="gate-row">
          <div class="gate-info">
            <span class="gate-name">{{ g.name }}</span>
            <span class="gate-bot">{{ g.bot }}</span>
          </div>
          <div class="gate-condition">
            <code>{{ g.condition }}</code>
          </div>
          <div class="gate-approvers">
            <span v-for="a in g.approvers" :key="a" class="approver-tag">{{ a }}</span>
          </div>
          <div class="gate-status" :class="g.enabled ? 'text-green' : 'text-muted'">
            {{ g.enabled ? 'Active' : 'Disabled' }}
          </div>
        </div>
      </div>
    </div>

    <!-- Audit trail -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          Audit Trail
        </h3>
      </div>
      <div class="audit-list">
        <div v-for="a in audit" :key="a.id" class="audit-row">
          <span :class="['audit-action', a.action]">{{ a.action }}</span>
          <span class="audit-gate">{{ a.gate }}</span>
          <span class="audit-by">by {{ a.approver }}</span>
          <span class="audit-reason">{{ a.reason }}</span>
          <span class="audit-time">{{ a.timestamp }}</span>
        </div>
      </div>
    </div>
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
.pending-row.is-approved { opacity: 0.6; }
.pending-row.is-rejected { opacity: 0.5; }

.pending-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pending-gate {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.pending-action {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.pending-context {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.pending-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.meta-sep { opacity: 0.5; }

.pending-actions {
  display: flex;
  gap: 10px;
}

.status-badge {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
}

.status-badge.approved { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-badge.rejected { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

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
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.gates-list {
  display: flex;
  flex-direction: column;
}

.gate-row {
  display: grid;
  grid-template-columns: 220px 1fr auto auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.gate-row:last-child { border-bottom: none; }

.gate-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gate-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.gate-bot {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.gate-condition code {
  font-size: 0.75rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 3px 8px;
  border-radius: 4px;
  font-family: 'Geist Mono', monospace;
}

.gate-approvers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.approver-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.gate-status {
  font-size: 0.78rem;
  font-weight: 600;
}

.text-green { color: #34d399; }
.text-muted { color: var(--text-tertiary); }

.audit-list {
  display: flex;
  flex-direction: column;
}

.audit-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 24px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.85rem;
}

.audit-row:last-child { border-bottom: none; }

.audit-action {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 3px;
  text-transform: uppercase;
  min-width: 68px;
  text-align: center;
}

.audit-action.approved { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.audit-action.rejected { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.audit-gate { font-weight: 500; color: var(--text-primary); }
.audit-by { color: var(--text-tertiary); }
.audit-reason { flex: 1; color: var(--text-secondary); }
.audit-time { color: var(--text-tertiary); font-size: 0.75rem; white-space: nowrap; }

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

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

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
