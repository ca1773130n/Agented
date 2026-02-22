<script setup lang="ts">
import { ref, toRef } from 'vue';
import type { Marketplace, PluginImportResponse } from '../../services/api';
import { pluginExportApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  show: boolean;
  marketplaces: Marketplace[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'imported', result: PluginImportResponse): void;
}>();

const showToast = useToast();

const importModalRef = ref<HTMLElement | null>(null);
const isOpen = toRef(props, 'show');
useFocusTrap(importModalRef, isOpen);

const activeTab = ref<'local' | 'marketplace'>('local');

// Local import state
const localPath = ref('');
const localPluginName = ref('');
const isImportingLocal = ref(false);

// Marketplace import state
const selectedMarketplaceId = ref('');
const remotePluginName = ref('');
const isImportingMarketplace = ref(false);

// Result
const importResult = ref<PluginImportResponse | null>(null);

function resetState() {
  activeTab.value = 'local';
  localPath.value = '';
  localPluginName.value = '';
  isImportingLocal.value = false;
  selectedMarketplaceId.value = '';
  remotePluginName.value = '';
  isImportingMarketplace.value = false;
  importResult.value = null;
}

function handleClose() {
  resetState();
  emit('close');
}

async function importLocal() {
  if (!localPath.value.trim()) {
    showToast('Please provide a directory path', 'error');
    return;
  }
  isImportingLocal.value = true;
  try {
    const result = await pluginExportApi.import({
      source_path: localPath.value.trim(),
      plugin_name: localPluginName.value.trim() || undefined,
    });
    importResult.value = result;
    emit('imported', result);
    showToast(`Imported plugin "${result.plugin_name}"`, 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to import plugin', 'error');
    }
  } finally {
    isImportingLocal.value = false;
  }
}

async function importFromMarketplace() {
  if (!selectedMarketplaceId.value || !remotePluginName.value.trim()) {
    showToast('Please select a marketplace and enter a plugin name', 'error');
    return;
  }
  isImportingMarketplace.value = true;
  try {
    const result = await pluginExportApi.importFromMarketplace({
      marketplace_id: selectedMarketplaceId.value,
      remote_plugin_name: remotePluginName.value.trim(),
    });
    importResult.value = result;
    emit('imported', result);
    showToast(`Imported plugin "${result.plugin_name}" from marketplace`, 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to import from marketplace', 'error');
    }
  } finally {
    isImportingMarketplace.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" ref="importModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-import-plugin" tabindex="-1" @click.self="handleClose" @keydown.escape="handleClose">
      <div class="modal import-modal">
        <div class="modal-header">
          <h2 id="modal-title-import-plugin">Import Plugin</h2>
          <button class="modal-close" @click="handleClose">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Import Success -->
          <template v-if="importResult">
            <div class="success-panel">
              <div class="success-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <h3>Import Successful</h3>
              </div>

              <div class="result-summary">
                <div class="result-row">
                  <span class="result-label">Plugin</span>
                  <span class="result-value">{{ importResult.plugin_name }}</span>
                </div>
                <div class="result-row">
                  <span class="result-label">Plugin ID</span>
                  <span class="result-value id-badge">{{ importResult.plugin_id }}</span>
                </div>
                <div class="result-counts">
                  <div class="count-item" v-if="importResult.agents_imported > 0">
                    <span class="count-num">{{ importResult.agents_imported }}</span>
                    <span class="count-label">Agents</span>
                  </div>
                  <div class="count-item" v-if="importResult.skills_imported > 0">
                    <span class="count-num">{{ importResult.skills_imported }}</span>
                    <span class="count-label">Skills</span>
                  </div>
                  <div class="count-item" v-if="importResult.commands_imported > 0">
                    <span class="count-num">{{ importResult.commands_imported }}</span>
                    <span class="count-label">Commands</span>
                  </div>
                  <div class="count-item" v-if="importResult.hooks_imported > 0">
                    <span class="count-num">{{ importResult.hooks_imported }}</span>
                    <span class="count-label">Hooks</span>
                  </div>
                  <div class="count-item" v-if="importResult.rules_imported > 0">
                    <span class="count-num">{{ importResult.rules_imported }}</span>
                    <span class="count-label">Rules</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Import Form -->
          <template v-else>
            <div class="tabs">
              <button
                class="tab"
                :class="{ active: activeTab === 'local' }"
                @click="activeTab = 'local'"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Local Directory
              </button>
              <button
                class="tab"
                :class="{ active: activeTab === 'marketplace' }"
                @click="activeTab = 'marketplace'"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="9" cy="21" r="1"/>
                  <circle cx="20" cy="21" r="1"/>
                  <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"/>
                </svg>
                From Marketplace
              </button>
            </div>

            <!-- Local Tab -->
            <div v-if="activeTab === 'local'" class="tab-content">
              <div class="form-group">
                <label>Directory Path *</label>
                <input
                  v-model="localPath"
                  type="text"
                  placeholder="/path/to/plugin-directory"
                  :disabled="isImportingLocal"
                />
              </div>
              <div class="form-group">
                <label>Plugin Name (optional)</label>
                <input
                  v-model="localPluginName"
                  type="text"
                  placeholder="Override auto-detected name"
                  :disabled="isImportingLocal"
                />
              </div>
            </div>

            <!-- Marketplace Tab -->
            <div v-if="activeTab === 'marketplace'" class="tab-content">
              <div class="form-group">
                <label>Marketplace *</label>
                <select v-model="selectedMarketplaceId" :disabled="isImportingMarketplace">
                  <option value="" disabled>Select a marketplace</option>
                  <option
                    v-for="mp in marketplaces"
                    :key="mp.id"
                    :value="mp.id"
                  >
                    {{ mp.name }}
                  </option>
                </select>
                <p v-if="marketplaces.length === 0" class="hint-text">No marketplaces configured. Add one in Settings.</p>
              </div>
              <div class="form-group">
                <label>Plugin Name *</label>
                <input
                  v-model="remotePluginName"
                  type="text"
                  placeholder="Plugin name in the marketplace"
                  :disabled="isImportingMarketplace"
                />
              </div>
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose">
            {{ importResult ? 'Close' : 'Cancel' }}
          </button>
          <template v-if="!importResult">
            <button
              v-if="activeTab === 'local'"
              class="btn btn-primary"
              :disabled="!localPath.trim() || isImportingLocal"
              @click="importLocal"
            >
              {{ isImportingLocal ? 'Importing...' : 'Import' }}
            </button>
            <button
              v-else
              class="btn btn-primary"
              :disabled="!selectedMarketplaceId || !remotePluginName.trim() || isImportingMarketplace"
              @click="importFromMarketplace"
            >
              {{ isImportingMarketplace ? 'Importing...' : 'Import' }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>

.import-modal {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header h2 { font-size: 1.25rem; font-weight: 600; }

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 0;
}

.tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary, #888);
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
  margin-bottom: -1px;
}

.tab svg {
  width: 16px;
  height: 16px;
}

.tab:hover {
  color: var(--text-primary, #fff);
}

.tab.active {
  color: var(--accent-violet, #8855ff);
  border-bottom-color: var(--accent-violet, #8855ff);
}

.tab-content {
  padding-top: 0.5rem;
}

/* Form */

.form-group input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.hint-text {
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

/* Success panel */
.success-panel {
  text-align: center;
}

.success-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.success-header svg {
  width: 28px;
  height: 28px;
  color: #00ff88;
}

.success-header h3 {
  font-size: 1.15rem;
  color: #00ff88;
}

.result-summary {
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 10px;
  padding: 1.25rem;
  text-align: left;
}

.result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.result-row + .result-row {
  border-top: 1px solid var(--border-default);
}

.result-label {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.result-value {
  font-weight: 500;
}

.id-badge {
  font-size: 0.8rem;
  font-family: monospace;
  padding: 0.2rem 0.5rem;
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
  border-radius: 4px;
}

.result-counts {
  display: flex;
  gap: 1rem;
  justify-content: center;
  padding: 1rem 0;
  border-top: 1px solid var(--border-default);
  margin-top: 0.5rem;
}

.count-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.count-num {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent-cyan, #00d4ff);
}

.count-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--text-secondary, #888);
}

/* Buttons */

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(136, 85, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}
</style>
