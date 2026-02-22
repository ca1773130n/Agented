<script setup lang="ts">
import { ref } from 'vue';

const props = withDefaults(
  defineProps<{
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{
  (e: 'send', text: string): void;
}>();

const inputText = ref('');
const history = ref<string[]>([]);
const historyIndex = ref(-1);

function handleSend() {
  const text = inputText.value.trim();
  if (!text) return;

  // Add to history (max 50)
  history.value.unshift(text);
  if (history.value.length > 50) {
    history.value.pop();
  }
  historyIndex.value = -1;

  emit('send', text);
  inputText.value = '';
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSend();
    return;
  }

  if (event.key === 'ArrowUp') {
    if (history.value.length === 0) return;
    event.preventDefault();
    if (historyIndex.value < history.value.length - 1) {
      historyIndex.value++;
      inputText.value = history.value[historyIndex.value];
    }
    return;
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault();
    if (historyIndex.value > 0) {
      historyIndex.value--;
      inputText.value = history.value[historyIndex.value];
    } else if (historyIndex.value === 0) {
      historyIndex.value = -1;
      inputText.value = '';
    }
    return;
  }
}
</script>

<template>
  <div class="session-input">
    <div class="input-row">
      <input
        type="text"
        v-model="inputText"
        class="input-field"
        placeholder="Type a message..."
        :disabled="props.disabled"
        @keydown="onKeydown"
      />
      <button
        class="send-btn"
        :disabled="props.disabled || !inputText.trim()"
        title="Send"
        @click="handleSend"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.session-input {
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 8px 12px;
  transition: border-color 0.15s;
}

.input-row:focus-within {
  border-color: var(--accent-cyan);
}

.input-field {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
  font-family: 'Geist Mono', monospace;
  outline: none;
  min-width: 0;
}

.input-field::placeholder {
  color: var(--text-muted);
}

.input-field:disabled {
  opacity: 0.5;
}

.send-btn {
  width: 32px;
  height: 32px;
  background: var(--accent-cyan);
  border: none;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.send-btn svg {
  width: 16px;
  height: 16px;
  color: #fff;
}
</style>
