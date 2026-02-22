<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { backendApi, ApiError } from '../../services/api';

const props = defineProps<{
  backendId: string;
  backendType: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'connected'): void;
}>();

// State
const status = ref<'loading' | 'authenticated' | 'not_authenticated' | 'error'>('loading');
const accounts = ref<Array<{ account_id: number; name: string; email: string; authenticated: boolean }>>([]);
const loginInstruction = ref('');
const errorMessage = ref('');

async function checkAuth() {
  status.value = 'loading';
  try {
    const result = await backendApi.checkAuthStatus(props.backendId);
    accounts.value = result.accounts;
    loginInstruction.value = result.login_instruction;

    const allAuthenticated = result.accounts.length > 0 && result.accounts.every(a => a.authenticated);
    const anyAuthenticated = result.accounts.some(a => a.authenticated);

    if (allAuthenticated) {
      status.value = 'authenticated';
    } else if (anyAuthenticated) {
      status.value = 'authenticated'; // partial — show both states
    } else {
      status.value = 'not_authenticated';
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to check auth status';
    errorMessage.value = message;
    status.value = 'error';
  }
}

function handleDone() {
  if (accounts.value.some(a => a.authenticated)) {
    emit('connected');
  }
  emit('close');
}

const cliCommands: Record<string, string> = {
  claude: 'claude',
  codex: 'codex login',
  gemini: 'gemini auth login',
};

onMounted(checkAuth);
</script>

<template>
  <div class="backend-connect">
    <!-- Header -->
    <div class="connect-header">
      <h3>Authentication Status</h3>
      <div class="connect-header-actions">
        <button @click="emit('close')" class="close-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="connect-content">
      <!-- Loading -->
      <div v-if="status === 'loading'" class="status-section">
        <div class="spinner"></div>
        <span class="status-text-dim">Checking credentials...</span>
      </div>

      <!-- Error -->
      <div v-else-if="status === 'error'" class="status-section error-section">
        <div class="status-icon error">!</div>
        <span>{{ errorMessage }}</span>
      </div>

      <!-- Results -->
      <template v-else>
        <!-- Account list -->
        <div v-if="accounts.length > 0" class="accounts-list">
          <div v-for="acct in accounts" :key="acct.account_id" class="account-row">
            <div class="account-status-dot" :class="acct.authenticated ? 'ok' : 'missing'"></div>
            <div class="account-info">
              <span class="account-name">{{ acct.name || 'Account' }}</span>
              <span v-if="acct.email" class="account-email">{{ acct.email }}</span>
            </div>
            <span class="auth-badge" :class="acct.authenticated ? 'ok' : 'missing'">
              {{ acct.authenticated ? 'Authenticated' : 'No Token' }}
            </span>
          </div>
        </div>

        <div v-else class="no-accounts">
          No accounts configured for this backend.
        </div>

        <!-- Instructions for unauthenticated accounts -->
        <div v-if="accounts.some(a => !a.authenticated)" class="instructions-section">
          <div class="instructions-header">How to authenticate</div>
          <p class="instructions-text">{{ loginInstruction }}</p>
          <div class="terminal-example">
            <code>$ {{ cliCommands[backendType] || backendType }}</code>
          </div>
          <p class="instructions-hint">
            After authenticating in your terminal, click "Refresh" to verify.
          </p>
        </div>
      </template>
    </div>

    <!-- Footer -->
    <div class="connect-footer">
      <button
        v-if="status !== 'loading'"
        @click="checkAuth"
        class="btn-refresh"
      >
        Refresh
      </button>
      <button @click="handleDone" class="btn-done">
        Done
      </button>
    </div>
  </div>
</template>

<style scoped>
.backend-connect {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
}

.connect-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.connect-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.connect-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.close-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.connect-content {
  padding: 20px;
  min-height: 100px;
}

.status-section {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  padding: 20px 0;
}

.status-text-dim {
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.status-icon.error {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255, 64, 129, 0.15);
  color: var(--accent-crimson, #ff4081);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.error-section span {
  color: var(--accent-crimson, #ff4081);
  font-size: 0.9rem;
}

.accounts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.account-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.account-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.account-status-dot.ok {
  background: var(--accent-emerald, #00ff88);
}

.account-status-dot.missing {
  background: var(--accent-crimson, #ff4081);
}

.account-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.account-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

.account-email {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.auth-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.auth-badge.ok {
  background: rgba(0, 255, 136, 0.1);
  color: var(--accent-emerald, #00ff88);
}

.auth-badge.missing {
  background: rgba(255, 64, 129, 0.1);
  color: var(--accent-crimson, #ff4081);
}

.no-accounts {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.9rem;
  padding: 20px 0;
}

.instructions-section {
  margin-top: 16px;
  padding: 16px;
  background: rgba(0, 180, 216, 0.06);
  border-radius: 8px;
  border-left: 3px solid var(--accent-cyan, #00b4d8);
}

.instructions-header {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.instructions-text {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.terminal-example {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 10px 14px;
}

.terminal-example code {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--accent-cyan, #00b4d8);
}

.instructions-hint {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin: 10px 0 0 0;
}

.connect-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-subtle);
}

.btn-refresh {
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-refresh:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
  border-color: var(--accent-cyan);
}

.btn-done {
  padding: 8px 20px;
  background: var(--accent-cyan, #00b4d8);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-done:hover {
  background: #00c4ee;
}
</style>
