<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter, useRoute } from 'vue-router';
import { commandApi, commandConversationApi, ApiError } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';
import ConfigPreviewSidebar from '../components/plugins/ConfigPreviewSidebar.vue';
import DesignModeToggle from '../components/base/DesignModeToggle.vue';
import PageLayout from '../components/base/PageLayout.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useUnsavedGuard } from '../composables/useUnsavedGuard';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const { t } = useI18n();
const router = useRouter();
const route = useRoute();

const commandId = computed(() => route.params.commandId ? Number(route.params.commandId) : null);

const showToast = useToast();
const isEditMode = computed(() => !!commandId.value);
const isLoadingEdit = ref(false);

// --------------- Mode toggle ---------------
// v0.7.90 — chat is the default design mode. Form stays as a
// secondary path for operators who already know the entity shape
// and want to fill it directly, but the AI-driven flow is the
// recommended way to bootstrap a new command from a description.
const designMode = ref<'form' | 'chat'>('chat');

// --------------- Form mode state ---------------
const formData = ref({
  name: '',
  description: '',
  content: '',
  arguments: '',
  enabled: true,
});
const isCreating = ref(false);
const showExportModal = ref(false);
const exportModalRef = ref<HTMLElement | null>(null);
const createdCommandId = ref<number | null>(null);

// Unsaved changes guard
const originalFormData = ref(JSON.stringify({ name: '', description: '', content: '', arguments: '', enabled: true }));
const isDirty = computed(() => JSON.stringify(formData.value) !== originalFormData.value);
useUnsavedGuard(isDirty);

useFocusTrap(exportModalRef, showExportModal);

// --------------- Chat mode state (via shared composable) ---------------
interface CommandArgument {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
}

interface ParsedCommandConfig {
  name: string;
  description: string;
  content: string;
  arguments: CommandArgument[];
  enabled: boolean;
}

const conversation = useConversation<ParsedCommandConfig>(commandConversationApi, createConfigParser<ParsedCommandConfig>('---COMMAND_CONFIG---'));

useWebMcpTool({
  name: 'agented_command_design_get_state',
  description: 'Returns the current state of the CommandDesignPage',
  page: 'CommandDesignPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'CommandDesignPage',
        isEditMode: isEditMode.value,
        commandId: commandId.value ?? null,
        designMode: designMode.value,
        formName: formData.value.name,
        isDirty: isDirty.value,
        isCreating: isCreating.value,
        isLoadingEdit: isLoadingEdit.value,
        chatMessagesCount: conversation.messages.value.length,
        canFinalize: conversation.canFinalize.value,
      }),
    }],
  }),
  deps: [isEditMode, designMode, formData, isDirty, isCreating, isLoadingEdit, conversation.messages, conversation.canFinalize],
});

const COMMAND_ICON_PATHS = [
  'M4 17l6-6-6-6',
  'M12 19h8',
];

// --------------- Mode switching ---------------
// v0.7.90 — chat is the default mode; shared start-or-resume
// helper so onMounted and the form→chat transition use the same
// flow.
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
  if (isEditMode.value) {
    loadExistingCommand();
  }
  if (designMode.value === 'chat') {
    ensureChatStarted();
  }
});

watch(designMode, (newMode) => {
  if (newMode === 'chat') {
    ensureChatStarted();
  }
});

// --------------- Form mode functions ---------------
async function loadExistingCommand() {
  if (!commandId.value) return;
  isLoadingEdit.value = true;
  try {
    const command = await commandApi.get(commandId.value);
    formData.value.name = command.name;
    formData.value.description = command.description || '';
    formData.value.content = command.content || '';
    formData.value.arguments = command.arguments || '';
    formData.value.enabled = !!command.enabled;
    originalFormData.value = JSON.stringify(formData.value);
  } catch (e) {
    showToast(t('commandDesign.toast.loadFailed'), 'error');
  } finally {
    isLoadingEdit.value = false;
  }
}

async function createCommand() {
  if (!formData.value.name.trim()) {
    showToast(t('commandDesign.toast.nameRequired'), 'error');
    return;
  }

  isCreating.value = true;
  try {
    if (isEditMode.value && commandId.value) {
      await commandApi.update(commandId.value, {
        name: formData.value.name,
        description: formData.value.description || undefined,
        content: formData.value.content || undefined,
        arguments: formData.value.arguments || undefined,
        enabled: formData.value.enabled,
      });
      originalFormData.value = JSON.stringify(formData.value);
      showToast(t('commandDesign.toast.updated', { name: formData.value.name }), 'success');
      router.push({ name: 'commands' });
    } else {
      const result = await commandApi.create({
        name: formData.value.name,
        description: formData.value.description || undefined,
        content: formData.value.content || undefined,
        arguments: formData.value.arguments || undefined,
        enabled: formData.value.enabled,
      });
      createdCommandId.value = result.command.id;
      showToast(t('commandDesign.toast.created', { name: formData.value.name }), 'success');
      showExportModal.value = true;
    }
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(isEditMode.value ? t('commandDesign.toast.updateFailed') : t('commandDesign.toast.createFailed'), 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function exportToLibrary() {
  const exportData = {
    name: formData.value.name,
    description: formData.value.description,
    content: formData.value.content,
    arguments: formData.value.arguments,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `command-${formData.value.name.replace(/\s+/g, '-').toLowerCase()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(t('commandDesign.toast.exported'), 'success');
}

function createAnother() {
  formData.value = {
    name: '',
    description: '',
    content: '',
    arguments: '',
    enabled: true,
  };
  originalFormData.value = JSON.stringify(formData.value);
  createdCommandId.value = null;
  showExportModal.value = false;
}

function handleFormCreated() {
  router.push({ name: 'commands' });
}

async function finalizeCommand() {
  const result = await conversation.finalize();
  if (result) {
    showToast(t('commandDesign.toast.createdSuccess', { name: (result.command as { name: string }).name }), 'success');
    router.push({ name: 'commands' });
  }
}

// v0.7.82 — tooltip mirrors the visible hint when disabled.
const finalizeTooltip = computed(() =>
  conversation.canFinalize.value
    ? t('commandDesign.tooltip.canFinalize')
    : t('commandDesign.tooltip.cannotFinalize'),
);

</script>

<template>
  <PageLayout fullHeight maxWidth="100%">
  <div class="design-page">
    <div class="design-header">
      <DesignModeToggle v-model="designMode" />
      <div class="header-title">
        <h1>{{ isEditMode ? t('commandDesign.editCommand') : t('commandDesign.designCommand') }}</h1>
        <p v-if="designMode === 'form'">{{ isEditMode ? t('commandDesign.editExisting') : t('commandDesign.createWithForm') }}</p>
        <p v-else>{{ t('commandDesign.chatWithClaude') }}</p>
      </div>
      <!-- v0.7.82 — always-visible disabled Create button in chat
           mode so a new operator can see the target action.
           Form mode has its own submit button below; this button
           is intentionally chat-mode only. -->
      <div v-if="designMode === 'chat'" class="finalize-control">
        <button
          class="btn btn-primary btn-finalize"
          :disabled="!conversation.canFinalize.value || conversation.isFinalizing.value"
          :title="finalizeTooltip"
          :aria-describedby="conversation.canFinalize.value ? undefined : 'finalize-hint'"
          @click="finalizeCommand"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          {{ conversation.isFinalizing.value ? t('commandDesign.creating') : t('commandDesign.createCommand') }}
        </button>
        <p
          v-if="!conversation.canFinalize.value"
          id="finalize-hint"
          class="finalize-hint"
        >
          {{ t('commandDesign.finalizeHint') }}
        </p>
      </div>
    </div>

    <!-- ==================== FORM MODE ==================== -->
    <div v-if="designMode === 'form'" class="design-content">
      <div class="design-form">
        <div class="form-section">
          <h3>{{ t('commandDesign.configuration') }}</h3>

          <div class="form-group">
            <label for="command-name">{{ t('commandDesign.field.name') }} *</label>
            <input
              id="command-name"
              v-model="formData.name"
              type="text"
              placeholder="my-command"
            />
            <p class="form-hint">{{ t('commandDesign.invokedAs', { name: formData.name || 'my-command' }) }}</p>
          </div>

          <div class="form-group">
            <label for="command-description">{{ t('commandDesign.field.description') }}</label>
            <input
              id="command-description"
              v-model="formData.description"
              type="text"
              :placeholder="t('commandDesign.field.descriptionPlaceholder')"
            />
          </div>

          <div class="form-group">
            <label for="command-arguments">{{ t('commandDesign.field.arguments') }}</label>
            <textarea
              id="command-arguments"
              v-model="formData.arguments"
              rows="4"
              placeholder='[
  { "name": "target", "type": "string", "required": true },
  { "name": "options", "type": "string", "required": false }
]'
            ></textarea>
            <p class="form-hint">{{ t('commandDesign.field.argumentsHint') }}</p>
          </div>

          <div class="form-group">
            <label for="command-content">{{ t('commandDesign.field.content') }}</label>
            <textarea
              id="command-content"
              v-model="formData.content"
              rows="12"
              placeholder="# Command Instructions

Describe what this command should do...

## Usage
/my-command <target> [options]

## Behavior
1. First, analyze the target
2. Then, perform the action
3. Finally, report the results
"
            ></textarea>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input type="checkbox" v-model="formData.enabled" />
              {{ t('commandDesign.enabled') }}
            </label>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn" @click="router.push({ name: 'commands' })">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" @click="createCommand" :disabled="isCreating">
            {{ isCreating ? (isEditMode ? t('commandDesign.updating') : t('commandDesign.creating')) : (isEditMode ? t('commandDesign.updateCommand') : t('commandDesign.createCommand')) }}
          </button>
        </div>
      </div>

      <div class="design-preview">
        <h3>{{ t('commandDesign.preview') }}</h3>
        <div class="preview-card">
          <div class="preview-header-form">
            <span class="preview-name">/{{ formData.name || 'command-name' }}</span>
          </div>
          <p class="preview-description">{{ formData.description || t('commandDesign.noDescription') }}</p>
          <div class="preview-content-form" v-if="formData.content">
            <pre>{{ formData.content.slice(0, 200) }}{{ formData.content.length > 200 ? '...' : '' }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== CHAT MODE ==================== -->
    <div v-else class="design-body">
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
        :use-cli-runner="conversation.useCliRunner.value"
        :assistant-icon-paths="COMMAND_ICON_PATHS"
        :input-placeholder="t('commandDesign.chatInputPlaceholder')"
        entity-label="command"
        :banner-title="t('commandDesign.bannerTitle')"
        :banner-button-label="t('commandDesign.bannerButton')"
        :detected-entity-name="conversation.detectedConfig.value?.name"
        @update:input-message="conversation.inputMessage.value = $event"
        @update:selected-backend="conversation.setBackend($event)"
        @update:selected-account-id="conversation.setAccountId($event)"
        @update:selected-model="conversation.setModel($event)"
        @update:use-cli-runner="conversation.setUseCliRunner($event)"
        @send="conversation.sendMessage"
        @keydown="conversation.handleKeyDown"
        @finalize="finalizeCommand"
      />

      <ConfigPreviewSidebar
        :has-config="!!conversation.detectedConfig.value"
        :empty-icon-paths="COMMAND_ICON_PATHS"
        :empty-text="t('commandDesign.sidebarEmpty')"
      >
        <template v-if="conversation.detectedConfig.value">
          <div class="config-field">
            <div class="config-label">{{ t('commandDesign.field.name') }}</div>
            <div class="config-value config-name">/{{ conversation.detectedConfig.value.name }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.description">
            <div class="config-label">{{ t('commandDesign.field.description') }}</div>
            <div class="config-value config-description">{{ conversation.detectedConfig.value.description }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.content">
            <div class="config-label">{{ t('commandDesign.field.content') }}</div>
            <pre class="config-code">{{ conversation.detectedConfig.value.content.slice(0, 300) }}{{ conversation.detectedConfig.value.content.length > 300 ? '...' : '' }}</pre>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.arguments && conversation.detectedConfig.value.arguments.length > 0">
            <div class="config-label">{{ t('commandDesign.argumentsLabel') }}</div>
            <div class="arguments-list">
              <div v-for="(arg, i) in conversation.detectedConfig.value.arguments" :key="i" class="argument-item">
                <span class="arg-name">{{ arg.name }}</span>
                <span class="arg-type">{{ arg.type }}</span>
                <span v-if="arg.required" class="arg-required">{{ t('commandDesign.required') }}</span>
                <span v-if="arg.description" class="arg-desc">{{ arg.description }}</span>
              </div>
            </div>
          </div>
          <div class="config-field">
            <div class="config-label">{{ t('commandDesign.enabled') }}</div>
            <div class="config-value">
              <span :class="['enabled-badge', conversation.detectedConfig.value.enabled ? 'yes' : 'no']">
                {{ conversation.detectedConfig.value.enabled ? t('common.yes') : t('common.no') }}
              </span>
            </div>
          </div>
        </template>
      </ConfigPreviewSidebar>
    </div>

    <!-- Export Modal (form mode) -->
    <Teleport to="body">
      <div v-if="showExportModal" ref="exportModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-command-created" tabindex="-1" @click.self="showExportModal = false" @keydown.escape="showExportModal = false">
        <div class="modal export-modal">
          <div class="modal-icon success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
          </div>
          <h2 id="modal-title-command-created">{{ t('commandDesign.modal.title') }}</h2>
          <p>{{ t('commandDesign.modal.bodyPrefix') }} <strong>/{{ formData.name }}</strong> {{ t('commandDesign.modal.bodySuffix') }}</p>
          <div class="modal-actions">
            <button class="btn" @click="exportToLibrary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              {{ t('commandDesign.modal.exportToLibrary') }}
            </button>
            <button class="btn btn-secondary" @click="createAnother">{{ t('commandDesign.modal.createAnother') }}</button>
            <button class="btn btn-primary" @click="handleFormCreated">{{ t('common.done') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
  </PageLayout>
</template>

<style scoped>
/* Design-page scoped overrides (violet-themed buttons, centered modal) */
.btn-primary { background: var(--accent-violet); color: #fff; }
.btn-primary:hover:not(:disabled) { background: #9966ff; }
.btn-primary svg { width: 16px; height: 16px; }
.btn-primary:disabled {
  background: var(--bg-tertiary, #2a2a30);
  color: var(--text-tertiary, #8a8a92);
  cursor: not-allowed;
  opacity: 0.85;
}

/* v0.7.82 — always-visible disabled Create button with hint */
.finalize-control {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  max-width: 320px;
}
.finalize-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
  text-align: right;
}
.modal { padding: 32px; text-align: center; }

/* Command-specific: form preview */
.preview-header-form { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.preview-name { font-weight: 600; font-family: var(--font-mono); color: var(--accent-cyan); }
.preview-content-form { background: var(--bg-tertiary); border-radius: 6px; padding: 12px; }
.preview-content-form pre { margin: 0; font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }

/* Command-specific: chat sidebar */
.config-name { font-family: var(--font-mono); font-weight: 600; color: var(--accent-cyan); }

/* Command-specific: arguments list */
.arguments-list { display: flex; flex-direction: column; gap: 8px; }
.argument-item { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 10px; background: var(--bg-tertiary); border-radius: 6px; font-size: 13px; }
.arg-name { font-family: var(--font-mono); font-weight: 600; color: var(--text-primary); }
.arg-type { font-size: 11px; padding: 2px 6px; border-radius: 3px; background: var(--accent-cyan-dim); color: var(--accent-cyan); font-weight: 500; }
.arg-required { font-size: 10px; padding: 1px 5px; border-radius: 3px; background: rgba(255, 51, 102, 0.15); color: #ff3366; font-weight: 600; text-transform: uppercase; }
.arg-desc { width: 100%; color: var(--text-tertiary); font-size: 12px; margin-top: 2px; }
</style>
