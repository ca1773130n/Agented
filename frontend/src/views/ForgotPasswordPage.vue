<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { authApi } from '../services/api';

const { t } = useI18n();

const email = ref('');
const submitted = ref(false);
const submitting = ref(false);
const error = ref<string | null>(null);

const canSubmit = computed(() => !submitting.value && email.value.trim().length > 0);

async function onSubmit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;
  try {
    await authApi.forgotPassword(email.value.trim());
    submitted.value = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : t('forgotPassword.sendError');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">{{ t('forgotPassword.title') }}</h1>
      <p v-if="!submitted" class="auth-subtitle">
        {{ t('forgotPassword.prompt') }}
      </p>
      <p v-else class="auth-subtitle">
        {{ t('forgotPassword.sent') }}
      </p>

      <form v-if="!submitted" class="auth-form" @submit.prevent="onSubmit">
        <label class="auth-field">
          <span class="auth-label">{{ t('forgotPassword.email') }}</span>
          <input
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="auth-input"
            data-test="forgot-email"
            :disabled="submitting"
          />
        </label>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button
          type="submit"
          class="auth-submit"
          data-test="forgot-submit"
          :disabled="!canSubmit"
        >
          {{ submitting ? t('forgotPassword.sending') : t('forgotPassword.sendLink') }}
        </button>
      </form>

      <p class="auth-switch">
        {{ t('forgotPassword.remembered') }}
        <router-link :to="{ name: 'login' }" class="auth-link">{{ t('forgotPassword.backToSignIn') }}</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg-primary); padding: 24px; }
.auth-card { width: 100%; max-width: 380px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; padding: 32px 28px; box-shadow: 0 16px 48px rgba(0,0,0,0.35); }
.auth-title { margin: 0 0 4px; font-size: 1.5rem; font-weight: 600; color: var(--text-primary); }
.auth-subtitle { margin: 0 0 24px; font-size: 0.875rem; color: var(--text-secondary); line-height: 1.5; }
.auth-form { display: flex; flex-direction: column; gap: 16px; }
.auth-field { display: flex; flex-direction: column; gap: 6px; }
.auth-label { font-size: 0.8125rem; color: var(--text-secondary); }
.auth-input { padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary); font-size: 0.9375rem; transition: border-color 0.15s; }
.auth-input:focus { outline: none; border-color: var(--accent-cyan); }
.auth-error { margin: 0; padding: 8px 12px; font-size: 0.8125rem; color: var(--accent-crimson); background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 6px; }
.auth-submit { padding: 10px 16px; background: var(--accent-cyan); color: var(--text-on-accent, #000); border: none; border-radius: 8px; font-size: 0.9375rem; font-weight: 600; cursor: pointer; transition: filter 0.15s; }
.auth-submit:hover:not(:disabled) { filter: brightness(1.1); }
.auth-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.auth-switch { margin: 16px 0 0; font-size: 0.8125rem; color: var(--text-secondary); text-align: center; }
.auth-link { color: var(--accent-cyan); text-decoration: none; font-weight: 500; }
.auth-link:hover { text-decoration: underline; }
</style>
