<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { HookEvent } from '../services/api';
import { hookApi, hookConversationApi, ApiError } from '../services/api';
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

const hookId = computed(() => route.params.hookId ? Number(route.params.hookId) : null);

const showToast = useToast();
const isEditMode = computed(() => !!hookId.value);
const isLoadingEdit = ref(false);

// ---------------------------------------------------------------------------
// Mode toggle
// ---------------------------------------------------------------------------
const designMode = ref<'form' | 'chat'>('form');

// ---------------------------------------------------------------------------
// Form mode state
// ---------------------------------------------------------------------------
const formData = ref({
  name: '',
  event: 'PreToolUse' as HookEvent,
  description: '',
  content: '',
  enabled: true,
});

const isCreating = ref(false);
const showExportModal = ref(false);
const exportModalRef = ref<HTMLElement | null>(null);
const createdHookId = ref<number | null>(null);

// Unsaved changes guard
const originalFormData = ref(JSON.stringify({ name: '', event: 'PreToolUse', description: '', content: '', enabled: true }));
const isDirty = computed(() => JSON.stringify(formData.value) !== originalFormData.value);
useUnsavedGuard(isDirty);

useFocusTrap(exportModalRef, showExportModal);

const HOOK_EVENTS: HookEvent[] = [
  'PreToolUse',
  'PostToolUse',
  'Stop',
  'SubagentStop',
  'SessionStart',
  'SessionEnd',
  'UserPromptSubmit',
  'PreCompact',
  'Notification',
];

const eventDescriptions: Record<HookEvent, string> = {
  PreToolUse: 'Triggered before any tool is used. Use to validate or modify tool inputs.',
  PostToolUse: 'Triggered after a tool completes. Use to process or validate outputs.',
  Stop: 'Triggered when the agent stops. Use for cleanup or final actions.',
  SubagentStop: 'Triggered when a subagent completes. Use to handle subagent results.',
  SessionStart: 'Triggered at session start. Use for initialization.',
  SessionEnd: 'Triggered at session end. Use for cleanup or summaries.',
  UserPromptSubmit: 'Triggered when user submits a prompt. Use to preprocess input.',
  PreCompact: 'Triggered before context compaction. Use to preserve important context.',
  Notification: 'Triggered for notifications. Use to handle alerts or messages.',
};

async function loadExistingHook() {
  if (!hookId.value) return;
  isLoadingEdit.value = true;
  try {
    const hook = await hookApi.get(hookId.value);
    formData.value.name = hook.name;
    formData.value.event = hook.event;
    formData.value.description = hook.description || '';
    formData.value.content = hook.content || '';
    formData.value.enabled = !!hook.enabled;
    originalFormData.value = JSON.stringify(formData.value);
  } catch (e) {
    showToast('Failed to load hook for editing', 'error');
  } finally {
    isLoadingEdit.value = false;
  }
}

async function createHookViaForm() {
  if (!formData.value.name.trim()) {
    showToast('Hook name is required', 'error');
    return;
  }

  isCreating.value = true;
  try {
    if (isEditMode.value && hookId.value) {
      await hookApi.update(hookId.value, {
        name: formData.value.name,
        event: formData.value.event,
        description: formData.value.description || undefined,
        content: formData.value.content || undefined,
        enabled: formData.value.enabled,
      });
      originalFormData.value = JSON.stringify(formData.value);
      showToast(`Hook "${formData.value.name}" updated`, 'success');
      router.push({ name: 'hooks' });
    } else {
      const result = await hookApi.create({
        name: formData.value.name,
        event: formData.value.event,
        description: formData.value.description || undefined,
        content: formData.value.content || undefined,
        enabled: formData.value.enabled,
      });
      createdHookId.value = result.hook.id;
      showToast(`Hook "${formData.value.name}" created`, 'success');
      showExportModal.value = true;
    }
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(isEditMode.value ? 'Failed to update hook' : 'Failed to create hook', 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function exportToLibrary() {
  const exportData = {
    name: formData.value.name,
    event: formData.value.event,
    description: formData.value.description,
    content: formData.value.content,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `hook-${formData.value.name.replace(/\s+/g, '-').toLowerCase()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Hook exported', 'success');
}

function handleFormDone() {
  router.push({ name: 'hooks' });
}

function createAnother() {
  formData.value = {
    name: '',
    event: 'PreToolUse',
    description: '',
    content: '',
    enabled: true,
  };
  originalFormData.value = JSON.stringify(formData.value);
  createdHookId.value = null;
  showExportModal.value = false;
}

// ---------------------------------------------------------------------------
// Chat mode state (via shared composable)
// ---------------------------------------------------------------------------
interface ParsedHookConfig {
  name: string;
  event: string;
  description: string;
  content: string;
  enabled: boolean;
}

const conversation = useConversation<ParsedHookConfig>(hookConversationApi, createConfigParser<ParsedHookConfig>('---HOOK_CONFIG---'));

useWebMcpTool({
  name: 'hive_hook_design_get_state',
  description: 'Returns the current state of the HookDesignPage',
  page: 'HookDesignPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'HookDesignPage',
        isEditMode: isEditMode.value,
        hookId: hookId.value ?? null,
        designMode: designMode.value,
        formName: formData.value.name,
        formEvent: formData.value.event,
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

const eventBadgeColor: Record<string, string> = {
  PreToolUse: '#ffaa33',
  PostToolUse: '#00d4ff',
  Stop: '#ff3366',
  SubagentStop: '#ff3366',
  SessionStart: '#00ff88',
  SessionEnd: '#00ff88',
  UserPromptSubmit: '#8855ff',
  PreCompact: '#f59e0b',
  Notification: '#00d4ff',
};

const HOOK_ICON_PATHS = [
  'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71',
  'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71',
];

async function finalizeHook() {
  const result = await conversation.finalize();
  if (result) {
    showToast(`Hook "${result.hook.name}" created successfully!`, 'success');
    router.push({ name: 'hooks' });
  }
}

// Check for active conversations on mount and load existing hook for edit mode
onMounted(() => {
  conversation.checkActiveConversations();
  if (isEditMode.value) {
    loadExistingHook();
  }
});

// Start conversation only when switching to chat mode
watch(designMode, (newMode) => {
  if (newMode === 'chat' && !conversation.chatStarted.value) {
    // If there's an active conversation to resume, resume it instead
    if (conversation.activeConversations.value.length > 0) {
      conversation.resumeConversation(conversation.activeConversations.value[0].id);
    } else {
      conversation.startConversation();
    }
  }
});

function handleBack() {
  if (designMode.value === 'chat') {
    conversation.abandonConversation();
  }
  router.push({ name: 'hooks' });
}
</script>

<template>
  <PageLayout :breadcrumbs="[
    { label: 'Hooks', action: () => handleBack() },
    { label: isEditMode ? 'Edit Hook' : 'Design Hook' },
  ]" fullHeight maxWidth="100%">
  <div class="design-page">
    <!-- Shared header -->
    <div class="design-header">
      <DesignModeToggle v-model="designMode" />

      <div class="header-title">
        <h1>{{ isEditMode ? 'Edit Hook' : 'Design a Hook' }}</h1>
        <p v-if="designMode === 'form'">{{ isEditMode ? 'Edit an existing hook' : 'Create a new hook with a form' }}</p>
        <p v-else>Chat with Claude to design your hook</p>
      </div>

      <button
        v-if="designMode === 'chat' && conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizeHook"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Hook' }}
      </button>
    </div>

    <!-- ================================================================= -->
    <!-- FORM MODE                                                         -->
    <!-- ================================================================= -->
    <div v-if="designMode === 'form'" class="design-content">
      <div class="design-form">
        <div class="form-section">
          <h3>Hook Configuration</h3>

          <div class="form-group">
            <label for="hook-name">Name *</label>
            <input
              id="hook-name"
              v-model="formData.name"
              type="text"
              placeholder="my-custom-hook"
            />
          </div>

          <div class="form-group">
            <label for="hook-event">Event Type *</label>
            <select id="hook-event" v-model="formData.event">
              <option v-for="evt in HOOK_EVENTS" :key="evt" :value="evt">
                {{ evt }}
              </option>
            </select>
            <p class="form-hint">{{ eventDescriptions[formData.event] }}</p>
          </div>

          <div class="form-group">
            <label for="hook-description">Description</label>
            <input
              id="hook-description"
              v-model="formData.description"
              type="text"
              placeholder="What does this hook do?"
            />
          </div>

          <div class="form-group">
            <label for="hook-content">Hook Content (Markdown)</label>
            <textarea
              id="hook-content"
              v-model="formData.content"
              rows="12"
              placeholder="# Hook Instructions

Describe what this hook should do when triggered...

## Behavior
- Validate inputs
- Check conditions
- Provide feedback

## Example
When the user tries to...
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
          <button class="btn" @click="router.push({ name: 'hooks' })">Cancel</button>
          <button class="btn btn-primary" @click="createHookViaForm" :disabled="isCreating">
            {{ isCreating ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Hook' : 'Create Hook') }}
          </button>
        </div>
      </div>

      <div class="design-preview">
        <h3>Preview</h3>
        <div class="preview-card">
          <div class="preview-header-row">
            <span class="preview-name">{{ formData.name || 'hook-name' }}</span>
            <span class="preview-event" :class="formData.event.toLowerCase()">{{ formData.event }}</span>
          </div>
          <p class="preview-description">{{ formData.description || 'No description' }}</p>
          <div class="preview-content-box" v-if="formData.content">
            <pre>{{ formData.content.slice(0, 200) }}{{ formData.content.length > 200 ? '...' : '' }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ================================================================= -->
    <!-- CHAT MODE                                                         -->
    <!-- ================================================================= -->
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
        :assistant-icon-paths="HOOK_ICON_PATHS"
        input-placeholder="Describe your hook or answer Claude's questions..."
        entity-label="hook"
        banner-title="Hook Ready to Create!"
        banner-button-label="Create Hook Now"
        :detected-entity-name="conversation.detectedConfig.value?.name"
        @update:input-message="conversation.inputMessage.value = $event"
        @update:selected-backend="conversation.setBackend($event)"
        @update:selected-account-id="conversation.setAccountId($event)"
        @update:selected-model="conversation.setModel($event)"
        @send="conversation.sendMessage"
        @keydown="conversation.handleKeyDown"
        @finalize="finalizeHook"
      />

      <ConfigPreviewSidebar
        :has-config="!!conversation.detectedConfig.value"
        :empty-icon-paths="HOOK_ICON_PATHS"
        empty-text="Hook configuration will appear here as you chat with Claude"
      >
        <template v-if="conversation.detectedConfig.value">
          <div class="config-field">
            <div class="config-label">Name</div>
            <div class="config-value">{{ conversation.detectedConfig.value.name }}</div>
          </div>
          <div class="config-field">
            <div class="config-label">Event</div>
            <div class="config-value">
              <span class="event-badge" :style="{ background: (eventBadgeColor[conversation.detectedConfig.value.event] || '#8855ff') + '26', color: eventBadgeColor[conversation.detectedConfig.value.event] || '#8855ff' }">
                {{ conversation.detectedConfig.value.event }}
              </span>
            </div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.description">
            <div class="config-label">Description</div>
            <div class="config-value config-description">{{ conversation.detectedConfig.value.description }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.content">
            <div class="config-label">Content</div>
            <pre class="config-code">{{ conversation.detectedConfig.value.content.slice(0, 300) }}{{ conversation.detectedConfig.value.content.length > 300 ? '...' : '' }}</pre>
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

    <!-- Export Modal (form mode only) -->
    <Teleport to="body">
      <div v-if="showExportModal" ref="exportModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-hook-created" tabindex="-1" @click.self="showExportModal = false" @keydown.escape="showExportModal = false">
        <div class="modal export-modal">
          <div class="modal-icon success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
          </div>
          <h2 id="modal-title-hook-created">Hook Created!</h2>
          <p>Your hook "<strong>{{ formData.name }}</strong>" has been created successfully.</p>
          <div class="modal-actions">
            <button class="btn" @click="exportToLibrary">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              Export to Library
            </button>
            <button class="btn btn-secondary" @click="createAnother">Create Another</button>
            <button class="btn btn-primary" @click="handleFormDone">Done</button>
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

/* Hook-specific: form preview event badge */
.preview-header-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.preview-event { font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 4px; background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15)); color: var(--accent-cyan, #00d4ff); }
.preview-content-box { background: var(--bg-tertiary); border-radius: 6px; padding: 12px; }
.preview-content-box pre { margin: 0; font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }

/* Hook-specific: chat sidebar event badge */
.event-badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
</style>
