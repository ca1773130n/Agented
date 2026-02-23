<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { superAgentApi } from '../services/api';
import { useStreamingParser } from '../composables/useStreamingParser';
import { useAiChat } from '../composables/useAiChat';
import EntityLayout from '../layouts/EntityLayout.vue';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import DocumentEditor from '../components/super-agents/DocumentEditor.vue';
import SubagentComposition from '../components/super-agents/SubagentComposition.vue';
import MessageInbox from '../components/super-agents/MessageInbox.vue';
import MessageThread from '../components/super-agents/MessageThread.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const route = useRoute();

const superAgentId = computed(() => route.params.superAgentId as string);

const superAgentIdRef = computed(() => superAgentId.value);
const {
  sessionId,
  sessions,
  messages,
  isProcessing,
  streamingContent,
  superAgent,
  error,
  processGroups,
  loadSessions,
  createSession,
  selectSession,
  sendMessage,
  endSession,
  setOnStreamingChunk,
} = useAiChat(superAgentIdRef);

// ---------------------------------------------------------------------------
// smd.js streaming markdown parser (shared composable)
// ---------------------------------------------------------------------------
const streamingParser = useStreamingParser();

// Connect the composable's streaming callback to the smd parser
setOnStreamingChunk((text: string) => {
  streamingParser.write(text);
});

onUnmounted(() => {
  streamingParser.destroy();
});

// Local input state for AiChatPanel
const inputMessage = ref('');

const selectedBackend = ref('auto');
const selectedAccountId = ref<string | null>(null);
const selectedModel = ref<string | null>(null);
const rightTab = ref<'identity' | 'team' | 'sessions' | 'messages'>('identity');
const selectedThreadPeer = ref<string | null>(null);

useWebMcpTool({
  name: 'agented_super_agent_playground_get_state',
  description: 'Returns the current state of the SuperAgent Playground page',
  page: 'SuperAgentPlayground',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SuperAgentPlayground',
        superAgentId: superAgentId.value,
        superAgentName: superAgent.value?.name ?? null,
        sessionId: sessionId.value,
        messageCount: messages.value.length,
        isProcessing: isProcessing.value,
        rightTab: rightTab.value,
      }),
    }],
  }),
  deps: [superAgent, sessionId, messages, isProcessing, rightTab],
});

function handleSelectThread(fromAgentId: string, toAgentId: string) {
  const peer = fromAgentId === superAgentId.value ? toAgentId : fromAgentId;
  selectedThreadPeer.value = peer;
}

function handleThreadBack() {
  selectedThreadPeer.value = null;
}

// Brain icon paths for the assistant avatar
const assistantIconPaths = [
  'M12 2a8 8 0 018 8v1a3 3 0 01-3 3h-1.5',
  'M2 10a8 8 0 018-8',
  'M9.5 14H8a3 3 0 01-3-3v-1',
  'M12 22v-8',
  'M8 22h8',
];

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

function formatSessionDate(dateStr?: string): string {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleString();
}

async function loadData() {
  const data = await superAgentApi.get(superAgentId.value);
  superAgent.value = data;
  // Fire-and-forget: load sessions
  loadSessions();
  return data;
}
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="super agent">
    <template #default="{ reload: _reload }">
  <div class="playground-page">
    <!-- Header -->
    <div class="playground-header">
      <button class="btn-back" @click="router.push({ name: 'super-agents' })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        Back
      </button>
      <div class="header-title">
        <h1>{{ superAgent?.name || 'SuperAgent Playground' }}</h1>
        <p v-if="superAgent?.description">{{ superAgent.description }}</p>
      </div>
      <div class="header-actions">
        <button
          v-if="!sessionId"
          class="btn btn-primary"
          @click="createSession"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          New Session
        </button>
        <button
          v-if="sessionId"
          class="btn btn-secondary"
          @click="endSession"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
          </svg>
          End Session
        </button>
      </div>
    </div>

    <!-- Error banner with retry -->
    <div v-if="error" class="error-banner">
      <span>{{ error }}</span>
      <button class="btn-retry" @click="createSession">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
        </svg>
        Retry
      </button>
    </div>

    <!-- Main content: two-column layout -->
    <div class="playground-content">
      <!-- Left panel: Chat UI -->
      <div class="left-panel">
        <AiChatPanel
          :messages="messages"
          :isProcessing="isProcessing"
          :streamingContent="streamingContent"
          :inputMessage="inputMessage"
          :conversationId="sessionId"
          :canFinalize="false"
          :isFinalizing="false"
          :initStreamingParser="streamingParser.init"
          :assistantIconPaths="assistantIconPaths"
          inputPlaceholder="Send a message to your SuperAgent..."
          entityLabel="SuperAgent"
          bannerTitle=""
          bannerButtonLabel=""
          :showBackendSelector="true"
          :selected-backend="selectedBackend"
          :selected-account-id="selectedAccountId"
          :selected-model="selectedModel"
          :useSmartScroll="true"
          :processGroups="processGroups"
          @update:inputMessage="inputMessage = $event"
          @update:selected-backend="selectedBackend = $event"
          @update:selected-account-id="selectedAccountId = $event"
          @update:selected-model="selectedModel = $event"
          @send="handleSend"
          @keydown="handleKeyDown"
        >
          <template #welcome>
            <div class="sa-welcome">
              <div class="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="8" r="4"/>
                  <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                  <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
                </svg>
              </div>
              <h2 v-if="!sessionId">Start a new session</h2>
              <h2 v-else>Session active</h2>
              <p v-if="!sessionId">
                Click "New Session" to begin chatting with {{ superAgent?.name || 'this SuperAgent' }}.
              </p>
              <p v-else>Send a message to begin the conversation.</p>
            </div>
          </template>
        </AiChatPanel>
      </div>

      <!-- Right panel: Tabs -->
      <div class="right-panel">
        <div class="right-tabs">
          <button
            :class="['right-tab', { active: rightTab === 'identity' }]"
            @click="rightTab = 'identity'"
          >
            Identity
          </button>
          <button
            :class="['right-tab', { active: rightTab === 'team' }]"
            @click="rightTab = 'team'"
          >
            Team
          </button>
          <button
            :class="['right-tab', { active: rightTab === 'sessions' }]"
            @click="rightTab = 'sessions'"
          >
            Sessions
          </button>
          <button
            :class="['right-tab', { active: rightTab === 'messages' }]"
            @click="rightTab = 'messages'"
          >
            Messages
          </button>
        </div>

        <div class="right-content">
          <!-- Identity tab: Document Editor -->
          <div v-if="rightTab === 'identity'" class="tab-panel identity-panel">
            <DocumentEditor :superAgentId="superAgentId" />
          </div>

          <!-- Team tab: Subagent Composition -->
          <div v-if="rightTab === 'team'" class="tab-panel">
            <SubagentComposition
              :superAgentId="superAgentId"
              :teamId="superAgent?.team_id ?? null"
            />
          </div>

          <!-- Sessions tab: Session list -->
          <div v-if="rightTab === 'sessions'" class="tab-panel">
            <div v-if="sessions.length === 0" class="empty-sessions">
              <p>No sessions yet. Start a new session to begin.</p>
            </div>
            <div v-else class="session-list">
              <div
                v-for="sess in sessions"
                :key="sess.id"
                :class="['session-card', { active: sess.id === sessionId }]"
                @click="selectSession(sess.id)"
              >
                <div class="session-info">
                  <span class="session-id">{{ sess.id }}</span>
                  <span class="session-date">{{ formatSessionDate(sess.started_at) }}</span>
                </div>
                <span :class="['session-status', `status-${sess.status}`]">
                  {{ sess.status }}
                </span>
              </div>
            </div>
          </div>

          <!-- Messages tab -->
          <div v-if="rightTab === 'messages'" class="tab-panel">
            <MessageInbox
              v-if="!selectedThreadPeer"
              :superAgentId="superAgentId"
              @selectThread="handleSelectThread"
            />
            <MessageThread
              v-else
              :superAgentId="superAgentId"
              :peerAgentId="selectedThreadPeer"
              @back="handleThreadBack"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.playground-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Header */
.playground-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

.header-title {
  flex: 1;
  min-width: 0;
}

.header-title h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-title p {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
}

.btn svg {
  width: 14px;
  height: 14px;
}

.btn-primary {
  background: var(--accent-violet);
  color: #fff;
}

.btn-primary:hover {
  background: var(--accent-violet);
  filter: brightness(1.15);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  color: var(--text-primary);
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--accent-crimson-dim);
  border-bottom: 1px solid rgba(255, 51, 102, 0.3);
  color: var(--accent-crimson);
  font-size: 13px;
  flex-shrink: 0;
}

.btn-retry {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--accent-crimson);
  border-radius: 4px;
  color: var(--accent-crimson);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-retry:hover {
  background: var(--accent-crimson);
  color: #fff;
}

/* Main content */
.playground-content {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.left-panel {
  flex: 3;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.right-panel {
  flex: 2;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-default);
  min-height: 0;
  min-width: 0;
}

/* Welcome override for chat panel slot */
.sa-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.welcome-icon {
  width: 64px;
  height: 64px;
  background: var(--bg-tertiary);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.welcome-icon svg {
  width: 32px;
  height: 32px;
  color: var(--accent-violet);
}

.sa-welcome h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.sa-welcome p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

/* Right panel tabs */
.right-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border-default);
  padding: 0 8px;
  flex-shrink: 0;
}

.right-tab {
  padding: 10px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: -1px;
}

.right-tab:hover {
  color: var(--text-secondary);
}

.right-tab.active {
  color: var(--accent-cyan);
  border-bottom-color: var(--accent-cyan);
}

.right-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.tab-panel {
  height: 100%;
  overflow-y: auto;
  padding: 12px;
}

.identity-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
}

/* Sessions list */
.empty-sessions {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.empty-sessions p {
  color: var(--text-tertiary);
  font-size: 14px;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.session-card:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  border-color: var(--border-default);
}

.session-card.active {
  border-color: var(--accent-violet);
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.1));
}

.session-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.session-id {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-date {
  font-size: 11px;
  color: var(--text-tertiary);
}

.session-status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  flex-shrink: 0;
}

.status-active {
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.15));
  color: var(--accent-emerald, #00ff88);
}

.status-paused {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.status-completed {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.status-terminated {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}
</style>
