<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Project } from '../services/api';
import { projectApi } from '../services/api';
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

const projects = ref<Project[]>([]);
const isLoading = ref(true);

const totalProjects = computed(() => projects.value.length);
const githubConnected = computed(() => projects.value.filter(p => p.github_repo).length);
const activeCount = computed(() => projects.value.filter(p => p.status === 'active').length);

useWebMcpTool({
  name: 'agented_projects_summary_get_state',
  description: 'Returns the current state of the ProjectsSummaryDashboard',
  page: 'ProjectsSummaryDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProjectsSummaryDashboard',
        isLoading: isLoading.value,
        totalProjects: totalProjects.value,
        githubConnected: githubConnected.value,
        activeCount: activeCount.value,
      }),
    }],
  }),
  deps: [isLoading, totalProjects, githubConnected, activeCount],
});

const columns: DataTableColumn[] = [
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
  { key: 'product_name', label: 'Product' },
  { key: 'github_repo', label: 'GitHub Repo' },
  { key: 'owner_team_name', label: 'Owner Team' },
];

function getStatusVariant(status: string): 'success' | 'neutral' {
  return status === 'active' ? 'success' : 'neutral';
}

async function loadData() {
  isLoading.value = true;
  try {
    const res = await projectApi.list();
    projects.value = res.projects || [];
  } catch {
    showToast('Failed to load projects data', 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="summary-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Projects' }]" />

    <PageHeader title="Projects Overview" subtitle="Summary of all projects across the organization">
      <template #actions>
        <button class="manage-btn" @click="router.push({ name: 'projects' })">Manage Projects</button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading projects data..." />

    <template v-else>
      <div class="stats-grid">
        <StatCard title="Total Projects" :value="totalProjects" />
        <StatCard title="Active" :value="activeCount" color="#22c55e" />
        <StatCard title="GitHub Connected" :value="githubConnected" color="var(--accent-violet)" />
      </div>

      <div class="entity-section">
        <div class="section-header">
          <h2 class="section-title">All Projects</h2>
          <span class="section-count">{{ totalProjects }} total</span>
        </div>

        <EmptyState v-if="projects.length === 0" title="No projects found" description="Create your first project to get started." />

        <DataTable v-else :columns="columns" :items="projects" row-clickable @row-click="(item: Project) => router.push({ name: 'project-dashboard', params: { projectId: item.id } })">
          <template #cell-name="{ item }">
            <span class="cell-name">{{ item.name }}</span>
          </template>
          <template #cell-status="{ item }">
            <StatusBadge :label="item.status" :variant="getStatusVariant(item.status)" />
          </template>
          <template #cell-product_name="{ item }">
            <span class="cell-secondary">{{ item.product_name || '-' }}</span>
          </template>
          <template #cell-github_repo="{ item }">
            <span v-if="item.github_repo" class="repo-badge">{{ item.github_repo }}</span>
            <span v-else class="cell-secondary">-</span>
          </template>
          <template #cell-owner_team_name="{ item }">
            <span class="cell-secondary">{{ item.owner_team_name || '-' }}</span>
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
.cell-name { font-weight: 600; color: var(--text-primary); }
.cell-secondary { color: var(--text-tertiary); }
.repo-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; background: var(--accent-violet-dim); color: var(--accent-violet); font-size: 0.75rem; font-family: var(--font-mono); }
@media (max-width: 900px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
