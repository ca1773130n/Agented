<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { PrReview, PrReviewStats, Trigger, PrHistoryPoint } from '../services/api';
import { prReviewApi, triggerApi, ApiError } from '../services/api';
import PrHistoryChart from '../components/security/PrHistoryChart.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import EmptyState from '../components/base/EmptyState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

const stats = ref<PrReviewStats | null>(null);
const reviews = ref<PrReview[]>([]);
const reviewTotal = ref(0);
const prTrigger = ref<Trigger | null>(null);
const history = ref<PrHistoryPoint[]>([]);
const isLoading = ref(true);
const filterPrStatus = ref<string>('');
const filterReviewStatus = ref<string>('');
const currentPage = ref(1);
const pageSize = ref(25);
const totalPages = computed(() => Math.max(1, Math.ceil(reviewTotal.value / pageSize.value)));

useWebMcpTool({
  name: 'hive_pr_dashboard_get_state',
  description: 'Returns the current state of the PrReviewDashboard',
  page: 'PrReviewDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'PrReviewDashboard',
        isLoading: isLoading.value,
        reviewCount: reviews.value.length,
        reviewTotal: reviewTotal.value,
        currentPage: currentPage.value,
        totalPages: totalPages.value,
        filterPrStatus: filterPrStatus.value,
        filterReviewStatus: filterReviewStatus.value,
        hasStats: !!stats.value,
        hasTrigger: !!prTrigger.value,
      }),
    }],
  }),
  deps: [isLoading, reviews, reviewTotal, currentPage, totalPages, filterPrStatus, filterReviewStatus, stats, prTrigger],
});

async function loadData() {
  isLoading.value = true;
  try {
    const [statsRes, reviewsRes, botsRes, historyRes] = await Promise.all([
      prReviewApi.getStats(),
      prReviewApi.list({
        limit: pageSize.value,
        offset: (currentPage.value - 1) * pageSize.value,
        pr_status: filterPrStatus.value || undefined,
        review_status: filterReviewStatus.value || undefined,
      }),
      triggerApi.list(),
      prReviewApi.getHistory(30),
    ]);
    stats.value = statsRes;
    reviews.value = reviewsRes.reviews || [];
    reviewTotal.value = reviewsRes.total || 0;
    prTrigger.value = botsRes.triggers?.find((t: Trigger) => t.id === 'bot-pr-review') || null;
    history.value = historyRes.history || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load PR review data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function runReview() {
  if (!prTrigger.value) return;
  try {
    await triggerApi.run('bot-pr-review');
    showToast('PR review trigger started', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to start PR review';
    showToast(message, 'error');
  }
}

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value) return;
  currentPage.value = page;
  loadData();
}

function applyFilters() {
  currentPage.value = 1;
  loadData();
}

function clearFilters() {
  filterPrStatus.value = '';
  filterReviewStatus.value = '';
  currentPage.value = 1;
  loadData();
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const prTableColumns: DataTableColumn[] = [
  { key: 'project_name', label: 'Project' },
  { key: 'pr_number', label: 'PR' },
  { key: 'pr_title', label: 'Title' },
  { key: 'pr_author', label: 'Author' },
  { key: 'pr_status', label: 'PR Status' },
  { key: 'review_status', label: 'Review Status' },
  { key: 'updated_at', label: 'Updated' },
];

function prStatusVariant(status: string): 'info' | 'violet' | 'neutral' {
  if (status === 'open') return 'info';
  if (status === 'merged') return 'violet';
  return 'neutral';
}

function reviewStatusVariant(status: string): 'success' | 'danger' | 'violet' | 'info' | 'warning' {
  if (status === 'approved') return 'success';
  if (status === 'changes_requested') return 'danger';
  if (status === 'fixed') return 'violet';
  if (status === 'reviewing') return 'info';
  return 'warning';
}

function reviewStatusLabel(status: string): string {
  if (status === 'changes_requested') return 'Changes Requested';
  return status.charAt(0).toUpperCase() + status.slice(1);
}

onMounted(loadData);
</script>

<template>
  <div class="pr-review-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'PR Review' }]" />

    <LoadingState v-if="isLoading" message="Loading PR review data..." />

    <template v-else>
      <!-- Stats Card -->
      <div class="card status-card">
        <div class="status-card-inner">
          <div class="status-header">
            <div class="status-title-area">
              <div class="status-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="18" cy="18" r="3"/>
                  <circle cx="6" cy="6" r="3"/>
                  <path d="M13 6h3a2 2 0 012 2v7"/>
                  <path d="M6 9v12"/>
                </svg>
              </div>
              <div>
                <h3>PR Review Status</h3>
                <p class="status-subtitle">Overview of pull requests across all tracked projects</p>
              </div>
            </div>
            <div class="status-actions">
              <span class="status-badge" :class="stats && stats.open_prs > 0 ? 'active' : 'clear'">
                {{ stats?.open_prs || 0 }} Open
              </span>
              <button class="btn btn-primary" @click="runReview" :disabled="!prTrigger?.enabled">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 12a9 9 0 11-9-9c2.52 0 4.93 1 6.74 2.74"/>
                  <path d="M21 3v6h-6"/>
                </svg>
                Run Review
              </button>
            </div>
          </div>

          <div class="stats-grid">
            <StatCard title="Total PRs" :value="stats?.total_prs ?? '-'" />
            <StatCard title="Open" :value="stats?.open_prs ?? '-'" color="var(--accent-cyan)" />
            <StatCard title="Merged" :value="stats?.merged_prs ?? '-'" color="var(--accent-violet)" />
            <StatCard title="Closed" :value="stats?.closed_prs ?? '-'" />
          </div>

          <div class="stats-grid review-stats">
            <StatCard title="Pending Review" :value="stats?.pending_reviews ?? '-'" color="var(--accent-amber)" />
            <StatCard title="Approved" :value="stats?.approved_reviews ?? '-'" color="var(--accent-emerald)" />
            <StatCard title="Changes Requested" :value="stats?.changes_requested ?? '-'" color="var(--accent-crimson)" />
            <StatCard title="Fixed" :value="stats?.fixed_reviews ?? '-'" color="var(--accent-cyan)" />
          </div>
        </div>
      </div>

      <!-- History Chart -->
      <div class="card chart-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 3v18h18"/>
              <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/>
            </svg>
            PR Activity Over Time
          </h3>
          <span class="card-badge">Last 30 days</span>
        </div>
        <div v-if="history.length === 0" class="chart-empty">
          <div class="empty-icon">&#x25C7;</div>
          <p>No PR activity data yet</p>
          <span>Historical data will appear as PRs are tracked</span>
        </div>
        <PrHistoryChart v-else :history="history" />
      </div>

      <!-- PR List -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
            </svg>
            Pull Requests
          </h3>
          <span class="card-badge">{{ reviewTotal }} total</span>
        </div>

        <!-- Filters -->
        <div class="filters-bar">
          <div class="filter-group">
            <label>PR Status</label>
            <select v-model="filterPrStatus" @change="applyFilters">
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="merged">Merged</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Review Status</label>
            <select v-model="filterReviewStatus" @change="applyFilters">
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="reviewing">Reviewing</option>
              <option value="approved">Approved</option>
              <option value="changes_requested">Changes Requested</option>
              <option value="fixed">Fixed</option>
            </select>
          </div>
          <button v-if="filterPrStatus || filterReviewStatus" class="btn-clear-filters" @click="clearFilters">
            Clear Filters
          </button>
        </div>

        <DataTable :columns="prTableColumns" :items="reviews">
          <template #empty>
            <EmptyState
              title="No pull requests tracked yet"
              description="PR data will appear here as the bot processes webhooks"
            />
          </template>
          <template #cell-project_name="{ item }">
            <span class="cell-project">{{ item.project_name }}</span>
          </template>
          <template #cell-pr_number="{ item }">
            <a
              :href="item.pr_url"
              target="_blank"
              rel="noopener noreferrer"
              class="pr-link"
              @click.stop
            >
              #{{ item.pr_number }}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                <path d="M15 3h6v6"/>
                <path d="M10 14L21 3"/>
              </svg>
            </a>
          </template>
          <template #cell-pr_title="{ item }">
            <span class="cell-title">{{ item.pr_title }}</span>
          </template>
          <template #cell-pr_author="{ item }">
            <span class="cell-author">{{ item.pr_author || '-' }}</span>
          </template>
          <template #cell-pr_status="{ item }">
            <StatusBadge :label="item.pr_status" :variant="prStatusVariant(item.pr_status)" />
          </template>
          <template #cell-review_status="{ item }">
            <StatusBadge :label="reviewStatusLabel(item.review_status)" :variant="reviewStatusVariant(item.review_status)" />
          </template>
          <template #cell-updated_at="{ item }">
            <span class="cell-date">{{ formatDate(item.updated_at) }}</span>
          </template>
        </DataTable>

        <div v-if="reviewTotal > pageSize" class="pagination">
          <button class="page-btn" :disabled="currentPage === 1" @click="goToPage(currentPage - 1)">Prev</button>
          <span class="page-info">Page {{ currentPage }} of {{ totalPages }}</span>
          <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">Next</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pr-review-dashboard {
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

/* Cards */
.card {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-header h3 svg {
  width: 18px;
  height: 18px;
  color: var(--accent-violet);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

/* Chart Card */
.chart-card .card-header h3 svg {
  color: var(--accent-cyan);
}

.chart-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
  gap: 8px;
}

.chart-empty .empty-icon {
  font-size: 2.5rem;
  color: var(--text-muted);
}

.chart-empty p {
  color: var(--text-secondary);
  font-weight: 500;
}

.chart-empty span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

/* Status Card */
.status-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  border-color: var(--border-default);
  padding: 0;
  overflow: hidden;
}

.status-card-inner {
  padding: 28px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 16px;
}

.status-title-area {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-violet-dim);
  border: 1px solid var(--accent-violet);
}

.status-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-violet);
}

.status-title-area h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.status-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-badge {
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.status-badge.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-badge.clear {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

/* Buttons */

.btn-primary:hover:not(:disabled) {
  box-shadow: 0 0 20px rgba(136, 85, 255, 0.3);
  transform: translateY(-1px);
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.review-stats {
  margin-top: 16px;
}

/* Filters */
.filters-bar {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-group label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-group select {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  padding: 8px 12px;
  font-size: 0.85rem;
  font-family: var(--font-sans);
  cursor: pointer;
  min-width: 160px;
}

.filter-group select:focus {
  outline: none;
  border-color: var(--accent-violet);
}

.btn-clear-filters {
  background: none;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-tertiary);
  padding: 8px 14px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-clear-filters:hover {
  border-color: var(--accent-crimson);
  color: var(--accent-crimson);
}

/* Cell styles */
.cell-project {
  font-weight: 500;
  color: var(--text-primary);
}

.cell-pr-number {
  white-space: nowrap;
}

.pr-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--accent-cyan);
  text-decoration: none;
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 0.85rem;
  transition: color var(--transition-fast);
}

.pr-link:hover {
  color: var(--text-primary);
}

.pr-link svg {
  width: 12px;
  height: 12px;
  opacity: 0.6;
}

.cell-title {
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  color: var(--text-primary);
}

.cell-author {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.cell-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}


/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.page-btn {
  padding: 6px 16px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.page-btn:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .status-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .filters-bar {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
