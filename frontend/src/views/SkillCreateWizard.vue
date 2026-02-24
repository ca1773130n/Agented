<script setup lang="ts">
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { skillConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

// ---------------------------------------------------------------------------
// Config interface matching the backend's ---SKILL_CONFIG--- JSON shape
// ---------------------------------------------------------------------------
interface SkillConfig {
  skill_name: string;
  description: string;
  triggers: string[];
  instructions: string;
  examples: string[];
}

const conversation = useConversation<SkillConfig>(
  skillConversationApi,
  createConfigParser<SkillConfig>('---SKILL_CONFIG---'),
);

useWebMcpTool({
  name: 'agented_skill_create_get_state',
  description: 'Returns the current state of the SkillCreateWizard',
  page: 'SkillCreateWizard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SkillCreateWizard',
        conversationId: conversation.conversationId.value,
        messagesCount: conversation.messages.value.length,
        isProcessing: conversation.isProcessing.value,
        canFinalize: conversation.canFinalize.value,
        isFinalizing: conversation.isFinalizing.value,
        detectedConfigName: conversation.detectedConfig.value?.skill_name ?? null,
        selectedBackend: conversation.selectedBackend.value,
      }),
    }],
  }),
  deps: [conversation.conversationId, conversation.messages, conversation.isProcessing, conversation.canFinalize, conversation.isFinalizing, conversation.detectedConfig],
});

const SKILL_ICON_PATHS = [
  'M12 2L2 7l10 5 10-5-10-5z',
  'M2 17l10 5 10-5',
  'M2 12l10 5 10-5',
];

async function finalizeSkill() {
  const result = await conversation.finalize();
  if (result) {
    showToast(`Skill "${(result.skill as { skill_name: string }).skill_name}" created successfully!`, 'success');
    router.push({ name: 'skill-detail', params: { skillId: result.skill_id as string } });
  }
}

async function abandonConversation() {
  await conversation.abandonConversation();
  router.push({ name: 'my-skills' });
}

onMounted(() => {
  conversation.startConversation();
});
</script>

<template>
  <div class="wizard-page">
    <div class="wizard-header">
      <AppBreadcrumb :items="[
        { label: 'Skills', action: () => abandonConversation() },
        { label: 'Create Skill' },
      ]" />
      <div class="header-title">
        <h1>Design a Skill</h1>
        <p>Chat with Claude to design your custom skill</p>
      </div>
      <button
        v-if="conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizeSkill"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Skill' }}
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
      :assistant-icon-paths="SKILL_ICON_PATHS"
      input-placeholder="Describe your skill or answer Claude's questions..."
      entity-label="skill"
      banner-title="Skill Ready to Create!"
      banner-button-label="Create Skill Now"
      :detected-entity-name="conversation.detectedConfig.value?.skill_name"
      @update:input-message="conversation.inputMessage.value = $event"
      @update:selected-backend="conversation.setBackend($event)"
      @update:selected-account-id="conversation.setAccountId($event)"
      @update:selected-model="conversation.setModel($event)"
      @send="conversation.sendMessage"
      @keydown="conversation.handleKeyDown"
      @finalize="finalizeSkill"
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
