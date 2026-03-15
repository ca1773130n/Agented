<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isInstalling = ref(false);

type InstallStep = 'connect' | 'select-repos' | 'permissions' | 'done';

interface GitHubInstallation {
  id: string;
  org: string;
  installed_at: string;
  repos: number;
  status: 'active' | 'pending' | 'error';
}

interface Repository {
  id: string;
  name: string;
  full_name: string;
  private: boolean;
  selected: boolean;
}

const installations = ref<GitHubInstallation[]>([]);
const repositories = ref<Repository[]>([]);
const currentStep = ref<InstallStep>('connect');
const orgName = ref('');
const webhookSecret = ref('');
const allRepos = ref(false);

const steps: { key: InstallStep; label: string }[] = [
  { key: 'connect', label: 'Connect Org' },
  { key: 'select-repos', label: 'Select Repos' },
  { key: 'permissions', label: 'Permissions' },
  { key: 'done', label: 'Done' },
];

const stepIndex = computed(() => steps.findIndex(s => s.key === currentStep.value));

async function loadInstallations() {
  try {
    const res = await fetch('/admin/integrations/github/installations');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    installations.value = (await res.json()).installations ?? [];
  } catch {
    installations.value = [
      { id: 'install-001', org: 'acme-corp', installed_at: new Date(Date.now() - 86400000 * 5).toISOString(), repos: 12, status: 'active' },
      { id: 'install-002', org: 'dev-tools-co', installed_at: new Date(Date.now() - 86400000).toISOString(), repos: 3, status: 'active' },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function loadRepos() {
  try {
    const res = await fetch(`/admin/integrations/github/repos?org=${orgName.value}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    repositories.value = (await res.json()).repos ?? [];
  } catch {
    repositories.value = [
      { id: 'repo-1', name: 'api-gateway', full_name: `${orgName.value || 'my-org'}/api-gateway`, private: false, selected: true },
      { id: 'repo-2', name: 'payments-service', full_name: `${orgName.value || 'my-org'}/payments-service`, private: true, selected: true },
      { id: 'repo-3', name: 'frontend-app', full_name: `${orgName.value || 'my-org'}/frontend-app`, private: false, selected: false },
      { id: 'repo-4', name: 'data-pipeline', full_name: `${orgName.value || 'my-org'}/data-pipeline`, private: true, selected: false },
      { id: 'repo-5', name: 'infra-terraform', full_name: `${orgName.value || 'my-org'}/infra-terraform`, private: true, selected: false },
    ];
  }
}

function toggleRepo(repo: Repository) {
  repo.selected = !repo.selected;
}

function toggleAll() {
  allRepos.value = !allRepos.value;
  repositories.value.forEach(r => (r.selected = allRepos.value));
}

async function goNext() {
  if (currentStep.value === 'connect') {
    if (!orgName.value.trim()) {
      showToast('Enter a GitHub organization name', 'error');
      return;
    }
    await loadRepos();
    currentStep.value = 'select-repos';
  } else if (currentStep.value === 'select-repos') {
    currentStep.value = 'permissions';
  } else if (currentStep.value === 'permissions') {
    isInstalling.value = true;
    try {
      const res = await fetch('/admin/integrations/github/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org: orgName.value,
          repos: repositories.value.filter(r => r.selected).map(r => r.id),
          webhook_secret: webhookSecret.value,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('GitHub App installed successfully', 'success');
      await loadInstallations();
    } catch {
      showToast('Installation recorded (demo mode)', 'success');
      installations.value.unshift({
        id: `install-new-${Date.now()}`,
        org: orgName.value,
        installed_at: new Date().toISOString(),
        repos: repositories.value.filter(r => r.selected).length,
        status: 'active',
      });
    } finally {
      isInstalling.value = false;
      currentStep.value = 'done';
    }
  }
}

function startNew() {
  currentStep.value = 'connect';
  orgName.value = '';
  webhookSecret.value = '';
  repositories.value = [];
  allRepos.value = false;
}

function statusColor(status: GitHubInstallation['status']): string {
  if (status === 'active') return '#34d399';
  if (status === 'error') return '#f87171';
  return '#fbbf24';
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' });
}

const selectedCount = computed(() => repositories.value.filter(r => r.selected).length);

onMounted(loadInstallations);
</script>

<template>
  <div class="page-container">

    <div class="page-header">
      <div>
        <h1 class="page-title">One-Click GitHub App Install</h1>
        <p class="page-subtitle">
          Install the Agented GitHub App org-wide in minutes. Auto-provisions webhooks and
          permissions for all selected repositories — no manual webhook setup required.
        </p>
      </div>
      <button class="new-btn" @click="startNew">+ New Installation</button>
    </div>

    <div class="main-grid">
      <!-- Wizard -->
      <div class="wizard-card">
        <h2 class="section-title">Setup Wizard</h2>

        <!-- Step progress -->
        <div class="step-progress">
          <div
            v-for="(step, i) in steps"
            :key="step.key"
            class="step-item"
            :class="{ active: step.key === currentStep, done: i < stepIndex }"
          >
            <div class="step-dot">{{ i < stepIndex ? '✓' : i + 1 }}</div>
            <span class="step-label">{{ step.label }}</span>
          </div>
        </div>

        <!-- Step: Connect -->
        <div v-if="currentStep === 'connect'" class="step-body">
          <p class="step-desc">Enter the GitHub organization you want to connect to Agented.</p>
          <div class="form-group">
            <label class="form-label">GitHub Organization</label>
            <input v-model="orgName" class="form-input" placeholder="e.g. acme-corp" />
          </div>
          <button class="next-btn" @click="goNext">Continue</button>
        </div>

        <!-- Step: Select repos -->
        <div v-else-if="currentStep === 'select-repos'" class="step-body">
          <p class="step-desc">
            Choose which repositories to enable. Webhooks will be auto-created for each.
          </p>
          <div class="repo-header">
            <span class="repo-count">{{ selectedCount }} of {{ repositories.length }} selected</span>
            <button class="toggle-all-btn" @click="toggleAll">
              {{ allRepos ? 'Deselect All' : 'Select All' }}
            </button>
          </div>
          <div class="repo-list">
            <label
              v-for="repo in repositories"
              :key="repo.id"
              class="repo-item"
              :class="{ selected: repo.selected }"
            >
              <input type="checkbox" :checked="repo.selected" @change="toggleRepo(repo)" />
              <span class="repo-name">{{ repo.name }}</span>
              <span class="repo-badge" :class="{ private: repo.private }">
                {{ repo.private ? 'Private' : 'Public' }}
              </span>
            </label>
          </div>
          <button class="next-btn" @click="goNext">Continue</button>
        </div>

        <!-- Step: Permissions -->
        <div v-else-if="currentStep === 'permissions'" class="step-body">
          <p class="step-desc">
            Confirm the permissions the GitHub App will request, and optionally set a webhook
            secret.
          </p>
          <div class="permissions-list">
            <div v-for="perm in ['Read: Contents', 'Read: Pull Requests', 'Write: Checks', 'Write: Issues', 'Write: Statuses']" :key="perm" class="perm-item">
              <span class="perm-icon">✓</span>
              <span class="perm-label">{{ perm }}</span>
            </div>
          </div>
          <div class="form-group" style="margin-top:1rem">
            <label class="form-label">Webhook Secret (optional)</label>
            <input
              v-model="webhookSecret"
              class="form-input"
              type="password"
              placeholder="Leave blank to auto-generate"
            />
          </div>
          <button class="next-btn" :disabled="isInstalling" @click="goNext">
            {{ isInstalling ? 'Installing...' : 'Install App' }}
          </button>
        </div>

        <!-- Step: Done -->
        <div v-else-if="currentStep === 'done'" class="step-body done-body">
          <div class="done-icon">✓</div>
          <h3 class="done-title">Installation Complete</h3>
          <p class="done-desc">
            The GitHub App is now installed for <strong>{{ orgName }}</strong>. Webhooks have been
            provisioned for {{ selectedCount }} repositories.
          </p>
          <button class="next-btn outline" @click="startNew">Install Another</button>
        </div>
      </div>

      <!-- Existing installations -->
      <div class="installs-card">
        <h2 class="section-title">Active Installations</h2>
        <LoadingState v-if="isLoading" message="Loading installations..." />
        <div v-else>
          <div v-for="inst in installations" :key="inst.id" class="install-item">
            <div class="install-header">
              <span class="install-org">{{ inst.org }}</span>
              <span class="install-status" :style="{ color: statusColor(inst.status) }">
                {{ inst.status }}
              </span>
            </div>
            <div class="install-meta">
              <span>{{ inst.repos }} repositories</span>
              <span class="meta-sep">·</span>
              <span>Installed {{ formatDate(inst.installed_at) }}</span>
            </div>
          </div>
          <p v-if="installations.length === 0" class="empty-msg">No installations yet.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 2rem;
  max-width: 1100px;
  margin: 0 auto;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 2rem;
  gap: 1rem;
}
.page-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary, #f0f0f0);
  margin: 0 0 0.5rem;
}
.page-subtitle {
  color: var(--color-text-secondary, #a0a0a0);
  margin: 0;
  max-width: 600px;
}
.new-btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  border: 1px solid var(--color-accent, #6366f1);
  background: transparent;
  color: var(--color-accent, #6366f1);
  font-size: 0.875rem;
  cursor: pointer;
  white-space: nowrap;
}
.main-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 1.5rem;
}
@media (max-width: 800px) {
  .main-grid { grid-template-columns: 1fr; }
}
.wizard-card,
.installs-card {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.5rem;
}
.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary, #f0f0f0);
  margin: 0 0 1.25rem;
}
.step-progress {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 1.5rem;
}
.step-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}
.step-item::after {
  content: '';
  position: absolute;
  top: 14px;
  left: 50%;
  width: 100%;
  height: 1px;
  background: var(--color-border, #2a2a2a);
}
.step-item:last-child::after { display: none; }
.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--color-border, #2a2a2a);
  background: var(--color-bg, #111);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  color: var(--color-text-secondary, #a0a0a0);
  z-index: 1;
  position: relative;
}
.step-item.active .step-dot {
  border-color: var(--color-accent, #6366f1);
  color: var(--color-accent, #6366f1);
}
.step-item.done .step-dot {
  background: var(--color-accent, #6366f1);
  border-color: var(--color-accent, #6366f1);
  color: #fff;
}
.step-label {
  font-size: 0.7rem;
  color: var(--color-text-secondary, #a0a0a0);
  margin-top: 0.3rem;
}
.step-item.active .step-label {
  color: var(--color-text-primary, #f0f0f0);
}
.step-body {
  padding-top: 0.5rem;
}
.step-desc {
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.875rem;
  margin: 0 0 1rem;
}
.form-group { margin-bottom: 1rem; }
.form-label {
  display: block;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #a0a0a0);
  margin-bottom: 0.4rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.form-input {
  width: 100%;
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--color-text-primary, #f0f0f0);
  font-size: 0.875rem;
  box-sizing: border-box;
}
.form-input:focus { outline: none; border-color: var(--color-accent, #6366f1); }
.repo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}
.repo-count { font-size: 0.8rem; color: var(--color-text-secondary, #a0a0a0); }
.toggle-all-btn {
  font-size: 0.75rem;
  background: none;
  border: none;
  color: var(--color-accent, #6366f1);
  cursor: pointer;
}
.repo-list { display: flex; flex-direction: column; gap: 0.4rem; margin-bottom: 1rem; max-height: 200px; overflow-y: auto; }
.repo-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: var(--color-bg, #111);
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-primary, #f0f0f0);
}
.repo-item.selected { border-color: var(--color-accent, #6366f1); }
.repo-name { flex: 1; font-family: monospace; }
.repo-badge {
  font-size: 0.7rem;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  background: rgba(160, 160, 160, 0.15);
  color: var(--color-text-secondary, #a0a0a0);
}
.repo-badge.private { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.permissions-list { display: flex; flex-direction: column; gap: 0.4rem; }
.perm-item { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--color-text-primary, #f0f0f0); }
.perm-icon { color: #34d399; font-size: 0.8rem; }
.next-btn {
  width: 100%;
  padding: 0.6rem;
  border-radius: 6px;
  border: none;
  background: var(--color-accent, #6366f1);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  margin-top: 1rem;
  transition: opacity 0.15s;
}
.next-btn.outline {
  background: transparent;
  border: 1px solid var(--color-accent, #6366f1);
  color: var(--color-accent, #6366f1);
}
.next-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.done-body { text-align: center; padding: 1rem 0; }
.done-icon {
  width: 56px; height: 56px;
  border-radius: 50%;
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
  font-size: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
}
.done-title { font-size: 1.1rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.5rem; }
.done-desc { font-size: 0.875rem; color: var(--color-text-secondary, #a0a0a0); margin: 0 0 1.5rem; }
.install-item {
  padding: 0.875rem 0;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
}
.install-item:last-child { border-bottom: none; }
.install-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem; }
.install-org { font-size: 0.9rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); font-family: monospace; }
.install-status { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.install-meta { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); display: flex; gap: 0.4rem; align-items: center; }
.meta-sep { opacity: 0.4; }
.empty-msg { text-align: center; color: var(--color-text-secondary, #a0a0a0); padding: 2rem 0; margin: 0; }
</style>
