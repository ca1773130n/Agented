<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useSketchChat } from '../composables/useSketchChat';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import SketchClassification from '../components/sketches/SketchClassification.vue';
import SketchRouting from '../components/sketches/SketchRouting.vue';
import SketchStatusTracker from '../components/sketches/SketchStatusTracker.vue';
import type { Sketch } from '../services/api/types';
import type { ConversationMessage } from '../services/api';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

function handleNavigateTo(view: string, id?: string) {
  if (view === 'super-agent-playground' && id) {
    router.push({ name: 'super-agent-playground', params: { superAgentId: id } });
  } else if (view === 'team-dashboard' && id) {
    router.push({ name: 'team-dashboard', params: { teamId: id } });
  } else {
    router.push({ name: view });
  }
}

const showToast = useToast();

const {
  sketches,
  currentSketch,
  selectedProjectId,
  projects,
  isProcessing,
  messages: rawMessages,
  error,
  loadProjects,
  loadSketches,
  submitSketch,
  routeSketch,
  selectSketch,
  clearChat,
} = useSketchChat();

const inputText = ref('');

useWebMcpTool({
  name: 'hive_sketch_chat_get_state',
  description: 'Returns the current state of the Sketch Chat page',
  page: 'SketchChatPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SketchChatPage',
        inputText: inputText.value,
        messageCount: rawMessages.value.length,
        currentSketchId: currentSketch.value?.id ?? null,
        currentSketchStatus: currentSketch.value?.status ?? null,
        hasClassification: !!currentSketch.value?.classification_json,
        isProcessing: isProcessing.value,
      }),
    }],
  }),
  deps: [inputText, rawMessages, currentSketch, isProcessing],
});

// Adapt useSketchChat messages (ChatMessage) to ConversationMessage format
const chatMessages = computed<ConversationMessage[]>(() =>
  rawMessages.value.map((m) => ({
    role: m.role as 'user' | 'assistant',
    content: m.content,
    timestamp: m.timestamp,
  })),
);

// Parse classification_json safely
const parsedClassification = computed(() => {
  if (!currentSketch.value?.classification_json) return null;
  try {
    return JSON.parse(currentSketch.value.classification_json);
  } catch {
    return null;
  }
});

// Parse routing_json safely
const parsedRouting = computed(() => {
  if (!currentSketch.value?.routing_json) return null;
  try {
    return JSON.parse(currentSketch.value.routing_json);
  } catch {
    return null;
  }
});

const canRoute = computed(() => {
  if (!currentSketch.value) return false;
  return currentSketch.value.status === 'classified';
});

const showResults = computed(() => {
  if (!currentSketch.value) return false;
  return ['routed', 'in_progress', 'completed'].includes(currentSketch.value.status);
});

const SKETCH_ICON_PATHS = [
  'M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z',
];

function handleSubmit() {
  const text = inputText.value.trim();
  if (!text || isProcessing.value) return;
  inputText.value = '';
  submitSketch(text);
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSubmit();
  }
}

function handleRouteClick() {
  if (currentSketch.value) {
    routeSketch(currentSketch.value.id);
  }
}

function handleSelectSketch(sketch: Sketch) {
  selectSketch(sketch);
}

function handleClear() {
  clearChat();
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString();
  } catch {
    return '';
  }
}

function getStatusClass(status: string): string {
  return `status-${status.replace('_', '-')}`;
}

// Reload sketches when project filter changes
watch(selectedProjectId, () => {
  loadSketches();
});

// Show error as toast
watch(error, (val) => {
  if (val) {
    showToast(val, 'error');
  }
});

onMounted(() => {
  loadProjects();
  loadSketches();
});
</script>

<template>
  <div class="sketch-chat-page">
    <!-- Left: Chat via AiChatPanel -->
    <div class="left-panel">
      <AiChatPanel
        :messages="chatMessages"
        :isProcessing="isProcessing"
        streamingContent=""
        :inputMessage="inputText"
        :conversationId="currentSketch?.id ?? null"
        :canFinalize="false"
        :isFinalizing="false"
        :assistantIconPaths="SKETCH_ICON_PATHS"
        inputPlaceholder="Describe your idea or feature request..."
        entityLabel="sketch"
        bannerTitle=""
        bannerButtonLabel=""
        :showBackendSelector="false"
        @update:inputMessage="inputText = $event"
        @send="handleSubmit"
        @keydown="handleKeyDown"
      >
        <template #header-extra>
          <div class="sketch-header-bar">
            <div class="header-left">
              <h2 class="page-title">Sketch Ideation</h2>
              <button v-if="currentSketch" class="btn-clear" @click="handleClear">
                New Sketch
              </button>
            </div>
            <div class="header-right">
              <select v-model="selectedProjectId" class="project-selector">
                <option :value="null">All Projects</option>
                <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
          </div>

          <!-- Classifying indicator -->
          <div v-if="isProcessing && !currentSketch?.classification_json" class="classifying-banner">
            <div class="loading-spinner small"></div>
            <span>Classifying your sketch...</span>
          </div>
        </template>

        <template #welcome>
          <div class="sketch-welcome">
            <div class="welcome-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
              </svg>
            </div>
            <h2>Sketch Ideation</h2>
            <p>Describe your idea or feature request to get started.</p>
            <p class="hint">Your sketch will be automatically classified and can be routed to a SuperAgent or Team.</p>
          </div>
        </template>
      </AiChatPanel>

      <!-- Recent sketches list below chat -->
      <div class="sketch-list">
        <div class="sketch-list-header">Recent Sketches</div>
        <div v-if="sketches.length === 0" class="sketch-list-empty">
          No sketches yet
        </div>
        <div
          v-for="sketch in sketches"
          :key="sketch.id"
          class="sketch-item"
          :class="{ 'sketch-item-active': currentSketch?.id === sketch.id }"
          @click="handleSelectSketch(sketch)"
        >
          <div class="sketch-item-title">{{ sketch.title }}</div>
          <div class="sketch-item-meta">
            <span class="sketch-status-badge" :class="getStatusClass(sketch.status)">{{ sketch.status }}</span>
            <span class="sketch-date">{{ formatDate(sketch.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Right: Info Panel -->
    <div class="info-panel" :class="{ 'info-panel-empty': !currentSketch }">
      <div v-if="!currentSketch" class="info-placeholder">
        <p>Select or create a sketch to see details</p>
      </div>
      <div v-else class="info-content">
        <div class="info-header">
          <h3 class="sketch-title">{{ currentSketch.title }}</h3>
        </div>

        <SketchStatusTracker :status="currentSketch.status" />
        <SketchClassification :classification="parsedClassification" />
        <SketchRouting :routing="parsedRouting" @navigateTo="(view: string, id?: string) => handleNavigateTo(view, id)" />

        <div v-if="canRoute" class="route-action">
          <button class="btn-route" :disabled="isProcessing" @click="handleRouteClick">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
            Route Sketch
          </button>
        </div>

        <div v-if="showResults" class="results-panel">
          <h4 class="results-title">Routing Results</h4>
          <div v-if="parsedRouting" class="results-content">
            <div v-if="parsedRouting.target_type && parsedRouting.target_type !== 'none'" class="result-item">
              <span class="result-label">Assigned To</span>
              <span class="result-value">
                {{ parsedRouting.target_type === 'super_agent' ? 'SuperAgent' : parsedRouting.target_type }}:
                {{ parsedRouting.target_id }}
              </span>
            </div>
            <div v-if="parsedRouting.reason" class="result-item">
              <span class="result-label">Reason</span>
              <span class="result-value">{{ parsedRouting.reason }}</span>
            </div>
            <div class="result-item">
              <span class="result-label">Status</span>
              <span :class="['result-status', getStatusClass(currentSketch!.status)]">{{ currentSketch!.status }}</span>
            </div>
          </div>
          <div v-else class="results-pending">
            <div class="loading-spinner small"></div>
            <span>Processing...</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sketch-chat-page {
  display: flex;
  gap: 0;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
}

/* Left panel with chat + sketch list */
.left-panel {
  flex: 6;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  border-right: 1px solid var(--border-default);
}

/* Header bar injected above chat */
.sketch-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-clear {
  padding: 4px 12px;
  font-size: 12px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-clear:hover {
  color: var(--text-primary);
  border-color: var(--accent-primary);
}

.project-selector {
  padding: 6px 10px;
  font-size: 13px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  outline: none;
  cursor: pointer;
  min-width: 160px;
}

.project-selector:focus {
  border-color: var(--accent-primary);
}

/* Classifying indicator */
.classifying-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 20px;
  background: rgba(0, 212, 255, 0.08);
  border-bottom: 1px solid rgba(0, 212, 255, 0.2);
  color: var(--accent-cyan, #00d4ff);
  font-size: 13px;
  flex-shrink: 0;
}

.loading-spinner.small {
  width: 16px;
  height: 16px;
  border: 2px solid var(--bg-tertiary);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Welcome screen */
.sketch-welcome {
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

.sketch-welcome h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.sketch-welcome p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.hint {
  margin-top: 4px !important;
  font-size: 12px !important;
  opacity: 0.7;
}

/* Sketch list below chat */
.sketch-list {
  border-top: 1px solid var(--border-default);
  max-height: 200px;
  overflow-y: auto;
  flex-shrink: 0;
}

.sketch-list-header {
  padding: 8px 20px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
}

.sketch-list-empty {
  padding: 16px 20px;
  font-size: 13px;
  color: var(--text-secondary);
  font-style: italic;
}

.sketch-item {
  padding: 8px 20px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-default);
  transition: background 0.15s;
}

.sketch-item:hover {
  background: var(--bg-secondary);
}

.sketch-item-active {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent-primary);
}

.sketch-item-title {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sketch-item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.sketch-status-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.status-draft { color: var(--text-secondary); }
.status-classified { color: var(--accent-violet); border-color: var(--accent-violet); }
.status-routed { color: var(--accent-cyan); border-color: var(--accent-cyan); }
.status-in-progress { color: var(--accent-amber); border-color: var(--accent-amber); }
.status-completed { color: var(--accent-emerald); border-color: var(--accent-emerald); }

.sketch-date {
  font-size: 11px;
  color: var(--text-secondary);
}

/* Info Panel - Right */
.info-panel {
  flex: 4;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-primary);
}

.info-panel-empty {
  align-items: center;
  justify-content: center;
}

.info-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-size: 14px;
}

.info-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
}

.info-header {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-default);
}

.sketch-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.route-action {
  padding: 12px 0;
}

.btn-route {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  background: var(--accent-primary);
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
  width: 100%;
  justify-content: center;
}

.btn-route:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-route:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.results-panel {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}
.results-title {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.results-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.result-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.result-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}
.result-status {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
}
.results-pending {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
