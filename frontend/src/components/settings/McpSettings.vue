<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { McpServer } from '../../services/api';
import { mcpServerApi, ApiError } from '../../services/api';
import ConfirmModal from '../base/ConfirmModal.vue';
import { useToast } from '../../composables/useToast';

const showToast = useToast();

const servers = ref<McpServer[]>([]);
const isLoading = ref(true);
const showAddForm = ref(false);
const filter = ref<'all' | 'presets' | 'custom'>('all');

const newServer = ref({
  name: '',
  display_name: '',
  description: '',
  server_type: 'stdio',
  command: '',
  args: '',
  env_json: '{}',
  url: '',
  category: 'general',
  icon: '',
  documentation_url: '',
  npm_package: '',
});

// Confirm delete state
const showDeleteServerConfirm = ref(false);
const pendingDeleteServerId = ref<string | null>(null);

const filteredServers = computed(() => {
  if (filter.value === 'presets') return servers.value.filter(s => s.is_preset === 1);
  if (filter.value === 'custom') return servers.value.filter(s => s.is_preset === 0);
  return servers.value;
});

async function loadServers() {
  isLoading.value = true;
  try {
    const data = await mcpServerApi.list();
    servers.value = data.servers || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load MCP servers';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function addCustomServer() {
  if (!newServer.value.name.trim()) {
    showToast('Name is required', 'error');
    return;
  }
  try {
    const payload: Record<string, unknown> = {
      name: newServer.value.name,
      server_type: newServer.value.server_type,
      category: newServer.value.category || 'general',
    };
    if (newServer.value.display_name) payload.display_name = newServer.value.display_name;
    if (newServer.value.description) payload.description = newServer.value.description;
    if (newServer.value.server_type === 'stdio') {
      if (newServer.value.command) payload.command = newServer.value.command;
      if (newServer.value.args) payload.args = newServer.value.args;
    } else {
      if (newServer.value.url) payload.url = newServer.value.url;
    }
    if (newServer.value.env_json && newServer.value.env_json !== '{}') {
      payload.env_json = newServer.value.env_json;
    }
    if (newServer.value.icon) payload.icon = newServer.value.icon;
    if (newServer.value.documentation_url) payload.documentation_url = newServer.value.documentation_url;
    if (newServer.value.npm_package) payload.npm_package = newServer.value.npm_package;

    await mcpServerApi.create(payload as Partial<McpServer>);
    showToast('MCP server added', 'success');
    showAddForm.value = false;
    newServer.value = {
      name: '', display_name: '', description: '', server_type: 'stdio',
      command: '', args: '', env_json: '{}', url: '', category: 'general',
      icon: '', documentation_url: '', npm_package: '',
    };
    await loadServers();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add MCP server';
    showToast(message, 'error');
  }
}

function deleteServer(id: string) {
  pendingDeleteServerId.value = id;
  showDeleteServerConfirm.value = true;
}

async function confirmDeleteServer() {
  const id = pendingDeleteServerId.value;
  showDeleteServerConfirm.value = false;
  pendingDeleteServerId.value = null;
  if (!id) return;
  try {
    await mcpServerApi.delete(id);
    showToast('MCP server deleted', 'success');
    await loadServers();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete MCP server';
    showToast(message, 'error');
  }
}

onMounted(loadServers);
</script>

<template>
  <div class="mcp-settings">
    <!-- Header -->
    <div class="section-header">
      <div class="header-text">
        <h2>MCP Servers</h2>
        <p class="section-subtitle">Model Context Protocol server catalog</p>
      </div>
      <div class="header-actions">
        <div class="filter-group">
          <button
            :class="['filter-btn', { active: filter === 'all' }]"
            @click="filter = 'all'"
          >All</button>
          <button
            :class="['filter-btn', { active: filter === 'presets' }]"
            @click="filter = 'presets'"
          >Presets</button>
          <button
            :class="['filter-btn', { active: filter === 'custom' }]"
            @click="filter = 'custom'"
          >Custom</button>
        </div>
        <button class="btn btn-primary" @click="showAddForm = !showAddForm">
          {{ showAddForm ? 'Cancel' : '+ Add Custom' }}
        </button>
      </div>
    </div>

    <!-- Add Form -->
    <div v-if="showAddForm" class="add-form-card">
      <h3>Add Custom MCP Server</h3>
      <div class="form-grid">
        <div class="form-group">
          <label>Name *</label>
          <input v-model="newServer.name" type="text" placeholder="e.g., my-custom-server" />
        </div>
        <div class="form-group">
          <label>Display Name</label>
          <input v-model="newServer.display_name" type="text" placeholder="e.g., My Custom Server" />
        </div>
        <div class="form-group full-width">
          <label>Description</label>
          <textarea v-model="newServer.description" placeholder="What does this server do?" rows="2"></textarea>
        </div>
        <div class="form-group">
          <label>Transport</label>
          <select v-model="newServer.server_type">
            <option value="stdio">stdio</option>
            <option value="http">http</option>
            <option value="sse">sse</option>
          </select>
        </div>
        <div class="form-group">
          <label>Category</label>
          <input v-model="newServer.category" type="text" placeholder="e.g., development" />
        </div>
        <div v-if="newServer.server_type === 'stdio'" class="form-group">
          <label>Command</label>
          <input v-model="newServer.command" type="text" placeholder="e.g., npx" />
        </div>
        <div v-if="newServer.server_type === 'stdio'" class="form-group">
          <label>Args (JSON array)</label>
          <input v-model="newServer.args" type="text" placeholder='e.g., ["-y", "my-pkg"]' />
        </div>
        <div v-if="newServer.server_type !== 'stdio'" class="form-group full-width">
          <label>URL</label>
          <input v-model="newServer.url" type="text" placeholder="e.g., https://api.example.com/mcp" />
        </div>
        <div class="form-group full-width">
          <label>Env JSON</label>
          <textarea v-model="newServer.env_json" placeholder='e.g., {"API_KEY": "${MY_API_KEY}"}' rows="2"></textarea>
        </div>
        <div class="form-group">
          <label>Icon</label>
          <input v-model="newServer.icon" type="text" placeholder="e.g., server" />
        </div>
        <div class="form-group">
          <label>NPM Package</label>
          <input v-model="newServer.npm_package" type="text" placeholder="e.g., @scope/pkg" />
        </div>
        <div class="form-group full-width">
          <label>Documentation URL</label>
          <input v-model="newServer.documentation_url" type="text" placeholder="https://..." />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-secondary" @click="showAddForm = false">Cancel</button>
        <button class="btn btn-primary" @click="addCustomServer">Save Server</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading MCP servers...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="filteredServers.length === 0" class="empty-state">
      <p v-if="filter === 'custom'">No custom MCP servers yet. Click "Add Custom" to create one.</p>
      <p v-else-if="filter === 'presets'">No preset MCP servers found.</p>
      <p v-else>No MCP servers found.</p>
    </div>

    <!-- Server Grid -->
    <div v-else class="server-grid">
      <div
        v-for="server in filteredServers"
        :key="server.id"
        class="server-card"
      >
        <div class="server-card-header">
          <div class="server-icon-wrapper">
            <span class="server-icon-text">{{ server.icon || 'server' }}</span>
          </div>
          <div class="server-badges">
            <span class="badge badge-transport">{{ server.server_type }}</span>
            <span class="badge badge-category">{{ server.category }}</span>
            <span v-if="server.is_preset === 1" class="badge badge-preset">Preset</span>
          </div>
        </div>
        <div class="server-card-body">
          <h4 class="server-name">{{ server.display_name || server.name }}</h4>
          <p class="server-description">{{ server.description || 'No description' }}</p>
        </div>
        <div class="server-card-footer">
          <a
            v-if="server.documentation_url"
            :href="server.documentation_url"
            target="_blank"
            rel="noopener noreferrer"
            class="link-btn"
          >Docs</a>
          <span v-if="server.npm_package" class="npm-label">{{ server.npm_package }}</span>
          <button
            v-if="server.is_preset === 0"
            class="btn btn-danger-sm"
            @click="deleteServer(server.id)"
          >Delete</button>
        </div>
      </div>
    </div>

    <ConfirmModal
      :open="showDeleteServerConfirm"
      title="Delete MCP Server"
      message="Delete this MCP server?"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDeleteServer"
      @cancel="showDeleteServerConfirm = false"
    />
  </div>
</template>

<style scoped>
.mcp-settings {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 1rem;
}

.header-text h2 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
  margin-bottom: 4px;
}

.section-subtitle {
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

/* Filter toggle */
.filter-group {
  display: flex;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle, #2a2a3a);
}

.filter-btn {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #888);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  color: var(--text-primary, #fff);
}

.filter-btn.active {
  background: var(--accent-cyan, #00d4ff);
  color: var(--bg-primary, #0a0a12);
  font-weight: 600;
}

/* Add Form */
.add-form-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default, #2a2a3a);
  border-radius: 12px;
  padding: 1.5rem;
}

.add-form-card h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
  margin-bottom: 1rem;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary, #888);
  margin-bottom: 4px;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-subtle, #2a2a3a);
  border-radius: 6px;
  color: var(--text-primary, #e0e0e0);
  font-size: 0.85rem;
  font-family: inherit;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.form-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
  margin-top: 1rem;
}

/* Server Grid */
.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.server-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, #2a2a3a);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, transform 0.2s;
}

.server-card:hover {
  border-color: var(--border-default, #3a3a4a);
  transform: translateY(-1px);
}

.server-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 0;
}

.server-icon-wrapper {
  width: 36px;
  height: 36px;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.server-icon-text {
  font-size: 0.65rem;
  color: var(--text-tertiary, #666);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  max-width: 32px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-badges {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.badge-transport {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent-cyan, #00d4ff);
}

.badge-category {
  background: rgba(0, 255, 136, 0.12);
  color: var(--accent-emerald, #00ff88);
}

.badge-preset {
  background: rgba(255, 170, 0, 0.12);
  color: var(--accent-amber, #ffaa00);
}

.server-card-body {
  padding: 12px 16px;
}

.server-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
  margin-bottom: 4px;
}

.server-description {
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.server-card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid var(--border-subtle, #2a2a3a);
  min-height: 40px;
}

.link-btn {
  font-size: 0.75rem;
  color: var(--accent-cyan, #00d4ff);
  text-decoration: none;
  transition: opacity 0.2s;
}

.link-btn:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.npm-label {
  font-size: 0.7rem;
  color: var(--text-tertiary, #666);
  font-family: 'Geist Mono', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.btn-danger-sm {
  padding: 4px 10px;
  font-size: 0.75rem;
  background: rgba(255, 80, 80, 0.12);
  color: #ff5050;
  border: 1px solid rgba(255, 80, 80, 0.2);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  margin-left: auto;
}

.btn-danger-sm:hover {
  background: rgba(255, 80, 80, 0.25);
  border-color: rgba(255, 80, 80, 0.4);
}

/* Loading */
.loading-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2rem;
  color: var(--text-secondary, #888);
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Empty */
.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
}

/* Buttons */
.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--accent-cyan, #00d4ff);
  color: var(--bg-primary, #0a0a12);
  font-weight: 600;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-subtle, #2a2a3a);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan, #00d4ff);
}
</style>
