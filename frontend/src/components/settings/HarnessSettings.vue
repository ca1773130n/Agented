<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { Marketplace, MarketplacePlugin } from '../../services/api';
import { settingsApi, marketplaceApi, pluginApi, pluginExportApi, ApiError } from '../../services/api';
import SyncStatusPanel from '../plugins/SyncStatusPanel.vue';
import { useToast } from '../../composables/useToast';

defineProps<{
  marketplaces: Marketplace[];
}>();

const showToast = useToast();

// Harness plugin settings
const harnessMarketplaceId = ref<string | null>(null);
const harnessPluginName = ref<string>('');
const harnessPluginsList = ref<MarketplacePlugin[]>([]);
const loadingHarnessSettings = ref(false);
const savingHarnessSettings = ref(false);

// Sync panel state -- exported plugins with export records
const exportedPlugins = ref<Array<{ plugin_id: string; plugin_name: string; export_path: string }>>([]);
const loadingExportedPlugins = ref(false);

async function loadHarnessSettings() {
  loadingHarnessSettings.value = true;
  try {
    const data = await settingsApi.getHarnessPlugin();
    harnessMarketplaceId.value = data.marketplace_id || null;
    harnessPluginName.value = data.plugin_name || '';
    // Load plugins for the selected marketplace if set
    if (harnessMarketplaceId.value) {
      await loadHarnessPlugins(harnessMarketplaceId.value);
    }
  } catch (err) {
    // Settings not configured yet, that's okay
    harnessMarketplaceId.value = null;
    harnessPluginName.value = '';
  } finally {
    loadingHarnessSettings.value = false;
  }
}

async function loadHarnessPlugins(marketplaceId: string) {
  try {
    const data = await marketplaceApi.listPlugins(marketplaceId);
    harnessPluginsList.value = data.plugins || [];
  } catch (err) {
    harnessPluginsList.value = [];
  }
}

async function onHarnessMarketplaceChange(marketplaceId: string) {
  harnessMarketplaceId.value = marketplaceId;
  harnessPluginName.value = '';
  harnessPluginsList.value = [];
  if (marketplaceId) {
    await loadHarnessPlugins(marketplaceId);
  }
}

async function saveHarnessSettings() {
  if (!harnessMarketplaceId.value || !harnessPluginName.value) {
    showToast('Please select a marketplace and plugin', 'error');
    return;
  }
  savingHarnessSettings.value = true;
  try {
    await settingsApi.setHarnessPlugin({
      marketplace_id: harnessMarketplaceId.value,
      plugin_name: harnessPluginName.value,
    });
    showToast('Harness plugin settings saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save settings';
    showToast(message, 'error');
  } finally {
    savingHarnessSettings.value = false;
  }
}

async function loadExportedPlugins() {
  loadingExportedPlugins.value = true;
  try {
    const data = await pluginApi.list();
    const plugins = data.plugins || [];
    const exported: Array<{ plugin_id: string; plugin_name: string; export_path: string }> = [];
    for (const plugin of plugins) {
      try {
        const exportsData = await pluginExportApi.listExports(plugin.id);
        const records = exportsData.exports || [];
        if (records.length > 0) {
          const latest = records[records.length - 1];
          if (latest.export_path) {
            exported.push({
              plugin_id: plugin.id,
              plugin_name: plugin.name,
              export_path: latest.export_path,
            });
          }
        }
      } catch {
        // Skip plugins that fail to load exports
      }
    }
    exportedPlugins.value = exported;
  } catch {
    exportedPlugins.value = [];
  } finally {
    loadingExportedPlugins.value = false;
  }
}

onMounted(() => {
  loadHarnessSettings();
  loadExportedPlugins();
});
</script>

<template>
  <div class="tab-content">
    <div class="card">
      <div class="card-header">
        <h3>Harness Integration Plugin</h3>
      </div>
      <div class="card-body">
        <p class="description">
          Select which marketplace plugin to use for harness integration.
          This plugin will be used when loading skills from or deploying to the marketplace.
        </p>

        <div v-if="loadingHarnessSettings" class="loading-state">
          <div class="spinner"></div>
          <span>Loading settings...</span>
        </div>

        <template v-else>
          <div class="form-group">
            <label>Marketplace</label>
            <select
              :value="harnessMarketplaceId || ''"
              @change="onHarnessMarketplaceChange(($event.target as HTMLSelectElement).value)"
            >
              <option value="">Select a marketplace...</option>
              <option v-for="mp in marketplaces" :key="mp.id" :value="mp.id">
                {{ mp.name }}
              </option>
            </select>
            <span v-if="marketplaces.length === 0" class="help-text">
              No marketplaces configured. Add one in the Plugin Marketplaces tab.
            </span>
          </div>

          <div v-if="harnessMarketplaceId" class="form-group">
            <label>Plugin Name</label>
            <input
              v-model="harnessPluginName"
              type="text"
              placeholder="e.g., multi-cli-harness"
            />
            <span class="help-text">
              Enter the plugin folder name from the marketplace repository (e.g., "multi-cli-harness")
            </span>
          </div>

          <div v-if="harnessPluginsList.length > 0" class="installed-plugins-hint">
            <span class="hint-label">Installed plugins from this marketplace:</span>
            <div class="plugin-chips">
              <span
                v-for="plugin in harnessPluginsList"
                :key="plugin.id"
                class="plugin-chip"
                @click="harnessPluginName = plugin.remote_name"
              >
                {{ plugin.remote_name }}
              </span>
            </div>
          </div>

          <div class="form-actions">
            <button
              class="btn btn-primary"
              :disabled="!harnessMarketplaceId || !harnessPluginName || savingHarnessSettings"
              @click="saveHarnessSettings"
            >
              <template v-if="savingHarnessSettings">
                <div class="spinner-sm"></div>
                Saving...
              </template>
              <template v-else>
                Save Settings
              </template>
            </button>
          </div>

          <div v-if="harnessMarketplaceId && harnessPluginName" class="current-config">
            <span class="config-label">Current Configuration:</span>
            <div class="config-value">
              <span class="marketplace-name">
                {{ marketplaces.find(m => m.id === harnessMarketplaceId)?.name || 'Unknown' }}
              </span>
              <span class="separator">/</span>
              <span class="plugin-name-display">{{ harnessPluginName }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Sync Status Section -->
    <div class="card sync-section">
      <div class="card-header">
        <h3>Plugin Sync</h3>
      </div>
      <div class="card-body">
        <div v-if="loadingExportedPlugins" class="loading-state">
          <div class="spinner"></div>
          <span>Loading exported plugins...</span>
        </div>

        <div v-else-if="exportedPlugins.length === 0" class="empty-state-inline">
          <p class="muted">Export a plugin first to enable sync</p>
        </div>

        <div v-else class="sync-panels">
          <div v-for="ep in exportedPlugins" :key="ep.plugin_id" class="sync-panel-wrapper">
            <div class="sync-plugin-label">{{ ep.plugin_name }}</div>
            <SyncStatusPanel
              :plugin-id="ep.plugin_id"
              :plugin-dir="ep.export_path"
              @synced="loadExportedPlugins"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
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

.card-body {
  padding: 1.25rem;
}

.muted {
  color: var(--text-tertiary, #666);
  font-size: 0.9rem;
}

/* Harness Tab Styles */
.description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
  line-height: 1.5;
}

.help-text {
  font-size: 0.8rem;
  color: var(--text-tertiary, #666);
  margin-top: 0.5rem;
  display: block;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group input[type="text"],
.form-group select {
  width: 100%;
  padding: 0.6rem 0.8rem;
  background: var(--bg-secondary, #1a1a2e);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary, #e0e0e0);
  font-size: 0.9rem;
}

.form-group input[type="text"]:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.installed-plugins-hint {
  margin-top: 1rem;
  padding: 1rem;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
}

.hint-label {
  font-size: 0.8rem;
  color: var(--text-tertiary, #666);
  display: block;
  margin-bottom: 0.5rem;
}

.plugin-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.plugin-chip {
  padding: 0.35rem 0.75rem;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  font-size: 0.8rem;
  color: var(--text-primary, #fff);
  cursor: pointer;
  transition: all 0.15s;
}

.plugin-chip:hover {
  border-color: var(--accent-cyan, #00d4ff);
  color: var(--accent-cyan, #00d4ff);
}

.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--bg-primary, #0a0a0f);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.current-config {
  margin-top: 1.5rem;
  padding: 1rem;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  border: 1px solid var(--accent-cyan, #00d4ff);
  border-radius: 8px;
}

.config-label {
  font-size: 0.75rem;
  color: var(--text-tertiary, #666);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: block;
  margin-bottom: 0.5rem;
}

.config-value {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.9rem;
}

.marketplace-name {
  color: var(--accent-emerald, #00ff88);
}

.separator {
  color: var(--text-tertiary, #666);
}

.plugin-name-display {
  color: var(--accent-cyan, #00d4ff);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.loading-state span {
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
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

/* Sync section */
.sync-section {
  margin-top: 1.5rem;
}

.empty-state-inline {
  padding: 1.5rem;
  text-align: center;
}

.sync-panels {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.sync-panel-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sync-plugin-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
  padding-left: 0.25rem;
}
</style>
