<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import type { SyncStatus } from '../../services/api';
import { pluginExportApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  pluginId: string;
  pluginDir: string;
}>();

const emit = defineEmits<{
  (e: 'synced'): void;
}>();

const showToast = useToast();

const syncStatus = ref<SyncStatus | null>(null);
const isLoadingStatus = ref(true);
const isSyncing = ref(false);
const isTogglingWatch = ref(false);
let pollInterval: ReturnType<typeof setInterval> | null = null;

function getStatusLabel(): string {
  if (!syncStatus.value) return 'Not configured';
  if (syncStatus.value.status === 'synced') return 'Synced';
  if (syncStatus.value.status === 'pending') return 'Pending';
  return 'Not configured';
}

function getStatusClass(): string {
  if (!syncStatus.value) return 'status-gray';
  if (syncStatus.value.status === 'synced') return 'status-green';
  if (syncStatus.value.status === 'pending') return 'status-amber';
  return 'status-gray';
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'Just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}d ago`;
}

async function loadSyncStatus() {
  try {
    const data = await pluginExportApi.getSyncStatus(props.pluginId);
    syncStatus.value = data;
  } catch (err) {
    // Status not available yet, that's okay
    syncStatus.value = null;
  } finally {
    isLoadingStatus.value = false;
  }
}

async function handleSync() {
  isSyncing.value = true;
  try {
    const result = await pluginExportApi.sync(props.pluginId, props.pluginDir);
    showToast(`Synced ${result.synced} entities, skipped ${result.skipped}`, 'success');
    emit('synced');
    await loadSyncStatus();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Sync failed';
    showToast(message, 'error');
  } finally {
    isSyncing.value = false;
  }
}

async function handleToggleWatch() {
  if (!syncStatus.value) return;
  const newState = !syncStatus.value.watching;
  isTogglingWatch.value = true;
  try {
    await pluginExportApi.toggleWatch(props.pluginId, props.pluginDir, newState);
    if (syncStatus.value) {
      syncStatus.value.watching = newState;
    }
    showToast(newState ? 'File watching enabled' : 'File watching disabled', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to toggle watch';
    showToast(message, 'error');
  } finally {
    isTogglingWatch.value = false;
  }
}

onMounted(() => {
  loadSyncStatus();
  pollInterval = setInterval(loadSyncStatus, 30000);
});

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
});
</script>

<template>
  <div class="sync-status-panel">
    <div class="panel-header">
      <h4 class="panel-title">Sync Status</h4>
      <span v-if="!isLoadingStatus" :class="['status-badge', getStatusClass()]">
        {{ getStatusLabel() }}
      </span>
    </div>

    <div v-if="isLoadingStatus" class="loading-state">
      <div class="spinner-sm"></div>
      <span>Loading status...</span>
    </div>

    <template v-else>
      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-label">Entities tracked</span>
          <span class="stat-value">{{ syncStatus?.entities_synced ?? 0 }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Last sync</span>
          <span class="stat-value">{{ formatRelativeTime(syncStatus?.last_synced_at ?? null) }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">Watch</span>
          <span :class="['stat-value', syncStatus?.watching ? 'watch-active' : 'watch-inactive']">
            <span :class="['watch-dot', syncStatus?.watching ? 'dot-active' : 'dot-inactive']"></span>
            {{ syncStatus?.watching ? 'Active' : 'Inactive' }}
          </span>
        </div>
      </div>

      <div class="action-row">
        <button
          class="btn btn-secondary btn-sm"
          :disabled="isSyncing"
          @click="handleSync"
        >
          <template v-if="isSyncing">
            <div class="spinner-xs"></div>
            Syncing...
          </template>
          <template v-else>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 4v6h-6M1 20v-6h6"/>
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
            </svg>
            Sync Now
          </template>
        </button>

        <div class="toggle-container">
          <span class="toggle-label">Watch for Changes</span>
          <button
            :class="['toggle-switch', { active: syncStatus?.watching }]"
            :disabled="isTogglingWatch"
            @click="handleToggleWatch"
          >
            <span class="toggle-knob"></span>
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sync-status-panel {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.25rem;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.panel-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #fff);
}

.status-badge {
  padding: 0.2rem 0.6rem;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 600;
}

.status-green {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
}

.status-amber {
  background: rgba(255, 170, 0, 0.15);
  color: #ffaa00;
}

.status-gray {
  background: rgba(136, 136, 136, 0.15);
  color: #888;
}

.stats-row {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
  padding: 0.75rem;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  color: var(--text-tertiary, #666);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 0.9rem;
  color: var(--text-primary, #fff);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.watch-active {
  color: var(--accent-emerald, #00ff88);
}

.watch-inactive {
  color: var(--text-tertiary, #666);
}

.watch-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot-active {
  background: var(--accent-emerald, #00ff88);
  box-shadow: 0 0 6px rgba(0, 255, 136, 0.5);
}

.dot-inactive {
  background: var(--text-tertiary, #666);
}

.action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan, #00d4ff);
}

.btn-sm {
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
}

.toggle-container {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.toggle-label {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.toggle-switch {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  border: none;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition: all 0.3s;
  padding: 0;
}

.toggle-switch.active {
  background: var(--accent-emerald, #00ff88);
  border-color: var(--accent-emerald, #00ff88);
}

.toggle-switch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--text-primary, #fff);
  transition: transform 0.3s;
}

.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
  background: var(--bg-primary, #0a0a0f);
}

.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-xs {
  width: 14px;
  height: 14px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

</style>
