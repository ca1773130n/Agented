<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { findingsApi } from '../services/api/findings';
import type { TriageFinding } from '../services/api/findings';

const router = useRouter();
const showToast = useToast();

type Severity = 'critical' | 'high' | 'medium' | 'low';
type Status = 'open' | 'in_progress' | 'resolved' | 'wont_fix';

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

const findings = ref<TriageFinding[]>([]);

onMounted(async () => {
  try {
    const resp = await findingsApi.list();
    findings.value = resp.findings;
  } catch {
    showToast('Failed to load findings', 'error');
  }
});

const filterSeverity = ref<Severity | 'all'>('all');
const filterBot = ref<string>('all');
const filterOwner = ref<string>('all');
const selectedFinding = ref<TriageFinding | null>(null);
const isDragging = ref<string | null>(null);
const dragOver = ref<Status | null>(null);

const allBots = computed(() => [...new Set(findings.value.map((f) => f.bot_id).filter(Boolean))] as string[]);
const allOwners = computed(() => [...new Set(findings.value.map((f) => f.owner).filter(Boolean))] as string[]);

const filtered = computed(() =>
  findings.value.filter((f) => {
    if (filterSeverity.value !== 'all' && f.severity !== filterSeverity.value) return false;
    if (filterBot.value !== 'all' && f.bot_id !== filterBot.value) return false;
    if (filterOwner.value !== 'all' && f.owner !== filterOwner.value) return false;
    return true;
  })
);

function columnFindings(status: Status): TriageFinding[] {
  return filtered.value.filter((f) => f.status === status);
}

function colCount(status: Status): number {
  return columnFindings(status).length;
}

function severityLabel(s: string): string {
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

async function onDrop(status: Status) {
  if (!isDragging.value) return;
  const finding = findings.value.find((f) => f.id === isDragging.value);
  if (finding && finding.status !== status) {
    const prevStatus = finding.status;
    // Optimistic update
    finding.status = status;
    try {
      await findingsApi.update(finding.id, { status });
      showToast(`Moved to "${columns.find((c) => c.key === status)?.label}"`, 'success');
    } catch {
      finding.status = prevStatus;
      showToast('Failed to update finding', 'error');
    }
  }
  isDragging.value = null;
  dragOver.value = null;
}

function onDragEnd() {
  isDragging.value = null;
  dragOver.value = null;
}

async function assignSelf(finding: TriageFinding) {
  const prevOwner = finding.owner;
  // Optimistic update
  finding.owner = 'me';
  try {
    await findingsApi.update(finding.id, { owner: 'me' });
    showToast('Assigned to you', 'success');
  } catch {
    finding.owner = prevOwner;
    showToast('Failed to assign finding', 'error');
  }
}

async function moveStatus(finding: TriageFinding, status: Status) {
  const prevStatus = finding.status;
  // Optimistic update
  finding.status = status;
  try {
    await findingsApi.update(finding.id, { status });
    showToast(`Moved to "${columns.find((c) => c.key === status)?.label}"`, 'success');
  } catch {
    finding.status = prevStatus;
    showToast('Failed to update finding', 'error');
  }
}

const openCount = computed(() => findings.value.filter((f) => f.status === 'open').length);
const criticalOpen = computed(
  () => findings.value.filter((f) => f.status === 'open' && f.severity === 'critical').length
);
</script>

<template>
  <div class="ftb-page">
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
            <div class="card-severity" :style="{ background: severityColors[finding.severity as Severity] ?? 'var(--text-tertiary)' }">
              {{ severityLabel(finding.severity) }}
            </div>
            <div class="card-title">{{ finding.title }}</div>
            <div class="card-meta">
              <span class="card-bot">{{ finding.bot_id ?? '—' }}</span>
              <span class="card-time">{{ relativeTime(finding.created_at) }}</span>
            </div>
            <div v-if="finding.file_ref" class="card-file">{{ finding.file_ref }}</div>
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
              :style="{ background: severityColors[selectedFinding.severity as Severity] ?? 'var(--text-tertiary)' }"
            >
              {{ severityLabel(selectedFinding.severity) }}
            </div>
            <button class="drawer-close" @click="selectedFinding = null">✕</button>
          </div>
          <h2 class="drawer-title">{{ selectedFinding.title }}</h2>
          <p class="drawer-desc">{{ selectedFinding.description }}</p>
          <dl class="drawer-meta">
            <dt>Bot</dt>
            <dd>{{ selectedFinding.bot_id ?? '—' }}</dd>
            <dt>File</dt>
            <dd>{{ selectedFinding.file_ref ?? '—' }}</dd>
            <dt>Owner</dt>
            <dd>{{ selectedFinding.owner ?? 'Unassigned' }}</dd>
            <dt>Reported</dt>
            <dd>{{ relativeTime(selectedFinding.created_at) }}</dd>
            <dt>Execution</dt>
            <dd>{{ selectedFinding.execution_id ?? '—' }}</dd>
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
