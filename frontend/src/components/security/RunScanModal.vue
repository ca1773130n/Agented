<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { Trigger } from '../../services/api';
import { triggerApi, ApiError } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  triggers: Trigger[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'scanStarted'): void;
}>();

const scanModalRef = ref<HTMLElement | null>(null);
const alwaysOpen = ref(true);
useFocusTrap(scanModalRef, alwaysOpen);

const selectedTriggerId = ref('');
const triggerInfo = ref<Trigger | null>(null);
const isRunning = ref(false);
const statusMessage = ref('');
const statusType = ref<'success' | 'error'>('success');
const showStatus = ref(false);

const triggersWithPaths = ref<Trigger[]>([]);

onMounted(() => {
  triggersWithPaths.value = props.triggers.filter(t => (t.path_count || 0) > 0);
});

async function onTriggerSelect() {
  if (!selectedTriggerId.value) {
    triggerInfo.value = null;
    return;
  }
  try {
    triggerInfo.value = await triggerApi.get(selectedTriggerId.value);
  } catch {
    triggerInfo.value = null;
  }
}

async function runScan() {
  if (!selectedTriggerId.value) {
    setStatus('Please select a trigger', 'error');
    return;
  }

  isRunning.value = true;
  showStatus.value = false;

  try {
    const result = await triggerApi.run(selectedTriggerId.value);
    setStatus(
      `Trigger "${result.message}" - Scan is running in the background. Results will appear after completion.`,
      'success'
    );
    setTimeout(() => {
      emit('scanStarted');
    }, 3000);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to start trigger';
    setStatus(message, 'error');
    isRunning.value = false;
  }
}

function setStatus(message: string, type: 'success' | 'error') {
  statusMessage.value = message;
  statusType.value = type;
  showStatus.value = true;
}
</script>

<template>
  <div ref="scanModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-run-scan" tabindex="-1" @click.self="emit('close')" @keydown.escape="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            <path d="M9 12l2 2 4-4"/>
          </svg>
        </div>
        <div>
          <h3 id="modal-title-run-scan">Run Security Scan</h3>
          <p class="modal-subtitle">Execute vulnerability analysis on project paths</p>
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <div class="form-group">
          <label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="11" width="18" height="10" rx="2"/>
              <circle cx="12" cy="5" r="2"/>
              <path d="M12 7v4"/>
            </svg>
            Select Trigger
          </label>
          <select v-model="selectedTriggerId" @change="onTriggerSelect">
            <option value="">
              {{ triggersWithPaths.length === 0 ? 'No triggers with configured paths' : 'Choose a trigger to run...' }}
            </option>
            <option v-for="trigger in triggersWithPaths" :key="trigger.id" :value="trigger.id">
              {{ trigger.name }} ({{ trigger.path_count }} path{{ trigger.path_count !== 1 ? 's' : '' }})
            </option>
          </select>
        </div>

        <div v-if="triggerInfo" class="info-panel">
          <div class="info-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span>Configured Paths</span>
          </div>
          <div class="paths-list">
            <div v-for="path in (triggerInfo.paths || [])" :key="path.local_project_path" class="path-entry">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M9 18l6-6-6-6"/>
              </svg>
              {{ path.local_project_path }}
            </div>
            <div v-if="!triggerInfo.paths || triggerInfo.paths.length === 0" class="empty-text">
              No paths configured for this trigger
            </div>
          </div>
        </div>

        <div v-if="showStatus" class="status-message" :class="statusType">
          <svg v-if="statusType === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M15 9l-6 6M9 9l6 6"/>
          </svg>
          {{ statusMessage }}
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
        <button class="btn btn-primary" :disabled="isRunning || !selectedTriggerId" @click="runScan">
          <svg v-if="isRunning" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          {{ isRunning ? 'Scan Started' : 'Run Scan' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>

@keyframes overlayFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes modalSlideIn {
  from { opacity: 0; transform: translateY(-20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-emerald-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent-emerald);
}

.modal-header h3 {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.modal-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.close-btn {
  margin-left: auto;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-tertiary);
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.form-group label svg {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
}

.form-group select:focus {
  border-color: var(--accent-cyan);
  outline: none;
  box-shadow: 0 0 0 3px var(--accent-cyan-dim);
}

.info-panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 20px;
}

.info-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.info-header svg {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
}

.paths-list {
  padding: 12px 16px;
}

.path-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.path-entry:last-child {
  border-bottom: none;
}

.path-entry svg {
  width: 12px;
  height: 12px;
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.empty-text {
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 12px 0;
}

.status-message {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  font-size: 0.875rem;
  line-height: 1.5;
}

.status-message svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 1px;
}

.status-message.success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
  border: 1px solid rgba(0, 255, 136, 0.2);
}

.status-message.error {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  border: 1px solid rgba(255, 51, 102, 0.2);
}

.btn-primary {
  background: var(--accent-emerald);
  color: var(--bg-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--text-primary);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.spinner {
  animation: spin 1s linear infinite;
}

</style>
