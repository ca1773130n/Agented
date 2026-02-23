<script setup lang="ts">
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { agentConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

// ---------------------------------------------------------------------------
// Config interface matching the backend's ---AGENT_CONFIG--- JSON shape
// ---------------------------------------------------------------------------
interface AgentConfig {
  name: string;
  description: string;
  role: string;
  goals: string[];
  skills: string[];
  context: string;
  system_prompt?: string;
}

const conversation = useConversation<AgentConfig>(
  agentConversationApi,
  createConfigParser<AgentConfig>('---AGENT_CONFIG---'),
);

useWebMcpTool({
  name: 'agented_agent_create_get_state',
  description: 'Returns the current state of the AgentCreateWizard',
  page: 'AgentCreateWizard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'AgentCreateWizard',
        conversationId: conversation.conversationId.value,
        messagesCount: conversation.messages.value.length,
        isProcessing: conversation.isProcessing.value,
        canFinalize: conversation.canFinalize.value,
        isFinalizing: conversation.isFinalizing.value,
        detectedConfigName: conversation.detectedConfig.value?.name ?? null,
        selectedBackend: conversation.selectedBackend.value,
      }),
    }],
  }),
  deps: [conversation.conversationId, conversation.messages, conversation.isProcessing, conversation.canFinalize, conversation.isFinalizing, conversation.detectedConfig],
});

const AGENT_ICON_PATHS = [
  'M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2',
  'M8.5 7a4 4 0 108 0 4 4 0 00-8 0',
  'M20 8v6M23 11h-6',
];

async function finalizeAgent() {
  const result = await conversation.finalize();
  if (result) {
    showToast(`Agent "${result.agent.name}" created successfully!`, 'success');
    router.push({ name: 'agent-design', params: { agentId: result.agent_id } });
  }
}

async function abandonConversation() {
  await conversation.abandonConversation();
  router.push({ name: 'agents' });
}

onMounted(() => {
  conversation.startConversation();
});
</script>

<template>
  <div class="wizard-page">
    <div class="wizard-header">
      <AppBreadcrumb :items="[
        { label: 'Agents', action: () => abandonConversation() },
        { label: 'Create Agent' },
      ]" />
      <div class="header-title">
        <h1>Design Agent</h1>
        <p>Chat with Claude to design your AI agent</p>
      </div>
      <button
        v-if="conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizeAgent"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Agent' }}
      </button>
    </div>

    <AiChatPanel
      :messages="conversation.messages.value"
      :is-processing="conversation.isProcessing.value"
      :streaming-content="conversation.streamingContent.value"
      :input-message="conversation.inputMessage.value"
      :conversation-id="conversation.conversationId.value"
      :can-finalize="conversation.canFinalize.value"
      :is-finalizing="conversation.isFinalizing.value"
      :init-streaming-parser="conversation.initStreamingParser"
      show-backend-selector
      :use-smart-scroll="true"
      :selected-backend="conversation.selectedBackend.value"
      :selected-account-id="conversation.selectedAccountId.value"
      :selected-model="conversation.selectedModel.value"
      :assistant-icon-paths="AGENT_ICON_PATHS"
      input-placeholder="Describe your agent or answer Claude's questions..."
      entity-label="agent"
      banner-title="Agent Ready to Create!"
      banner-button-label="Create Agent Now"
      :detected-entity-name="conversation.detectedConfig.value?.name"
      @update:input-message="conversation.inputMessage.value = $event"
      @update:selected-backend="conversation.setBackend($event)"
      @update:selected-account-id="conversation.setAccountId($event)"
      @update:selected-model="conversation.setModel($event)"
      @send="conversation.sendMessage"
      @keydown="conversation.handleKeyDown"
      @finalize="finalizeAgent"
    />
  </div>
</template>

<style scoped>
.wizard-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.wizard-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-title {
  flex: 1;
}

.header-title h1 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.header-title p {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.btn-finalize {
  padding: 10px 20px;
}

.btn-primary svg {
  width: 16px;
  height: 16px;
}
</style>
