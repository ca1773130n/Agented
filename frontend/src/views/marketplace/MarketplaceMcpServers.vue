<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { MarketplaceSearchResult } from '../../services/api';
import { marketplaceApi, mcpServerApi, ApiError } from '../../services/api';
import LoadingState from '../../components/base/LoadingState.vue';
import EmptyState from '../../components/base/EmptyState.vue';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';
import { useWebMcpTool } from '../../composables/useWebMcpTool';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const showToast = useToast();

const searchQuery = ref('');
const searchResults = ref<MarketplaceSearchResult[]>([]);
const isSearching = ref(false);
const isRefreshing = ref(false);

const selectedServer = ref<MarketplaceSearchResult | null>(null);
const isInstalling = ref(false);
const detailModalRef = ref<HTMLElement | null>(null);
const hasSelectedServer = computed(() => !!selectedServer.value);

useFocusTrap(detailModalRef, hasSelectedServer);

const showInstallForm = ref(false);
const installForm = ref({
  server_type: 'stdio' as string,
  command: '',
  args: '',
  url: '',
  env_json: '',
  timeout_ms: 30000,
});

useWebMcpTool({
  name: 'agented_marketplace_mcp_servers_get_state',
  description: 'Returns the current state of the Marketplace MCP Servers tab',
  page: 'MarketplaceMcpServers',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'MarketplaceMcpServers',
        availableServersCount: searchResults.value.length,
        isLoading: isSearching.value,
      }),
    }],
  }),
  deps: [searchResults, isSearching],
});

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
    showToast(t('marketplaceMcpServers.toast.cacheRefreshed'), 'success');
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast(t('marketplaceMcpServers.toast.cacheRefreshFailed'), 'error');
  } finally {
    isRefreshing.value = false;
  }
}

function selectServer(server: MarketplaceSearchResult) {
  selectedServer.value = server;
  showInstallForm.value = false;
}

function closeDetail() {
  selectedServer.value = null;
  showInstallForm.value = false;
}

function openInstallForm() {
  installForm.value = {
    server_type: 'stdio',
    command: '',
    args: '',
    url: '',
    env_json: '',
    timeout_ms: 30000,
  };
  showInstallForm.value = true;
}

async function installServer(server: MarketplaceSearchResult) {
  isInstalling.value = true;
  try {
    await mcpServerApi.create({
      name: server.name,
      description: server.description || undefined,
      server_type: installForm.value.server_type,
      command: installForm.value.command || undefined,
      args: installForm.value.args || undefined,
      url: installForm.value.url || undefined,
      env_json: installForm.value.env_json || undefined,
      timeout_ms: installForm.value.timeout_ms,
    });
    showToast(t('marketplaceMcpServers.toast.installed', { name: server.name }), 'success');
    server.installed = true;
    selectedServer.value = null;
    showInstallForm.value = false;
    await performSearch(searchQuery.value.trim());
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('marketplaceMcpServers.toast.installFailed');
    showToast(message, 'error');
  } finally {
    isInstalling.value = false;
  }
}

onMounted(async () => {
  await performSearch('');
});
</script>

<template>
  <div class="marketplace-pane">
    <!-- Search Bar -->
    <div class="search-bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="t('marketplaceMcpServers.searchPlaceholder')"
        @input="onSearchInput"
      />
      <button class="refresh-btn" :disabled="isRefreshing" :title="t('marketplaceMcpServers.refreshTitle')" @click="refreshCache">
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
            {{ t('marketplaceMcpServers.resultsFor', { query: searchQuery, count: searchResults.length }) }}
          </template>
          <template v-else>
            {{ t('marketplaceMcpServers.allAvailable', { count: searchResults.length }) }}
          </template>
        </h2>
      </div>

      <LoadingState v-if="isSearching" :message="t('marketplaceMcpServers.searching')" />

      <EmptyState
        v-else-if="searchResults.length === 0"
        :title="t('marketplaceMcpServers.emptyTitle')"
        :description="t('marketplaceMcpServers.emptyDescription')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </template>
      </EmptyState>

      <div v-else class="results-grid">
        <div
          v-for="result in searchResults"
          :key="`${result.marketplace_id}-${result.name}`"
          class="server-card"
          style="cursor: pointer;"
          @click="selectServer(result)"
        >
          <div class="server-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="2" width="20" height="8" rx="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2"/>
              <circle cx="6" cy="6" r="1" fill="currentColor"/>
              <circle cx="6" cy="18" r="1" fill="currentColor"/>
            </svg>
          </div>
          <div class="server-info">
            <div class="server-name-row">
              <h3>{{ result.name }}</h3>
              <span v-if="result.version" class="version-badge">v{{ result.version }}</span>
              <span v-if="result.installed" class="installed-badge">{{ t('marketplaceMcpServers.installedBadge') }}</span>
            </div>
            <p class="server-description">{{ result.description || t('marketplaceMcpServers.noDescription') }}</p>
            <span class="marketplace-badge">{{ result.marketplace_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Server Detail Panel -->
    <Teleport to="body">
      <div
        v-if="selectedServer"
        ref="detailModalRef"
        class="modal-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title-mcp-detail"
        tabindex="-1"
        @click.self="closeDetail"
        @keydown.escape="closeDetail"
      >
        <div class="detail-panel">
          <div class="detail-header">
            <div class="detail-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="2" width="20" height="8" rx="2"/>
                <rect x="2" y="14" width="20" height="8" rx="2"/>
                <circle cx="6" cy="6" r="1" fill="currentColor"/>
                <circle cx="6" cy="18" r="1" fill="currentColor"/>
              </svg>
            </div>
            <div class="detail-title">
              <h2 id="modal-title-mcp-detail">{{ selectedServer.name }}</h2>
              <span v-if="selectedServer.version" class="version-badge">v{{ selectedServer.version }}</span>
            </div>
            <button class="close-btn" @click="closeDetail">&times;</button>
          </div>
          <div class="detail-body">
            <p class="detail-description">{{ selectedServer.description || t('marketplaceMcpServers.noDescriptionAvailable') }}</p>
            <div class="detail-meta">
              <div class="meta-row">
                <span class="meta-label">{{ t('marketplaceMcpServers.marketplace') }}</span>
                <span class="meta-value">{{ selectedServer.marketplace_name }}</span>
              </div>
              <div v-if="selectedServer.version" class="meta-row">
                <span class="meta-label">{{ t('marketplaceMcpServers.version') }}</span>
                <span class="meta-value">{{ selectedServer.version }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">{{ t('marketplaceMcpServers.status') }}</span>
                <span :class="['meta-value', selectedServer.installed ? 'installed' : 'available']">
                  {{ selectedServer.installed ? t('marketplaceMcpServers.installedBadge') : t('marketplaceMcpServers.available') }}
                </span>
              </div>
            </div>

            <div v-if="showInstallForm && !selectedServer.installed" class="install-config">
              <h3 class="config-title">{{ t('marketplaceMcpServers.form.configuration') }}</h3>
              <div class="form-group">
                <label>{{ t('marketplaceMcpServers.form.serverType') }}</label>
                <select v-model="installForm.server_type">
                  <option value="stdio">stdio</option>
                  <option value="sse">sse</option>
                  <option value="http">http</option>
                </select>
              </div>
              <div v-if="installForm.server_type === 'stdio'" class="form-group">
                <label>{{ t('marketplaceMcpServers.form.command') }}</label>
                <input v-model="installForm.command" type="text" placeholder="e.g., npx -y @modelcontextprotocol/server-filesystem" />
              </div>
              <div v-if="installForm.server_type === 'stdio'" class="form-group">
                <label>{{ t('marketplaceMcpServers.form.arguments') }}</label>
                <input v-model="installForm.args" type="text" placeholder="e.g., /path/to/allowed/dir" />
              </div>
              <div v-if="installForm.server_type !== 'stdio'" class="form-group">
                <label>{{ t('marketplaceMcpServers.form.url') }}</label>
                <input v-model="installForm.url" type="text" placeholder="e.g., http://localhost:3001/sse" />
              </div>
              <div class="form-group">
                <label>{{ t('marketplaceMcpServers.form.envVars') }}</label>
                <textarea v-model="installForm.env_json" placeholder='{"API_KEY": "your-key"}'></textarea>
              </div>
              <div class="form-group">
                <label>{{ t('marketplaceMcpServers.form.timeout') }}</label>
                <input v-model.number="installForm.timeout_ms" type="number" placeholder="30000" />
              </div>
            </div>
          </div>
          <div class="detail-footer">
            <button class="btn" @click="closeDetail">{{ t('common.close') }}</button>
            <template v-if="!selectedServer.installed">
              <button
                v-if="!showInstallForm"
                class="btn btn-primary"
                @click="openInstallForm()"
              >
                {{ t('marketplaceMcpServers.installAsMcp') }}
              </button>
              <template v-else>
                <button class="btn" @click="showInstallForm = false">{{ t('common.back') }}</button>
                <button
                  class="btn btn-primary"
                  :disabled="isInstalling"
                  @click="installServer(selectedServer)"
                >
                  {{ isInstalling ? t('marketplaceMcpServers.installing') : t('marketplaceMcpServers.install') }}
                </button>
              </template>
            </template>
            <span v-else class="already-installed">{{ t('marketplaceMcpServers.alreadyInstalled') }}</span>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.marketplace-pane {
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

.server-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  transition: all 0.15s;
}

.server-card:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-elevated);
}

.server-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.server-icon svg {
  width: 22px;
  height: 22px;
}

.server-info {
  flex: 1;
  min-width: 0;
}

.server-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.server-name-row h3 {
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
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  color: var(--accent-cyan);
  border-radius: 4px;
  font-weight: 500;
}

.server-description {
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

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover {
  background: #00c4ee;
  color: #000;
}

.form-group {
  margin-bottom: 12px;
}

.form-group label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-group textarea {
  min-height: 60px;
  resize: vertical;
  font-family: var(--font-mono, monospace);
  font-size: 13px;
}

.install-config {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border-default);
}

.config-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

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
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
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

.meta-value.installed {
  color: var(--accent-cyan);
}

.meta-value.available {
  color: #388bfd;
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
  color: var(--accent-cyan);
  font-weight: 500;
}
</style>
