<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { workflowApi, workflowConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';
import WorkflowCanvas from '../components/workflow/WorkflowCanvas.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const { t } = useI18n();
const router = useRouter();

const showToast = useToast();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/** Workflow config the assistant emits between ---WORKFLOW_CONFIG--- markers. */
interface ParsedWorkflowConfig {
  name?: string;
  description?: string;
  graph?: { nodes?: unknown[]; edges?: unknown[]; settings?: Record<string, unknown> };
}

// Real workflow-design chat: a live LLM resolved from the caller's configured
// account via /api/workflows/conversations, exactly like the Command/Rule/Hook
// design pages. Replaces the old SuperAgent-gated keyword stub.
const conversation = useConversation<ParsedWorkflowConfig>(
  workflowConversationApi,
  createConfigParser<ParsedWorkflowConfig>('---WORKFLOW_CONFIG---'),
);

const previewWorkflowId = ref<string | null>(null);
const generatedWorkflowId = ref<string | null>(null);

useWebMcpTool({
  name: 'agented_workflow_playground_get_state',
  description: 'Returns the current state of the Workflow Playground page',
  page: 'WorkflowPlaygroundPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'WorkflowPlaygroundPage',
        messageCount: conversation.messages.value.length,
        isProcessing: conversation.isProcessing.value,
        previewWorkflowId: previewWorkflowId.value,
        chatStarted: conversation.chatStarted.value,
      }),
    }],
  }),
  deps: [conversation.messages, conversation.isProcessing, previewWorkflowId, conversation.chatStarted],
});

// Chat panel configuration
const assistantIconPaths = [
  'M12 2L2 7l10 5 10-5-10-5z',
  'M2 17l10 5 10-5',
  'M2 12l10 5 10-5',
];

// ---------------------------------------------------------------------------
// Conversation lifecycle (start / resume) + graph preview
// ---------------------------------------------------------------------------

function ensureChatStarted() {
  if (conversation.chatStarted.value) return;
  if (conversation.activeConversations.value.length > 0) {
    conversation.resumeConversation(conversation.activeConversations.value[0].id);
  } else {
    conversation.startConversation();
  }
}

onMounted(async () => {
  await conversation.checkActiveConversations();
  ensureChatStarted();
});

// When the assistant emits a workflow graph, materialize a live preview.
watch(
  () => conversation.detectedConfig.value,
  (cfg) => {
    if (cfg?.graph) tryCreateWorkflowFromJson(JSON.stringify(cfg.graph));
  },
);

// Template quick-starts: send a starter prompt to the REAL assistant so it
// designs (and can then refine) the workflow conversationally.
function insertTemplate(kind: 'deploy' | 'review' | 'data' | 'monitor') {
  conversation.inputMessage.value = t(`workflowPlayground.templatePrompts.${kind}`);
  conversation.sendMessage();
}

// ---------------------------------------------------------------------------
// Workflow Creation from JSON
// ---------------------------------------------------------------------------

async function tryCreateWorkflowFromJson(jsonStr: string) {
  try {
    const graph = JSON.parse(jsonStr);

    // Validate basic structure
    if (!graph.nodes || !Array.isArray(graph.nodes)) return;
    if (!graph.edges || !Array.isArray(graph.edges)) return;

    // Create workflow
    const result = await workflowApi.create({
      name: t('workflowPlayground.generated.name', { time: new Date().toLocaleTimeString() }),
      description: t('workflowPlayground.generated.description'),
      trigger_type: 'manual',
    });

    // Create a version with the graph
    await workflowApi.createVersion(result.workflow_id, {
      graph_json: JSON.stringify(graph),
    });

    generatedWorkflowId.value = result.workflow_id;
    previewWorkflowId.value = result.workflow_id;

    await nextTick();
    showToast(t('workflowPlayground.toast.generated'), 'success');
  } catch {
    showToast(t('workflowPlayground.toast.generateFailed'), 'error');
  }
}

// ---------------------------------------------------------------------------
// Navigation to Builder
// ---------------------------------------------------------------------------

function openInBuilder() {
  if (!generatedWorkflowId.value) return;
  router.push({ name: 'workflow-builder', params: { workflowId: generatedWorkflowId.value } });
}
</script>

<template>
  <div class="workflow-playground-page">
    <!-- Header -->
    <div class="playground-header">
      <div class="header-title">
        <h1>{{ t('workflowPlayground.title') }}</h1>
        <p>{{ t('workflowPlayground.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button
          v-if="generatedWorkflowId"
          class="btn btn-primary"
          @click="openInBuilder"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          {{ t('workflowPlayground.openInBuilder') }}
        </button>
      </div>
    </div>

    <!-- Main content: two-column layout -->
    <div class="playground-content">
      <!-- Left panel: Chat UI -->
      <div class="left-panel">
        <AiChatPanel
          :messages="conversation.messages.value"
          :isProcessing="conversation.isProcessing.value"
          :streamingContent="conversation.streamingContent.value"
          :inputMessage="conversation.inputMessage.value"
          :conversationId="conversation.conversationId.value"
          :canFinalize="conversation.canFinalize.value"
          :isFinalizing="conversation.isFinalizing.value"
          :initStreamingParser="conversation.initStreamingParser"
          :assistantIconPaths="assistantIconPaths"
          :inputPlaceholder="t('workflowPlayground.inputPlaceholder')"
          :entityLabel="t('workflowPlayground.entityLabel')"
          bannerTitle=""
          bannerButtonLabel=""
          :showBackendSelector="true"
          :selected-backend="conversation.selectedBackend.value"
          :selected-account-id="conversation.selectedAccountId.value"
          :selected-model="conversation.selectedModel.value"
          :useCliRunner="conversation.useCliRunner.value"
          @update:inputMessage="conversation.inputMessage.value = $event"
          @update:selected-backend="conversation.setBackend($event)"
          @update:selected-account-id="conversation.setAccountId($event)"
          @update:selected-model="conversation.setModel($event)"
          @update:useCliRunner="conversation.setUseCliRunner($event)"
          @send="conversation.sendMessage"
          @keydown="conversation.handleKeyDown"
        >
          <template #welcome>
            <div class="wf-welcome">
              <div class="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="8" y="2" width="8" height="5" rx="1"/>
                  <rect x="8" y="10" width="8" height="5" rx="1"/>
                  <rect x="8" y="18" width="8" height="5" rx="1"/>
                  <line x1="12" y1="7" x2="12" y2="10"/>
                  <line x1="12" y1="15" x2="12" y2="18"/>
                </svg>
              </div>
              <h2>{{ t('workflowPlayground.welcome.title') }}</h2>
              <p>{{ t('workflowPlayground.welcome.intro') }}</p>
              <div class="template-buttons">
                <button type="button" class="template-btn" @click="insertTemplate('deploy')">
                  {{ t('workflowPlayground.templates.deploy') }}
                </button>
                <button type="button" class="template-btn" @click="insertTemplate('review')">
                  {{ t('workflowPlayground.templates.review') }}
                </button>
                <button type="button" class="template-btn" @click="insertTemplate('data')">
                  {{ t('workflowPlayground.templates.data') }}
                </button>
                <button type="button" class="template-btn" @click="insertTemplate('monitor')">
                  {{ t('workflowPlayground.templates.monitor') }}
                </button>
              </div>
              <p class="welcome-hint">{{ t('workflowPlayground.welcome.hint') }}</p>
            </div>
          </template>
        </AiChatPanel>
      </div>

      <!-- Right panel: Canvas preview -->
      <div class="right-panel">
        <div v-if="!previewWorkflowId" class="preview-placeholder">
          <div class="placeholder-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <rect x="8" y="6" width="8" height="4" rx="1"/>
              <rect x="8" y="14" width="8" height="4" rx="1"/>
              <line x1="12" y1="10" x2="12" y2="14"/>
            </svg>
          </div>
          <h3>{{ t('workflowPlayground.preview.title') }}</h3>
          <p>{{ t('workflowPlayground.preview.description') }}</p>
        </div>
        <WorkflowCanvas
          v-else
          :workflow-id="previewWorkflowId"
          :read-only="true"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-playground-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
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

.header-title {
  flex: 1;
  min-width: 0;
}

.header-title h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-title p {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.demo-badge {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(255, 187, 0, 0.1);
  border: 1px solid rgba(255, 187, 0, 0.3);
  border-radius: 4px;
  color: #ffbb00;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Main content */
.playground-content {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.left-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-default);
  min-height: 0;
  min-width: 0;
}

/* Welcome screen */
.wf-welcome {
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
  color: var(--accent-cyan);
}

.wf-welcome h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.wf-welcome p {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.suggestions {
  list-style: none;
  padding: 0;
  margin: 0;
  text-align: left;
}

.suggestions li {
  padding: 8px 12px;
  margin: 4px 0;
  background: var(--bg-tertiary);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: default;
}

.demo-reason {
  margin-left: 4px;
  opacity: 0.85;
  font-weight: 400;
}

.template-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin: 4px 0 12px 0;
}

.template-btn {
  padding: 8px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.template-btn:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-secondary);
}

.welcome-hint {
  font-size: 12px;
  color: var(--text-tertiary, var(--text-secondary));
  max-width: 420px;
}

/* Preview placeholder */
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
}

.placeholder-icon {
  width: 80px;
  height: 80px;
  background: var(--bg-tertiary);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.placeholder-icon svg {
  width: 40px;
  height: 40px;
  color: var(--text-tertiary);
}

.preview-placeholder h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.preview-placeholder p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  max-width: 300px;
}
</style>
