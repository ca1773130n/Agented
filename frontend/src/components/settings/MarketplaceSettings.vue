<script setup lang="ts">
import { ref } from 'vue';
import type { Marketplace, MarketplacePlugin, Plugin } from '../../services/api';
import { marketplaceApi, pluginApi, pluginExportApi, ApiError } from '../../services/api';
import ConfirmModal from '../base/ConfirmModal.vue';
import { useToast } from '../../composables/useToast';

defineProps<{
  marketplaces: Marketplace[];
}>();

const emit = defineEmits<{
  (e: 'refreshed'): void;
  (e: 'show-add-modal'): void;
}>();

const showToast = useToast();

// Selected marketplace for plugin management
const selectedMarketplace = ref<Marketplace | null>(null);
const marketplacePlugins = ref<MarketplacePlugin[]>([]);
const loadingPlugins = ref(false);
const isLoading = ref(false);

// Test connection results per marketplace
const testResults = ref<Map<string, { connected: boolean; message: string }>>(new Map());
const testingConnection = ref<string | null>(null);

// Deploy form state
const showDeployForm = ref<string | null>(null);
const availablePlugins = ref<Plugin[]>([]);
const deployPluginId = ref('');
const deployVersion = ref('1.0.0');
const isDeploying = ref(false);

// Refresh marketplace state
const refreshingMarketplace = ref<string | null>(null);

// Discovered plugins from marketplace repo
interface DiscoveredPlugin {
  name: string;
  description?: string;
  version?: string;
  source?: string;
  installed: boolean;
}
const discoveredPlugins = ref<DiscoveredPlugin[]>([]);
const installingPlugin = ref<string | null>(null);

// Confirm delete/uninstall state
const showDeleteMarketplaceConfirm = ref(false);
const pendingDeleteMarketplace = ref<Marketplace | null>(null);
const showUninstallConfirm = ref(false);
const pendingUninstallPlugin = ref<MarketplacePlugin | null>(null);

async function selectMarketplace(marketplace: Marketplace) {
  selectedMarketplace.value = marketplace;
  loadingPlugins.value = true;
  try {
    const data = await marketplaceApi.listPlugins(marketplace.id);
    marketplacePlugins.value = data.plugins || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load plugins';
    showToast(message, 'error');
    marketplacePlugins.value = [];
  } finally {
    loadingPlugins.value = false;
  }
  // Auto-discover available plugins (uses 5-min cache)
  refreshMarketplace(marketplace);
}

function deleteMarketplace(marketplace: Marketplace) {
  pendingDeleteMarketplace.value = marketplace;
  showDeleteMarketplaceConfirm.value = true;
}

async function confirmDeleteMarketplace() {
  const marketplace = pendingDeleteMarketplace.value;
  showDeleteMarketplaceConfirm.value = false;
  pendingDeleteMarketplace.value = null;
  if (!marketplace) return;
  try {
    await marketplaceApi.delete(marketplace.id);
    showToast('Marketplace deleted', 'success');
    if (selectedMarketplace.value?.id === marketplace.id) {
      selectedMarketplace.value = null;
      marketplacePlugins.value = [];
    }
    emit('refreshed');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete marketplace';
    showToast(message, 'error');
  }
}

function uninstallPlugin(plugin: MarketplacePlugin) {
  if (!selectedMarketplace.value) return;
  pendingUninstallPlugin.value = plugin;
  showUninstallConfirm.value = true;
}

async function confirmUninstallPlugin() {
  const plugin = pendingUninstallPlugin.value;
  showUninstallConfirm.value = false;
  pendingUninstallPlugin.value = null;
  if (!plugin || !selectedMarketplace.value) return;
  try {
    await marketplaceApi.uninstallPlugin(selectedMarketplace.value.id, plugin.id);
    showToast('Plugin uninstalled', 'success');
    await selectMarketplace(selectedMarketplace.value);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to uninstall plugin';
    showToast(message, 'error');
  }
}

async function testConnection(marketplaceId: string) {
  testingConnection.value = marketplaceId;
  try {
    const result = await pluginExportApi.testConnection(marketplaceId);
    testResults.value.set(marketplaceId, result);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Connection test failed';
    testResults.value.set(marketplaceId, { connected: false, message });
  } finally {
    testingConnection.value = null;
  }
}

async function deployPlugin(marketplaceId: string) {
  if (!deployPluginId.value) {
    showToast('Please select a plugin to deploy', 'error');
    return;
  }
  isDeploying.value = true;
  try {
    const result = await pluginExportApi.deploy({
      plugin_id: deployPluginId.value,
      marketplace_id: marketplaceId,
      version: deployVersion.value || undefined,
    });
    showToast(`Deployed "${result.plugin_name}" successfully`, 'success');
    showDeployForm.value = null;
    deployPluginId.value = '';
    deployVersion.value = '1.0.0';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Deploy failed';
    showToast(message, 'error');
  } finally {
    isDeploying.value = false;
  }
}

async function refreshMarketplace(marketplace: Marketplace) {
  refreshingMarketplace.value = marketplace.id;
  try {
    const result = await marketplaceApi.discoverPlugins(marketplace.id);
    discoveredPlugins.value = result.plugins || [];
    // Also reload installed plugins
    const data = await marketplaceApi.listPlugins(marketplace.id);
    if (selectedMarketplace.value?.id === marketplace.id) {
      marketplacePlugins.value = data.plugins || [];
    }
    showToast(`Found ${result.total} plugin(s) in "${marketplace.name}"`, 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to discover plugins';
    showToast(message, 'error');
  } finally {
    refreshingMarketplace.value = null;
  }
}

async function installPlugin(pluginName: string) {
  if (!selectedMarketplace.value) return;
  installingPlugin.value = pluginName;
  try {
    await pluginExportApi.importFromMarketplace({
      marketplace_id: selectedMarketplace.value.id,
      remote_plugin_name: pluginName,
    });
    showToast(`Installed "${pluginName}"`, 'success');
    // Refresh both lists
    await refreshMarketplace(selectedMarketplace.value);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to install plugin';
    showToast(message, 'error');
  } finally {
    installingPlugin.value = null;
  }
}

async function loadAvailablePlugins() {
  try {
    const data = await pluginApi.list();
    availablePlugins.value = data.plugins || [];
  } catch {
    availablePlugins.value = [];
  }
}

function getTypeLabel(type: string): string {
  switch (type) {
    case 'git': return 'Git Repository';
    case 'http': return 'HTTP Endpoint';
    case 'local': return 'Local Directory';
    default: return type;
  }
}

// Load available plugins for deploy form on mount
loadAvailablePlugins();
</script>

<template>
  <div class="tab-content">
    <div class="marketplaces-layout">
      <!-- Marketplaces List -->
      <div class="card marketplaces-list">
        <div class="card-header">
          <h3>Marketplaces</h3>
          <button class="btn btn-primary btn-sm" @click="emit('show-add-modal')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Add
          </button>
        </div>

        <div v-if="isLoading" class="loading-state">
          <div class="spinner"></div>
          <span>Loading...</span>
        </div>

        <div v-else-if="marketplaces.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            </svg>
          </div>
          <p>No marketplaces configured</p>
          <span>Add a marketplace to install plugins</span>
        </div>

        <div v-else class="list">
          <div
            v-for="marketplace in marketplaces"
            :key="marketplace.id"
            :class="['list-item', { active: selectedMarketplace?.id === marketplace.id }]"
            @click="selectMarketplace(marketplace)"
          >
            <div class="item-info">
              <div class="item-name">
                {{ marketplace.name }}
                <span v-if="marketplace.is_default" class="badge default">Default</span>
              </div>
              <div class="item-meta">{{ getTypeLabel(marketplace.type) }}</div>
            </div>
            <div class="item-actions">
              <button
                class="btn-icon btn-test"
                @click.stop="testConnection(marketplace.id)"
                :disabled="testingConnection === marketplace.id"
                title="Test Connection"
              >
                <div v-if="testingConnection === marketplace.id" class="spinner-xs"></div>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
              </button>
              <button
                class="btn-icon btn-refresh"
                @click.stop="refreshMarketplace(marketplace)"
                :disabled="refreshingMarketplace === marketplace.id"
                title="Refresh Plugins"
              >
                <div v-if="refreshingMarketplace === marketplace.id" class="spinner-xs"></div>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="23 4 23 10 17 10"/>
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                </svg>
              </button>
              <button
                class="btn-icon btn-deploy"
                @click.stop="showDeployForm = showDeployForm === marketplace.id ? null : marketplace.id"
                title="Deploy Plugin"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </button>
              <button
                class="btn-icon btn-danger"
                @click.stop="deleteMarketplace(marketplace)"
                title="Delete"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </div>

            <!-- Test connection result -->
            <div v-if="testResults.has(marketplace.id)" class="test-result" @click.stop>
              <span v-if="testResults.get(marketplace.id)?.connected" class="test-success">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="test-icon">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                Connected
              </span>
              <span v-else class="test-failure">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="test-icon">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                {{ testResults.get(marketplace.id)?.message || 'Connection failed' }}
              </span>
            </div>

            <!-- Deploy form -->
            <div v-if="showDeployForm === marketplace.id" class="deploy-form" @click.stop>
              <div class="deploy-form-group">
                <label>Plugin</label>
                <select v-model="deployPluginId">
                  <option value="">Select a plugin...</option>
                  <option v-for="plugin in availablePlugins" :key="plugin.id" :value="plugin.id">
                    {{ plugin.name }} (v{{ plugin.version }})
                  </option>
                </select>
              </div>
              <div class="deploy-form-group">
                <label>Version</label>
                <input v-model="deployVersion" type="text" placeholder="1.0.0" />
              </div>
              <div class="deploy-form-actions">
                <button class="btn btn-sm btn-secondary" @click="showDeployForm = null">Cancel</button>
                <button
                  class="btn btn-sm btn-primary"
                  :disabled="!deployPluginId || isDeploying"
                  @click="deployPlugin(marketplace.id)"
                >
                  {{ isDeploying ? 'Deploying...' : 'Deploy' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Plugins Panel -->
      <div class="card plugins-panel">
        <div v-if="!selectedMarketplace" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
          </div>
          <p>Select a marketplace</p>
          <span>View and manage installed plugins</span>
        </div>

        <template v-else>
          <div class="card-header">
            <h3>{{ selectedMarketplace.name }} Plugins</h3>
            <span class="url-display">{{ selectedMarketplace.url }}</span>
          </div>

          <div v-if="loadingPlugins" class="loading-state">
            <div class="spinner"></div>
            <span>Loading plugins...</span>
          </div>

          <div v-else-if="marketplacePlugins.length === 0" class="empty-state">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>
            <p>No plugins installed</p>
            <span>Plugins from this marketplace will appear here</span>
          </div>

          <div v-else class="list">
            <div v-for="plugin in marketplacePlugins" :key="plugin.id" class="list-item plugin-item">
              <div class="item-info">
                <div class="item-name">{{ plugin.remote_name }}</div>
                <div class="item-meta">
                  <span v-if="plugin.version">v{{ plugin.version }}</span>
                  <span v-if="plugin.installed_at">Installed {{ new Date(plugin.installed_at).toLocaleDateString() }}</span>
                </div>
              </div>
              <button class="btn-icon btn-danger" @click="uninstallPlugin(plugin)" title="Uninstall">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- Available Plugins (from discovery) -->
          <div v-if="discoveredPlugins.length > 0" class="discovered-section">
            <div class="card-header discovered-header">
              <h3>Available Plugins</h3>
              <span class="plugin-count">{{ discoveredPlugins.filter(p => !p.installed).length }} available</span>
            </div>
            <div v-if="discoveredPlugins.filter(p => !p.installed).length === 0" class="empty-state-inline">
              <p class="muted">All plugins are already installed</p>
            </div>
            <div v-else class="list">
              <div v-for="plugin in discoveredPlugins.filter(p => !p.installed)" :key="plugin.name" class="list-item plugin-item">
                <div class="item-info">
                  <div class="item-name">{{ plugin.name }}</div>
                  <div class="item-meta">
                    <span v-if="plugin.version">v{{ plugin.version }}</span>
                    <span v-if="plugin.description">{{ plugin.description }}</span>
                  </div>
                </div>
                <button
                  class="btn btn-sm btn-primary"
                  :disabled="installingPlugin === plugin.name"
                  @click="installPlugin(plugin.name)"
                >
                  {{ installingPlugin === plugin.name ? 'Installing...' : 'Install' }}
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <ConfirmModal
      :open="showDeleteMarketplaceConfirm"
      title="Delete Marketplace"
      :message="pendingDeleteMarketplace ? 'Delete \u201C' + pendingDeleteMarketplace.name + '\u201D? This will also remove installed plugin references.' : 'Delete this marketplace?'"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDeleteMarketplace"
      @cancel="showDeleteMarketplaceConfirm = false"
    />

    <ConfirmModal
      :open="showUninstallConfirm"
      title="Uninstall Plugin"
      :message="pendingUninstallPlugin ? 'Uninstall \u201C' + pendingUninstallPlugin.remote_name + '\u201D?' : 'Uninstall this plugin?'"
      confirm-label="Uninstall"
      variant="danger"
      @confirm="confirmUninstallPlugin"
      @cancel="showUninstallConfirm = false"
    />
  </div>
</template>

<style scoped>
/* Marketplaces Layout */
.marketplaces-layout {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 1.5rem;
}

@media (max-width: 900px) {
  .marketplaces-layout {
    grid-template-columns: 1fr;
  }
}

/* Cards */
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.muted {
  color: var(--text-tertiary, #666);
  font-size: 0.9rem;
}

/* List */
.list {
  display: flex;
  flex-direction: column;
}

.list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.15s;
  flex-wrap: wrap;
}

.list-item:last-child {
  border-bottom: none;
}

.list-item:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.list-item.active {
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  border-left: 3px solid var(--accent-cyan, #00d4ff);
}

.item-info {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-weight: 500;
  color: var(--text-primary, #fff);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.item-meta {
  font-size: 0.8rem;
  color: var(--text-tertiary, #666);
  margin-top: 0.25rem;
  display: flex;
  gap: 1rem;
}

.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.default {
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.15));
  color: var(--accent-emerald, #00ff88);
}

.url-display {
  font-size: 0.75rem;
  color: var(--text-tertiary, #666);
  font-family: var(--font-mono);
}

/* Empty/Loading States */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted, #555);
  margin-bottom: 1rem;
}

.empty-icon svg {
  width: 100%;
  height: 100%;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary, #666);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

.loading-state span {
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
}

/* Buttons */
.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan, #00d4ff);
}

.btn-sm {
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
}

.btn-icon {
  width: 32px;
  height: 32px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary, #666);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-icon svg {
  width: 16px;
  height: 16px;
}

.btn-icon:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.btn-icon.btn-danger:hover {
  background: rgba(255, 77, 77, 0.15);
  color: #ff4d4d;
}

/* Marketplace item actions */
.item-actions {
  display: flex;
  gap: 0.25rem;
  align-items: center;
}

.btn-icon.btn-test:hover {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}

.btn-icon.btn-refresh:hover {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}

.btn-icon.btn-deploy:hover {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
}

.spinner-xs {
  width: 14px;
  height: 14px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Test connection result */
.test-result {
  padding: 0.5rem 1.25rem;
  font-size: 0.8rem;
  width: 100%;
}

.test-success {
  color: var(--accent-emerald, #00ff88);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.test-failure {
  color: #ff4d4d;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.test-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

/* Deploy form */
.deploy-form {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border-default);
  background: var(--bg-tertiary, #1a1a24);
  width: 100%;
}

.deploy-form-group {
  margin-bottom: 0.75rem;
}

.deploy-form-group label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  margin-bottom: 0.35rem;
}

.deploy-form-group select,
.deploy-form-group input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary, #fff);
  font-size: 0.85rem;
}

.deploy-form-group select:focus,
.deploy-form-group input:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.deploy-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

/* Discovered plugins section */
.discovered-section {
  border-top: 1px solid var(--border-default);
  margin-top: 0;
}

.discovered-header {
  background: var(--bg-tertiary, #1a1a24);
}

.plugin-count {
  font-size: 0.75rem;
  color: var(--text-tertiary, #666);
}

.empty-state-inline {
  padding: 1.5rem;
  text-align: center;
}
</style>
