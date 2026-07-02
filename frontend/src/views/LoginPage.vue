<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from '../composables/useAuth';
import { useI18n } from 'vue-i18n';
import { healthApi, authApi } from '../services/api';
import { setApiKey, clearApiKey } from '../services/api/client';

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

function goNext() {
  const next = (route.query.next as string) || '/';
  router.push(next);
}

async function onSubmit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;
  try {
    await login(email.value.trim(), password.value);
    goNext();
  } catch (err) {
    error.value =
      err instanceof Error && err.message
        ? err.message
        : t('login.invalidCredentials');
  } finally {
    submitting.value = false;
  }
}

// API-key sign-in: operators who authenticate with the admin X-API-Key (no
// account) need a way back in after sessionStorage clears. Paste → store →
// validate against /health/auth-status (it checks the key) → in, or clear + error.
const apiKey = ref('');
const apiKeySubmitting = ref(false);
const apiKeyError = ref<string | null>(null);

// Optional OIDC SSO (25-04): render a button per configured provider returned by
// /health/auth-status. None configured → no buttons; the API-key/login form is
// unchanged and primary.
const oidcProviders = ref<string[]>([]);

onMounted(async () => {
  try {
    const status = await healthApi.authStatus();
    oidcProviders.value = status.oidc_providers ?? [];
  } catch {
    oidcProviders.value = [];
  }
});

function providerLabel(provider: string): string {
  const key = `sso.${provider}`;
  const label = t(key);
  return label === key ? provider : label;
}

function startSso(provider: string) {
  // Full navigation (not fetch) so the browser follows the IdP redirect chain.
  window.location.href = authApi.oidcStartUrl(provider);
}

async function onApiKeySubmit() {
  const key = apiKey.value.trim();
  if (!key || apiKeySubmitting.value) return;
  apiKeySubmitting.value = true;
  apiKeyError.value = null;
  setApiKey(key);
  try {
    const status = await healthApi.authStatus();
    if (status.authenticated) {
      goNext();
    } else {
      clearApiKey();
      apiKeyError.value = t('login.invalidApiKey');
    }
  } catch {
    clearApiKey();
    apiKeyError.value = t('login.invalidApiKey');
  } finally {
    apiKeySubmitting.value = false;
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

      <div v-if="oidcProviders.length" class="login-sso">
        <div class="login-divider"><span>{{ t('sso.orSso') }}</span></div>
        <button
          v-for="provider in oidcProviders"
          :key="provider"
          type="button"
          class="login-sso-btn"
          :data-test="`sso-${provider}`"
          @click="startSso(provider)"
        >
          {{ t('sso.continueWith', { provider: providerLabel(provider) }) }}
        </button>
      </div>

      <div class="login-divider"><span>{{ t('login.or') }}</span></div>

      <form class="login-form" @submit.prevent="onApiKeySubmit">
        <label class="login-field">
          <span class="login-label">{{ t('login.apiKeyLabel') }}</span>
          <input
            v-model="apiKey"
            type="password"
            autocomplete="off"
            class="login-input"
            data-test="login-api-key"
            :placeholder="t('login.apiKeyPlaceholder')"
            :disabled="apiKeySubmitting"
          />
        </label>

        <p v-if="apiKeyError" class="login-error" role="alert" data-test="login-api-key-error">
          {{ apiKeyError }}
        </p>

        <button
          type="submit"
          class="login-submit login-submit-secondary"
          data-test="login-api-key-submit"
          :disabled="apiKeySubmitting || !apiKey.trim()"
        >
          {{ apiKeySubmitting ? t('login.verifying') : t('login.useApiKey') }}
        </button>
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

.login-divider {
  display: flex;
  align-items: center;
  text-align: center;
  margin: 20px 0 16px;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.login-divider::before,
.login-divider::after {
  content: '';
  flex: 1;
  border-top: 1px solid var(--border-default);
}

.login-divider span {
  padding: 0 10px;
}

.login-submit-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.login-link {
  color: var(--accent-cyan);
  text-decoration: none;
  font-weight: 500;
}

.login-link:hover {
  text-decoration: underline;
}

.login-sso {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.login-sso-btn {
  width: 100%;
  padding: 0.6rem 1rem;
  border: 1px solid var(--border, #333);
  border-radius: 8px;
  background: var(--surface, #1a1a1a);
  color: inherit;
  cursor: pointer;
  font-size: 0.9rem;
}
.login-sso-btn:hover {
  background: var(--surface-hover, #222);
}
</style>
