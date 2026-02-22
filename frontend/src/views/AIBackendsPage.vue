<template>
  <PageLayout :breadcrumbs="[{ label: 'AI Backends' }]">
    <PageHeader title="AI Backends" subtitle="Manage AI backend providers and accounts">
      <template #actions>
        <button
          class="btn btn-primary add-account-btn"
          :disabled="isAddingAccount"
          @click="addProxyAccount"
        >
          <svg v-if="!isAddingAccount" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          <div v-else class="spinner-sm"></div>
          {{ isAddingAccount ? 'Logging in...' : 'Add Account' }}
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading backends..." />

    <ErrorState v-else-if="error" :message="error" @retry="loadBackends()" />

    <EmptyState v-else-if="backends.length === 0" title="No backends configured" description="AI backends will appear here once detected">
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09"/>
        </svg>
      </template>
    </EmptyState>

    <div v-else class="backends-grid">
      <div
        v-for="backend in backends"
        :key="backend.id"
        class="backend-card"
        :class="{ disabled: !backend.is_installed }"
        @click="router.push({ name: 'backend-detail', params: { backendId: backend.id } })"
      >
        <div class="backend-header">
          <div class="backend-icon" :class="backend.type">
            <svg v-if="backend.type === 'claude'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
            </svg>
            <svg v-else-if="backend.type === 'codex'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l9.196 5.308v10.616L12 23.232l-9.196-5.308V7.308z"/>
            </svg>
            <svg v-else-if="backend.type === 'gemini'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l3.09 6.26L22 12l-6.91 3.74L12 22l-3.09-6.26L2 12l6.91-3.74z"/>
            </svg>
            <svg v-else-if="backend.type === 'opencode'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            <span v-else>{{ backend.name[0] }}</span>
          </div>
          <div class="backend-info">
            <h3>{{ backend.name }}</h3>
            <span class="backend-type-label">{{ parseVersion(backend.version) || backend.type }}</span>
          </div>
          <div class="backend-status" :class="{ installed: backend.is_installed }">
            {{ backend.is_installed ? 'Installed' : 'Not Installed' }}
          </div>
        </div>

        <div class="backend-meta">
          <div v-if="backend.models?.length" class="meta-item">
            <span class="meta-label">Models:</span>
            <span class="meta-value">
              <span v-for="model in backend.models" :key="model" class="model-pill">{{ model }}</span>
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Accounts:</span>
            <span class="meta-value account-badge" :class="{ 'has-accounts': (backend.account_count ?? 0) > 0 }">
              {{ (backend.account_count ?? 0) > 0 ? backend.account_count : 'None' }}
            </span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Last Used:</span>
            <span class="meta-value">{{ formatLastUsed(backend.last_used_at) }}</span>
          </div>
          <div v-if="getCapabilityTags(backend.id).length > 0" class="meta-item">
            <span class="meta-label">Capabilities:</span>
            <span class="meta-value">
              <span v-for="tag in getCapabilityTags(backend.id)" :key="tag" class="capability-pill">{{ tag }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="test-panel-section">
      <div class="section-header">
        <h2>Test Backend</h2>
        <p class="subtitle">Send a test prompt to verify your backend configuration</p>
      </div>
      <div class="test-chat-container">
        <AiChatPanel
          :messages="chatMessages"
          :is-processing="chatIsProcessing"
          :streaming-content="chatStreamingContent"
          :input-message="inputMessage"
          :conversation-id="chatSessionId"
          :can-finalize="false"
          :is-finalizing="false"
          :init-streaming-parser="streamingParser.init"
          show-backend-selector
          :selected-backend="selectedBackend"
          :selected-account-id="selectedAccountId"
          :selected-model="selectedModel"
          :chat-mode="chatMode"
          :backend-responses="backendResponses"
          :synthesis-state="synthesisState"
          :is-all-mode-active="isAllModeActive"
          :assistant-icon-paths="['M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z']"
          input-placeholder="Send a prompt — Enter to send, Shift+Enter for new line"
          entity-label="backend"
          banner-title=""
          banner-button-label=""
          :use-smart-scroll="true"
          :process-groups="chatProcessGroups"
          @update:input-message="inputMessage = $event"
          @update:selected-backend="selectedBackend = $event"
          @update:selected-account-id="selectedAccountId = $event"
          @update:selected-model="selectedModel = $event"
          @update:chat-mode="chatMode = $event"
          @send="handleSend"
          @keydown="handleKeyDown"
        >
          <template #welcome>
            <div v-if="chatMessages.length === 0 && !chatIsProcessing" class="chat-welcome">
              <div class="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
                </svg>
              </div>
              <h2>Test Your Backends</h2>
              <p>Select a backend and send a test prompt to verify it works correctly</p>
            </div>
          </template>
        </AiChatPanel>
      </div>
    </div>
  </PageLayout>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { backendApi, superAgentApi, type AIBackend, type BackendCapabilities } from '../services/api';
import { useAiChat } from '../composables/useAiChat';
import { useStreamingParser } from '../composables/useStreamingParser';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();

const showToast = useToast();

/** Extract just the version number (e.g. "2.1.49") from a full version string like "2.1.49 (Claude Code)". */
function parseVersion(version?: string): string {
  if (!version) return '';
  const match = version.match(/\d+\.\d+[\d.]*/);
  return match ? `v${match[0]}` : version;
}

function formatLastUsed(timestamp?: string): string {
  if (!timestamp) return 'Never';
  const d = new Date(timestamp);
  if (isNaN(d.getTime())) return 'Never';
  const date = d.toLocaleDateString();
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return `${date} ${time}`;
}

// =============================================================================
// Backend List State
// =============================================================================

const backends = ref<AIBackend[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const backendCapabilities = ref<Map<string, BackendCapabilities>>(new Map());
const isAddingAccount = ref(false);

async function addProxyAccount() {
  if (isAddingAccount.value) return;
  isAddingAccount.value = true;
  showToast('Opening browser for Claude OAuth login...', 'info');
  try {
    const result = await backendApi.proxyLogin();
    if (result.status === 'completed') {
      showToast('Account added successfully', 'success');
      await loadBackends(true);
    } else {
      showToast(result.message || 'Login failed', 'error');
    }
  } catch (e: any) {
    showToast(e.message || 'Failed to start login', 'error');
  } finally {
    isAddingAccount.value = false;
  }
}

async function loadBackends(silent = false) {
  if (!silent) {
    isLoading.value = true;
    error.value = null;
  }
  try {
    const response = await backendApi.list();
    backends.value = response.backends;
  } catch (err) {
    if (!silent) {
      error.value = 'Failed to load backends';
    }
  } finally {
    if (!silent) {
      isLoading.value = false;
    }
  }
}

async function autoCheckBackends() {
  if (backends.value.length === 0) return;
  await Promise.allSettled(
    backends.value.map(async (b) => {
      const result = await backendApi.check(b.id);
      if (result.capabilities) {
        backendCapabilities.value.set(b.id, result.capabilities);
      }
      // Discover models for installed backends
      if (result.installed) {
        try {
          await backendApi.discoverModels(b.id);
        } catch {
          // Model discovery is best-effort
        }
      }
      return result;
    })
  );
  // Silent reload — don't flash loading spinner
  await loadBackends(true);
}

function getCapabilityTags(backendId: string): string[] {
  const caps = backendCapabilities.value.get(backendId);
  if (!caps) return [];
  const tags: string[] = [];
  if (caps.supports_json_output) tags.push('JSON Output');
  if (caps.supports_token_usage) tags.push('Token Usage');
  if (caps.supports_streaming) tags.push('Streaming');
  if (caps.supports_non_interactive) tags.push('Non-Interactive');
  return tags;
}

// =============================================================================
// Test Chat — uses useAiChat (single source of truth for all AI chat panels)
// =============================================================================

const SYSTEM_TEST_AGENT_NAME = 'Backend Test Agent';

const testAgentId = ref('');
const {
  sessionId: chatSessionId,
  messages: chatMessages,
  isProcessing: chatIsProcessing,
  streamingContent: chatStreamingContent,
  processGroups: chatProcessGroups,
  sendMessage,
  createSession,
  setOnStreamingChunk,
  chatMode,
  backendResponses,
  synthesisState,
  isAllModeActive,
} = useAiChat(testAgentId);

const streamingParser = useStreamingParser();
setOnStreamingChunk((text: string) => {
  streamingParser.write(text);
});
onUnmounted(() => {
  streamingParser.destroy();
});

const inputMessage = ref('');
const selectedBackend = ref('auto');
const selectedAccountId = ref<string | null>(null);
const selectedModel = ref<string | null>(null);

async function ensureTestAgent() {
  try {
    const result = await superAgentApi.list();
    const existing = result.super_agents.find(
      (sa) => sa.name === SYSTEM_TEST_AGENT_NAME,
    );
    if (existing) {
      testAgentId.value = existing.id;
      return;
    }
    // Create the system test agent
    const created = await superAgentApi.create({
      name: SYSTEM_TEST_AGENT_NAME,
      description: 'System agent for testing AI backends',
    });
    testAgentId.value = created.super_agent_id;
  } catch (e: any) {
    console.error('Failed to ensure test agent:', e);
  }
}

function handleSend() {
  if (!inputMessage.value.trim()) return;
  const msg = inputMessage.value.trim();
  inputMessage.value = '';
  sendMessage(msg, {
    backend: selectedBackend.value !== 'auto' ? selectedBackend.value : undefined,
    account_id: selectedAccountId.value || undefined,
    model: selectedModel.value || undefined,
  });
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
}

// =============================================================================
// Lifecycle
// =============================================================================

onMounted(async () => {
  await loadBackends();
  autoCheckBackends();
  await ensureTestAgent();
  // Auto-create a session so the chat input is enabled immediately
  if (testAgentId.value) {
    await createSession();
  }
});
</script>

<style scoped>
.add-account-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.backends-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.backend-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.backend-card:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px var(--accent-cyan-dim);
}

.backend-card.disabled {
  opacity: 0.6;
}

.backend-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.backend-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.backend-icon.claude { background: linear-gradient(135deg, #D97757, #bf6344); }
.backend-icon.opencode { background: linear-gradient(135deg, #00B894, #00a07e); }
.backend-icon.gemini { background: linear-gradient(135deg, #4285F4, #3575db); }
.backend-icon.codex { background: linear-gradient(135deg, #10A37F, #0d8a6a); }

.backend-icon svg {
  width: 24px;
  height: 24px;
}

.backend-info {
  flex: 1;
  min-width: 0;
}

.backend-info h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.backend-type-label {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.backend-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  flex-shrink: 0;
}

.backend-status.installed {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.backend-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.meta-label {
  color: var(--text-tertiary);
}

.meta-value {
  color: var(--text-secondary);
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}

.model-pill {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
  border: 1px solid rgba(136, 85, 255, 0.25);
}

.account-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(150, 150, 150, 0.1);
  color: var(--text-tertiary);
}

.account-badge.has-accounts {
  background: rgba(0, 255, 136, 0.12);
  color: var(--accent-emerald);
}

.capability-pill {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(16, 185, 129, 0.12);
  color: var(--accent-emerald);
  border: 1px solid rgba(16, 185, 129, 0.2);
}

/* Test Panel Section */
.test-panel-section {
  margin-top: 32px;
}

.test-panel-section .section-header {
  margin-bottom: 16px;
}

.test-panel-section .section-header h2 {
  margin: 0 0 4px 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.test-panel-section .section-header .subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.test-chat-container {
  border: 1px solid var(--border-default);
  border-radius: 12px;
  background: var(--bg-secondary);
  height: 500px;
  display: flex;
  overflow: hidden;
}

/* Welcome screen override */
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.welcome-icon {
  width: 80px;
  height: 80px;
  background: var(--bg-tertiary);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.welcome-icon svg {
  width: 40px;
  height: 40px;
  color: var(--accent-violet);
}

.chat-welcome h2 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.chat-welcome p {
  margin: 0;
  color: var(--text-secondary);
}
</style>
