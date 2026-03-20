<script setup lang="ts">
import { ref } from 'vue';
import { healthApi, setApiKey } from '../../services/api';

const emit = defineEmits<{
  authenticated: [];
}>();

const apiKeyInput = ref('');
const error = ref<string | null>(null);
const verifying = ref(false);
const dismissed = ref(false);

async function submit() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    error.value = 'Please enter an API key';
    return;
  }

  verifying.value = true;
  error.value = null;

  try {
    const result = await healthApi.verifyKey(key);
    if (result.valid) {
      setApiKey(key);
      emit('authenticated');
    } else {
      error.value = result.message || 'Invalid API key';
    }
  } catch {
    error.value = 'Failed to verify key. Is the backend running?';
  } finally {
    verifying.value = false;
  }
}

function dismiss() {
  dismissed.value = true;
}
</script>

<template>
  <div v-if="!dismissed" class="api-key-banner" role="alert">
    <div class="banner-content">
      <div class="banner-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      </div>
      <div class="banner-text">
        <strong>API key required</strong>
        <span class="banner-description">The backend requires authentication. Enter your <code>AGENTED_API_KEY</code> to continue.</span>
      </div>
      <form class="banner-form" @submit.prevent="submit">
        <input
          v-model="apiKeyInput"
          type="password"
          placeholder="Enter API key..."
          class="banner-input"
          autocomplete="off"
          :disabled="verifying"
        />
        <button type="submit" class="banner-submit" :disabled="verifying || !apiKeyInput.trim()">
          {{ verifying ? 'Verifying...' : 'Connect' }}
        </button>
      </form>
      <button class="banner-dismiss" @click="dismiss" aria-label="Dismiss">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="error" class="banner-error">{{ error }}</div>
  </div>
</template>

<style scoped>
.api-key-banner {
  background: var(--surface-elevated, #1a1a2e);
  border-bottom: 1px solid var(--accent-amber, #f59e0b);
  padding: 10px 20px;
  z-index: 100;
}

.banner-content {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.banner-icon {
  color: var(--accent-amber, #f59e0b);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.banner-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: var(--text-primary, #e0e0e0);
  min-width: 0;
}

.banner-text strong {
  font-weight: 600;
}

.banner-description {
  color: var(--text-secondary, #999);
  font-size: 12px;
}

.banner-description code {
  background: var(--surface-secondary, rgba(255, 255, 255, 0.06));
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
}

.banner-form {
  display: flex;
  gap: 8px;
  margin-left: auto;
  flex-shrink: 0;
}

.banner-input {
  background: var(--surface-secondary, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--border-primary, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--text-primary, #e0e0e0);
  width: 220px;
  outline: none;
  transition: border-color 0.15s;
}

.banner-input:focus {
  border-color: var(--accent-amber, #f59e0b);
}

.banner-input::placeholder {
  color: var(--text-tertiary, #666);
}

.banner-submit {
  background: var(--accent-amber, #f59e0b);
  color: #000;
  border: none;
  border-radius: 6px;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}

.banner-submit:hover:not(:disabled) {
  opacity: 0.9;
}

.banner-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.banner-dismiss {
  background: none;
  border: none;
  color: var(--text-tertiary, #666);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  transition: color 0.15s;
}

.banner-dismiss:hover {
  color: var(--text-primary, #e0e0e0);
}

.banner-error {
  color: var(--accent-crimson, #ef4444);
  font-size: 12px;
  margin-top: 6px;
  padding-left: 30px;
}
</style>
