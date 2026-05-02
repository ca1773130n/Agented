<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuth } from '../composables/useAuth';

const route = useRoute();
const router = useRouter();
const { signup } = useAuth();

const email = ref('');
const password = ref('');
const displayName = ref('');
const submitting = ref(false);
const error = ref<string | null>(null);

const canSubmit = computed(
  () =>
    !submitting.value &&
    email.value.trim().length > 0 &&
    password.value.length >= 8,
);

async function onSubmit() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;
  try {
    await signup(email.value.trim(), password.value, displayName.value.trim());
    const next = (route.query.next as string) || '/';
    router.push(next);
  } catch (err) {
    error.value =
      err instanceof Error && err.message ? err.message : 'Signup failed';
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="signup-page">
    <div class="signup-card">
      <h1 class="signup-title">Create an account</h1>
      <p class="signup-subtitle">Sign up for Agented.</p>

      <form class="signup-form" @submit.prevent="onSubmit">
        <label class="signup-field">
          <span class="signup-label">Email</span>
          <input
            v-model="email"
            type="email"
            required
            autocomplete="email"
            class="signup-input"
            data-test="signup-email"
            :disabled="submitting"
          />
        </label>

        <label class="signup-field">
          <span class="signup-label">Display name <em class="signup-optional">(optional)</em></span>
          <input
            v-model="displayName"
            type="text"
            autocomplete="name"
            class="signup-input"
            data-test="signup-display-name"
            :disabled="submitting"
          />
        </label>

        <label class="signup-field">
          <span class="signup-label">Password</span>
          <input
            v-model="password"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            class="signup-input"
            data-test="signup-password"
            :disabled="submitting"
          />
          <span class="signup-help">At least 8 characters.</span>
        </label>

        <p v-if="error" class="signup-error" role="alert" data-test="signup-error">
          {{ error }}
        </p>

        <button
          type="submit"
          class="signup-submit"
          data-test="signup-submit"
          :disabled="!canSubmit"
        >
          {{ submitting ? 'Creating account…' : 'Create account' }}
        </button>

        <p class="signup-switch">
          Already have an account?
          <router-link :to="{ name: 'login' }" class="signup-link">Sign in</router-link>
        </p>
      </form>
    </div>
  </div>
</template>

<style scoped>
.signup-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  padding: 24px;
}

.signup-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
}

.signup-title {
  margin: 0 0 4px;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.signup-subtitle {
  margin: 0 0 24px;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.signup-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.signup-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.signup-label {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.signup-optional {
  font-style: normal;
  color: var(--text-tertiary);
  font-size: 0.75rem;
}

.signup-input {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9375rem;
  transition: border-color 0.15s;
}

.signup-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.signup-help {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.signup-error {
  margin: 0;
  padding: 8px 12px;
  font-size: 0.8125rem;
  color: var(--accent-crimson);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
}

.signup-submit {
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

.signup-submit:hover:not(:disabled) {
  filter: brightness(1.1);
}

.signup-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.signup-switch {
  margin: 8px 0 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  text-align: center;
}

.signup-link {
  color: var(--accent-cyan);
  text-decoration: none;
  font-weight: 500;
}

.signup-link:hover {
  text-decoration: underline;
}
</style>
