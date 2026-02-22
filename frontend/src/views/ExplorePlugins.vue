<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { MarketplaceSearchResult, Marketplace } from '../services/api';
import { marketplaceApi, pluginExportApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
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
const searchResults = ref<MarketplaceSearchResult[]>([]);
const isSearching = ref(false);
const isRefreshing = ref(false);

// Marketplace management state
const registeredMarketplaces = ref<Marketplace[]>([]);
const showAddModal = ref(false);
const newMarketplace = ref({ name: '', url: '', description: '' });

// Detail panel state
const selectedPlugin = ref<MarketplaceSearchResult | null>(null);
const isInstalling = ref(false);

const addModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addModalRef, showAddModal);
const detailModalRef = ref<HTMLElement | null>(null);
const detailModalOpen = computed(() => !!selectedPlugin.value);
useFocusTrap(detailModalRef, detailModalOpen);

useWebMcpTool({
  name: 'hive_explore_plugins_get_state',
  description: 'Returns the current state of the Explore Plugins page',
  page: 'ExplorePlugins',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ExplorePlugins',
        searchQuery: searchQuery.value,
        resultsCount: searchResults.value.length,
        isSearching: isSearching.value,
      }),
    }],
  }),
  deps: [searchQuery, searchResults, isSearching],
});

// Debounced search
let debounceTimer: ReturnType<typeof setTimeout>;

function debouncedSearch(query: string) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    performSearch(query);
  }, 300);
}

async function performSearch(query: string) {
  isSearching.value = true;
  try {
    const response = await marketplaceApi.search(query, 'plugin');
    searchResults.value = response.results;
  } catch (e) {
    searchResults.value = [];
  } finally {
    isSearching.value = false;
  }
}

function onSearchInput() {
  const q = searchQuery.value.trim();
  if (q.length >= 2 || q.length === 0) {
    debouncedSearch(q);
  }
}

async function refreshCache() {
  isRefreshing.value = true;
  try {
    await marketplaceApi.refreshCache();
    showToast('Marketplace cache refreshed', 'success');
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to refresh cache', 'error');
  } finally {
    isRefreshing.value = false;
  }
}

async function loadMarketplaces() {
  try {
    const response = await marketplaceApi.list();
    registeredMarketplaces.value = response.marketplaces;
  } catch (e) {
    // Silently fail - marketplace management is secondary
  }
}

async function addMarketplace() {
  if (!newMarketplace.value.name.trim() || !newMarketplace.value.url.trim()) {
    showToast('Name and URL are required', 'error');
    return;
  }
  try {
    await marketplaceApi.create({
      name: newMarketplace.value.name,
      url: newMarketplace.value.url,
      type: 'git',
    });
    showToast('Marketplace added', 'success');
    showAddModal.value = false;
    newMarketplace.value = { name: '', url: '', description: '' };
    await loadMarketplaces();
    // Re-search to include new marketplace
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to add marketplace', 'error');
  }
}

async function removeMarketplace(marketplaceId: string) {
  try {
    await marketplaceApi.delete(marketplaceId);
    showToast('Marketplace removed', 'success');
    await loadMarketplaces();
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to remove marketplace', 'error');
  }
}

function selectPlugin(plugin: MarketplaceSearchResult) {
  selectedPlugin.value = plugin;
}

function closeDetail() {
  selectedPlugin.value = null;
}

async function installPlugin(plugin: MarketplaceSearchResult) {
  isInstalling.value = true;
  try {
    await pluginExportApi.importFromMarketplace({
      marketplace_id: plugin.marketplace_id,
      remote_plugin_name: plugin.name,
    });
    showToast(`Installed "${plugin.name}" successfully`, 'success');
    // Mark as installed in local state
    plugin.installed = true;
    selectedPlugin.value = null;
    // Refresh search results to reflect installation
    await performSearch(searchQuery.value.trim());
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to install plugin';
    showToast(message, 'error');
  } finally {
    isInstalling.value = false;
  }
}

onMounted(async () => {
  await loadMarketplaces();
  await performSearch('');
});
</script>

<template>
  <div class="explore-page">
    <AppBreadcrumb :items="[{ label: 'Plugins', action: () => router.push({ name: 'plugins' }) }, { label: 'Explore' }]" />
    <PageHeader title="Explore Plugins" subtitle="Search plugins across all registered marketplace registries">
      <template #actions>
        <button class="btn-back" @click="router.push({ name: 'plugins' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back to Plugins
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
        placeholder="Search plugins across all marketplaces..."
        @input="onSearchInput"
      />
      <button class="refresh-btn" :disabled="isRefreshing" title="Refresh marketplace data" @click="refreshCache">
        <svg :class="{ spinning: isRefreshing }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
      </button>
    </div>

    <!-- Search Results -->
    <div class="results-section">
      <div class="section-header">
        <h2>
          <template v-if="searchQuery.trim()">
            Results for "{{ searchQuery }}" ({{ searchResults.length }})
          </template>
          <template v-else>
            All Available Plugins ({{ searchResults.length }})
          </template>
        </h2>
      </div>

      <LoadingState v-if="isSearching" message="Searching plugins..." />

      <EmptyState
        v-else-if="searchResults.length === 0"
        title="No plugins found"
        description="Try a different search term or add more marketplace registries."
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
          v-for="plugin in searchResults"
          :key="`${plugin.marketplace_id}-${plugin.name}`"
          class="plugin-card"
          style="cursor: pointer;"
          @click="selectPlugin(plugin)"
        >
          <div class="plugin-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <path d="M3 9h18M9 21V9"/>
            </svg>
          </div>
          <div class="plugin-info">
            <div class="plugin-name-row">
              <h3>{{ plugin.name }}</h3>
              <span v-if="plugin.version" class="version-badge">v{{ plugin.version }}</span>
              <span v-if="plugin.installed" class="installed-badge">Installed</span>
            </div>
            <p class="plugin-description">{{ plugin.description || 'No description' }}</p>
            <span class="marketplace-badge">{{ plugin.marketplace_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Manage Marketplace Registries -->
    <div class="registries-section">
      <div class="section-header">
        <h2>Manage Marketplace Registries ({{ registeredMarketplaces.length }})</h2>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Registry
        </button>
      </div>

      <EmptyState
        v-if="registeredMarketplaces.length === 0"
        title="No registries"
        description="No marketplace registries registered. Add a registry to start discovering plugins."
      />

      <div v-else class="registries-list">
        <div
          v-for="marketplace in registeredMarketplaces"
          :key="marketplace.id"
          class="registry-row"
        >
          <div class="registry-icon">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
          </div>
          <div class="registry-info">
            <span class="registry-name">{{ marketplace.name }}</span>
            <span class="registry-url">{{ marketplace.url }}</span>
          </div>
          <button class="remove-btn" title="Remove registry" @click="removeMarketplace(marketplace.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Add Marketplace Modal -->
    <Teleport to="body">
      <div v-if="showAddModal" ref="addModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-marketplace" tabindex="-1" @click.self="showAddModal = false" @keydown.escape="showAddModal = false">
        <div class="modal">
          <h2 id="modal-title-add-marketplace">Add Marketplace Registry</h2>
          <form @submit.prevent="addMarketplace">
            <div class="form-group">
              <label for="marketplace-name">Name *</label>
              <input
                id="marketplace-name"
                v-model="newMarketplace.name"
                type="text"
                placeholder="My Plugin Repository"
                required
              />
            </div>
            <div class="form-group">
              <label for="marketplace-url">Git URL *</label>
              <input
                id="marketplace-url"
                v-model="newMarketplace.url"
                type="url"
                placeholder="https://github.com/user/repo"
                required
              />
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showAddModal = false">Cancel</button>
              <button type="submit" class="btn btn-primary">Add Registry</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>

    <!-- Plugin Detail Panel -->
    <Teleport to="body">
      <div v-if="selectedPlugin" ref="detailModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-plugin-detail" tabindex="-1" @click.self="closeDetail" @keydown.escape="closeDetail">
        <div class="detail-panel">
          <div class="detail-header">
            <div class="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <path d="M3 9h18M9 21V9"/>
              </svg>
            </div>
            <div class="detail-title">
              <h2 id="modal-title-plugin-detail">{{ selectedPlugin.name }}</h2>
              <span v-if="selectedPlugin.version" class="version-badge">v{{ selectedPlugin.version }}</span>
            </div>
            <button class="close-btn" @click="closeDetail">&times;</button>
          </div>
          <div class="detail-body">
            <p class="detail-description">{{ selectedPlugin.description || 'No description available.' }}</p>
            <div class="detail-meta">
              <div class="meta-row">
                <span class="meta-label">Marketplace</span>
                <span class="meta-value">{{ selectedPlugin.marketplace_name }}</span>
              </div>
              <div v-if="selectedPlugin.version" class="meta-row">
                <span class="meta-label">Version</span>
                <span class="meta-value">{{ selectedPlugin.version }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Status</span>
                <span :class="['meta-value', selectedPlugin.installed ? 'installed' : 'available']">
                  {{ selectedPlugin.installed ? 'Installed' : 'Available' }}
                </span>
              </div>
            </div>
          </div>
          <div class="detail-footer">
            <button class="btn" @click="closeDetail">Close</button>
            <button
              v-if="!selectedPlugin.installed"
              class="btn btn-primary"
              :disabled="isInstalling"
              @click="installPlugin(selectedPlugin)"
            >
              {{ isInstalling ? 'Installing...' : 'Install Plugin' }}
            </button>
            <span v-else class="already-installed">Already installed</span>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.explore-page {
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

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.refresh-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

/* Results section */
.results-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.plugin-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  transition: all 0.15s;
}

.plugin-card:hover {
  border-color: var(--accent-emerald);
  background: var(--bg-elevated);
}

.plugin-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-emerald);
}

.plugin-icon svg {
  width: 22px;
  height: 22px;
}

.plugin-info {
  flex: 1;
  min-width: 0;
}

.plugin-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.plugin-name-row h3 {
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

.installed-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.1));
  color: var(--accent-emerald);
  border-radius: 4px;
  font-weight: 500;
}

.plugin-description {
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
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 4px;
  font-weight: 500;
}

/* Registries section */
.registries-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.registries-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.registry-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.registry-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-violet);
}

.registry-icon svg {
  width: 16px;
  height: 16px;
}

.registry-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.registry-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.registry-url {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.remove-btn:hover {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.remove-btn svg {
  width: 14px;
  height: 14px;
}

/* Buttons */
.btn-primary {
  background: var(--accent-emerald);
  color: #000;
}

.btn-primary:hover {
  background: #00ff99;
  color: #000;
}

/* Modal styles */
.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  max-width: 450px;
  width: 90%;
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
}

/* Plugin Detail Panel */
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
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-emerald);
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

.meta-value.installed {
  color: var(--accent-emerald);
}

.meta-value.available {
  color: var(--accent-blue, #388bfd);
}

.detail-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.already-installed {
  font-size: 13px;
  color: var(--accent-emerald);
  font-weight: 500;
}
</style>
