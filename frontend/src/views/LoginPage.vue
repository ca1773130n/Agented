<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from '../composables/useAuth';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { login } = useAuth();

const email = ref('');
const password = ref('');
const submitting = ref(false);
const error = ref<string | null>(null);

const canSubmit = computed(
  () => !submitting.value && email.value.trim().length > 0 && password.value.length > 0,
);

async function onSubmit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;
  try {
    await login(email.value.trim(), password.value);
    const next = (route.query.next as string) || '/';
    router.push(next);
  } catch (err) {
    error.value =
      err instanceof Error && err.message
        ? err.message
        : t('login.invalidCredentials');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="login-title">{{ t('login.signIn') }}</h1>
      <p class="login-subtitle">{{ t('login.useAgentedAccount') }}</p>

      <form class="login-form" @submit.prevent="onSubmit">
        <label class="login-field">
          <span class="login-label">{{ t('login.email') }}</span>
          <input
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="login-input"
            data-test="login-email"
            :disabled="submitting"
          />
        </label>

        <label class="login-field">
          <span class="login-label">{{ t('login.password') }}</span>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="login-input"
            data-test="login-password"
            :disabled="submitting"
          />
        </label>

        <p v-if="error" class="login-error" role="alert" data-test="login-error">
          {{ error }}
        </p>

        <button
          type="submit"
          class="login-submit"
          data-test="login-submit"
          :disabled="!canSubmit"
        >
          {{ submitting ? t('login.signingIn') : t('login.signIn') }}
        </button>

        <p class="login-switch">
          {{ t('login.newHere') }}
          <router-link :to="{ name: 'signup' }" class="login-link">{{ t('login.createAccount') }}</router-link>
          ·
          <router-link :to="{ name: 'forgot-password' }" class="login-link">{{ t('login.forgotPassword') }}</router-link>
        </p>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
}

.login-title {
  margin: 0 0 4px;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.login-subtitle {
  margin: 0 0 24px;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.login-label {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.login-input {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9375rem;
  transition: border-color 0.15s;
}

.login-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.login-error {
  margin: 0;
  padding: 8px 12px;
  font-size: 0.8125rem;
  color: var(--accent-crimson);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
}

.login-submit {
  margin-top: 4px;
  padding: 10px 16px;
  background: var(--accent-cyan);
  color: var(--text-on-accent, #000);
  border: none;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s;
}

.login-submit:hover:not(:disabled) {
  filter: brightness(1.1);
}

.login-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-switch {
  margin: 8px 0 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  text-align: center;
}

.login-link {
  color: var(--accent-cyan);
  text-decoration: none;
  font-weight: 500;
}

.login-link:hover {
  text-decoration: underline;
}
</style>
