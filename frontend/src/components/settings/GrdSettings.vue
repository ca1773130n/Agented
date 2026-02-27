<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { settingsApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const showToast = useToast();

const autoInitEnabled = ref(true);
const syncOnSessionComplete = ref(true);
const defaultVerificationLevel = ref('proxy');
const isLoading = ref(true);
const isSaving = ref(false);

async function loadSettings() {
  try {
    isLoading.value = true;
    const { settings: allSettings } = await settingsApi.getAll();
    autoInitEnabled.value = allSettings['grd.auto_init_enabled'] !== 'false';
    syncOnSessionComplete.value = allSettings['grd.sync_on_complete'] !== 'false';
    defaultVerificationLevel.value = allSettings['grd.default_verification_level'] || 'proxy';
  } catch {
    // Settings may not exist yet — use defaults
  } finally {
    isLoading.value = false;
  }
}

async function saveSettings() {
  try {
    isSaving.value = true;
    await settingsApi.set('grd.auto_init_enabled', String(autoInitEnabled.value));
    await settingsApi.set('grd.sync_on_complete', String(syncOnSessionComplete.value));
    await settingsApi.set('grd.default_verification_level', defaultVerificationLevel.value);
    showToast('GRD settings saved', 'success');
  } catch (e) {
    const message = e instanceof ApiError ? e.message : 'Failed to save GRD settings';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

onMounted(loadSettings);
</script>

<template>
  <div class="tab-content">
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <span>Loading GRD settings...</span>
    </div>

    <template v-else>
      <div class="card">
        <div class="card-header">
          <h3>Project Initialization</h3>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>Auto-initialize GRD on project creation</strong>
                <span class="toggle-description">Automatically run map-codebase and new-project when a project is created</span>
              </span>
              <button
                :class="['toggle-switch', { active: autoInitEnabled }]"
                @click="autoInitEnabled = !autoInitEnabled"
              >
                <span class="toggle-knob"></span>
              </button>
            </label>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h3>Sync Behavior</h3>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>Sync on session completion</strong>
                <span class="toggle-description">Automatically sync .planning/ files to database when a planning session completes</span>
              </span>
              <button
                :class="['toggle-switch', { active: syncOnSessionComplete }]"
                @click="syncOnSessionComplete = !syncOnSessionComplete"
              >
                <span class="toggle-knob"></span>
              </button>
            </label>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h3>Default Verification Level</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <select v-model="defaultVerificationLevel" class="form-select">
              <option value="sanity">Sanity</option>
              <option value="proxy">Proxy</option>
              <option value="deferred">Deferred</option>
            </select>
            <span class="help-text">Default verification level for new phases</span>
          </div>
        </div>
      </div>

      <div class="form-actions" style="margin-top: 1.5rem;">
        <button class="btn btn-primary" :disabled="isSaving" @click="saveSettings">
          {{ isSaving ? 'Saving...' : 'Save GRD Settings' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.card { overflow: hidden; }
.card-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary, #fff); margin: 0; }
.card-body { padding: 1.25rem; }
.form-group:last-child { margin-bottom: 0; }
.help-text { font-size: 0.8rem; color: var(--text-tertiary, #666); margin-top: 0.5rem; display: block; }
.toggle-group { margin-bottom: 0; }
.toggle-label { display: flex !important; align-items: center; justify-content: space-between; gap: 1rem; cursor: pointer; }
.toggle-text { display: flex; flex-direction: column; gap: 0.25rem; }
.toggle-text strong { font-size: 0.9rem; color: var(--text-primary, #fff); font-weight: 500; }
.toggle-description { font-size: 0.8rem; color: var(--text-tertiary, #666); }
.toggle-switch { position: relative; width: 44px; height: 24px; border-radius: 12px; border: none; background: var(--bg-tertiary, #1a1a24); cursor: pointer; transition: background 0.2s; flex-shrink: 0; padding: 0; }
.toggle-switch.active { background: var(--accent-cyan, #00d4ff); }
.toggle-knob { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: var(--text-primary, #fff); transition: transform 0.2s; }
.toggle-switch.active .toggle-knob { transform: translateX(20px); }
.form-select { width: 100%; padding: 0.75rem 1rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary, #fff); font-size: 0.9rem; transition: border-color 0.15s; }
.form-select:focus { outline: none; border-color: var(--accent-cyan, #00d4ff); }
.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }
.loading-state span { color: var(--text-tertiary, #666); font-size: 0.85rem; }
.spinner { width: 32px; height: 32px; border: 3px solid var(--bg-tertiary, #1a1a24); border-top-color: var(--accent-cyan, #00d4ff); border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
