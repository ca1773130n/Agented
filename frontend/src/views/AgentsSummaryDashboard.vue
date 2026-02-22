<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Agent } from '../services/api';
import { agentApi } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

const agents = ref<Agent[]>([]);
const isLoading = ref(true);

const totalAgents = computed(() => agents.value.length);
const enabledCount = computed(() => agents.value.filter(a => a.enabled === 1).length);
const claudeCount = computed(() => agents.value.filter(a => a.backend_type === 'claude').length);
const openCodeCount = computed(() => agents.value.filter(a => a.backend_type === 'opencode').length);

useWebMcpTool({
  name: 'hive_agents_summary_get_state',
  description: 'Returns the current state of the AgentsSummaryDashboard',
  page: 'AgentsSummaryDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'AgentsSummaryDashboard',
        isLoading: isLoading.value,
        totalAgents: totalAgents.value,
        enabledCount: enabledCount.value,
        claudeCount: claudeCount.value,
        openCodeCount: openCodeCount.value,
      }),
    }],
  }),
  deps: [isLoading, totalAgents, enabledCount, claudeCount, openCodeCount],
});

const columns: DataTableColumn[] = [
  { key: 'name', label: 'Name' },
  { key: 'role', label: 'Role' },
  { key: 'backend_type', label: 'Backend' },
  { key: 'enabled', label: 'Enabled' },
  { key: 'creation_status', label: 'Status' },
];

function getBackendVariant(backend: string): 'info' | 'violet' | 'neutral' {
  if (backend === 'claude') return 'info';
  if (backend === 'opencode') return 'violet';
  return 'neutral';
}

function getStatusVariant(status: string): 'success' | 'warning' | 'neutral' {
  if (status === 'completed') return 'success';
  if (status === 'in_progress' || status === 'designing') return 'warning';
  return 'neutral';
}

async function loadData() {
  isLoading.value = true;
  try {
    const res = await agentApi.list();
    agents.value = res.agents || [];
  } catch {
    showToast('Failed to load agents data', 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="summary-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Agents' }]" />

    <PageHeader title="Agents Overview" subtitle="Summary of all AI agents and their configurations">
      <template #actions>
        <button class="manage-btn" @click="router.push({ name: 'agents' })">
          Manage Agents
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading agents data..." />

    <template v-else>
      <div class="stats-grid">
        <StatCard title="Total Agents" :value="totalAgents" />
        <StatCard title="Enabled" :value="enabledCount" color="#22c55e" />
        <StatCard title="Claude Backend" :value="claudeCount" color="var(--accent-cyan)" />
        <StatCard title="OpenCode Backend" :value="openCodeCount" color="var(--accent-violet)" />
      </div>

      <div class="entity-section">
        <div class="section-header">
          <h2 class="section-title">All Agents</h2>
          <span class="section-count">{{ totalAgents }} total</span>
        </div>

        <EmptyState
          v-if="agents.length === 0"
          title="No agents found"
          description="Design your first agent to get started."
        />

        <DataTable
          v-else
          :columns="columns"
          :items="agents"
          row-clickable
          @row-click="(item: Agent) => router.push({ name: 'agent-design', params: { agentId: item.id } })"
        >
          <template #cell-name="{ item }">
            <span class="cell-name">{{ item.name }}</span>
          </template>
          <template #cell-role="{ item }">
            <span class="cell-secondary">{{ item.role || '-' }}</span>
          </template>
          <template #cell-backend_type="{ item }">
            <StatusBadge :label="item.backend_type" :variant="getBackendVariant(item.backend_type)" />
          </template>
          <template #cell-enabled="{ item }">
            <StatusBadge :label="item.enabled === 1 ? 'Yes' : 'No'" :variant="item.enabled === 1 ? 'success' : 'neutral'" />
          </template>
          <template #cell-creation_status="{ item }">
            <StatusBadge :label="item.creation_status" :variant="getStatusVariant(item.creation_status)" />
          </template>
        </DataTable>
      </div>
    </template>
  </div>
</template>

<style scoped>
.summary-dashboard {
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

.manage-btn {
  padding: 10px 20px;
  border: 1px solid var(--accent-cyan);
  border-radius: 8px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.manage-btn:hover {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.entity-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.section-count {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.cell-name {
  font-weight: 600;
  color: var(--text-primary);
}

.cell-secondary {
  color: var(--text-tertiary);
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
