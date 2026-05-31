<template>
  <div class="fallback-chain-editor">
    <div class="section-title-row">
      <h3>{{ t('fallbackChainEditor.title') }}</h3>
      <span class="info-tooltip" :title="t('fallbackChainEditor.infoTooltip')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
      </span>
    </div>

    <div v-if="loading" class="chain-loading">
      <div class="spinner-small"></div>
      <span>{{ t('fallbackChainEditor.loading') }}</span>
    </div>

    <template v-else>
      <div v-if="chain.length === 0" class="chain-empty">
        <p>{{ t('fallbackChainEditor.empty') }}</p>
        <button class="enable-btn" @click="addStep">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('fallbackChainEditor.enableFallback') }}
        </button>
      </div>

      <div v-else class="chain-list">
        <div
          v-for="(entry, index) in chain"
          :key="index"
          class="chain-entry"
          :class="{ dragging: dragIndex === index, 'drag-over': dragOverIndex === index }"
          draggable="true"
          @dragstart="onDragStart(index, $event)"
          @dragover.prevent="onDragOver(index)"
          @dragend="onDragEnd"
          @drop="onDrop(index)"
        >
          <div class="drag-handle" :title="t('fallbackChainEditor.dragToReorder')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </div>

          <span class="step-badge">{{ index + 1 }}</span>

          <select
            class="backend-select"
            :value="entry.backend_type"
            @change="updateEntryBackend(index, ($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>{{ t('fallbackChainEditor.selectBackend') }}</option>
            <option
              v-for="b in availableBackends"
              :key="b.id"
              :value="b.type"
            >
              {{ b.name }} ({{ b.type }})
            </option>
          </select>

          <select
            class="account-select"
            :value="entry.account_id ?? ''"
            @change="updateEntryAccount(index, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ t('fallbackChainEditor.autoSelect') }}</option>
            <option
              v-for="acct in accountsForBackend(entry.backend_type)"
              :key="acct.id"
              :value="acct.id"
            >
              {{ acct.account_name }}
            </option>
          </select>

          <button class="remove-btn" :title="t('fallbackChainEditor.removeStep')" @click="removeStep(index)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        <button class="add-step-btn" @click="addStep">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('fallbackChainEditor.addStep') }}
        </button>

        <div class="chain-actions">
          <button class="btn-save" :disabled="saving" @click="save">
            {{ saving ? t('fallbackChainEditor.saving') : t('common.save') }}
          </button>
          <button class="btn-reset" :disabled="saving" @click="resetChain">
            {{ t('fallbackChainEditor.reset') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { orchestrationApi } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  triggerId: string;
  availableBackends: Array<{ id: string; name: string; type: string }>;
  availableAccounts: Array<{ id: string; account_name: string; backend_id: string }>;
}>();

const emit = defineEmits<{
  (e: 'saved'): void;
  (e: 'error', message: string): void;
}>();

const showToast = useToast();

interface ChainEntry {
  backend_type: string;
  account_id: string | null;
}

const chain = ref<ChainEntry[]>([]);
const loading = ref(true);
const saving = ref(false);

// Drag state
const dragIndex = ref<number | null>(null);
const dragOverIndex = ref<number | null>(null);

async function loadChain() {
  loading.value = true;
  try {
    const data = await orchestrationApi.getFallbackChain(props.triggerId);
    chain.value = (data.chain || []).map(e => ({
      backend_type: e.backend_type,
      account_id: e.account_id,
    }));
  } catch {
    // No chain configured yet -- that's OK
    chain.value = [];
  } finally {
    loading.value = false;
  }
}

function accountsForBackend(backendType: string) {
  const matchingBackend = props.availableBackends.find(b => b.type === backendType);
  if (!matchingBackend) return [];
  return props.availableAccounts.filter(a => a.backend_id === matchingBackend.id);
}

function addStep() {
  const defaultType = props.availableBackends.length > 0 ? props.availableBackends[0].type : '';
  chain.value.push({ backend_type: defaultType, account_id: null });
}

function removeStep(index: number) {
  chain.value.splice(index, 1);
}

function updateEntryBackend(index: number, backendType: string) {
  chain.value[index].backend_type = backendType;
  chain.value[index].account_id = null; // Reset account when backend changes
}

function updateEntryAccount(index: number, value: string) {
  chain.value[index].account_id = value || null;
}

// Drag and drop handlers
function onDragStart(index: number, event: DragEvent) {
  dragIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
  }
}

function onDragOver(index: number) {
  dragOverIndex.value = index;
}

function onDragEnd() {
  dragIndex.value = null;
  dragOverIndex.value = null;
}

function onDrop(toIndex: number) {
  if (dragIndex.value === null || dragIndex.value === toIndex) return;
  const item = chain.value.splice(dragIndex.value, 1)[0];
  chain.value.splice(toIndex, 0, item);
  dragIndex.value = null;
  dragOverIndex.value = null;
}

async function save() {
  saving.value = true;
  try {
    await orchestrationApi.setFallbackChain(props.triggerId, chain.value);
    showToast?.(t('fallbackChainEditor.saved'), 'success');
    emit('saved');
  } catch (err) {
    const msg = err instanceof Error ? err.message : t('fallbackChainEditor.saveFailed');
    showToast?.(msg, 'error');
    emit('error', msg);
  } finally {
    saving.value = false;
  }
}

async function resetChain() {
  await loadChain();
}

onMounted(() => {
  loadChain();
});
</script>

<style scoped>
.fallback-chain-editor {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1.25rem;
}

.section-title-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.section-title-row h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.info-tooltip {
  display: flex;
  align-items: center;
  color: var(--text-tertiary);
  cursor: help;
}

.info-tooltip svg {
  width: 16px;
  height: 16px;
}

.chain-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.chain-empty {
  text-align: center;
  padding: 1.5rem;
  color: var(--text-tertiary);
}

.chain-empty p {
  margin: 0 0 1rem;
  font-size: 0.875rem;
}

.enable-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--accent-cyan-dim);
  border: 1px solid var(--accent-cyan);
  color: var(--accent-cyan);
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.enable-btn:hover {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.enable-btn svg {
  width: 14px;
  height: 14px;
}

.chain-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.chain-entry {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  transition: all var(--transition-fast);
}

.chain-entry.dragging {
  opacity: 0.5;
}

.chain-entry.drag-over {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px var(--accent-cyan-dim);
}

.drag-handle {
  display: flex;
  align-items: center;
  cursor: grab;
  color: var(--text-tertiary);
  padding: 0.25rem;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle svg {
  width: 14px;
  height: 14px;
}

.step-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
}

.backend-select,
.account-select {
  flex: 1;
  padding: 0.4rem 0.6rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8125rem;
  min-width: 0;
}

.backend-select:focus,
.account-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 4px;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.remove-btn:hover {
  color: var(--accent-crimson);
  background: var(--accent-crimson-dim);
}

.remove-btn svg {
  width: 14px;
  height: 14px;
}

.add-step-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: transparent;
  border: 1px dashed var(--border-default);
  color: var(--text-tertiary);
  border-radius: 6px;
  font-size: 0.8125rem;
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-top: 0.25rem;
}

.add-step-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.add-step-btn svg {
  width: 14px;
  height: 14px;
}

.chain-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.btn-save {
  padding: 0.5rem 1.25rem;
  background: var(--accent-cyan);
  color: var(--bg-primary);
  border: none;
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-save:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-reset {
  padding: 0.5rem 1.25rem;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-reset:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-reset:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
