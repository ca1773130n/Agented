<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Plugin, PluginComponent } from '../services/api';
import { pluginApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  pluginId?: string;
}>();

const route = useRoute();
const router = useRouter();
const pluginId = computed(() => (route.params.pluginId as string) || props.pluginId || '');

const showToast = useToast();

const plugin = ref<Plugin | null>(null);
const isSaving = ref(false);
const activeTab = ref<'overview' | 'skills' | 'commands' | 'hooks' | 'agents'>('overview');

// Edit states
const isEditingInfo = ref(false);
const editForm = ref({ name: '', description: '', version: '', status: '', author: '' });

// Component management
const showAddComponentModal = ref(false);
const newComponent = ref({ name: '', type: 'skill', content: '' });

// Edit component state
const isEditingComponent = ref(false);
const editingComponent = ref<PluginComponent | null>(null);
const editComponentForm = ref({ name: '', content: '' });

// Confirm delete component state
const showDeleteComponentConfirm = ref(false);
const pendingDeleteComponent = ref<PluginComponent | null>(null);

const editInfoModalRef = ref<HTMLElement | null>(null);
const addComponentModalRef = ref<HTMLElement | null>(null);
const editComponentModalRef = ref<HTMLElement | null>(null);
useWebMcpTool({
  name: 'agented_plugin_detail_get_state',
  description: 'Returns the current state of the PluginDetailPage',
  page: 'PluginDetailPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'PluginDetailPage',
        pluginId: plugin.value?.id ?? null,
        pluginName: plugin.value?.name ?? null,
        isSaving: isSaving.value,
        activeTab: activeTab.value,
        componentsCount: plugin.value?.components?.length ?? 0,
        isEditingInfo: isEditingInfo.value,
        showAddComponentModal: showAddComponentModal.value,
        isEditingComponent: isEditingComponent.value,
      }),
    }],
  }),
  deps: [plugin, isSaving, activeTab, isEditingInfo, showAddComponentModal, isEditingComponent],
});

useFocusTrap(editInfoModalRef, isEditingInfo);
useFocusTrap(addComponentModalRef, showAddComponentModal);
useFocusTrap(editComponentModalRef, isEditingComponent);

async function loadPlugin() {
  const data = await pluginApi.get(pluginId.value);
  plugin.value = data;
  if (plugin.value) {
    editForm.value = {
      name: plugin.value.name,
      description: plugin.value.description || '',
      version: plugin.value.version,
      status: plugin.value.status,
      author: plugin.value.author || '',
    };
  }
  return data;
}

async function savePluginInfo() {
  if (!plugin.value) return;
  isSaving.value = true;
  try {
    await pluginApi.update(pluginId.value, {
      name: editForm.value.name,
      description: editForm.value.description || undefined,
      version: editForm.value.version,
      status: editForm.value.status,
      author: editForm.value.author || undefined,
    });
    plugin.value = { ...plugin.value, ...editForm.value };
    isEditingInfo.value = false;
    showToast('Plugin updated successfully', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update plugin';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

async function addComponent() {
  if (!newComponent.value.name.trim()) {
    showToast('Component name is required', 'error');
    return;
  }
  try {
    await pluginApi.addComponent(pluginId.value, {
      name: newComponent.value.name,
      type: newComponent.value.type,
      content: newComponent.value.content || undefined,
    });
    showToast('Component added', 'success');
    showAddComponentModal.value = false;
    newComponent.value = { name: '', type: 'skill', content: '' };
    await loadPlugin();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add component';
    showToast(message, 'error');
  }
}

function deleteComponent(component: PluginComponent) {
  pendingDeleteComponent.value = component;
  showDeleteComponentConfirm.value = true;
}

async function confirmDeleteComponent() {
  const component = pendingDeleteComponent.value;
  showDeleteComponentConfirm.value = false;
  pendingDeleteComponent.value = null;
  if (!component) return;
  try {
    await pluginApi.removeComponent(pluginId.value, component.id);
    showToast('Component deleted', 'success');
    await loadPlugin();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete component';
    showToast(message, 'error');
  }
}

function editComponent(component: PluginComponent) {
  editingComponent.value = component;
  editComponentForm.value = { name: component.name, content: component.content || '' };
  isEditingComponent.value = true;
}

async function saveComponent() {
  if (!editingComponent.value) return;
  try {
    await pluginApi.updateComponent(pluginId.value, editingComponent.value.id, {
      name: editComponentForm.value.name,
      content: editComponentForm.value.content || undefined,
    });
    showToast('Component updated', 'success');
    isEditingComponent.value = false;
    editingComponent.value = null;
    await loadPlugin();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update component';
    showToast(message, 'error');
  }
}

function getComponentsByType(type: string): PluginComponent[] {
  return plugin.value?.components?.filter(c => c.type === type) || [];
}

function getStatusClass(status: string) {
  switch (status) {
    case 'published': return 'status-published';
    case 'draft': return 'status-draft';
    case 'deprecated': return 'status-deprecated';
    default: return '';
  }
}

function getComponentIcon(type: string) {
  switch (type) {
    case 'skill': return 'M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5';
    case 'command': return 'M4 17l6-5-6-5M12 19h8';
    case 'hook': return 'M12 2v20M2 12h20';
    case 'agent': return 'M12 8a4 4 0 100-8 4 4 0 000 8zM6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2';
    default: return 'M4 4h16v16H4z';
  }
}

function navigateToComponent(_component: PluginComponent) {
  // Component navigation by type/name - not yet mapped to specific routes
}


</script>

<template>
  <EntityLayout :load-entity="loadPlugin" entity-label="plugin">
    <template #default="{ reload: _reload }">
    <div class="plugin-detail-page">
    <AppBreadcrumb :items="[{ label: 'Plugins', action: () => router.push({ name: 'plugins' }) }, { label: plugin?.name || 'Plugin' }]" />

    <template v-if="plugin">
      <!-- Plugin Header -->
      <PageHeader :title="plugin.name" :subtitle="plugin.description">
        <template #actions>
          <div class="header-meta">
            <span class="version-badge">v{{ plugin.version }}</span>
            <span :class="['status-badge', getStatusClass(plugin.status)]">{{ plugin.status }}</span>
            <span v-if="plugin.author" class="author">by {{ plugin.author }}</span>
          </div>
          <button class="btn btn-secondary" @click="isEditingInfo = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
        </template>
      </PageHeader>

      <!-- Tabs -->
      <div class="tabs">
        <button
          :class="['tab', { active: activeTab === 'overview' }]"
          @click="activeTab = 'overview'"
        >
          Overview
        </button>
        <button
          :class="['tab', { active: activeTab === 'skills' }]"
          @click="activeTab = 'skills'"
        >
          Skills ({{ getComponentsByType('skill').length }})
        </button>
        <button
          :class="['tab', { active: activeTab === 'commands' }]"
          @click="activeTab = 'commands'"
        >
          Commands ({{ getComponentsByType('command').length }})
        </button>
        <button
          :class="['tab', { active: activeTab === 'hooks' }]"
          @click="activeTab = 'hooks'"
        >
          Hooks ({{ getComponentsByType('hook').length }})
        </button>
        <button
          :class="['tab', { active: activeTab === 'agents' }]"
          @click="activeTab = 'agents'"
        >
          Agents ({{ getComponentsByType('agent').length }})
        </button>
      </div>

      <!-- Tab Content -->
      <div class="tab-content">
        <!-- Overview Tab -->
        <div v-if="activeTab === 'overview'" class="overview-tab">
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-icon skills">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5"/>
                </svg>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ getComponentsByType('skill').length }}</span>
                <span class="stat-label">Skills</span>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon hooks">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2v20M2 12h20"/>
                </svg>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ getComponentsByType('hook').length }}</span>
                <span class="stat-label">Hooks</span>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon agents">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 8a4 4 0 100-8 4 4 0 000 8zM6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                </svg>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ getComponentsByType('agent').length }}</span>
                <span class="stat-label">Agents</span>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon commands">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M4 17l6-5-6-5M12 19h8"/>
                </svg>
              </div>
              <div class="stat-info">
                <span class="stat-value">{{ getComponentsByType('command').length }}</span>
                <span class="stat-label">Commands</span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3>All Components</h3>
              <button class="btn btn-small btn-primary" @click="showAddComponentModal = true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                Add Component
              </button>
            </div>
            <div class="card-body">
              <div v-if="plugin.components && plugin.components.length > 0" class="components-list">
                <div v-for="component in plugin.components" :key="component.id" class="component-row clickable" @click="navigateToComponent(component)">
                  <div class="component-icon" :class="component.type">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                      <path :d="getComponentIcon(component.type)"/>
                    </svg>
                  </div>
                  <div class="component-info">
                    <span class="component-name">{{ component.name }}</span>
                    <span class="component-type">{{ component.type }}</span>
                  </div>
                  <button class="btn btn-icon btn-secondary" @click.stop="editComponent(component)" title="Edit component">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button class="btn btn-icon btn-danger" @click.stop="deleteComponent(component)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                  </button>
                </div>
              </div>
              <p v-else class="empty-text">No components yet. Add skills, commands, hooks, or agents to this plugin.</p>
            </div>
          </div>
        </div>

        <!-- Skills Tab -->
        <div v-if="activeTab === 'skills'" class="components-tab">
          <div class="tab-header">
            <h3>Skills</h3>
            <button class="btn btn-small btn-primary" @click="newComponent.type = 'skill'; showAddComponentModal = true">
              Add Skill
            </button>
          </div>
          <div v-if="getComponentsByType('skill').length > 0" class="components-list">
            <div v-for="component in getComponentsByType('skill')" :key="component.id" class="component-card clickable" @click="navigateToComponent(component)">
              <div class="component-icon skill">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5"/>
                </svg>
              </div>
              <div class="component-content">
                <h4>{{ component.name }}</h4>
                <pre v-if="component.content" class="component-code">{{ component.content }}</pre>
              </div>
              <button class="btn btn-icon btn-secondary" @click.stop="editComponent(component)" title="Edit component">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn btn-icon btn-danger" @click.stop="deleteComponent(component)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>
                </svg>
              </button>
            </div>
          </div>
          <p v-else class="empty-text">No skills defined. Skills provide reusable functionality for your plugin.</p>
        </div>

        <!-- Commands Tab -->
        <div v-if="activeTab === 'commands'" class="components-tab">
          <div class="tab-header">
            <h3>Commands</h3>
            <button class="btn btn-small btn-primary" @click="newComponent.type = 'command'; showAddComponentModal = true">
              Add Command
            </button>
          </div>
          <div v-if="getComponentsByType('command').length > 0" class="components-list">
            <div v-for="component in getComponentsByType('command')" :key="component.id" class="component-card clickable" @click="navigateToComponent(component)">
              <div class="component-icon command">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M4 17l6-5-6-5M12 19h8"/>
                </svg>
              </div>
              <div class="component-content">
                <h4>{{ component.name }}</h4>
                <pre v-if="component.content" class="component-code">{{ component.content }}</pre>
              </div>
              <button class="btn btn-icon btn-secondary" @click.stop="editComponent(component)" title="Edit component">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn btn-icon btn-danger" @click.stop="deleteComponent(component)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>
                </svg>
              </button>
            </div>
          </div>
          <p v-else class="empty-text">No commands defined. Commands provide CLI functionality for your plugin.</p>
        </div>

        <!-- Hooks Tab -->
        <div v-if="activeTab === 'hooks'" class="components-tab">
          <div class="tab-header">
            <h3>Hooks</h3>
            <button class="btn btn-small btn-primary" @click="newComponent.type = 'hook'; showAddComponentModal = true">
              Add Hook
            </button>
          </div>
          <div v-if="getComponentsByType('hook').length > 0" class="components-list">
            <div v-for="component in getComponentsByType('hook')" :key="component.id" class="component-card clickable" @click="navigateToComponent(component)">
              <div class="component-icon hook">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2v20M2 12h20"/>
                </svg>
              </div>
              <div class="component-content">
                <h4>{{ component.name }}</h4>
                <pre v-if="component.content" class="component-code">{{ component.content }}</pre>
              </div>
              <button class="btn btn-icon btn-secondary" @click.stop="editComponent(component)" title="Edit component">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn btn-icon btn-danger" @click.stop="deleteComponent(component)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>
                </svg>
              </button>
            </div>
          </div>
          <p v-else class="empty-text">No hooks defined. Hooks allow your plugin to respond to events.</p>
        </div>

        <!-- Agents Tab -->
        <div v-if="activeTab === 'agents'" class="components-tab">
          <div class="tab-header">
            <h3>Agents</h3>
            <button class="btn btn-small btn-primary" @click="newComponent.type = 'agent'; showAddComponentModal = true">
              Add Agent
            </button>
          </div>
          <div v-if="getComponentsByType('agent').length > 0" class="components-list">
            <div v-for="component in getComponentsByType('agent')" :key="component.id" class="component-card clickable" @click="navigateToComponent(component)">
              <div class="component-icon agent">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 8a4 4 0 100-8 4 4 0 000 8zM6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                </svg>
              </div>
              <div class="component-content">
                <h4>{{ component.name }}</h4>
                <pre v-if="component.content" class="component-code">{{ component.content }}</pre>
              </div>
              <button class="btn btn-icon btn-secondary" @click.stop="editComponent(component)" title="Edit component">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="btn btn-icon btn-danger" @click.stop="deleteComponent(component)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>
                </svg>
              </button>
            </div>
          </div>
          <p v-else class="empty-text">No agents defined. Agents provide autonomous functionality for your plugin.</p>
        </div>
      </div>
    </template>

    <!-- Edit Plugin Modal -->
    <Teleport to="body">
      <div v-if="isEditingInfo" ref="editInfoModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-edit-plugin-info" tabindex="-1" @click.self="isEditingInfo = false" @keydown.escape="isEditingInfo = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-edit-plugin-info">Edit Plugin</h2>
            <button class="modal-close" @click="isEditingInfo = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Plugin Name *</label>
              <input v-model="editForm.name" type="text" placeholder="Plugin name" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="editForm.description" placeholder="Describe the plugin..."></textarea>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Version</label>
                <input v-model="editForm.version" type="text" placeholder="1.0.0" />
              </div>
              <div class="form-group">
                <label>Status</label>
                <select v-model="editForm.status">
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="deprecated">Deprecated</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>Author</label>
              <input v-model="editForm.author" type="text" placeholder="Your name or org" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="isEditingInfo = false">Cancel</button>
            <button class="btn btn-primary" :disabled="isSaving" @click="savePluginInfo">
              {{ isSaving ? 'Saving...' : 'Save Changes' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Add Component Modal -->
    <Teleport to="body">
      <div v-if="showAddComponentModal" ref="addComponentModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-component" tabindex="-1" @click.self="showAddComponentModal = false" @keydown.escape="showAddComponentModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-add-component">Add Component</h2>
            <button class="modal-close" @click="showAddComponentModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Component Name *</label>
              <input v-model="newComponent.name" type="text" placeholder="e.g., my-skill" />
            </div>
            <div class="form-group">
              <label>Type</label>
              <select v-model="newComponent.type">
                <option value="skill">Skill</option>
                <option value="command">Command</option>
                <option value="hook">Hook</option>
                <option value="agent">Agent</option>
              </select>
            </div>
            <div class="form-group">
              <label>Content (Optional)</label>
              <textarea v-model="newComponent.content" placeholder="Component configuration or code..." rows="6"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showAddComponentModal = false">Cancel</button>
            <button class="btn btn-primary" @click="addComponent">Add Component</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit Component Modal -->
    <Teleport to="body">
      <div v-if="isEditingComponent" ref="editComponentModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-edit-component" tabindex="-1"
           @click.self="isEditingComponent = false" @keydown.escape="isEditingComponent = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-edit-component">Edit Component</h2>
            <button class="modal-close" @click="isEditingComponent = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Component Name</label>
              <input v-model="editComponentForm.name" type="text" />
            </div>
            <div class="form-group">
              <label>Content</label>
              <textarea v-model="editComponentForm.content" rows="10" placeholder="Component content..."></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="isEditingComponent = false">Cancel</button>
            <button class="btn btn-primary" @click="saveComponent">Save Changes</button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteComponentConfirm"
      title="Delete Component"
      :message="pendingDeleteComponent ? 'Delete component \u201C' + pendingDeleteComponent.name + '\u201D?' : 'Delete this component?'"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDeleteComponent"
      @cancel="showDeleteComponentConfirm = false"
    />
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.plugin-detail-page {
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

/* Header Meta */
.header-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.version-badge {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: monospace;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-draft { background: rgba(255, 193, 7, 0.2); color: #ffc107; }
.status-published { background: rgba(0, 255, 136, 0.2); color: #00ff88; }
.status-deprecated { background: rgba(255, 77, 77, 0.2); color: #ff4d4d; }

.author {
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 0;
}

.tab {
  padding: 12px 20px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
}

.tab:hover {
  color: var(--text-secondary);
}

.tab.active {
  color: var(--accent-cyan);
  border-bottom-color: var(--accent-cyan);
}

/* Tab Content */
.tab-content {
  min-height: 300px;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon svg {
  width: 20px;
  height: 20px;
}

.stat-icon.skills { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan); }
.stat-icon.commands { background: rgba(136, 85, 255, 0.15); color: #8855ff; }
.stat-icon.hooks { background: rgba(255, 193, 7, 0.15); color: #ffc107; }
.stat-icon.agents { background: rgba(0, 255, 136, 0.15); color: var(--accent-emerald); }

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

/* Cards */
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-body {
  padding: 20px;
}

/* Components List */
.components-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.component-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.component-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.component-icon svg {
  width: 16px;
  height: 16px;
}

.component-icon.skill { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan); }
.component-icon.command { background: rgba(136, 85, 255, 0.15); color: #8855ff; }
.component-icon.hook { background: rgba(255, 193, 7, 0.15); color: #ffc107; }
.component-icon.agent { background: rgba(0, 255, 136, 0.15); color: var(--accent-emerald); }

.component-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.component-name {
  font-weight: 500;
  color: var(--text-primary);
}

.component-type {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-transform: capitalize;
}

/* Component Cards (for tabs) */
.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.tab-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.component-card {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  margin-bottom: 12px;
}

.component-content {
  flex: 1;
  min-width: 0;
}

.component-content h4 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.component-code {
  background: var(--bg-tertiary);
  padding: 12px;
  border-radius: 6px;
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-text {
  color: var(--text-tertiary);
  text-align: center;
  padding: 40px 20px;
}

/* Buttons */

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-small {
  padding: 6px 12px;
  font-size: 0.8rem;
}

.btn-icon {
  padding: 8px;
}

.btn-danger {
  background: transparent;
  color: var(--text-tertiary);
}

.btn-danger:hover {
  color: #ff4d4d;
  background: rgba(255, 77, 77, 0.1);
}

/* Modal */

.modal-header h2 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
}

/* Form */

.form-group input,
.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.component-row.clickable,
.component-card.clickable {
  cursor: pointer;
  transition: all 0.15s;
}

.component-row.clickable:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  transform: translateX(4px);
}

.component-card.clickable:hover {
  border-color: var(--accent-cyan);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}


</style>
