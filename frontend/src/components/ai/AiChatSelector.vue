<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { backendApi } from '../../services/api';
import type { AIBackend } from '../../services/api';
import type { ChatMode } from '../../composables/useAllMode';

const props = withDefaults(
  defineProps<{
    backend: string;
    accountId: string | null;
    model: string | null;
    chatMode?: ChatMode;
  }>(),
  {
    chatMode: undefined,
  },
);

const emit = defineEmits<{
  (e: 'update:backend', value: string): void;
  (e: 'update:accountId', value: string | null): void;
  (e: 'update:model', value: string | null): void;
  (e: 'update:chatMode', value: ChatMode): void;
}>();

const chatModes: Array<{ value: ChatMode; label: string }> = [
  { value: 'single', label: 'Single' },
  { value: 'all', label: 'All' },
  { value: 'compound', label: 'Compound' },
];

const backends = ref<AIBackend[]>([]);
const loading = ref(true);

onMounted(async () => {
  try {
    const result = await backendApi.list();
    backends.value = (result.backends || []).filter((b) => b.is_installed === 1);
  } catch {
    // Silently fail -- selector will just show "Auto"
  } finally {
    loading.value = false;
  }
});

const selectedBackendData = computed(() => {
  if (props.backend === 'auto') return null;
  return backends.value.find((b) => b.type === props.backend) || null;
});

const accountOptions = computed(() => {
  const b = selectedBackendData.value;
  if (!b || !b.account_emails) return [];
  return b.account_emails
    .split(',')
    .map((e) => e.trim())
    .filter(Boolean);
});

const modelOptions = computed(() => {
  const b = selectedBackendData.value;
  if (!b || !b.models) return [];
  return b.models;
});

const isAutoMode = computed(() => props.backend === 'auto');

// Reset account and model when backend changes
watch(
  () => props.backend,
  () => {
    emit('update:accountId', null);
    emit('update:model', null);
  },
);

function onBackendChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit('update:backend', value);
  // Selecting a specific backend forces single mode (all/compound only works with "auto")
  if (value !== 'auto' && props.chatMode && props.chatMode !== 'single') {
    emit('update:chatMode', 'single');
  }
}

function onAccountChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit('update:accountId', value || null);
}

function onModelChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  emit('update:model', value || null);
}
</script>

<template>
  <div class="ai-chat-selector">
    <div class="selector-group">
      <label class="selector-label">Backend:</label>
      <select
        class="selector-select"
        :value="backend"
        @change="onBackendChange"
        :disabled="loading"
      >
        <option value="auto">Auto</option>
        <option v-for="b in backends" :key="b.type" :value="b.type">
          {{ b.name }}
        </option>
      </select>
    </div>

    <div class="selector-group">
      <label class="selector-label">Account:</label>
      <select
        class="selector-select"
        :value="accountId || ''"
        @change="onAccountChange"
        :disabled="isAutoMode || accountOptions.length === 0"
      >
        <option value="">Auto</option>
        <option v-for="email in accountOptions" :key="email" :value="email">
          {{ email }}
        </option>
      </select>
    </div>

    <div class="selector-group">
      <label class="selector-label">Model:</label>
      <select
        class="selector-select"
        :value="model || ''"
        @change="onModelChange"
        :disabled="isAutoMode || modelOptions.length === 0"
      >
        <option value="">Auto</option>
        <option v-for="m in modelOptions" :key="m" :value="m">
          {{ m }}
        </option>
      </select>
    </div>

    <div v-if="chatMode" class="selector-group mode-group">
      <span class="mode-separator"></span>
      <label
        v-for="m in chatModes"
        :key="m.value"
        class="mode-radio"
        :class="{ active: chatMode === m.value }"
      >
        <input
          type="radio"
          name="chatMode"
          :value="m.value"
          :checked="chatMode === m.value"
          @change="emit('update:chatMode', m.value)"
        />
        {{ m.label }}
      </label>
    </div>

    <slot name="trailing" />
  </div>
</template>

<style scoped>
.ai-chat-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.selector-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.selector-label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.selector-select {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  min-width: 80px;
}

.selector-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.selector-select:focus {
  border-color: var(--accent-violet);
}

.mode-separator {
  width: 1px;
  height: 20px;
  background: var(--border-default);
  margin-right: 4px;
}

.mode-group {
  gap: 2px;
}

.mode-radio {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 3px 8px;
  border-radius: 4px;
  transition: all 0.15s;
  white-space: nowrap;
}

.mode-radio:hover {
  color: var(--text-primary);
}

.mode-radio.active {
  color: var(--accent-violet);
  font-weight: 600;
}

.mode-radio input[type="radio"] {
  appearance: none;
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  border: 1.5px solid var(--text-tertiary);
  border-radius: 50%;
  cursor: pointer;
  position: relative;
  flex-shrink: 0;
}

.mode-radio input[type="radio"]:checked {
  border-color: var(--accent-violet);
}

.mode-radio input[type="radio"]:checked::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-violet);
}
</style>
