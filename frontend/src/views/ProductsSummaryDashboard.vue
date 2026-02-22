<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Product } from '../services/api';
import { productApi } from '../services/api';
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

const products = ref<Product[]>([]);
const isLoading = ref(true);

const totalProducts = computed(() => products.value.length);
const activeCount = computed(() => products.value.filter(p => p.status === 'active').length);
const inactiveCount = computed(() => products.value.filter(p => p.status !== 'active').length);
const totalProjectCount = computed(() => products.value.reduce((sum, p) => sum + (p.project_count || 0), 0));

useWebMcpTool({
  name: 'hive_products_summary_get_state',
  description: 'Returns the current state of the ProductsSummaryDashboard',
  page: 'ProductsSummaryDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProductsSummaryDashboard',
        isLoading: isLoading.value,
        totalProducts: totalProducts.value,
        activeCount: activeCount.value,
        inactiveCount: inactiveCount.value,
        totalProjectCount: totalProjectCount.value,
      }),
    }],
  }),
  deps: [isLoading, totalProducts, activeCount, inactiveCount, totalProjectCount],
});

const columns: DataTableColumn[] = [
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
  { key: 'project_count', label: 'Projects' },
  { key: 'owner_team_name', label: 'Owner Team' },
  { key: 'updated_at', label: 'Updated' },
];

function getStatusVariant(status: string): 'success' | 'neutral' {
  return status === 'active' ? 'success' : 'neutral';
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

async function loadData() {
  isLoading.value = true;
  try {
    const res = await productApi.list();
    products.value = res.products || [];
  } catch {
    showToast('Failed to load products data', 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadData);
</script>

<template>
  <div class="summary-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Products' }]" />

    <PageHeader title="Products Overview" subtitle="Summary of all products across the organization">
      <template #actions>
        <button class="manage-btn" @click="router.push({ name: 'products' })">Manage Products</button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading products data..." />

    <template v-else>
      <div class="stats-grid">
        <StatCard title="Total Products" :value="totalProducts" />
        <StatCard title="Active" :value="activeCount" color="#22c55e" />
        <StatCard title="Inactive" :value="inactiveCount" color="var(--accent-amber)" />
        <StatCard title="Total Projects" :value="totalProjectCount" color="var(--accent-cyan)" />
      </div>

      <div class="entity-section">
        <div class="section-header">
          <h2 class="section-title">All Products</h2>
          <span class="section-count">{{ totalProducts }} total</span>
        </div>

        <EmptyState v-if="products.length === 0" title="No products found" description="Create your first product to get started." />

        <DataTable v-else :columns="columns" :items="products" row-clickable @row-click="(item: Product) => router.push({ name: 'product-dashboard', params: { productId: item.id } })">
          <template #cell-name="{ item }">
            <span class="cell-name">{{ item.name }}</span>
          </template>
          <template #cell-status="{ item }">
            <StatusBadge :label="item.status" :variant="getStatusVariant(item.status)" />
          </template>
          <template #cell-project_count="{ item }">
            <span class="cell-mono">{{ item.project_count }}</span>
          </template>
          <template #cell-owner_team_name="{ item }">
            <span class="cell-secondary">{{ item.owner_team_name || '-' }}</span>
          </template>
          <template #cell-updated_at="{ item }">
            <span class="cell-date">{{ formatDate(item.updated_at) }}</span>
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
.cell-mono { font-family: var(--font-mono); font-weight: 600; }
.cell-secondary { color: var(--text-tertiary); }
.cell-date { font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-tertiary); }
@media (max-width: 900px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
