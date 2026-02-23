<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Team } from '../services/api';
import { teamApi } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

const teams = ref<Team[]>([]);
const isLoading = ref(true);

const totalTeams = computed(() => teams.value.length);
const totalMembers = computed(() => teams.value.reduce((sum, t) => sum + (t.member_count || 0), 0));
const enabledCount = computed(() => teams.value.filter(t => t.enabled !== 0).length);

useWebMcpTool({
  name: 'agented_teams_summary_get_state',
  description: 'Returns the current state of the TeamsSummaryDashboard',
  page: 'TeamsSummaryDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TeamsSummaryDashboard',
        isLoading: isLoading.value,
        totalTeams: totalTeams.value,
        totalMembers: totalMembers.value,
        enabledCount: enabledCount.value,
      }),
    }],
  }),
  deps: [isLoading, totalTeams, totalMembers, enabledCount],
});

const columns: DataTableColumn[] = [
  { key: 'name', label: 'Name' },
  { key: 'member_count', label: 'Members' },
  { key: 'leader_name', label: 'Leader' },
  { key: 'topology', label: 'Topology' },
  { key: 'trigger_source', label: 'Trigger' },
];

async function loadData() {
  isLoading.value = true;
  try {
    const res = await teamApi.list();
    teams.value = res.teams || [];
  } catch {
    showToast('Failed to load teams data', 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="summary-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Teams' }]" />

    <PageHeader title="Teams Overview" subtitle="Summary of all teams and their members">
      <template #actions>
        <button class="manage-btn" @click="router.push({ name: 'teams' })">Manage Teams</button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading teams data..." />

    <template v-else>
      <div class="stats-grid">
        <StatCard title="Total Teams" :value="totalTeams" />
        <StatCard title="Total Members" :value="totalMembers" color="var(--accent-cyan)" />
        <StatCard title="Enabled" :value="enabledCount" color="#22c55e" />
      </div>

      <div class="entity-section">
        <div class="section-header">
          <h2 class="section-title">All Teams</h2>
          <span class="section-count">{{ totalTeams }} total</span>
        </div>

        <EmptyState v-if="teams.length === 0" title="No teams found" description="Create your first team to get started." />

        <DataTable v-else :columns="columns" :items="teams" row-clickable @row-click="(item: Team) => router.push({ name: 'team-dashboard', params: { teamId: item.id } })">
          <template #cell-name="{ item }">
            <span class="cell-name">
              <span class="team-color" :style="{ backgroundColor: item.color || 'var(--text-muted)' }"></span>
              {{ item.name }}
            </span>
          </template>
          <template #cell-member_count="{ item }">
            <span class="cell-mono">{{ item.member_count }}</span>
          </template>
          <template #cell-leader_name="{ item }">
            <span class="cell-secondary">{{ item.leader_name || '-' }}</span>
          </template>
          <template #cell-topology="{ item }">
            <span v-if="item.topology" class="topology-badge">{{ item.topology }}</span>
            <span v-else class="cell-secondary">-</span>
          </template>
          <template #cell-trigger_source="{ item }">
            <span class="cell-secondary">{{ item.trigger_source || '-' }}</span>
          </template>
        </DataTable>
      </div>
    </template>
  </div>
</template>

<style scoped>
.summary-dashboard { display: flex; flex-direction: column; gap: 24px; width: 100%; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.manage-btn { padding: 10px 20px; border: 1px solid var(--accent-cyan); border-radius: 8px; background: var(--accent-cyan-dim); color: var(--accent-cyan); font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all var(--transition-fast); white-space: nowrap; }
.manage-btn:hover { background: var(--accent-cyan); color: var(--bg-primary); }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.entity-section { background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 24px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.section-title { font-family: var(--font-mono); font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.section-count { font-size: 0.7rem; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 10px; background: var(--bg-tertiary); border-radius: 4px; }
.cell-name { font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 10px; }
.team-color { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.cell-mono { font-family: var(--font-mono); font-weight: 600; }
.cell-secondary { color: var(--text-tertiary); }
.topology-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; background: var(--bg-tertiary); color: var(--text-secondary); text-transform: capitalize; }
@media (max-width: 900px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
