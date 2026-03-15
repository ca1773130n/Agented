<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { repoBotDefaultsApi } from '../services/api/repo-bot-defaults';
import type { AvailableBot, RepoBotBinding } from '../services/api/repo-bot-defaults';

const showToast = useToast();

const bindings = ref<RepoBotBinding[]>([]);
const availableBots = ref<AvailableBot[]>([]);

const showAddModal = ref(false);
const newRepo = ref('');
const newSelectedBots = ref<string[]>([]);

const botTypeColor: Record<string, string> = {
  security: '#f59e0b',
  review: '#06b6d4',
  test: '#34d399',
  docs: '#a78bfa',
};

function botName(id: string) {
  return availableBots.value.find(b => b.id === id)?.name ?? id;
}

function botColor(id: string) {
  const type = availableBots.value.find(b => b.id === id)?.type ?? 'review';
  return botTypeColor[type];
}

async function toggleEnabled(binding: RepoBotBinding) {
  const newEnabled = !binding.enabled;
  try {
    await repoBotDefaultsApi.toggleEnabled(binding.repo, newEnabled);
    binding.enabled = newEnabled;
    showToast(`Default bots ${newEnabled ? 'enabled' : 'disabled'} for ${binding.repo}`, 'success');
  } catch {
    showToast(`Failed to update binding for ${binding.repo}`, 'error');
  }
}

async function removeBinding(repo: string) {
  try {
    await repoBotDefaultsApi.remove(repo);
    const idx = bindings.value.findIndex(b => b.repo === repo);
    if (idx !== -1) bindings.value.splice(idx, 1);
    showToast('Repository binding removed', 'success');
  } catch {
    showToast('Failed to remove binding', 'error');
  }
}

function openAddModal() {
  newRepo.value = '';
  newSelectedBots.value = [];
  showAddModal.value = true;
}

function toggleBotSelection(botId: string) {
  const idx = newSelectedBots.value.indexOf(botId);
  if (idx === -1) newSelectedBots.value.push(botId);
  else newSelectedBots.value.splice(idx, 1);
}

async function saveBinding() {
  if (!newRepo.value.trim() || newSelectedBots.value.length === 0) {
    showToast('Enter a repository and select at least one bot', 'error');
    return;
  }
  try {
    await repoBotDefaultsApi.create({
      repo: newRepo.value.trim(),
      bot_ids: [...newSelectedBots.value],
    });
    // Refresh list from server
    const data = await repoBotDefaultsApi.list();
    bindings.value = data.bindings;
    showAddModal.value = false;
    showToast(`Default bots configured for ${newRepo.value.trim()}`, 'success');
  } catch {
    showToast('Failed to save binding', 'error');
  }
}

onMounted(async () => {
  try {
    const data = await repoBotDefaultsApi.list();
    bindings.value = data.bindings;
    availableBots.value = data.bots;
  } catch {
    showToast('Failed to load repository bindings', 'error');
  }
});

const totalBound = computed(() => bindings.value.filter(b => b.enabled).length);
</script>

<template>
  <div class="repo-defaults">

    <PageHeader
      title="Repository-Level Default Bots"
      subtitle="Associate default bots with GitHub repos so new projects automatically inherit them."
    >
      <template #actions>
        <button class="btn btn-primary" @click="openAddModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Repository
        </button>
      </template>
    </PageHeader>

    <div class="stats-row">
      <div class="stat-card">
        <span class="stat-value">{{ bindings.length }}</span>
        <span class="stat-label">Repositories Configured</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ totalBound }}</span>
        <span class="stat-label">Active Bindings</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ bindings.reduce((s, b) => s + b.projectCount, 0) }}</span>
        <span class="stat-label">Projects Inheriting Bots</span>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
          Repository Bindings
        </h3>
      </div>

      <div v-if="bindings.length === 0" class="empty">
        <p>No repositories configured yet. Click "Add Repository" to get started.</p>
      </div>

      <div v-else class="bindings-list">
        <div v-for="binding in bindings" :key="binding.repo" class="binding-row">
          <div class="binding-repo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
            <span class="repo-name">{{ binding.repo }}</span>
            <span class="project-count">{{ binding.projectCount }} project{{ binding.projectCount !== 1 ? 's' : '' }}</span>
          </div>

          <div class="binding-bots">
            <span
              v-for="botId in binding.bots"
              :key="botId"
              class="bot-chip"
              :style="{ borderColor: botColor(botId) + '40', color: botColor(botId) }"
            >
              {{ botName(botId) }}
            </span>
          </div>

          <div class="binding-actions">
            <button
              class="toggle-btn"
              :class="{ active: binding.enabled }"
              @click="toggleEnabled(binding)"
            >
              {{ binding.enabled ? 'Enabled' : 'Disabled' }}
            </button>
            <button class="icon-btn" title="Remove" @click="removeBinding(binding.repo)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add Repository Binding</h3>
          <button class="icon-btn" @click="showAddModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="modal-body">
          <label class="field-label">GitHub Repository (owner/repo)</label>
          <input v-model="newRepo" type="text" class="text-input" placeholder="e.g. acme/my-service" />

          <label class="field-label" style="margin-top: 16px;">Default Bots</label>
          <div class="bot-options">
            <label v-for="bot in availableBots" :key="bot.id" class="bot-option">
              <input
                type="checkbox"
                :value="bot.id"
                :checked="newSelectedBots.includes(bot.id)"
                @change="toggleBotSelection(bot.id)"
              />
              <span class="bot-option-dot" :style="{ background: botTypeColor[bot.type] }"></span>
              {{ bot.name }}
            </label>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveBinding">Save Binding</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.repo-defaults {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-cyan);
}

.stat-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
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
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.empty {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.875rem;
}

.bindings-list {
  display: flex;
  flex-direction: column;
}

.binding-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.binding-row:last-child { border-bottom: none; }

.binding-repo {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}

.repo-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
  font-family: monospace;
}

.project-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.binding-bots {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.bot-chip {
  font-size: 0.72rem;
  padding: 2px 8px;
  background: transparent;
  border: 1px solid;
  border-radius: 4px;
}

.binding-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-btn {
  font-size: 0.75rem;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.toggle-btn.active {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
}

.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px;
  border-radius: 7px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 480px;
  max-width: 95vw;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.text-input {
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.bot-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bot-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.bot-option input[type="checkbox"] { cursor: pointer; }

.bot-option-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .stats-row { grid-template-columns: 1fr; }
  .binding-row { grid-template-columns: 1fr; gap: 8px; }
}
</style>
