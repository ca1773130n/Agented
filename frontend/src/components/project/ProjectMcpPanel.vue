<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { McpServer, ProjectMcpServerDetail, McpSyncResult } from '../../services/api';
import { mcpServerApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  projectId: string;
}>();

const showToast = useToast();

const availableServers = ref<McpServer[]>([]);
const assignedServers = ref<ProjectMcpServerDetail[]>([]);
const isLoading = ref(true);
const isSyncing = ref(false);
const syncResult = ref<McpSyncResult | null>(null);
const showPreview = ref(false);
const showAddMenu = ref(false);

// Edit state for env overrides per server
const editingOverrides = ref<Record<string, string>>({});

const unassignedServers = computed(() => {
  const assignedIds = new Set(assignedServers.value.map(s => s.mcp_server_id));
  return availableServers.value.filter(s => !assignedIds.has(s.id));
});

async function loadData() {
  isLoading.value = true;
  try {
    const [allData, projectData] = await Promise.all([
      mcpServerApi.list(),
      mcpServerApi.listForProject(props.projectId),
    ]);
    availableServers.value = allData.servers || [];
    assignedServers.value = projectData.servers || [];
    // Initialize env override edit state
    const overrides: Record<string, string> = {};
    for (const s of assignedServers.value) {
      overrides[s.mcp_server_id] = s.env_overrides_json || '{}';
    }
    editingOverrides.value = overrides;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load MCP data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function assignServer(serverId: string) {
  try {
    await mcpServerApi.assignToProject(props.projectId, serverId);
    showToast('MCP server assigned', 'success');
    showAddMenu.value = false;
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to assign MCP server';
    showToast(message, 'error');
  }
}

async function unassignServer(serverId: string) {
  try {
    await mcpServerApi.unassignFromProject(props.projectId, serverId);
    showToast('MCP server removed', 'success');
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to remove MCP server';
    showToast(message, 'error');
  }
}

async function toggleEnabled(server: ProjectMcpServerDetail) {
  try {
    await mcpServerApi.updateAssignment(props.projectId, server.mcp_server_id, {
      enabled: server.assignment_enabled === 1 ? 0 : 1,
    });
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to toggle server';
    showToast(message, 'error');
  }
}

async function saveEnvOverrides(server: ProjectMcpServerDetail) {
  const newOverrides = editingOverrides.value[server.mcp_server_id];
  try {
    // Validate JSON
    JSON.parse(newOverrides || '{}');
    await mcpServerApi.updateAssignment(props.projectId, server.mcp_server_id, {
      env_overrides_json: newOverrides,
    });
    showToast('Env overrides saved', 'success');
    await loadData();
  } catch (err) {
    if (err instanceof SyntaxError) {
      showToast('Invalid JSON for env overrides', 'error');
      return;
    }
    const message = err instanceof ApiError ? err.message : 'Failed to save overrides';
    showToast(message, 'error');
  }
}

async function syncToProject() {
  isSyncing.value = true;
  try {
    const result = await mcpServerApi.syncProject(props.projectId);
    syncResult.value = result;
    showPreview.value = false;
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(`Synced ${result.servers || 0} servers to .mcp.json`, 'success');
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to sync';
    showToast(message, 'error');
  } finally {
    isSyncing.value = false;
  }
}

async function previewSync() {
  try {
    const result = await mcpServerApi.previewSync(props.projectId);
    syncResult.value = result;
    showPreview.value = true;
    if (result.error) {
      showToast(result.error, 'error');
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to preview';
    showToast(message, 'error');
  }
}

function dismissSyncResult() {
  syncResult.value = null;
  showPreview.value = false;
}

onMounted(loadData);
</script>

<template>
  <div class="mcp-panel">
    <!-- Header -->
    <div class="panel-header">
      <div class="panel-title">
        <h3>MCP Servers</h3>
        <span class="panel-count">{{ assignedServers.length }} assigned</span>
      </div>
      <div class="panel-actions">
        <button class="btn btn-secondary-sm" @click="previewSync">Preview</button>
        <button
          class="btn btn-primary-sm"
          :disabled="isSyncing"
          @click="syncToProject"
        >
          {{ isSyncing ? 'Syncing...' : 'Sync to .mcp.json' }}
        </button>
      </div>
    </div>

    <!-- Sync result -->
    <div v-if="syncResult" class="sync-result" :class="{ preview: showPreview }">
      <div class="sync-result-header">
        <span class="sync-result-label">{{ showPreview ? 'Preview' : 'Sync Complete' }}</span>
        <button class="dismiss-btn" @click="dismissSyncResult">&times;</button>
      </div>
      <div v-if="syncResult.error" class="sync-error">{{ syncResult.error }}</div>
      <template v-else>
        <div v-if="syncResult.written" class="sync-info">
          Written to: <code>{{ syncResult.written }}</code>
          ({{ syncResult.servers }} servers)
        </div>
        <div v-if="syncResult.diff" class="sync-diff">
          <pre>{{ syncResult.diff }}</pre>
        </div>
        <div v-if="syncResult.would_write" class="sync-info">
          Would write to: <code>{{ syncResult.would_write }}</code>
          ({{ syncResult.servers_count }} servers)
        </div>
      </template>
    </div>

    <!-- Loading -->
    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading...</span>
    </div>

    <template v-else>
      <!-- Assigned servers list -->
      <div v-if="assignedServers.length === 0" class="empty-state">
        <p>No MCP servers assigned to this project yet.</p>
      </div>

      <div v-else class="assigned-list">
        <div
          v-for="server in assignedServers"
          :key="server.mcp_server_id"
          class="assigned-item"
          :class="{ disabled: server.assignment_enabled === 0 }"
        >
          <div class="assigned-item-main">
            <label class="toggle-switch">
              <input
                type="checkbox"
                :checked="server.assignment_enabled === 1"
                @change="toggleEnabled(server)"
              />
              <span class="toggle-slider"></span>
            </label>
            <div class="assigned-info">
              <span class="assigned-name">{{ server.display_name || server.name }}</span>
              <span class="assigned-meta">
                <span class="badge-sm badge-transport-sm">{{ server.server_type }}</span>
                <span class="badge-sm badge-category-sm">{{ server.category }}</span>
              </span>
            </div>
            <button class="remove-btn" @click="unassignServer(server.mcp_server_id)" title="Remove from project">&times;</button>
          </div>
          <div class="env-overrides">
            <label class="env-label">Env Overrides (JSON)</label>
            <div class="env-row">
              <textarea
                v-model="editingOverrides[server.mcp_server_id]"
                class="env-textarea"
                rows="2"
                placeholder='{"VAR": "${VALUE}"}'
              ></textarea>
              <button
                class="btn btn-secondary-xs"
                @click="saveEnvOverrides(server)"
              >Save</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Add server -->
      <div class="add-section">
        <button class="btn btn-add" @click="showAddMenu = !showAddMenu">
          {{ showAddMenu ? 'Cancel' : '+ Add MCP Server' }}
        </button>
        <div v-if="showAddMenu && unassignedServers.length > 0" class="add-menu">
          <div
            v-for="server in unassignedServers"
            :key="server.id"
            class="add-menu-item"
            @click="assignServer(server.id)"
          >
            <span class="add-item-name">{{ server.display_name || server.name }}</span>
            <span class="add-item-meta">
              <span class="badge-sm badge-transport-sm">{{ server.server_type }}</span>
              <span v-if="server.is_preset === 1" class="badge-sm badge-preset-sm">Preset</span>
            </span>
          </div>
        </div>
        <div v-if="showAddMenu && unassignedServers.length === 0" class="add-menu-empty">
          All available servers are already assigned.
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.mcp-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-title h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.panel-count {
  font-size: 0.75rem;
  color: var(--text-tertiary, #666);
  background: var(--bg-tertiary, #1a1a24);
  padding: 2px 8px;
  border-radius: 4px;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

/* Sync result */
.sync-result {
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--accent-emerald, #00ff88);
  border-radius: 8px;
  padding: 12px;
}

.sync-result.preview {
  border-color: var(--accent-cyan, #00d4ff);
}

.sync-result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.sync-result-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-emerald, #00ff88);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preview .sync-result-label {
  color: var(--accent-cyan, #00d4ff);
}

.dismiss-btn {
  background: none;
  border: none;
  color: var(--text-tertiary, #666);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 4px;
}

.dismiss-btn:hover {
  color: var(--text-primary, #fff);
}

.sync-error {
  color: #ff5050;
  font-size: 0.85rem;
}

.sync-info {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.sync-info code {
  font-family: 'Geist Mono', monospace;
  color: var(--text-primary, #fff);
  background: var(--bg-secondary, #12121a);
  padding: 2px 6px;
  border-radius: 4px;
}

.sync-diff {
  margin-top: 8px;
}

.sync-diff pre {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-primary, #e0e0e0);
  background: var(--bg-secondary, #12121a);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  max-height: 300px;
  white-space: pre-wrap;
  line-height: 1.5;
}

/* Assigned list */
.assigned-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.assigned-item {
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-subtle, #2a2a3a);
  border-radius: 8px;
  padding: 12px;
  transition: opacity 0.2s;
}

.assigned-item.disabled {
  opacity: 0.5;
}

.assigned-item-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Toggle switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, #2a2a3a);
  border-radius: 10px;
  transition: all 0.2s;
}

.toggle-slider::before {
  position: absolute;
  content: '';
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background: var(--text-tertiary, #666);
  border-radius: 50%;
  transition: all 0.2s;
}

.toggle-switch input:checked + .toggle-slider {
  background: rgba(0, 212, 255, 0.2);
  border-color: var(--accent-cyan, #00d4ff);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(16px);
  background: var(--accent-cyan, #00d4ff);
}

.assigned-info {
  flex: 1;
  min-width: 0;
}

.assigned-name {
  display: block;
  font-weight: 500;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
}

.assigned-meta {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}

.badge-sm {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.badge-transport-sm {
  background: rgba(0, 212, 255, 0.1);
  color: var(--accent-cyan, #00d4ff);
}

.badge-category-sm {
  background: rgba(0, 255, 136, 0.1);
  color: var(--accent-emerald, #00ff88);
}

.badge-preset-sm {
  background: rgba(255, 170, 0, 0.1);
  color: var(--accent-amber, #ffaa00);
}

.remove-btn {
  background: none;
  border: none;
  color: var(--text-tertiary, #666);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 4px;
  flex-shrink: 0;
  transition: color 0.2s;
}

.remove-btn:hover {
  color: #ff5050;
}

/* Env overrides */
.env-overrides {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, #2a2a3a);
}

.env-label {
  display: block;
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-tertiary, #666);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.env-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.env-textarea {
  flex: 1;
  padding: 6px 10px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, #2a2a3a);
  border-radius: 6px;
  color: var(--text-primary, #e0e0e0);
  font-family: 'Geist Mono', monospace;
  font-size: 0.75rem;
  resize: vertical;
}

.env-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

/* Add section */
.add-section {
  position: relative;
}

.btn-add {
  padding: 8px 16px;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px dashed var(--border-subtle, #2a2a3a);
  border-radius: 8px;
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
  cursor: pointer;
  width: 100%;
  text-align: center;
  transition: all 0.2s;
}

.btn-add:hover {
  border-color: var(--accent-cyan, #00d4ff);
  color: var(--accent-cyan, #00d4ff);
}

.add-menu {
  margin-top: 8px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default, #2a2a3a);
  border-radius: 8px;
  overflow: hidden;
  max-height: 300px;
  overflow-y: auto;
}

.add-menu-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.add-menu-item:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.add-menu-item + .add-menu-item {
  border-top: 1px solid var(--border-subtle, #2a2a3a);
}

.add-item-name {
  font-size: 0.85rem;
  color: var(--text-primary, #fff);
}

.add-item-meta {
  display: flex;
  gap: 4px;
}

.add-menu-empty {
  padding: 12px;
  text-align: center;
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
}

/* Buttons */
.btn {
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary-sm {
  padding: 6px 14px;
  background: var(--accent-cyan, #00d4ff);
  color: var(--bg-primary, #0a0a12);
  font-size: 0.8rem;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary-sm:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-primary-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary-sm {
  padding: 6px 14px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-subtle, #2a2a3a);
  font-size: 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary-sm:hover {
  border-color: var(--accent-cyan, #00d4ff);
}

.btn-secondary-xs {
  padding: 4px 10px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary, #888);
  border: 1px solid var(--border-subtle, #2a2a3a);
  font-size: 0.7rem;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.btn-secondary-xs:hover {
  border-color: var(--accent-cyan, #00d4ff);
  color: var(--text-primary, #fff);
}

/* Loading / Empty */
.loading-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 1.5rem;
  color: var(--text-secondary, #888);
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.empty-state {
  text-align: center;
  padding: 1.5rem;
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
}
</style>
