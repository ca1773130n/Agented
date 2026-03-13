<script setup lang="ts">
import { ref, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { rbacApi, ApiError } from '../services/api';
import type { UserRole, PermissionMatrix } from '../services/api';

const showToast = useToast();
const isLoading = ref(true);
const loadError = ref<string | null>(null);

const roles = ref<UserRole[]>([]);
const permissions = ref<PermissionMatrix>({});

const showCreateForm = ref(false);
const newApiKey = ref('');
const newLabel = ref('');
const newRole = ref('viewer');
const isCreating = ref(false);
const deletingId = ref<string | null>(null);
const editingId = ref<string | null>(null);
const editRole = ref('');
const editLabel = ref('');
const isSavingEdit = ref(false);

const ROLE_OPTIONS = ['viewer', 'operator', 'editor', 'admin'];

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [rolesData, permsData] = await Promise.all([
      rbacApi.listRoles(),
      rbacApi.getPermissions(),
    ]);
    roles.value = rolesData.roles ?? [];
    permissions.value = permsData.permissions ?? {};
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load RBAC data';
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function handleCreate() {
  if (!newApiKey.value.trim() || !newLabel.value.trim()) {
    showToast('API key and label are required', 'info');
    return;
  }
  isCreating.value = true;
  try {
    const result = await rbacApi.createRole({
      api_key: newApiKey.value.trim(),
      label: newLabel.value.trim(),
      role: newRole.value,
    });
    if (result.role) {
      roles.value.unshift(result.role);
    }
    newApiKey.value = '';
    newLabel.value = '';
    newRole.value = 'viewer';
    showCreateForm.value = false;
    showToast('Role created', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create role';
    showToast(message, 'error');
  } finally {
    isCreating.value = false;
  }
}

function startEdit(role: UserRole) {
  editingId.value = role.id;
  editRole.value = role.role;
  editLabel.value = role.label;
}

function cancelEdit() {
  editingId.value = null;
}

async function saveEdit(roleId: string) {
  isSavingEdit.value = true;
  try {
    const updated = await rbacApi.updateRole(roleId, {
      label: editLabel.value,
      role: editRole.value,
    });
    const idx = roles.value.findIndex(r => r.id === roleId);
    if (idx !== -1 && updated) {
      roles.value[idx] = updated;
    }
    editingId.value = null;
    showToast('Role updated', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update role';
    showToast(message, 'error');
  } finally {
    isSavingEdit.value = false;
  }
}

async function handleDelete(role: UserRole) {
  deletingId.value = role.id;
  try {
    await rbacApi.deleteRole(role.id);
    roles.value = roles.value.filter(r => r.id !== role.id);
    showToast('Role deleted', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete role';
    showToast(message, 'error');
  } finally {
    deletingId.value = null;
  }
}

function maskApiKey(key: string): string {
  if (key.length <= 8) return key.slice(0, 4) + '...';
  return key.slice(0, 8) + '...' + key.slice(-4);
}

onMounted(loadData);
</script>

<template>
  <div class="rbac-settings-page">
    <AppBreadcrumb :items="[{ label: 'Admin' }, { label: 'RBAC Settings' }]" />

    <div class="page-title-row">
      <div>
        <h2>Role-Based Access Control</h2>
        <p class="subtitle">Manage API key roles and view the permission matrix</p>
      </div>
      <button class="btn btn-primary" @click="showCreateForm = !showCreateForm">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Add Role
      </button>
    </div>

    <LoadingState v-if="isLoading" message="Loading RBAC configuration..." />

    <div v-else-if="loadError" class="card error-card">
      <div class="error-inner">
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="loadData">Retry</button>
      </div>
    </div>

    <template v-else>
      <!-- Create Form -->
      <div v-if="showCreateForm" class="card create-card">
        <div class="card-header">
          <h3>Add New Role</h3>
        </div>
        <div class="form-body">
          <div class="field-row-3">
            <div class="field-group">
              <label class="field-label">API Key</label>
              <input v-model="newApiKey" type="text" class="text-input" placeholder="agnt_sk_..." />
            </div>
            <div class="field-group">
              <label class="field-label">Label</label>
              <input v-model="newLabel" type="text" class="text-input" placeholder="CI/CD Pipeline" />
            </div>
            <div class="field-group">
              <label class="field-label">Role</label>
              <select v-model="newRole" class="role-select">
                <option v-for="r in ROLE_OPTIONS" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" @click="showCreateForm = false">Cancel</button>
            <button class="btn btn-primary" :disabled="isCreating || !newApiKey.trim() || !newLabel.trim()" @click="handleCreate">
              {{ isCreating ? 'Creating...' : 'Create Role' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Permission matrix -->
      <div v-if="Object.keys(permissions).length > 0" class="card">
        <div class="card-header">
          <h3>Permission Matrix</h3>
        </div>
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Permissions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(perms, roleName) in permissions" :key="roleName">
              <td class="role-name">{{ roleName }}</td>
              <td class="perm-list">
                <span v-for="p in perms" :key="p" class="perm-tag">{{ p }}</span>
                <span v-if="perms.length === 0" class="no-perms">No permissions</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- User Role Assignments -->
      <div class="card">
        <div class="card-header">
          <h3>API Key Role Assignments</h3>
          <span class="card-badge">{{ roles.length }} roles</span>
        </div>
        <div v-if="roles.length === 0" class="list-empty">
          No roles configured. Add a role to map API keys to permissions.
        </div>
        <table v-else class="users-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>API Key</th>
              <th>Role</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.id">
              <td class="label-cell">
                <template v-if="editingId === role.id">
                  <input v-model="editLabel" type="text" class="text-input text-input--inline" />
                </template>
                <template v-else>{{ role.label }}</template>
              </td>
              <td class="api-key-cell">
                <code>{{ maskApiKey(role.api_key) }}</code>
              </td>
              <td>
                <template v-if="editingId === role.id">
                  <select v-model="editRole" class="role-select role-select--inline">
                    <option v-for="r in ROLE_OPTIONS" :key="r" :value="r">{{ r }}</option>
                  </select>
                </template>
                <span v-else class="role-badge" :class="`role-${role.role}`">{{ role.role }}</span>
              </td>
              <td class="date-cell">{{ role.created_at ? new Date(role.created_at).toLocaleDateString() : '-' }}</td>
              <td class="actions-cell">
                <template v-if="editingId === role.id">
                  <button class="btn btn-sm btn-save" :disabled="isSavingEdit" @click="saveEdit(role.id)">Save</button>
                  <button class="btn btn-sm btn-cancel" @click="cancelEdit">Cancel</button>
                </template>
                <template v-else>
                  <button class="btn btn-sm btn-edit" @click="startEdit(role)">Edit</button>
                  <button class="btn btn-sm btn-delete" :disabled="deletingId === role.id" @click="handleDelete(role)">
                    {{ deletingId === role.id ? '...' : 'Delete' }}
                  </button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.rbac-settings-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.create-card {
  border-color: var(--accent-cyan);
}

.form-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-row-3 {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.error-card {
  padding: 48px;
}

.error-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.error-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.list-empty {
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.matrix-table,
.users-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.matrix-table th,
.users-table th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.matrix-table td,
.users-table td {
  padding: 10px 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.matrix-table tr:last-child td,
.users-table tr:last-child td {
  border-bottom: none;
}

.role-name {
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.perm-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.perm-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.no-perms {
  font-size: 0.78rem;
  color: var(--text-muted);
  font-style: italic;
}

.label-cell {
  font-weight: 500;
  color: var(--text-primary);
}

.api-key-cell code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.08);
  padding: 3px 8px;
  border-radius: 4px;
}

.date-cell {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.role-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: capitalize;
}

.role-admin { background: rgba(239, 68, 68, 0.12); color: #ef4444; }
.role-editor { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.role-operator { background: rgba(52, 211, 153, 0.12); color: #34d399; }
.role-viewer { background: var(--bg-tertiary); color: var(--text-tertiary); }

.actions-cell {
  display: flex;
  gap: 6px;
  white-space: nowrap;
}

.text-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus { outline: none; border-color: var(--accent-cyan); }
.text-input--inline { padding: 4px 8px; font-size: 0.82rem; }

.role-select {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.82rem;
  cursor: pointer;
  text-transform: capitalize;
}

.role-select:focus { outline: none; border-color: var(--accent-cyan); }
.role-select--inline { padding: 4px 8px; font-size: 0.78rem; }

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { padding: 8px 16px; font-size: 0.875rem; background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost { padding: 8px 14px; font-size: 0.875rem; background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); cursor: pointer; border-radius: 8px; }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-sm { padding: 4px 10px; font-size: 0.78rem; }

.btn-edit { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-edit:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.btn-save { background: rgba(52, 211, 153, 0.15); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.3); }
.btn-save:hover:not(:disabled) { background: rgba(52, 211, 153, 0.25); }
.btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-cancel { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-tertiary); }
.btn-cancel:hover { color: var(--text-primary); }

.btn-delete { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-tertiary); }
.btn-delete:hover:not(:disabled) { border-color: #ef4444; color: #ef4444; }
.btn-delete:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
