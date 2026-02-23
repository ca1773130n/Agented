<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { McpServer, Project } from '../services/api';
import { mcpServerApi, projectApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const route = useRoute();
const mcpServerId = computed(() => route.params.mcpServerId as string);

const showToast = useToast();

const server = ref<McpServer | null>(null);
const isSaving = ref(false);
const isEditingInfo = ref(false);
const isTesting = ref(false);
const testResult = ref<{ success: boolean; message: string } | null>(null);

const editForm = ref({
  name: '',
  display_name: '',
  description: '',
  server_type: 'stdio',
  command: '',
  args: '',
  url: '',
  timeout_ms: 30000,
  documentation_url: '',
  npm_package: '',
});

// Secret hiding
const showSecrets = ref(false);

function maskSecretValue(jsonStr: string | null): string {
  if (!jsonStr) return '';
  try {
    const obj = JSON.parse(jsonStr);
    const masked: Record<string, string> = {};
    for (const [key, val] of Object.entries(obj)) {
      masked[key] = typeof val === 'string' && val.length > 0 ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022' : String(val);
    }
    return JSON.stringify(masked, null, 2);
  } catch {
    return '\u2022'.repeat(20);
  }
}

// Project assignments
const allProjects = ref<Project[]>([]);
const showAssignModal = ref(false);
const assignModalRef = ref<HTMLElement | null>(null);
const editModalRef = ref<HTMLElement | null>(null);
const selectedProjectToAssign = ref('');

useFocusTrap(assignModalRef, showAssignModal);
useFocusTrap(editModalRef, isEditingInfo);

useWebMcpTool({
  name: 'agented_mcp_detail_get_state',
  description: 'Returns the current state of the McpServerDetailPage',
  page: 'McpServerDetailPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'McpServerDetailPage',
        serverId: server.value?.id ?? null,
        serverName: server.value?.name ?? null,
        serverType: server.value?.server_type ?? null,
        isSaving: isSaving.value,
        isEditingInfo: isEditingInfo.value,
        isTesting: isTesting.value,
        testResult: testResult.value,
        enabled: server.value?.enabled ?? null,
        toolsCount: 0,
      }),
    }],
  }),
  deps: [server, isSaving, isEditingInfo, isTesting, testResult],
});

async function loadAssignments() {
  try {
    const data = await projectApi.list();
    allProjects.value = data.projects || [];
  } catch { /* ignore */ }
}

async function assignToProject() {
  if (!selectedProjectToAssign.value) return;
  try {
    await mcpServerApi.assignToProject(selectedProjectToAssign.value, mcpServerId.value);
    showToast('Server assigned to project', 'success');
    showAssignModal.value = false;
    selectedProjectToAssign.value = '';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to assign server';
    showToast(message, 'error');
  }
}

// Enable/disable toggle
async function toggleEnabled() {
  if (!server.value) return;
  try {
    await mcpServerApi.update(mcpServerId.value, {
      enabled: server.value.enabled ? 0 : 1,
    } as Partial<McpServer>);
    showToast(server.value.enabled ? 'Server disabled' : 'Server enabled', 'success');
    await loadServer();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update server';
    showToast(message, 'error');
  }
}

async function testConnection() {
  isTesting.value = true;
  testResult.value = null;
  try {
    const result = await mcpServerApi.testConnection(mcpServerId.value);
    testResult.value = result;
    if (result.success) {
      showToast('Connection successful', 'success');
    } else {
      showToast(result.message || 'Connection failed', 'error');
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      testResult.value = { success: false, message: 'Test endpoint not available' };
      showToast('Test endpoint not available', 'error');
    } else {
      const message = err instanceof ApiError ? err.message : 'Connection test failed';
      testResult.value = { success: false, message };
      showToast(message, 'error');
    }
  } finally {
    isTesting.value = false;
  }
}

async function loadServer() {
  const data = await mcpServerApi.get(mcpServerId.value);
  server.value = data;
  if (data) {
    editForm.value = {
      name: data.name || '',
      display_name: data.display_name || '',
      description: data.description || '',
      server_type: data.server_type || 'stdio',
      command: data.command || '',
      args: data.args || '',
      url: data.url || '',
      timeout_ms: data.timeout_ms || 30000,
      documentation_url: data.documentation_url || '',
      npm_package: data.npm_package || '',
    };
  }
  // Fire-and-forget: load project assignments
  loadAssignments();
  return data;
}

async function saveServerInfo() {
  if (!server.value) return;
  isSaving.value = true;
  try {
    await mcpServerApi.update(mcpServerId.value, {
      name: editForm.value.name,
      display_name: editForm.value.display_name || undefined,
      description: editForm.value.description || undefined,
      server_type: editForm.value.server_type,
      command: editForm.value.command || undefined,
      args: editForm.value.args || undefined,
      url: editForm.value.url || undefined,
      timeout_ms: editForm.value.timeout_ms,
      documentation_url: editForm.value.documentation_url || undefined,
      npm_package: editForm.value.npm_package || undefined,
    } as Partial<McpServer>);
    showToast('Server updated successfully', 'success');
    isEditingInfo.value = false;
    await loadServer();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update server';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

function getServerTypeBadgeClass(serverType: string) {
  switch (serverType) {
    case 'stdio': return 'type-stdio';
    case 'sse': return 'type-sse';
    case 'http': return 'type-http';
    default: return '';
  }
}

</script>

<template>
  <EntityLayout :load-entity="loadServer" entity-label="MCP server">
    <template #default="{ reload: _reload }">
  <div class="mcp-server-detail-page">
    <AppBreadcrumb :items="[
      { label: 'MCP Servers', action: () => router.push({ name: 'mcp-servers' }) },
      { label: server?.display_name || server?.name || 'Server' },
    ]" />

    <template v-if="server">
      <!-- Server Header -->
      <PageHeader :title="server.display_name || server.name" :subtitle="server.description || undefined">
        <template #actions>
          <div class="header-meta">
            <span v-if="server.display_name" class="name-badge">{{ server.name }}</span>
            <span :class="['type-badge', getServerTypeBadgeClass(server.server_type)]">{{ server.server_type }}</span>
            <span v-if="server.is_preset" class="preset-badge">Preset</span>
            <span v-if="server.category" class="category-badge">{{ server.category }}</span>
          </div>
          <button class="btn btn-secondary" :disabled="isTesting" @click="testConnection">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
            {{ isTesting ? 'Testing...' : 'Test Connection' }}
          </button>
          <button
            :class="['btn', server.enabled ? 'btn-active' : 'btn-inactive']"
            @click="toggleEnabled"
          >
            {{ server.enabled ? 'Enabled' : 'Disabled' }}
          </button>
          <button v-if="!server.is_preset" class="btn btn-secondary" @click="isEditingInfo = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
        </template>
      </PageHeader>

      <div v-if="testResult" :class="['test-result', testResult.success ? 'test-pass' : 'test-fail']">
        <svg v-if="testResult.success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        <span>{{ testResult.message }}</span>
      </div>

      <!-- Configuration Card -->
      <div class="config-card">
        <div class="config-card-header">
          <h3>Configuration</h3>
        </div>
        <div class="config-card-body">
          <div class="config-grid">
            <div v-if="server.command" class="config-field">
              <span class="config-label">Command</span>
              <code class="config-code">{{ server.command }}</code>
            </div>
            <div v-if="server.args" class="config-field">
              <span class="config-label">Args</span>
              <code class="config-code">{{ server.args }}</code>
            </div>
            <div v-if="server.url" class="config-field">
              <span class="config-label">URL</span>
              <code class="config-code">{{ server.url }}</code>
            </div>
            <div v-if="server.env_json" class="config-field">
              <div class="config-label-row">
                <span class="config-label">Environment Variables</span>
                <button class="reveal-btn" @click="showSecrets = !showSecrets">
                  {{ showSecrets ? 'Hide' : 'Reveal' }}
                </button>
              </div>
              <pre class="config-code-block">{{ showSecrets ? server.env_json : maskSecretValue(server.env_json) }}</pre>
            </div>
            <div v-if="server.headers_json" class="config-field">
              <div class="config-label-row">
                <span class="config-label">Headers</span>
                <button class="reveal-btn" @click="showSecrets = !showSecrets">
                  {{ showSecrets ? 'Hide' : 'Reveal' }}
                </button>
              </div>
              <pre class="config-code-block">{{ showSecrets ? server.headers_json : maskSecretValue(server.headers_json) }}</pre>
            </div>
            <div class="config-field">
              <span class="config-label">Timeout</span>
              <span class="config-value">{{ server.timeout_ms }}ms</span>
            </div>
            <div v-if="server.npm_package" class="config-field">
              <span class="config-label">NPM Package</span>
              <code class="config-code">{{ server.npm_package }}</code>
            </div>
            <div v-if="server.documentation_url" class="config-field">
              <span class="config-label">Documentation</span>
              <a :href="server.documentation_url" target="_blank" class="config-link">{{ server.documentation_url }}</a>
            </div>
            <div v-if="!server.command && !server.url && !server.npm_package" class="config-empty">
              No configuration details available.
            </div>
          </div>
        </div>
      </div>

      <!-- Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon type-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="2" width="20" height="8" rx="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2"/>
            </svg>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ server.server_type }}</span>
            <span class="stat-label">Transport</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon timeout-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ (server.timeout_ms / 1000).toFixed(0) }}s</span>
            <span class="stat-label">Timeout</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon status-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
          <div class="stat-info">
            <span class="stat-value">{{ server.enabled ? 'Enabled' : 'Disabled' }}</span>
            <span class="stat-label">Status</span>
          </div>
        </div>
      </div>

      <!-- Project Assignments -->
      <div class="config-card">
        <div class="config-card-header">
          <h3>Project Assignments</h3>
          <button class="btn btn-sm btn-secondary" @click="showAssignModal = true">
            Assign to Project
          </button>
        </div>
        <div class="config-card-body">
          <div v-if="allProjects.length === 0" class="config-empty">
            No projects available.
          </div>
          <div v-else class="project-list">
            <p class="assignment-hint">Use "Assign to Project" to link this server to a project's MCP configuration.</p>
          </div>
        </div>
      </div>
    </template>

    <!-- Assign to Project Modal -->
    <Teleport to="body">
      <div v-if="showAssignModal" ref="assignModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-assign-project" tabindex="-1" @click.self="showAssignModal = false" @keydown.escape="showAssignModal = false">
        <div class="modal modal-small">
          <div class="modal-header">
            <h2 id="modal-title-assign-project">Assign to Project</h2>
            <button class="modal-close" @click="showAssignModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Project</label>
              <select v-model="selectedProjectToAssign">
                <option value="" disabled>Select a project...</option>
                <option v-for="proj in allProjects" :key="proj.id" :value="proj.id">
                  {{ proj.name }}
                </option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showAssignModal = false">Cancel</button>
            <button class="btn btn-primary" :disabled="!selectedProjectToAssign" @click="assignToProject">
              Assign
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit Server Modal -->
    <Teleport to="body">
      <div v-if="isEditingInfo" ref="editModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-edit-mcp-info" tabindex="-1" @click.self="isEditingInfo = false" @keydown.escape="isEditingInfo = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-edit-mcp-info">Edit MCP Server</h2>
            <button class="modal-close" @click="isEditingInfo = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Server Name *</label>
              <input v-model="editForm.name" type="text" placeholder="Server name" />
            </div>
            <div class="form-group">
              <label>Display Name</label>
              <input v-model="editForm.display_name" type="text" placeholder="Human-friendly display name" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="editForm.description" placeholder="Describe the server..."></textarea>
            </div>
            <div class="form-group">
              <label>Server Type</label>
              <select v-model="editForm.server_type">
                <option value="stdio">stdio</option>
                <option value="sse">sse</option>
                <option value="http">http</option>
              </select>
            </div>
            <div v-if="editForm.server_type === 'stdio'" class="form-group">
              <label>Command</label>
              <input v-model="editForm.command" type="text" placeholder="Command to run" />
            </div>
            <div v-if="editForm.server_type === 'stdio'" class="form-group">
              <label>Args</label>
              <input v-model="editForm.args" type="text" placeholder="Command arguments" />
            </div>
            <div v-if="editForm.server_type !== 'stdio'" class="form-group">
              <label>URL</label>
              <input v-model="editForm.url" type="text" placeholder="Server URL" />
            </div>
            <div class="form-group">
              <label>Timeout (ms)</label>
              <input v-model.number="editForm.timeout_ms" type="number" placeholder="30000" />
            </div>
            <div class="form-group">
              <label>NPM Package</label>
              <input v-model="editForm.npm_package" type="text" placeholder="e.g., @modelcontextprotocol/server-filesystem" />
            </div>
            <div class="form-group">
              <label>Documentation URL</label>
              <input v-model="editForm.documentation_url" type="text" placeholder="https://..." />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="isEditingInfo = false">Cancel</button>
            <button class="btn btn-primary" :disabled="isSaving" @click="saveServerInfo">
              {{ isSaving ? 'Saving...' : 'Save Changes' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.mcp-server-detail-page {
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

.name-badge {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-family: var(--font-mono);
}

.type-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.type-stdio { background: rgba(0, 212, 255, 0.2); color: var(--accent-cyan); }
.type-sse { background: rgba(136, 85, 255, 0.2); color: var(--accent-violet); }
.type-http { background: rgba(0, 255, 136, 0.2); color: var(--accent-emerald); }

.preset-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  background: rgba(255, 170, 0, 0.2);
  color: var(--accent-amber);
}

.category-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* Config Card */
.config-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.config-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.config-card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.config-card-body {
  padding: 20px;
}

.config-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-tertiary);
  letter-spacing: 0.5px;
}

.config-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.reveal-btn {
  padding: 2px 8px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.reveal-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-color: var(--accent-cyan);
}

.config-value {
  font-size: 14px;
  color: var(--text-primary);
}

.config-code {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  word-break: break-all;
}

.config-code-block {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
}

.config-link {
  color: var(--accent-cyan);
  font-size: 0.85rem;
  text-decoration: none;
}

.config-link:hover {
  text-decoration: underline;
}

.config-empty {
  color: var(--text-tertiary);
  text-align: center;
  padding: 20px;
  font-size: 0.9rem;
}

/* Project Assignments */
.project-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.assignment-hint {
  color: var(--text-tertiary);
  font-size: 13px;
  margin: 0;
}

/* Stats */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
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

.stat-icon.type-icon { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan); }
.stat-icon.timeout-icon { background: rgba(255, 170, 0, 0.15); color: var(--accent-amber); }
.stat-icon.status-icon { background: rgba(0, 255, 136, 0.15); color: var(--accent-emerald); }

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

/* Buttons */
.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
}

.btn-active {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
  border: 1px solid rgba(0, 255, 136, 0.3);
}

.btn-active:hover {
  background: rgba(0, 255, 136, 0.25);
}

.btn-inactive {
  background: rgba(136, 136, 136, 0.15);
  color: var(--text-tertiary);
  border: 1px solid var(--border-default);
}

.btn-inactive:hover {
  background: rgba(136, 136, 136, 0.25);
  color: var(--text-secondary);
}

/* Modal */
.modal-small {
  max-width: 400px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
}

/* Test Result */
.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
}

.test-pass {
  background: rgba(0, 255, 136, 0.1);
  border: 1px solid rgba(0, 255, 136, 0.25);
  color: var(--accent-emerald, #00ff88);
}

.test-fail {
  background: rgba(255, 51, 102, 0.1);
  border: 1px solid rgba(255, 51, 102, 0.25);
  color: var(--accent-crimson, #ff3366);
}
</style>
