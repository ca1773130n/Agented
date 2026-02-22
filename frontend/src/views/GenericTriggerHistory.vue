<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { AuditRecord, Trigger, ProjectInfo } from '../services/api';
import { auditApi, triggerApi } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import EmptyState from '../components/base/EmptyState.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  triggerId?: string;
}>();

const route = useRoute();
const router = useRouter();
const triggerId = computed(() => (route.params.triggerId as string) || props.triggerId || '');

const trigger = ref<Trigger | null>(null);
const audits = ref<AuditRecord[]>([]);
const projects = ref<ProjectInfo[]>([]);
const selectedProject = ref('');

const filteredAudits = ref<AuditRecord[]>([]);

useWebMcpTool({
  name: 'hive_trigger_history_get_state',
  description: 'Returns the current state of the Trigger History page',
  page: 'GenericTriggerHistory',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'GenericTriggerHistory',
        historyEntriesCount: audits.value.length,
        triggerId: triggerId.value,
      }),
    }],
  }),
  deps: [audits],
});

const columns: DataTableColumn[] = [
  { key: 'project', label: 'Project' },
  { key: 'audit_date', label: 'Date' },
  { key: 'trigger_content', label: 'Prompt Request' },
  { key: 'total_findings', label: 'Result' },
  { key: 'log', label: 'Log', align: 'center' },
  { key: 'status', label: 'Status' },
];

function applyFilter() {
  if (!selectedProject.value) {
    filteredAudits.value = audits.value;
  } else {
    filteredAudits.value = audits.value.filter(a => a.project_path === selectedProject.value);
  }
}

watch(selectedProject, applyFilter);

async function loadData() {
  const [botRes, historyRes, projectsRes] = await Promise.all([
    triggerApi.get(triggerId.value).catch(() => null),
    auditApi.getHistory({ trigger_id: triggerId.value }),
    auditApi.getProjects(),
  ]);
  trigger.value = botRes;
  audits.value = historyRes.audits || [];
  projects.value = projectsRes.projects || [];
  applyFilter();
  return trigger.value;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function truncate(text: string | object | undefined, maxLen = 60): string {
  if (!text) return '-';
  const str = typeof text === 'object' ? JSON.stringify(text) : String(text);
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str;
}

function getStatusVariant(status: string): 'success' | 'danger' | 'neutral' {
  if (status === 'pass') return 'success';
  if (status === 'fail') return 'danger';
  return 'neutral';
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="trigger history">
    <template #default="{ reload: _reload }">
  <div class="trigger-history">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: trigger?.name || 'Trigger', action: () => router.push({ name: 'trigger-dashboard', params: { triggerId } }) }, { label: 'History' }]" />

    <PageHeader :title="(trigger?.name || 'Trigger') + ' History'" subtitle="Execution history and results">
      <template #actions>
        <div class="header-stats">
          <div class="stat-chip">
            <span class="stat-value">{{ audits.length }}</span>
            <span class="stat-label">Executions</span>
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
          Showing {{ filteredAudits.length }} of {{ audits.length }} executions
        </div>
      </div>

      <DataTable
        :columns="columns"
        :items="filteredAudits"
      >
        <template #empty>
          <EmptyState title="No execution history available" />
        </template>
        <template #cell-project="{ item }">
          <span class="project-name">{{ item.project_name || item.project_path }}</span>
        </template>
        <template #cell-audit_date="{ item }">
          <span class="cell-date">{{ formatDate(item.audit_date) }}</span>
        </template>
        <template #cell-trigger_content="{ item }">
          <span class="prompt-text" :title="typeof item.trigger_content === 'string' ? item.trigger_content : ''">
            {{ truncate(item.trigger_content) }}
          </span>
        </template>
        <template #cell-total_findings="{ item }">
          <span class="findings-total">{{ item.total_findings }} findings</span>
        </template>
        <template #cell-log="{ item }">
          <button class="btn-icon-sm" title="View details" @click.stop="router.push({ name: 'audit-detail', params: { auditId: item.audit_id } })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
            </svg>
          </button>
        </template>
        <template #cell-status="{ item }">
          <StatusBadge :label="item.status" :variant="getStatusVariant(item.status)" />
        </template>
      </DataTable>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.trigger-history {
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

.card {
  padding: 24px;
}

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

.cell-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.prompt-text {
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 250px;
}

.findings-total {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: var(--font-mono);
}

.btn-icon-sm {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
  transition: all var(--transition-fast);
}

.btn-icon-sm:hover {
  background: var(--accent-cyan-dim);
}

.btn-icon-sm svg {
  width: 16px;
  height: 16px;
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
