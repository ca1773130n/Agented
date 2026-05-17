<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { skillConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import SkillCreatePreviewDrawer from '../components/skills/SkillCreatePreviewDrawer.vue';

const router = useRouter();
const showToast = useToast();

// v0.7.77 — config shape now matches the multi-file Anthropic
// Skills schema the backend emits via SKILL_CREATION_SYSTEM_PROMPT.
// Only ``skill_name`` is read by the wizard UI (for the detected-
// entity banner); the rest is opaque pass-through to finalize.
interface SkillConfig {
  skill_name: string;
  frontmatter?: {
    description?: string;
    license?: string;
    allowed_tools?: string[];
    tags?: string[];
  };
  body?: string;
  files?: Array<{ path: string; content: string }>;
  // Legacy fields kept on the type so a mid-flight conversation
  // emitting the v0.7.75 schema doesn't break parsing.
  description?: string;
  triggers?: string[];
  instructions?: string;
  examples?: string[];
}

const conversation = useConversation<SkillConfig>(
  skillConversationApi,
  createConfigParser<SkillConfig>('---SKILL_CONFIG---'),
);

// v0.7.77 — preview drawer state. Clicking the Create button no
// longer finalizes directly; it opens the drawer which renders the
// rendered tree via ``preview-finalize`` and lets the operator
// inspect each file before committing.
const showPreview = ref(false);

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

function openPreview() {
  // v0.7.77 — the wizard's Create button now opens the preview
  // drawer instead of finalizing directly. The drawer's own
  // Create button runs ``commitFinalize`` below.
  showPreview.value = true;
}

async function commitFinalize(expectedConfigHash: string) {
  // v0.7.77 (codex BLOCK 4) — the drawer passes the hash of the
  // config it rendered; backend 409s if claude has emitted a
  // newer one since. On mismatch, useConversation's toast
  // already surfaces the 409 message; the drawer stays open so
  // the operator can re-preview (the watcher on messageCount
  // will have already re-fetched).
  const result = await conversation.finalize(expectedConfigHash);
  if (result) {
    showPreview.value = false;
    // v0.7.78 — conv is finalized; clear localStorage so the
    // next visit starts fresh instead of trying to resume a
    // dead conv.
    rememberConvId(null);
    showToast(
      `Skill "${(result.skill as { skill_name: string }).skill_name}" created successfully!`,
      'success',
    );
    router.push({ name: 'skill-detail', params: { skillId: result.skill_id as string } });
  }
}

// v0.7.78 — auto-resume the wizard's chat after page refresh /
// backend restart. Resolution order:
//   1. localStorage ``agented_skill_conv_id`` (per-browser ref) —
//      try to resume that conv. 404 means the row was finalized
//      or stale-purged; fall through.
//   2. Server's most-recent active conv (``listActive``). Lets a
//      different browser / fresh-cache load still pick up an
//      in-flight conversation the operator started elsewhere.
//   3. Brand-new conversation via ``startConversation``.
// localStorage is updated whenever the conversation_id changes
// (start success or resume), and cleared on finalize / abandon
// so the next page load doesn't try to resume a finalized conv.
const SKILL_CONV_LOCALSTORAGE_KEY = 'agented_skill_conv_id';

function rememberConvId(id: string | null) {
  try {
    if (id) localStorage.setItem(SKILL_CONV_LOCALSTORAGE_KEY, id);
    else localStorage.removeItem(SKILL_CONV_LOCALSTORAGE_KEY);
  } catch {
    // localStorage may be disabled in private mode; tolerate it.
  }
}

async function tryResume(convId: string): Promise<boolean> {
  try {
    await conversation.resumeConversation(convId);
    return !!conversation.conversationId.value;
  } catch {
    return false;
  }
}

onMounted(async () => {
  // (1) localStorage
  let cached: string | null = null;
  try {
    cached = localStorage.getItem(SKILL_CONV_LOCALSTORAGE_KEY);
  } catch {
    cached = null;
  }
  if (cached && (await tryResume(cached))) {
    rememberConvId(cached);
    return;
  }
  // (2) server's most-recent active
  try {
    const res = await skillConversationApi.listActive();
    const newest = res.active_conversations?.[0];
    if (newest && (await tryResume(newest.id))) {
      rememberConvId(newest.id);
      return;
    }
  } catch {
    // Auth or network failure — fall through to fresh start.
  }
  // (3) fresh start
  rememberConvId(null);
  await conversation.startConversation();
  rememberConvId(conversation.conversationId.value);
});
</script>

<template>
  <div class="wizard-page">
    <div class="wizard-header">
      <div class="header-title">
        <h1>Design a Skill</h1>
        <p>Chat with Claude to design your custom skill</p>
      </div>
      <button
        v-if="conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="openPreview"
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
      @finalize="openPreview"
    />

    <!-- v0.7.77 — slide-over preview of the rendered skill
         package (SKILL.md + helpers/references). Operator
         inspects each file before clicking Create, which
         triggers the actual ``finalize`` POST. -->
    <SkillCreatePreviewDrawer
      :open="showPreview"
      :conversation-id="conversation.conversationId.value"
      :is-finalizing="conversation.isFinalizing.value"
      :message-count="conversation.messages.value.length"
      @close="showPreview = false"
      @create="commitFinalize"
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
