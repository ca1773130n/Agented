<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { marketplaceApi } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

// Search state
const searchQuery = ref('');
const results = ref<any[]>([]);
const isSearching = ref(false);
const selectedItem = ref<any>(null);

const detailModalRef = ref<HTMLElement | null>(null);
const detailModalOpen = computed(() => !!selectedItem.value);
useFocusTrap(detailModalRef, detailModalOpen);

useWebMcpTool({
  name: 'agented_explore_super_agents_get_state',
  description: 'Returns the current state of the Explore SuperAgents page',
  page: 'ExploreSuperAgents',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ExploreSuperAgents',
        availableAgentsCount: results.value.length,
        isLoading: isSearching.value,
      }),
    }],
  }),
  deps: [results, isSearching],
});

// Debounced search
let searchTimeout: ReturnType<typeof setTimeout> | null = null;

function debouncedSearch() {
  if (searchTimeout) clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    performSearch();
  }, 300);
}

async function performSearch() {
  const q = searchQuery.value.trim();
  isSearching.value = true;
  try {
    // super_agent type not yet supported by marketplace search type union --
    // cast to string to bypass type check until marketplace is extended
    const response = await marketplaceApi.search(q, 'super_agent' as 'plugin');
    results.value = response.results || [];
  } catch (_e) {
    // Marketplace may not support super_agent type yet -- show empty state
    results.value = [];
  } finally {
    isSearching.value = false;
  }
}

function selectItem(item: any) {
  selectedItem.value = item;
}

function closeDetail() {
  selectedItem.value = null;
}

function importPackage(_item: any) {
  showToast('SuperAgent import coming in a future update', 'info');
}

function onSearchInput() {
  debouncedSearch();
}
</script>

<template>
  <div class="explore-sa-page">
    <PageHeader title="Explore SuperAgents" subtitle="Discover and import SuperAgent packages from marketplace registries">
      <template #actions>
        <button class="btn-back" @click="router.push({ name: 'super-agents' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back to SuperAgents
        </button>
      </template>
    </PageHeader>

    <!-- Search Bar -->
    <div class="search-bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Search SuperAgent packages across marketplaces..."
        @input="onSearchInput"
      />
    </div>

    <!-- Results Section -->
    <div class="results-section">
      <div class="section-header">
        <h2 v-if="searchQuery.trim()">Results for "{{ searchQuery }}" ({{ results.length }})</h2>
        <h2 v-else>Available SuperAgent Packages ({{ results.length }})</h2>
      </div>

      <LoadingState v-if="isSearching" message="Searching..." />

      <EmptyState
        v-else-if="results.length === 0"
        title="No SuperAgent packages found"
        description="SuperAgent marketplace integration coming soon. Check back after marketplaces are configured to index SuperAgent packages."
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </template>
      </EmptyState>

      <!-- Results Grid -->
      <div v-else class="results-grid">
        <div
          v-for="item in results"
          :key="`${item.marketplace_id}-${item.name}`"
          class="result-card"
          @click="selectItem(item)"
        >
          <div class="result-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="8" r="4"/>
              <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
              <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
            </svg>
          </div>
          <div class="result-info">
            <div class="result-name-row">
              <h3>{{ item.name }}</h3>
              <span v-if="item.version" class="version-badge">v{{ item.version }}</span>
            </div>
            <p class="result-description">{{ item.description || 'No description' }}</p>
            <span v-if="item.marketplace_name" class="marketplace-badge">{{ item.marketplace_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail Panel -->
    <Teleport to="body">
      <div v-if="selectedItem" ref="detailModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-superagent-detail" tabindex="-1" @click.self="closeDetail" @keydown.escape="closeDetail">
        <div class="detail-panel">
          <div class="detail-header">
            <div class="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="8" r="4"/>
                <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
              </svg>
            </div>
            <div class="detail-title">
              <h2 id="modal-title-superagent-detail">{{ selectedItem.name }}</h2>
              <span v-if="selectedItem.version" class="version-badge">v{{ selectedItem.version }}</span>
            </div>
            <button class="close-btn" @click="closeDetail">&times;</button>
          </div>
          <div class="detail-body">
            <p class="detail-description">{{ selectedItem.description || 'No description available.' }}</p>
            <div class="detail-meta">
              <div v-if="selectedItem.marketplace_name" class="meta-row">
                <span class="meta-label">Marketplace</span>
                <span class="meta-value">{{ selectedItem.marketplace_name }}</span>
              </div>
              <div v-if="selectedItem.version" class="meta-row">
                <span class="meta-label">Version</span>
                <span class="meta-value">{{ selectedItem.version }}</span>
              </div>
            </div>
          </div>
          <div class="detail-footer">
            <button class="btn" @click="closeDetail">Close</button>
            <button class="btn btn-primary" @click="importPackage(selectedItem)">Import</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.explore-sa-page {
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

/* Search Bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  margin-bottom: 24px;
}

.search-bar > svg {
  width: 20px;
  height: 20px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-bar input {
  flex: 1;
  background: transparent;
  border: none;
  font-size: 14px;
  color: var(--text-primary);
}

.search-bar input:focus {
  outline: none;
}

.search-bar input::placeholder {
  color: var(--text-tertiary);
}

/* Results section */
.results-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.section-header {
  margin-bottom: 20px;
}

.section-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.result-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  transition: all 0.15s;
  cursor: pointer;
}

.result-card:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-elevated);
}

.result-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent-cyan-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.result-icon svg {
  width: 22px;
  height: 22px;
}

.result-info {
  flex: 1;
  min-width: 0;
}

.result-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.result-name-row h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.version-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  border-radius: 4px;
}

.result-description {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.marketplace-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(56, 139, 253, 0.1);
  color: #388bfd;
  border-radius: 4px;
  font-weight: 500;
}

/* Detail panel */
.detail-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  width: 100%;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.2s ease;
}

@keyframes slideIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.detail-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent-cyan-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.detail-icon svg {
  width: 22px;
  height: 22px;
}

.detail-title {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-title h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
  padding: 4px;
}

.close-btn:hover {
  color: var(--text-primary);
}

.detail-body {
  padding: 24px;
}

.detail-description {
  margin: 0 0 20px 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.meta-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}
</style>
