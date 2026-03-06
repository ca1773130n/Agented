<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

type Severity = 'critical' | 'high' | 'medium' | 'low';
type Status = 'open' | 'in_progress' | 'resolved' | 'wont_fix';

interface Finding {
  id: string;
  title: string;
  severity: Severity;
  status: Status;
  bot: string;
  file?: string;
  owner?: string;
  createdAt: string;
  executionId: string;
  description: string;
}

const severityColors: Record<Severity, string> = {
  critical: 'var(--accent-red)',
  high: 'var(--accent-amber)',
  medium: 'var(--accent-yellow)',
  low: 'var(--accent-cyan)',
};

const columns: { key: Status; label: string; icon: string }[] = [
  { key: 'open', label: 'Open', icon: '●' },
  { key: 'in_progress', label: 'In Progress', icon: '◑' },
  { key: 'resolved', label: 'Resolved', icon: '✓' },
  { key: 'wont_fix', label: "Won't Fix", icon: '✕' },
];

const findings = ref<Finding[]>([
  {
    id: 'f-001',
    title: 'SQL injection in user search endpoint',
    severity: 'critical',
    status: 'open',
    bot: 'bot-security',
    file: 'backend/app/routes/users.py:142',
    owner: undefined,
    createdAt: '2026-03-05T14:22:00Z',
    executionId: 'exec-abc123',
    description: 'User-controlled input is concatenated directly into a SQL query without parameterization.',
  },
  {
    id: 'f-002',
    title: 'Missing rate limiting on /api/auth/login',
    severity: 'high',
    status: 'open',
    bot: 'bot-security',
    file: 'backend/app/routes/auth.py:88',
    owner: 'alice',
    createdAt: '2026-03-05T14:23:00Z',
    executionId: 'exec-abc123',
    description: 'The login endpoint has no rate limiting, enabling brute-force credential attacks.',
  },
  {
    id: 'f-003',
    title: 'Outdated dependency: requests 2.27.1 (CVE-2023-32681)',
    severity: 'high',
    status: 'in_progress',
    bot: 'bot-dep-check',
    file: 'backend/pyproject.toml',
    owner: 'bob',
    createdAt: '2026-03-04T09:10:00Z',
    executionId: 'exec-def456',
    description: 'requests 2.27.1 is vulnerable to proxy credential leakage. Upgrade to >=2.31.0.',
  },
  {
    id: 'f-004',
    title: 'Hardcoded JWT secret in config fallback',
    severity: 'critical',
    status: 'in_progress',
    bot: 'bot-security',
    file: 'backend/app/config.py:34',
    owner: 'alice',
    createdAt: '2026-03-04T09:12:00Z',
    executionId: 'exec-def456',
    description: 'A static fallback secret "changeme" is used when JWT_SECRET env var is unset.',
  },
  {
    id: 'f-005',
    title: 'PR #148: missing null checks in payment handler',
    severity: 'medium',
    status: 'open',
    bot: 'bot-pr-review',
    file: 'frontend/src/services/payment.ts:67',
    owner: undefined,
    createdAt: '2026-03-06T08:00:00Z',
    executionId: 'exec-ghi789',
    description: 'paymentResponse.data?.items can be undefined but is accessed without a guard.',
  },
  {
    id: 'f-006',
    title: 'Excessive permissions on S3 bucket policy',
    severity: 'high',
    status: 'resolved',
    bot: 'bot-security',
    file: 'deploy/terraform/s3.tf:22',
    owner: 'carol',
    createdAt: '2026-03-02T16:00:00Z',
    executionId: 'exec-jkl012',
    description: 'Bucket ACL is set to public-read; should be private with explicit grants.',
  },
  {
    id: 'f-007',
    title: 'console.log with sensitive data in production build',
    severity: 'low',
    status: 'resolved',
    bot: 'bot-pr-review',
    file: 'frontend/src/composables/useAuth.ts:89',
    owner: 'bob',
    createdAt: '2026-03-01T11:30:00Z',
    executionId: 'exec-mno345',
    description: 'Auth token is logged to the browser console in the sign-in flow.',
  },
  {
    id: 'f-008',
    title: 'CORS wildcard on /api/* endpoints',
    severity: 'medium',
    status: 'wont_fix',
    bot: 'bot-security',
    file: 'backend/app/__init__.py:55',
    owner: 'carol',
    createdAt: '2026-02-28T09:00:00Z',
    executionId: 'exec-pqr678',
    description: 'All origins allowed; acceptable for internal dev environment, flagged for prod review.',
  },
]);

const filterSeverity = ref<Severity | 'all'>('all');
const filterBot = ref<string>('all');
const filterOwner = ref<string>('all');
const selectedFinding = ref<Finding | null>(null);
const isDragging = ref<string | null>(null);
const dragOver = ref<Status | null>(null);

const allBots = computed(() => [...new Set(findings.value.map((f) => f.bot))]);
const allOwners = computed(() => [...new Set(findings.value.map((f) => f.owner).filter(Boolean))] as string[]);

const filtered = computed(() =>
  findings.value.filter((f) => {
    if (filterSeverity.value !== 'all' && f.severity !== filterSeverity.value) return false;
    if (filterBot.value !== 'all' && f.bot !== filterBot.value) return false;
    if (filterOwner.value !== 'all' && f.owner !== filterOwner.value) return false;
    return true;
  })
);

function columnFindings(status: Status): Finding[] {
  return filtered.value.filter((f) => f.status === status);
}

function colCount(status: Status): number {
  return columnFindings(status).length;
}

function severityLabel(s: Severity): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 1) return 'just now';
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function onDragStart(id: string) {
  isDragging.value = id;
}

function onDragEnter(status: Status) {
  dragOver.value = status;
}

function onDragLeave() {
  dragOver.value = null;
}

function onDrop(status: Status) {
  if (!isDragging.value) return;
  const finding = findings.value.find((f) => f.id === isDragging.value);
  if (finding && finding.status !== status) {
    finding.status = status;
    showToast(`Moved to "${columns.find((c) => c.key === status)?.label}"`, 'success');
  }
  isDragging.value = null;
  dragOver.value = null;
}

function onDragEnd() {
  isDragging.value = null;
  dragOver.value = null;
}

function assignSelf(finding: Finding) {
  finding.owner = 'me';
  showToast('Assigned to you', 'success');
}

function moveStatus(finding: Finding, status: Status) {
  finding.status = status;
  showToast(`Moved to "${columns.find((c) => c.key === status)?.label}"`, 'success');
}

const openCount = computed(() => findings.value.filter((f) => f.status === 'open').length);
const criticalOpen = computed(
  () => findings.value.filter((f) => f.status === 'open' && f.severity === 'critical').length
);
</script>

<template>
  <div class="ftb-page">
    <AppBreadcrumb
      :items="[{ label: 'Platform' }, { label: 'Findings Triage Board' }]"
    />
    <PageHeader
      title="Findings Triage Board"
      description="Triage, assign, and track actionable findings from all security, code review, and analysis bots."
    />

    <!-- Summary bar -->
    <div class="ftb-summary">
      <div class="summary-stat">
        <span class="stat-value" style="color: var(--accent-red)">{{ criticalOpen }}</span>
        <span class="stat-label">Critical Open</span>
      </div>
      <div class="summary-stat">
        <span class="stat-value">{{ openCount }}</span>
        <span class="stat-label">Total Open</span>
      </div>
      <div class="summary-stat">
        <span class="stat-value">{{ findings.filter((f) => f.status === 'in_progress').length }}</span>
        <span class="stat-label">In Progress</span>
      </div>
      <div class="summary-stat">
        <span class="stat-value" style="color: var(--accent-cyan)">{{
          findings.filter((f) => f.status === 'resolved').length
        }}</span>
        <span class="stat-label">Resolved</span>
      </div>
    </div>

    <!-- Filters -->
    <div class="ftb-filters">
      <select v-model="filterSeverity" class="ftb-select">
        <option value="all">All Severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <select v-model="filterBot" class="ftb-select">
        <option value="all">All Bots</option>
        <option v-for="b in allBots" :key="b" :value="b">{{ b }}</option>
      </select>
      <select v-model="filterOwner" class="ftb-select">
        <option value="all">All Owners</option>
        <option v-for="o in allOwners" :key="o" :value="o">{{ o }}</option>
      </select>
      <button class="ftb-btn-outline" @click="router.push({ name: 'findings-trend-analysis' })">
        View Trends →
      </button>
    </div>

    <!-- Kanban board -->
    <div class="kanban-board">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-column"
        :class="{ 'drag-over': dragOver === col.key }"
        @dragover.prevent="onDragEnter(col.key)"
        @dragleave="onDragLeave"
        @drop="onDrop(col.key)"
      >
        <div class="col-header">
          <span class="col-icon">{{ col.icon }}</span>
          <span class="col-label">{{ col.label }}</span>
          <span class="col-count">{{ colCount(col.key) }}</span>
        </div>

        <div class="col-body">
          <div
            v-for="finding in columnFindings(col.key)"
            :key="finding.id"
            class="finding-card"
            :class="{ dragging: isDragging === finding.id }"
            draggable="true"
            @dragstart="onDragStart(finding.id)"
            @dragend="onDragEnd"
            @click="selectedFinding = finding"
          >
            <div class="card-severity" :style="{ background: severityColors[finding.severity] }">
              {{ severityLabel(finding.severity) }}
            </div>
            <div class="card-title">{{ finding.title }}</div>
            <div class="card-meta">
              <span class="card-bot">{{ finding.bot }}</span>
              <span class="card-time">{{ relativeTime(finding.createdAt) }}</span>
            </div>
            <div v-if="finding.file" class="card-file">{{ finding.file }}</div>
            <div class="card-footer">
              <span v-if="finding.owner" class="card-owner">@{{ finding.owner }}</span>
              <button v-else class="card-assign" @click.stop="assignSelf(finding)">Assign me</button>
            </div>
          </div>

          <div v-if="columnFindings(col.key).length === 0" class="col-empty">No findings</div>
        </div>
      </div>
    </div>

    <!-- Detail drawer -->
    <Transition name="drawer">
      <div v-if="selectedFinding" class="detail-drawer" @click.self="selectedFinding = null">
        <div class="drawer-panel">
          <div class="drawer-header">
            <div
              class="drawer-severity"
              :style="{ background: severityColors[selectedFinding.severity] }"
            >
              {{ severityLabel(selectedFinding.severity) }}
            </div>
            <button class="drawer-close" @click="selectedFinding = null">✕</button>
          </div>
          <h2 class="drawer-title">{{ selectedFinding.title }}</h2>
          <p class="drawer-desc">{{ selectedFinding.description }}</p>
          <dl class="drawer-meta">
            <dt>Bot</dt>
            <dd>{{ selectedFinding.bot }}</dd>
            <dt>File</dt>
            <dd>{{ selectedFinding.file ?? '—' }}</dd>
            <dt>Owner</dt>
            <dd>{{ selectedFinding.owner ?? 'Unassigned' }}</dd>
            <dt>Reported</dt>
            <dd>{{ relativeTime(selectedFinding.createdAt) }}</dd>
            <dt>Execution</dt>
            <dd>{{ selectedFinding.executionId }}</dd>
          </dl>
          <div class="drawer-actions">
            <span class="drawer-label">Move to:</span>
            <button
              v-for="col in columns"
              :key="col.key"
              class="ftb-btn-outline"
              :disabled="selectedFinding.status === col.key"
              @click="moveStatus(selectedFinding!, col.key)"
            >
              {{ col.label }}
            </button>
          </div>
          <div class="drawer-link-row">
            <button class="ftb-btn-outline" @click="router.push({ name: 'execution-history' })">
              View Execution →
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ftb-page {
  padding: 24px;
  max-width: 100%;
}

.ftb-summary {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  padding: 16px;
  background: var(--surface-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.summary-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 1.6rem;
  font-weight: 700;
  line-height: 1;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.ftb-filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  align-items: center;
}

.ftb-select {
  background: var(--surface-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  padding: 6px 12px;
  font-size: 0.85rem;
  cursor: pointer;
}

.ftb-btn-outline {
  background: none;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  padding: 6px 12px;
  font-size: 0.85rem;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    color var(--transition-fast);
}

.ftb-btn-outline:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.ftb-btn-outline:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.kanban-board {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .kanban-board {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 500px) {
  .kanban-board {
    grid-template-columns: 1fr;
  }
}

.kanban-column {
  background: var(--surface-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  min-height: 200px;
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.kanban-column.drag-over {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 2px rgba(0, 212, 255, 0.2);
}

.col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-default);
  font-weight: 600;
  font-size: 0.85rem;
}

.col-icon {
  font-size: 0.7rem;
  opacity: 0.6;
}

.col-label {
  flex: 1;
  color: var(--text-primary);
}

.col-count {
  background: var(--surface-tertiary);
  border-radius: 10px;
  padding: 1px 7px;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.col-body {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.col-empty {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  padding: 24px 0;
}

.finding-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 10px 12px;
  cursor: grab;
  transition:
    box-shadow var(--transition-fast),
    opacity var(--transition-fast);
}

.finding-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.finding-card.dragging {
  opacity: 0.4;
  cursor: grabbing;
}

.card-severity {
  display: inline-block;
  border-radius: 4px;
  padding: 1px 7px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--surface-primary);
  margin-bottom: 6px;
}

.card-title {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.35;
}

.card-meta {
  display: flex;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.card-bot {
  font-family: var(--font-mono, monospace);
  background: var(--surface-secondary);
  padding: 1px 5px;
  border-radius: 3px;
}

.card-file {
  font-family: var(--font-mono, monospace);
  font-size: 0.7rem;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}

.card-owner {
  font-size: 0.75rem;
  color: var(--accent-cyan);
}

.card-assign {
  background: none;
  border: none;
  font-size: 0.72rem;
  color: var(--text-tertiary);
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.card-assign:hover {
  color: var(--accent-cyan);
}

/* Detail drawer */
.detail-drawer {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
  display: flex;
  justify-content: flex-end;
}

.drawer-panel {
  width: min(480px, 100vw);
  background: var(--surface-primary);
  border-left: 1px solid var(--border-default);
  padding: 24px;
  overflow-y: auto;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.drawer-severity {
  border-radius: 5px;
  padding: 2px 10px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--surface-primary);
}

.drawer-close {
  background: none;
  border: none;
  font-size: 1rem;
  color: var(--text-tertiary);
  cursor: pointer;
}

.drawer-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 10px;
}

.drawer-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0 0 18px;
  line-height: 1.6;
}

.drawer-meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 16px;
  margin-bottom: 20px;
}

.drawer-meta dt {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.drawer-meta dd {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin: 0;
  font-family: var(--font-mono, monospace);
}

.drawer-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.drawer-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.drawer-link-row {
  margin-top: 8px;
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s;
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
</style>
