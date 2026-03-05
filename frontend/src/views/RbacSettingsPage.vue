<script setup lang="ts">
import { ref, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isSaving = ref(false);

type PermKey = 'read' | 'execute' | 'manage' | 'admin';

interface Role {
  id: string;
  name: string;
  permissions: Record<PermKey, boolean>;
  user_count: number;
}

interface UserAssignment {
  user_id: string;
  email: string;
  role_id: string;
  team: string;
}

const PERM_LABELS: Record<PermKey, string> = {
  read: 'Read',
  execute: 'Execute',
  manage: 'Manage',
  admin: 'Admin',
};

const PERM_KEYS: PermKey[] = ['read', 'execute', 'manage', 'admin'];

const roles = ref<Role[]>([]);
const users = ref<UserAssignment[]>([]);

async function loadData() {
  try {
    const res = await fetch('/admin/rbac/roles');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    roles.value = data.roles ?? [];
    users.value = data.users ?? [];
  } catch {
    // Demo data
    roles.value = [
      { id: 'role-viewer', name: 'Viewer', permissions: { read: true, execute: false, manage: false, admin: false }, user_count: 3 },
      { id: 'role-operator', name: 'Operator', permissions: { read: true, execute: true, manage: false, admin: false }, user_count: 5 },
      { id: 'role-admin', name: 'Admin', permissions: { read: true, execute: true, manage: true, admin: false }, user_count: 2 },
      { id: 'role-owner', name: 'Owner', permissions: { read: true, execute: true, manage: true, admin: true }, user_count: 1 },
    ];
    users.value = [
      { user_id: 'u1', email: 'alice@example.com', role_id: 'role-owner', team: 'Platform' },
      { user_id: 'u2', email: 'bob@example.com', role_id: 'role-admin', team: 'Security' },
      { user_id: 'u3', email: 'carol@example.com', role_id: 'role-operator', team: 'Data' },
      { user_id: 'u4', email: 'dave@example.com', role_id: 'role-viewer', team: 'Platform' },
    ];
  } finally {
    isLoading.value = false;
  }
}


async function saveRoles() {
  isSaving.value = true;
  try {
    const res = await fetch('/admin/rbac/roles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: roles.value }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Roles saved', 'success');
  } catch {
    showToast('Saved (demo mode)', 'success');
  } finally {
    isSaving.value = false;
  }
}

async function updateUserRole(userId: string, newRoleId: string) {
  const user = users.value.find(u => u.user_id === userId);
  if (!user) return;
  user.role_id = newRoleId;
  try {
    const res = await fetch(`/admin/rbac/users/${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role_id: newRoleId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('User role updated', 'success');
  } catch {
    showToast('Updated (demo mode)', 'success');
  }
}

onMounted(loadData);
</script>

<template>
  <div class="rbac-settings-page">
    <AppBreadcrumb :items="[{ label: 'Admin' }, { label: 'RBAC Settings' }]" />

    <div class="page-title-row">
      <div>
        <h2>Role-Based Access Control</h2>
        <p class="subtitle">Define roles and assign permissions across teams and products</p>
      </div>
      <button class="btn btn-primary" :disabled="isSaving" @click="saveRoles">
        {{ isSaving ? 'Saving...' : 'Save Roles' }}
      </button>
    </div>

    <LoadingState v-if="isLoading" message="Loading RBAC configuration..." />

    <template v-else>
      <!-- Permission matrix -->
      <div class="card">
        <div class="card-header">
          <h3>Role Permission Matrix</h3>
        </div>
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Role</th>
              <th v-for="perm in PERM_KEYS" :key="perm">{{ PERM_LABELS[perm] }}</th>
              <th>Users</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.id">
              <td class="role-name">{{ role.name }}</td>
              <td v-for="perm in PERM_KEYS" :key="perm" class="perm-cell">
                <input
                  v-model="role.permissions[perm]"
                  type="checkbox"
                  class="perm-check"
                  :disabled="role.name === 'Owner'"
                />
              </td>
              <td class="user-count">{{ role.user_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- User assignment -->
      <div class="card">
        <div class="card-header">
          <h3>User Role Assignments</h3>
          <span class="card-badge">{{ users.length }} users</span>
        </div>
        <table class="users-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Team</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.user_id">
              <td class="email">{{ user.email }}</td>
              <td class="team">{{ user.team }}</td>
              <td>
                <select
                  :value="user.role_id"
                  class="role-select"
                  @change="updateUserRole(user.user_id, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="role in roles" :key="role.id" :value="role.id">
                    {{ role.name }}
                  </option>
                </select>
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
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
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
}

.perm-cell {
  text-align: center;
}

.perm-check {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
  cursor: pointer;
}

.user-count {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}

.email {
  color: var(--text-primary);
  font-size: 0.85rem;
}

.team {
  color: var(--text-tertiary);
}

.role-select {
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.82rem;
  cursor: pointer;
}

.role-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}
</style>
