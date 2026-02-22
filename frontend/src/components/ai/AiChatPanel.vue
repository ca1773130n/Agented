<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue';
import type { ConversationMessage } from '../../services/api';
import type { ProcessGroup as ProcessGroupType } from '../../composables/useProcessGroups';
import { renderMarkdown, attachCodeCopyHandlers } from '../../composables/useMarkdown';
import AiChatSelector from './AiChatSelector.vue';
import AllModeResponse from './AllModeResponse.vue';
import CompoundSynthesis from './CompoundSynthesis.vue';
import MessageBubble from './MessageBubble.vue';
import MessageActions from './MessageActions.vue';
import ProcessGroupComponent from './ProcessGroup.vue';
import type { ChatMode, BackendResponse, SynthesisState } from '../../composables/useAllMode';

const props = withDefaults(
  defineProps<{
    messages: ConversationMessage[];
    isProcessing: boolean;
    streamingContent: string;
    inputMessage: string;
    conversationId: string | null;
    canFinalize: boolean;
    isFinalizing: boolean;
    /** SVG path(s) for the assistant avatar icon */
    assistantIconPaths: string[];
    /** Placeholder text for the input textarea */
    inputPlaceholder: string;
    /** Entity label for the welcome message, e.g. "hook", "command" */
    entityLabel: string;
    /** Banner title when config is ready, e.g. "Hook Ready to Create!" */
    bannerTitle: string;
    /** Banner button label, e.g. "Create Hook Now" */
    bannerButtonLabel: string;
    /** Name of the detected entity for the banner, e.g. "my-custom-hook" */
    detectedEntityName?: string;
    /** Initializes the smd.js streaming parser on the given container element */
    initStreamingParser?: (container: HTMLElement) => void;
    /** Toggle the AiChatSelector bar above the chat */
    showBackendSelector?: boolean;
    /** Current backend selection */
    selectedBackend?: string;
    /** Current account selection */
    selectedAccountId?: string | null;
    /** Current model selection */
    selectedModel?: string | null;
    /** Hides input area when true */
    readOnly?: boolean;
    /** Enable smart auto-scroll (scroll-position preservation when user scrolls up) */
    useSmartScroll?: boolean;
    /** Active process groups (tool calls, reasoning blocks) to display inline */
    processGroups?: Map<string, ProcessGroupType>;
    /** Current chat mode (single/all/compound) */
    chatMode?: ChatMode;
    /** Per-backend responses for All/Compound mode */
    backendResponses?: Map<string, BackendResponse>;
    /** Synthesis state for Compound mode */
    synthesisState?: SynthesisState | null;
    /** Whether All/Compound mode is actively streaming */
    isAllModeActive?: boolean;
  }>(),
  {
    showBackendSelector: false,
    selectedBackend: 'auto',
    selectedAccountId: null,
    selectedModel: null,
    readOnly: false,
    useSmartScroll: false,
    chatMode: 'single',
    synthesisState: null,
    isAllModeActive: false,
  },
);

const chatContainer = ref<HTMLElement | null>(null);
const streamingContainer = ref<HTMLElement | null>(null);

const BACKEND_DISPLAY_NAMES: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  gemini: 'Gemini',
  opencode: 'OpenCode',
};

/** Display name for the currently selected backend (used for streaming/thinking indicators). */
const assistantName = computed(() =>
  BACKEND_DISPLAY_NAMES[props.selectedBackend] ?? 'AI'
);

/** Display name for a specific message (uses only the message's stored backend, never the current dropdown). */
function messageAssistantName(msg: ConversationMessage): string {
  return (msg.backend && BACKEND_DISPLAY_NAMES[msg.backend]) || 'AI';
}

/** Track whether user is near the bottom of the chat (for smart scroll). */
const isNearBottomState = ref(true);
const TOLERANCE_PX = 32; // ~2rem

function checkIsNearBottom(): boolean {
  const el = chatContainer.value;
  if (!el) return true;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  return distanceFromBottom <= TOLERANCE_PX;
}

function onChatScroll() {
  if (props.useSmartScroll) {
    isNearBottomState.value = checkIsNearBottom();
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      if (props.useSmartScroll && !isNearBottomState.value) return;
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
  });
}

function forceScrollToBottom() {
  isNearBottomState.value = true;
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTo({ top: chatContainer.value.scrollHeight, behavior: 'instant' });
    }
  });
}

/** Whether to show the "scroll to bottom" floating button. */
const showScrollButton = computed(() => props.useSmartScroll && !isNearBottomState.value);

// Auto-scroll when messages change and attach code copy handlers
watch(() => props.messages.length, () => {
  scrollToBottom();
  nextTick(() => {
    if (chatContainer.value) {
      attachCodeCopyHandlers(chatContainer.value);
    }
  });
});

// Auto-scroll when streaming content updates
watch(() => props.streamingContent, scrollToBottom);

// Auto-scroll when processing starts (thinking indicator appears)
watch(() => props.isProcessing, (val) => {
  if (val) scrollToBottom();
});

// Auto-scroll when all/compound mode backend responses update
watch(
  () => {
    if (!props.backendResponses) return 0;
    let total = 0;
    for (const r of props.backendResponses.values()) {
      total += r.content.length;
    }
    return total;
  },
  scrollToBottom,
);

// Auto-scroll when synthesis content updates (compound mode)
watch(
  () => props.synthesisState?.content?.length ?? 0,
  scrollToBottom,
);

// Initialize smd.js parser when the streaming container element appears in the DOM
watch(streamingContainer, (el) => {
  if (el && props.initStreamingParser) {
    props.initStreamingParser(el);
  }
  scrollToBottom();
});

const emit = defineEmits<{
  (e: 'update:inputMessage', value: string): void;
  (e: 'send'): void;
  (e: 'keydown', event: KeyboardEvent): void;
  (e: 'finalize'): void;
  (e: 'update:selectedBackend', value: string): void;
  (e: 'update:selectedAccountId', value: string | null): void;
  (e: 'update:selectedModel', value: string | null): void;
  (e: 'update:chatMode', mode: ChatMode): void;
}>();

function onInput(event: Event) {
  const textarea = event.target as HTMLTextAreaElement;
  emit('update:inputMessage', textarea.value);
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

/** Compute the processGroups entries as an array for v-for iteration. */
const processGroupEntries = computed(() => {
  if (!props.processGroups) return [];
  return Array.from(props.processGroups.entries());
});
</script>

<template>
  <div class="chat-panel">
    <AiChatSelector
      v-if="showBackendSelector"
      :backend="selectedBackend"
      :account-id="selectedAccountId ?? null"
      :model="selectedModel ?? null"
      :chat-mode="chatMode"
      @update:backend="emit('update:selectedBackend', $event)"
      @update:account-id="emit('update:selectedAccountId', $event)"
      @update:model="emit('update:selectedModel', $event)"
      @update:chat-mode="emit('update:chatMode', $event)"
    >
      <template #trailing>
        <slot name="selector-trailing" />
      </template>
    </AiChatSelector>

    <slot name="header-extra" />

    <div class="chat-container" ref="chatContainer" @scroll="onChatScroll">
      <slot name="welcome">
        <div v-if="messages.length === 0 && !isProcessing" class="chat-welcome">
          <div class="welcome-icon" :class="{ connecting: !conversationId }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path v-for="(d, i) in assistantIconPaths" :key="i" :d="d"/>
            </svg>
          </div>
          <h2>{{ conversationId ? 'Ready to chat' : `Connecting to ${assistantName}...` }}</h2>
          <p>{{ assistantName }} will guide you through designing your {{ entityLabel }}</p>
        </div>
      </slot>

      <!-- Message rendering: use MessageBubble when useSmartScroll is enabled, legacy inline otherwise -->
      <template v-if="useSmartScroll">
        <div v-for="(msg, index) in messages" :key="index" class="message-wrapper" :class="msg.role">
          <MessageBubble
            :role="msg.role"
            :content="msg.content"
            :timestamp="msg.timestamp"
            :avatar-paths="assistantIconPaths"
            :skip-transition="messages.length > 10 && index < messages.length - 5"
            :assistant-name="messageAssistantName(msg)"
          />
          <MessageActions
            v-if="!isProcessing || index < messages.length - 1"
            :content="msg.content"
            :allMessages="index === messages.length - 1 ? messages : undefined"
          />
        </div>
      </template>
      <template v-else>
        <div v-for="(msg, index) in messages" :key="index" :class="['message', 'message-wrapper', msg.role]">
          <div class="message-avatar">
            <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path v-for="(d, i) in assistantIconPaths" :key="i" :d="d"/>
            </svg>
          </div>
          <div class="message-content">
            <div class="message-header">
              <span class="message-role">{{ msg.role === 'user' ? 'You' : messageAssistantName(msg) }}</span>
              <span class="message-time">{{ new Date(msg.timestamp).toLocaleTimeString() }}</span>
            </div>
            <div class="message-text markdown-body markdown-rendered" v-html="renderMarkdown(msg.content)"></div>
            <MessageActions
              v-if="!isProcessing || index < messages.length - 1"
              :content="msg.content"
              :allMessages="index === messages.length - 1 ? messages : undefined"
            />
          </div>
        </div>
      </template>

      <!-- Streaming indicator (single mode only) -->
      <div v-if="isProcessing && (chatMode === 'single' || !chatMode)" class="message assistant streaming">
        <div class="message-avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path v-for="(d, i) in assistantIconPaths" :key="i" :d="d"/>
          </svg>
        </div>
        <div class="message-content">
          <div class="message-header">
            <span class="message-role">{{ assistantName }}</span>
            <span class="typing-indicator">typing...</span>
          </div>
          <div class="message-text smd-streaming-container markdown-rendered" ref="streamingContainer"></div>
        </div>
      </div>

      <!-- All/Compound mode: tabbed multi-backend response display -->
      <AllModeResponse
        v-if="(chatMode === 'all' || chatMode === 'compound') && backendResponses && backendResponses.size > 0"
        :responses="backendResponses"
        :synthesis-state="synthesisState ?? null"
        :collapsible="chatMode === 'compound'"
      />

      <!-- Compound mode: synthesis result bubble -->
      <CompoundSynthesis
        v-if="synthesisState && synthesisState.status !== 'waiting'"
        :synthesis="synthesisState"
      />

      <!-- Process groups (tool calls, reasoning, code execution) -->
      <template v-if="processGroupEntries.length > 0">
        <ProcessGroupComponent
          v-for="[groupId, group] in processGroupEntries"
          :key="groupId"
          :id="groupId"
          :type="group.type"
          :label="group.label"
          :timestamp="group.timestamp"
          :auto-collapse-ms="group.type === 'tool_call' ? 4000 : 2000"
        >
          <pre class="process-group-content">{{ group.content }}</pre>
        </ProcessGroupComponent>
      </template>

      <div v-if="isProcessing && !streamingContent" class="processing-indicator">
        <div class="dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span>{{ assistantName }} is thinking...</span>
      </div>

      <!-- Scroll to bottom button (only shown when useSmartScroll and user scrolled up) -->
      <button
        v-if="showScrollButton"
        class="scroll-to-bottom-btn"
        @click="forceScrollToBottom"
        title="Scroll to bottom"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
    </div>

    <div v-if="canFinalize" class="convert-banner">
      <div class="banner-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path v-for="(d, i) in assistantIconPaths" :key="i" :d="d"/>
          <path d="M20 6L9 17l-5-5" stroke-width="2.5"/>
        </svg>
      </div>
      <div class="banner-content">
        <h3>{{ bannerTitle }}</h3>
        <p>{{ assistantName }} has designed your {{ entityLabel }}{{ detectedEntityName ? ': ' + detectedEntityName : '' }}. Click the button to finalize.</p>
      </div>
      <button class="btn btn-primary btn-convert" :disabled="isFinalizing" @click="emit('finalize')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ isFinalizing ? 'Creating...' : bannerButtonLabel }}
      </button>
    </div>

    <div v-if="!readOnly" class="input-area">
      <div class="input-wrapper">
        <textarea
          :value="inputMessage"
          @input="onInput($event)"
          :placeholder="inputPlaceholder"
          :disabled="isProcessing"
          @keydown="emit('keydown', $event)"
          rows="1"
        ></textarea>
        <button
          class="btn-send"
          :disabled="!inputMessage.trim() || isProcessing"
          @click="emit('send')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  position: relative;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
}

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

.welcome-icon.connecting {
  animation: connectPulse 1.5s infinite ease-in-out;
}

@keyframes connectPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.95); }
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

.message {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.message.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.message.assistant {
  align-self: flex-start;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: var(--accent-cyan-dim);
}

.message.user .message-avatar svg {
  color: var(--accent-cyan);
}

.message.assistant .message-avatar {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
}

.message.assistant .message-avatar svg {
  color: var(--accent-violet, #8855ff);
}

.message-avatar svg {
  width: 20px;
  height: 20px;
}

.message-content {
  background: var(--bg-tertiary);
  border-radius: 12px;
  padding: 12px 16px;
  min-width: 100px;
  position: relative;
}

/* Show message actions on hover */
.message-wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
}

.message-wrapper.user {
  align-items: flex-end;
}

.message-wrapper.assistant {
  align-items: flex-start;
}

.message-wrapper:hover :deep(.message-actions) {
  opacity: 1;
  pointer-events: auto;
}

.message.user .message-content {
  background: var(--accent-cyan-dim);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.message-role {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.typing-indicator {
  font-size: 11px;
  color: var(--accent-violet);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.message-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* smd.js streaming container base styles */
.smd-streaming-container {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* Process group inline content */
.process-group-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-secondary);
}

.processing-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 12px;
  align-self: flex-start;
  color: var(--text-secondary);
  font-size: 14px;
}

.dots {
  display: flex;
  gap: 4px;
}

.dots span {
  width: 8px;
  height: 8px;
  background: var(--accent-violet);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.dots span:nth-child(1) { animation-delay: -0.32s; }
.dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Scroll to bottom button */
.scroll-to-bottom-btn {
  position: sticky;
  bottom: 8px;
  align-self: flex-end;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  z-index: 10;
}

.scroll-to-bottom-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--accent-violet);
}

.scroll-to-bottom-btn svg {
  width: 18px;
  height: 18px;
  color: var(--text-secondary);
}

/* Convert Banner */
.convert-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  background: linear-gradient(135deg, rgba(136, 85, 255, 0.1) 0%, rgba(0, 212, 255, 0.1) 100%);
  border-top: 1px solid var(--accent-violet);
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.banner-icon {
  width: 48px;
  height: 48px;
  background: var(--accent-violet);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.banner-icon svg {
  width: 28px;
  height: 28px;
  color: #fff;
}

.banner-content {
  flex: 1;
}

.banner-content h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.banner-content p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.btn-convert {
  padding: 12px 24px;
  font-size: 15px;
  font-weight: 600;
  background: linear-gradient(135deg, var(--accent-violet) 0%, var(--accent-cyan) 100%);
  border: none;
  box-shadow: 0 4px 12px rgba(136, 85, 255, 0.3);
}

.btn-convert:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(136, 85, 255, 0.4);
}

.btn-convert svg {
  width: 18px;
  height: 18px;
}

/* Input area */
.input-area {
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.input-wrapper {
  display: flex;
  gap: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 12px 16px;
  transition: border-color 0.15s;
}

.input-wrapper:focus-within {
  border-color: var(--accent-violet);
}

.input-wrapper textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 120px;
}

.input-wrapper textarea::placeholder {
  color: var(--text-tertiary);
}

.btn-send {
  width: 40px;
  height: 40px;
  background: var(--accent-violet);
  border: none;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.btn-send:hover:not(:disabled) {
  background: #9966ff;
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-send svg {
  width: 20px;
  height: 20px;
  color: #fff;
}

/* Button base styles (needed for convert banner button) */

.btn-primary {
  background: var(--accent-violet);
  color: #fff;
}

.btn-primary:hover {
  background: #9966ff;
}

.btn-primary svg {
  width: 16px;
  height: 16px;
}
</style>
