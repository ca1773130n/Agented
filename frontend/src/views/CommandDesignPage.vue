<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { commandApi, commandConversationApi, ApiError } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import ConfigPreviewSidebar from '../components/plugins/ConfigPreviewSidebar.vue';
import DesignModeToggle from '../components/base/DesignModeToggle.vue';
import PageLayout from '../components/base/PageLayout.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useUnsavedGuard } from '../composables/useUnsavedGuard';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const route = useRoute();

const commandId = computed(() => route.params.commandId ? Number(route.params.commandId) : null);

const showToast = useToast();
const isEditMode = computed(() => !!commandId.value);
const isLoadingEdit = ref(false);

// --------------- Mode toggle ---------------
const designMode = ref<'form' | 'chat'>('form');

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
  name: 'hive_command_design_get_state',
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
onMounted(() => {
  conversation.checkActiveConversations();
  if (isEditMode.value) {
    loadExistingCommand();
  }
});

watch(designMode, (newMode) => {
  if (newMode === 'chat' && !conversation.chatStarted.value) {
    if (conversation.activeConversations.value.length > 0) {
      conversation.resumeConversation(conversation.activeConversations.value[0].id);
    } else {
      conversation.startConversation();
    }
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
    showToast('Failed to load command for editing', 'error');
  } finally {
    isLoadingEdit.value = false;
  }
}

async function createCommand() {
  if (!formData.value.name.trim()) {
    showToast('Command name is required', 'error');
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
      showToast(`Command "${formData.value.name}" updated`, 'success');
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
      showToast(`Command "${formData.value.name}" created`, 'success');
      showExportModal.value = true;
    }
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(isEditMode.value ? 'Failed to update command' : 'Failed to create command', 'error');
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
  showToast('Command exported', 'success');
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
    showToast(`Command "${result.command.name}" created successfully!`, 'success');
    router.push({ name: 'commands' });
  }
}

async function handleCancel() {
  if (conversation.conversationId.value) {
    await conversation.abandonConversation();
  }
  router.push({ name: 'commands' });
}
</script>

<template>
  <PageLayout :breadcrumbs="[
    { label: 'Commands', action: () => handleCancel() },
    { label: isEditMode ? 'Edit Command' : 'Design Command' },
  ]" fullHeight maxWidth="100%">
  <div class="design-page">
    <div class="design-header">
      <DesignModeToggle v-model="designMode" />
      <div class="header-title">
        <h1>{{ isEditMode ? 'Edit Command' : 'Design a Command' }}</h1>
        <p v-if="designMode === 'form'">{{ isEditMode ? 'Edit an existing slash command' : 'Create a new slash command with a form' }}</p>
        <p v-else>Chat with Claude to design your slash command</p>
      </div>
      <button
        v-if="designMode === 'chat' && conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizeCommand"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Command' }}
      </button>
    </div>

    <!-- ==================== FORM MODE ==================== -->
    <div v-if="designMode === 'form'" class="design-content">
      <div class="design-form">
        <div class="form-section">
          <h3>Command Configuration</h3>

          <div class="form-group">
            <label for="command-name">Name *</label>
            <input
              id="command-name"
              v-model="formData.name"
              type="text"
              placeholder="my-command"
            />
            <p class="form-hint">The command will be invoked as /{{ formData.name || 'my-command' }}</p>
          </div>

          <div class="form-group">
            <label for="command-description">Description</label>
            <input
              id="command-description"
              v-model="formData.description"
              type="text"
              placeholder="What does this command do?"
            />
          </div>

          <div class="form-group">
            <label for="command-arguments">Arguments (JSON Array)</label>
            <textarea
              id="command-arguments"
              v-model="formData.arguments"
              rows="4"
              placeholder='[
  { "name": "target", "type": "string", "required": true },
  { "name": "options", "type": "string", "required": false }
]'
            ></textarea>
            <p class="form-hint">Define the arguments your command accepts</p>
          </div>

          <div class="form-group">
            <label for="command-content">Command Content (Markdown)</label>
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
              Enabled
            </label>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn" @click="router.push({ name: 'commands' })">Cancel</button>
          <button class="btn btn-primary" @click="createCommand" :disabled="isCreating">
            {{ isCreating ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Command' : 'Create Command') }}
          </button>
        </div>
      </div>

      <div class="design-preview">
        <h3>Preview</h3>
        <div class="preview-card">
          <div class="preview-header-form">
            <span class="preview-name">/{{ formData.name || 'command-name' }}</span>
          </div>
          <p class="preview-description">{{ formData.description || 'No description' }}</p>
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
        :assistant-icon-paths="COMMAND_ICON_PATHS"
        input-placeholder="Describe your command or answer Claude's questions..."
        entity-label="command"
        banner-title="Command Ready to Create!"
        banner-button-label="Create Command Now"
        :detected-entity-name="conversation.detectedConfig.value?.name"
        @update:input-message="conversation.inputMessage.value = $event"
        @update:selected-backend="conversation.setBackend($event)"
        @update:selected-account-id="conversation.setAccountId($event)"
        @update:selected-model="conversation.setModel($event)"
        @send="conversation.sendMessage"
        @keydown="conversation.handleKeyDown"
        @finalize="finalizeCommand"
      />

      <ConfigPreviewSidebar
        :has-config="!!conversation.detectedConfig.value"
        :empty-icon-paths="COMMAND_ICON_PATHS"
        empty-text="Command configuration will appear here as you chat with Claude"
      >
        <template v-if="conversation.detectedConfig.value">
          <div class="config-field">
            <div class="config-label">Name</div>
            <div class="config-value config-name">/{{ conversation.detectedConfig.value.name }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.description">
            <div class="config-label">Description</div>
            <div class="config-value config-description">{{ conversation.detectedConfig.value.description }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.content">
            <div class="config-label">Content</div>
            <pre class="config-code">{{ conversation.detectedConfig.value.content.slice(0, 300) }}{{ conversation.detectedConfig.value.content.length > 300 ? '...' : '' }}</pre>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.arguments && conversation.detectedConfig.value.arguments.length > 0">
            <div class="config-label">Arguments</div>
            <div class="arguments-list">
              <div v-for="(arg, i) in conversation.detectedConfig.value.arguments" :key="i" class="argument-item">
                <span class="arg-name">{{ arg.name }}</span>
                <span class="arg-type">{{ arg.type }}</span>
                <span v-if="arg.required" class="arg-required">required</span>
                <span v-if="arg.description" class="arg-desc">{{ arg.description }}</span>
              </div>
            </div>
          </div>
          <div class="config-field">
            <div class="config-label">Enabled</div>
            <div class="config-value">
              <span :class="['enabled-badge', conversation.detectedConfig.value.enabled ? 'yes' : 'no']">
                {{ conversation.detectedConfig.value.enabled ? 'Yes' : 'No' }}
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
          <h2 id="modal-title-command-created">Command Created!</h2>
          <p>Your command "<strong>/{{ formData.name }}</strong>" has been created successfully.</p>
          <div class="modal-actions">
            <button class="btn" @click="exportToLibrary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              Export to Library
            </button>
            <button class="btn btn-secondary" @click="createAnother">Create Another</button>
            <button class="btn btn-primary" @click="handleFormCreated">Done</button>
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
.btn-primary:hover { background: #9966ff; }
.btn-primary svg { width: 16px; height: 16px; }
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
