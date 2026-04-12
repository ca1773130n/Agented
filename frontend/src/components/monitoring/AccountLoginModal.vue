<script setup lang="ts">
/**
 * AccountLoginModal -- Starts a CLI login session for a backend account.
 *
 * Uses the same /admin/backends/<id>/connect SSE endpoint as AccountWizard.
 * Shows real-time terminal output and handles interactive prompts.
 */
import { ref, onUnmounted } from 'vue';
import { backendManagementApi } from '../../services/api';
import { createAuthenticatedEventSource } from '../../services/api/client';
import type { AuthenticatedEventSource } from '../../services/api/client';

const props = defineProps<{
  open: boolean;
  backendId: string;
  backendType: string;
  backendName: string;
  configPath?: string;
}>();

const emit = defineEmits<{
  close: [];
  success: [];
}>();

const loginStatus = ref<'idle' | 'connecting' | 'streaming' | 'completed' | 'error'>('idle');
const loginLines = ref<string[]>([]);
const loginError = ref('');
const loginSessionId = ref('');
const pendingQuestion = ref('');
const pendingOptions = ref<string[]>([]);
const pendingInteractionId = ref('');
const userResponse = ref('');
const sendingResponse = ref(false);

// Proxy login state
const proxyStatus = ref<'idle' | 'running' | 'device_auth' | 'success' | 'skipped'>('idle');
const proxyMessage = ref('');
const proxyDeviceCode = ref('');
const proxyOAuthUrl = ref('');
const proxyCallbackUrl = ref('');
const proxyForwarding = ref(false);

let loginEventSource: AuthenticatedEventSource | null = null;

async function startLogin() {
  loginStatus.value = 'connecting';
  loginLines.value = [];
  loginError.value = '';
  try {
    const result = await backendManagementApi.startConnect(props.backendId, props.configPath);
    loginSessionId.value = result.session_id;
    const es = createAuthenticatedEventSource(
      `/admin/backends/${props.backendId}/connect/${result.session_id}/stream`
    );
    loginEventSource = es;

    es.addEventListener('log', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      loginLines.value.push(data.content);
      scrollTerminal();
    });
    es.addEventListener('question', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      pendingQuestion.value = data.prompt || '';
      pendingOptions.value = data.options || [];
      pendingInteractionId.value = data.interaction_id || '';
      loginStatus.value = 'streaming';
    });
    es.addEventListener('oauth_url', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.url) {
        loginLines.value.push(`OAuth URL: ${data.url}`);
        window.open(data.url, '_blank');
      }
    });
    es.addEventListener('complete', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.status === 'completed') {
        loginStatus.value = 'completed';
        // Register with CLIProxyAPI
        runProxyLogin();
      } else {
        loginStatus.value = 'error';
        loginError.value = data.error_message || 'Login failed';
      }
      es.close();
    });
    es.addEventListener('error', () => {
      if (loginStatus.value !== 'completed') {
        loginStatus.value = 'error';
        loginError.value = 'Connection lost';
      }
    });
    loginStatus.value = 'streaming';
  } catch (e: unknown) {
    loginStatus.value = 'error';
    loginError.value = e instanceof Error ? e.message : 'Failed to start login';
  }
}

async function sendResponse() {
  if (!userResponse.value.trim() && !pendingOptions.value.length) return;
  sendingResponse.value = true;
  try {
    await backendManagementApi.respondConnect(
      props.backendId,
      loginSessionId.value,
      pendingInteractionId.value,
      { response: userResponse.value.trim() },
    );
    userResponse.value = '';
    pendingQuestion.value = '';
    pendingOptions.value = [];
    pendingInteractionId.value = '';
  } catch {
    loginLines.value.push('Error: Failed to send response');
  } finally {
    sendingResponse.value = false;
  }
}

function selectOption(_opt: string, index: number) {
  userResponse.value = String(index + 1);
  sendResponse();
}

function scrollTerminal() {
  setTimeout(() => {
    const el = document.querySelector('.login-modal .login-terminal-output');
    if (el) el.scrollTop = el.scrollHeight;
  }, 50);
}

function cleanup() {
  if (loginEventSource) {
    loginEventSource.close();
    loginEventSource = null;
  }
  if (loginSessionId.value) {
    backendManagementApi.cancelConnect(props.backendId, loginSessionId.value).catch(() => {});
  }
}

function handleClose() {
  cleanup();
  loginStatus.value = 'idle';
  loginLines.value = [];
  loginError.value = '';
  emit('close');
}

async function runProxyLogin() {
  if (!['claude', 'codex', 'gemini'].includes(props.backendType)) {
    proxyStatus.value = 'skipped';
    return;
  }
  proxyStatus.value = 'running';
  proxyMessage.value = `Registering with API proxy...`;
  try {
    const res = await backendManagementApi.proxyLogin(props.backendType, props.configPath);
    if (res.status === 'ok') {
      proxyStatus.value = 'success';
      proxyMessage.value = res.message || 'API proxy configured';
    } else if (res.status === 'started' && res.device_code) {
      proxyStatus.value = 'device_auth';
      proxyDeviceCode.value = res.device_code;
      proxyOAuthUrl.value = res.oauth_url || '';
      proxyMessage.value = 'Enter the code below to register with API proxy';
    } else if (res.status === 'started' && res.oauth_url) {
      // Auto-open + callback paste for remote deployments
      proxyStatus.value = 'device_auth';
      proxyDeviceCode.value = '';
      proxyOAuthUrl.value = res.oauth_url;
      window.open(res.oauth_url, '_blank');
      proxyMessage.value = 'Sign in with Google, then paste the redirect URL below';
    } else {
      proxyStatus.value = 'skipped';
      proxyMessage.value = res.message || 'Proxy login skipped';
    }
  } catch {
    proxyStatus.value = 'skipped';
    proxyMessage.value = 'API proxy not available';
  }
}

async function forwardCallback() {
  if (!proxyCallbackUrl.value.trim()) return;
  proxyForwarding.value = true;
  try {
    const res = await backendManagementApi.proxyCallbackForward(proxyCallbackUrl.value.trim());
    if (res.status === 'ok' || res.status === 'success') {
      proxyStatus.value = 'success';
      proxyMessage.value = 'API proxy login completed';
    } else {
      proxyMessage.value = res.message || 'Callback forward failed';
    }
  } catch (e: unknown) {
    proxyMessage.value = `Forward failed: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    proxyForwarding.value = false;
  }
}

function handleDone() {
  cleanup();
  loginStatus.value = 'idle';
  loginLines.value = [];
  proxyStatus.value = 'idle';
  emit('success');
}

onUnmounted(cleanup);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      @click.self="handleClose"
      @keydown.escape="handleClose"
    >
      <div class="modal login-modal">
        <div class="modal-header">
          <h2 class="modal-title">Login to {{ backendName }}</h2>
          <button class="modal-close" @click="handleClose">&times;</button>
        </div>

        <!-- Idle — start button -->
        <template v-if="loginStatus === 'idle'">
          <p class="modal-message">Start a CLI login session for this {{ backendName }} account.</p>
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="handleClose">Cancel</button>
            <button class="btn btn-primary" @click="startLogin">Start Login</button>
          </div>
        </template>

        <!-- Connecting -->
        <template v-else-if="loginStatus === 'connecting'">
          <div class="login-connecting">
            <div class="spinner-sm"></div>
            <span>Connecting...</span>
          </div>
        </template>

        <!-- Streaming — interactive terminal -->
        <template v-else-if="loginStatus === 'streaming'">
          <div class="login-terminal-output">
            <div v-for="(line, i) in loginLines" :key="i" class="terminal-line">{{ line }}</div>
          </div>
          <!-- Option buttons -->
          <div v-if="pendingOptions.length > 0" class="login-options">
            <p v-if="pendingQuestion" class="login-question">{{ pendingQuestion }}</p>
            <button v-for="(opt, i) in pendingOptions" :key="i" class="login-option" @click="selectOption(opt, i)">
              <span class="option-num">{{ i + 1 }}</span>
              <span>{{ opt }}</span>
            </button>
          </div>
          <!-- Free-text input -->
          <div v-else-if="pendingQuestion" class="login-input-row">
            <span class="terminal-prompt">&gt;</span>
            <input
              v-model="userResponse"
              class="terminal-input"
              :placeholder="pendingQuestion"
              :disabled="sendingResponse"
              @keydown.enter="sendResponse"
              autofocus
            />
            <button class="btn btn-sm btn-primary" :disabled="sendingResponse" @click="sendResponse">Send</button>
          </div>
        </template>

        <!-- Completed -->
        <template v-else-if="loginStatus === 'completed'">
          <div class="login-success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span>CLI login completed</span>
          </div>

          <!-- Proxy login status -->
          <div v-if="proxyStatus === 'running'" class="proxy-section">
            <div class="spinner-sm"></div>
            <span>{{ proxyMessage }}</span>
          </div>
          <div v-else-if="proxyStatus === 'device_auth'" class="proxy-section proxy-device">
            <p class="proxy-msg">{{ proxyMessage }}</p>
            <div class="proxy-code"><code>{{ proxyDeviceCode }}</code></div>
            <a v-if="proxyOAuthUrl" :href="proxyOAuthUrl" target="_blank" class="btn btn-sm btn-outline proxy-link">
              {{ proxyDeviceCode ? 'Open Device Login Page' : 'Open OAuth Login Page' }}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
              </svg>
            </a>
            <!-- Callback URL paste for remote deployments -->
            <div v-if="proxyOAuthUrl && !proxyDeviceCode" class="proxy-callback">
              <p class="proxy-hint">After signing in, browser redirects to localhost which fails remotely. Copy that URL and paste here:</p>
              <div class="proxy-cb-row">
                <input v-model="proxyCallbackUrl" type="text" placeholder="http://localhost:8085/oauth2callback?code=..." :disabled="proxyForwarding" class="proxy-cb-input" />
                <button class="btn btn-sm btn-primary" :disabled="!proxyCallbackUrl.trim() || proxyForwarding" @click="forwardCallback">
                  {{ proxyForwarding ? '...' : 'Submit' }}
                </button>
              </div>
            </div>
          </div>
          <div v-else-if="proxyStatus === 'success'" class="proxy-section proxy-ok">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span>{{ proxyMessage }}</span>
          </div>
          <div v-else-if="proxyStatus === 'skipped'" class="proxy-section proxy-skip">
            <span>{{ proxyMessage }}</span>
          </div>

          <div class="modal-actions">
            <button class="btn btn-primary" @click="handleDone">Done</button>
          </div>
        </template>

        <!-- Error -->
        <template v-else-if="loginStatus === 'error'">
          <div class="login-terminal-output" v-if="loginLines.length">
            <div v-for="(line, i) in loginLines" :key="i" class="terminal-line">{{ line }}</div>
          </div>
          <p class="login-error-msg">{{ loginError }}</p>
          <div class="modal-actions">
            <button class="btn btn-secondary" @click="handleClose">Close</button>
            <button class="btn btn-primary" @click="startLogin">Retry</button>
          </div>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.login-modal {
  max-width: 560px;
  width: 95%;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.modal-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}
.modal-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0 4px;
}
.modal-message {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 1.5rem;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.625rem;
  margin-top: 1rem;
}
.login-connecting {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem 0;
  color: var(--text-secondary);
}
.login-terminal-output {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 0.75rem;
  max-height: 250px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Monaco', 'Cascadia Code', monospace;
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--text-secondary);
  margin-bottom: 0.75rem;
}
.terminal-line {
  white-space: pre-wrap;
  word-break: break-all;
}
.login-options {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.login-question {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin: 0 0 0.5rem;
}
.login-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8125rem;
  color: var(--text-primary);
  text-align: left;
}
.login-option:hover {
  border-color: var(--accent-violet);
}
.option-num {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.login-input-row {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.terminal-prompt {
  color: var(--accent-emerald);
  font-family: monospace;
}
.terminal-input {
  flex: 1;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  padding: 0.375rem 0.5rem;
  font-family: monospace;
  font-size: 0.8125rem;
  color: var(--text-primary);
}
.login-success {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem 0;
  color: var(--accent-emerald);
  font-weight: 500;
}
.login-error-msg {
  color: var(--accent-red, #ef4444);
  font-size: 0.875rem;
}
.proxy-section {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding: 0.625rem 0.75rem;
  border-radius: 8px;
  font-size: 0.8125rem;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  color: var(--text-secondary);
}
.proxy-device {
  flex-direction: column;
  align-items: center;
  gap: 0.625rem;
}
.proxy-msg {
  margin: 0;
  font-size: 0.8125rem;
}
.proxy-code {
  padding: 0.375rem 1.25rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
}
.proxy-code code {
  font-family: 'SF Mono', 'Monaco', monospace;
  font-size: 1.125rem;
  font-weight: 700;
  letter-spacing: 2px;
  color: #e4e4e7;
}
.proxy-link {
  font-size: 0.75rem;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
.proxy-ok {
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.15);
  color: var(--accent-emerald);
}
.proxy-callback {
  width: 100%;
  margin-top: 0.375rem;
}
.proxy-hint {
  margin: 0 0 0.375rem;
  font-size: 0.6875rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.proxy-cb-row {
  display: flex;
  gap: 0.375rem;
}
.proxy-cb-input {
  flex: 1;
  font-size: 0.6875rem;
  padding: 0.3rem 0.5rem;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-primary);
  font-family: monospace;
}
.proxy-skip {
  background: rgba(234, 179, 8, 0.06);
  border-color: rgba(234, 179, 8, 0.1);
  color: var(--text-tertiary);
}
</style>
