<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import type { Marketplace } from '../services/api';
import { marketplaceApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import GeneralSettings from '../components/settings/GeneralSettings.vue';
import MarketplaceSettings from '../components/settings/MarketplaceSettings.vue';
import HarnessSettings from '../components/settings/HarnessSettings.vue';
import McpSettings from '../components/settings/McpSettings.vue';
import GrdSettings from '../components/settings/GrdSettings.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const showToast = useToast();

const TAB_NAMES = ['general', 'marketplaces', 'harness', 'mcp', 'grd'] as const;
type TabName = (typeof TAB_NAMES)[number];

function getTabFromHash(): TabName {
  const hash = window.location.hash.replace('#', '');
  if ((TAB_NAMES as readonly string[]).includes(hash)) {
    return hash as TabName;
  }
  return 'general';
}

const activeTab = ref<TabName>('general');
const marketplaces = ref<Marketplace[]>([]);
const isLoading = ref(true);
const showAddModal = ref(false);

const addModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addModalRef, showAddModal);

useWebMcpTool({
  name: 'agented_settings_get_state',
  description: 'Returns the current state of the Settings page',
  page: 'SettingsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SettingsPage',
        activeTab: activeTab.value,
        marketplacesCount: marketplaces.value.length,
        showAddModal: showAddModal.value,
        isLoading: isLoading.value,
      }),
    }],
  }),
  deps: [activeTab, marketplaces, showAddModal, isLoading],
});

useWebMcpTool({
  name: 'agented_settings_switch_tab',
  description: 'Switches the active tab on the Settings page',
  page: 'SettingsPage',
  inputSchema: { type: 'object', properties: { tab: { type: 'string', description: 'Tab name: general, marketplaces, harness, mcp, or grd' } }, required: ['tab'] },
  execute: async (args: Record<string, unknown>) => {
    const tab = args.tab as string;
    if ((TAB_NAMES as readonly string[]).includes(tab)) {
      activeTab.value = tab as TabName;
      return { content: [{ type: 'text' as const, text: JSON.stringify({ success: true, activeTab: activeTab.value }) }] };
    }
    return { content: [{ type: 'text' as const, text: JSON.stringify({ success: false, error: 'Invalid tab name' }) }] };
  },
});

const newMarketplace = ref({
  name: '',
  url: '',
  type: 'git' as 'git' | 'http' | 'local',
  is_default: false,
});

async function loadMarketplaces() {
  isLoading.value = true;
  try {
    const data = await marketplaceApi.list();
    marketplaces.value = data.marketplaces || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load marketplaces';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function addMarketplace() {
  if (!newMarketplace.value.name.trim() || !newMarketplace.value.url.trim()) {
    showToast('Name and URL are required', 'error');
    return;
  }
  try {
    await marketplaceApi.create(newMarketplace.value);
    showToast('Marketplace added successfully', 'success');
    showAddModal.value = false;
    newMarketplace.value = { name: '', url: '', type: 'git', is_default: false };
    await loadMarketplaces();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add marketplace';
    showToast(message, 'error');
  }
}

function onHashChange() {
  activeTab.value = getTabFromHash();
}

watch(activeTab, (newTab) => {
  window.location.hash = newTab;
  if (newTab === 'marketplaces') {
    loadMarketplaces();
  }
});

onMounted(() => {
  activeTab.value = getTabFromHash();
  if (activeTab.value === 'marketplaces') {
    loadMarketplaces();
  }
  window.addEventListener('hashchange', onHashChange);
});

onUnmounted(() => {
  window.removeEventListener('hashchange', onHashChange);
});
</script>

<template>
  <div class="settings-page">
    <AppBreadcrumb :items="[{ label: 'Settings' }]" />
    <PageHeader title="Settings" subtitle="Application settings and configuration" />

    <!-- Tabs -->
    <div class="tabs">
      <button
        :class="['tab', { active: activeTab === 'general' }]"
        @click="activeTab = 'general'"
      >
        General
      </button>
      <button
        :class="['tab', { active: activeTab === 'marketplaces' }]"
        @click="activeTab = 'marketplaces'"
      >
        Plugin Marketplaces
      </button>
      <button
        :class="['tab', { active: activeTab === 'harness' }]"
        @click="activeTab = 'harness'"
      >
        Harness Plugin
      </button>
      <button
        :class="['tab', { active: activeTab === 'mcp' }]"
        @click="activeTab = 'mcp'"
      >
        MCP Servers
      </button>
      <button
        :class="['tab', { active: activeTab === 'grd' }]"
        @click="activeTab = 'grd'"
      >
        GRD Planning
      </button>
    </div>

    <!-- Tab Content -->
    <GeneralSettings v-if="activeTab === 'general'" />
    <MarketplaceSettings
      v-if="activeTab === 'marketplaces'"
      :marketplaces="marketplaces"
      @refreshed="loadMarketplaces"
      @show-add-modal="showAddModal = true"
    />
    <HarnessSettings v-if="activeTab === 'harness'" :marketplaces="marketplaces" />
    <McpSettings v-if="activeTab === 'mcp'" />
    <GrdSettings v-if="activeTab === 'grd'" />

    <!-- Add Marketplace Modal -->
    <Teleport to="body">
      <div v-if="showAddModal" ref="addModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-marketplace-settings" tabindex="-1" @click.self="showAddModal = false" @keydown.escape="showAddModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-add-marketplace-settings">Add Marketplace</h2>
            <button class="modal-close" @click="showAddModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="marketplace-name">Name *</label>
              <input id="marketplace-name" v-model="newMarketplace.name" type="text" placeholder="e.g., Harness Plugins" />
            </div>
            <div class="form-group">
              <label for="marketplace-url">URL *</label>
              <input id="marketplace-url" v-model="newMarketplace.url" type="text" placeholder="e.g., https://github.com/org/repo or enterprise URL" />
            </div>
            <div class="form-group">
              <label for="marketplace-type">Type</label>
              <select id="marketplace-type" v-model="newMarketplace.type">
                <option value="git">Git Repository</option>
                <option value="http">HTTP Endpoint</option>
                <option value="local">Local Directory</option>
              </select>
            </div>
            <div class="form-group checkbox">
              <label for="marketplace-default">
                <input id="marketplace-default" v-model="newMarketplace.is_default" type="checkbox" />
                Set as default marketplace
              </label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
            <button class="btn btn-primary" @click="addMarketplace">Add Marketplace</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.settings-page {
}

/* Tabs */
.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 0.5rem;
}

.tab {
  padding: 0.75rem 1.5rem;
  border: none;
  background: transparent;
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border-radius: 8px 8px 0 0;
  transition: all 0.2s;
}

.tab:hover {
  color: var(--text-primary, #fff);
  background: var(--bg-tertiary, #1a1a24);
}

.tab.active {
  color: var(--accent-cyan, #00d4ff);
  background: var(--bg-tertiary, #1a1a24);
}

/* Modal */
.modal {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  width: 100%;
  max-width: 480px;
  margin: 1rem;
  animation: modalIn 0.2s ease;
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

.modal-header h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.modal-close {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-tertiary, #666);
  font-size: 1.5rem;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s;
}

.modal-close:hover {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
}

/* Form */
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

.form-group.checkbox label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.form-group.checkbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan, #00d4ff);
}
</style>
