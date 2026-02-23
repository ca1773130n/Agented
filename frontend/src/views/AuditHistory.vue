<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { AuditRecord, ProjectInfo } from '../services/api';
import { auditApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = withDefaults(defineProps<{
  triggerId?: string;
  initialProjectFilter?: string | null;
}>(), {
  triggerId: '',
  initialProjectFilter: null,
});

const route = useRoute();
const router = useRouter();

const showToast = useToast();

const audits = ref<AuditRecord[]>([]);
const projects = ref<ProjectInfo[]>([]);
const isLoading = ref(true);
const selectedProject = ref((route.query.project as string) || props.initialProjectFilter || '');

useWebMcpTool({
  name: 'agented_audit_history_get_state',
  description: 'Returns the current state of the Audit History page',
  page: 'AuditHistory',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'AuditHistory',
        auditsCount: audits.value.length,
        selectedProject: selectedProject.value,
        isLoading: isLoading.value,
      }),
    }],
  }),
  deps: [audits, selectedProject, isLoading],
});

const filteredAudits = computed(() => {
  if (!selectedProject.value) return audits.value;
  return audits.value.filter(a => a.project_path === selectedProject.value);
});

const pageTitle = computed(() => {
  if (props.triggerId === 'bot-security') return 'Security Scan History';
  return 'Audit Logs';
});

const pageSubtitle = computed(() => {
  if (props.triggerId === 'bot-security') return 'Security scan history and results';
  return 'Security scan history and results';
});

const columns = computed<DataTableColumn[]>(() => {
  const cols: DataTableColumn[] = [
    { key: 'project', label: 'Project' },
  ];
  if (!props.triggerId) {
    cols.push({ key: 'trigger_name', label: 'Trigger' });
  }
  cols.push(
    { key: 'group_id', label: 'Group ID' },
    { key: 'audit_date', label: 'Date' },
    { key: 'total_findings', label: 'Findings' },
    { key: 'critical', label: 'Critical' },
    { key: 'high', label: 'High' },
    { key: 'medium', label: 'Medium' },
    { key: 'low', label: 'Low' },
    { key: 'status', label: 'Status' },
  );
  return cols;
});

async function loadData() {
  isLoading.value = true;
  try {
    const historyOpts: { trigger_id?: string } = {};
    if (props.triggerId) historyOpts.trigger_id = props.triggerId;
    const [historyRes, projectsRes] = await Promise.all([
      auditApi.getHistory(historyOpts),
      auditApi.getProjects(),
    ]);
    audits.value = historyRes.audits || [];
    projects.value = projectsRes.projects || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load audit data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch(() => props.triggerId, loadData);
watch(() => props.initialProjectFilter, (newVal) => {
  if (newVal !== null && newVal !== undefined) {
    selectedProject.value = newVal;
  }
});

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function getStatusVariant(status: string): 'success' | 'danger' | 'neutral' {
  if (status === 'pass') return 'success';
  if (status === 'fail') return 'danger';
  return 'neutral';
}

function getSeverityVariant(severity: string): 'danger' | 'warning' | 'info' | 'success' {
  if (severity === 'critical') return 'danger';
  if (severity === 'high') return 'warning';
  if (severity === 'medium') return 'info';
  return 'success';
}

onMounted(loadData);
</script>

<template>
  <div class="audit-history">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Audit History' }]" />

    <PageHeader :title="pageTitle" :subtitle="pageSubtitle">
      <template #actions>
        <div class="header-stats">
          <div class="stat-chip">
            <span class="stat-value">{{ audits.length }}</span>
            <span class="stat-label">Total Audits</span>
          </div>
          <div class="stat-chip">
            <span class="stat-value">{{ projects.length }}</span>
            <span class="stat-label">Projects</span>
          </div>
        </div>
      </template>
    </PageHeader>

    <div class="card">
      <!-- Filter Bar -->
      <div class="filter-bar">
        <div class="filter-group">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polygon points="22,3 2,3 10,12.46 10,19 14,21 14,12.46"/>
          </svg>
          <label>Filter by Project</label>
          <select v-model="selectedProject">
            <option value="">All Projects</option>
            <option v-for="p in projects" :key="p.project_path" :value="p.project_path">
              {{ p.project_name || p.project_path }}
            </option>
          </select>
        </div>
        <div class="filter-info">
          Showing {{ filteredAudits.length }} of {{ audits.length }} audits
        </div>
      </div>

      <LoadingState v-if="isLoading" message="Loading audit history..." />

      <DataTable
        v-else
        :columns="columns"
        :items="filteredAudits"
        row-clickable
        @row-click="(item: AuditRecord) => router.push({ name: 'audit-detail', params: { auditId: item.audit_id } })"
      >
        <template #empty>
          <EmptyState title="No audit data available" />
        </template>
        <template #cell-project="{ item }">
          <span class="project-name">{{ item.project_name || item.project_path }}</span>
        </template>
        <template #cell-trigger_name="{ item }">
          <span class="cell-trigger">{{ item.trigger_name || '-' }}</span>
        </template>
        <template #cell-group_id="{ item }">
          <span class="cell-group">{{ item.group_id || '-' }}</span>
        </template>
        <template #cell-audit_date="{ item }">
          <span class="cell-date">{{ formatDate(item.audit_date) }}</span>
        </template>
        <template #cell-total_findings="{ item }">
          <span class="findings-total">{{ item.total_findings }}</span>
        </template>
        <template #cell-critical="{ item }">
          <StatusBadge :label="String(item.critical)" :variant="getSeverityVariant('critical')" />
        </template>
        <template #cell-high="{ item }">
          <StatusBadge :label="String(item.high)" :variant="getSeverityVariant('high')" />
        </template>
        <template #cell-medium="{ item }">
          <StatusBadge :label="String(item.medium)" :variant="getSeverityVariant('medium')" />
        </template>
        <template #cell-low="{ item }">
          <StatusBadge :label="String(item.low)" :variant="getSeverityVariant('low')" />
        </template>
        <template #cell-status="{ item }">
          <StatusBadge :label="item.status" :variant="getStatusVariant(item.status)" />
        </template>
      </DataTable>
    </div>
  </div>
</template>

<style scoped>
.audit-history {
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

/* Header Stats (inside PageHeader actions slot) */
.header-stats {
  display: flex;
  gap: 16px;
}

.stat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.stat-chip .stat-value {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-chip .stat-label {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 2px;
}

/* Card */
.card {
  padding: 24px;
}

/* Filter Bar */
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  margin-bottom: 20px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-group svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
}

.filter-group label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  white-space: nowrap;
}

.filter-group select {
  padding: 10px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 0.875rem;
  background: var(--bg-secondary);
  color: var(--text-primary);
  min-width: 240px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.filter-group select:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.filter-info {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* Cell styles */
.project-name {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cell-trigger {
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: nowrap;
}

.cell-group {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-muted);
}

.cell-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.findings-total {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

@media (max-width: 900px) {
  .filter-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .filter-group select {
    min-width: 100%;
  }
}
</style>
