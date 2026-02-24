<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { RuleType } from '../services/api';
import { ruleApi, ruleConversationApi, ApiError } from '../services/api';
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

const ruleId = computed(() => route.params.ruleId ? Number(route.params.ruleId) : null);

const showToast = useToast();
const isEditMode = computed(() => !!ruleId.value);
const isLoadingEdit = ref(false);

// Mode Toggle
const designMode = ref<'form' | 'chat'>('form');

// Form Mode State
const formData = ref({
  name: '',
  rule_type: 'validation' as RuleType,
  description: '',
  condition: '',
  action: '',
  enabled: true,
});

const isCreating = ref(false);
const showExportModal = ref(false);
const exportModalRef = ref<HTMLElement | null>(null);
const createdRuleId = ref<number | null>(null);

// Unsaved changes guard
const originalFormData = ref(JSON.stringify({ name: '', rule_type: 'validation', description: '', condition: '', action: '', enabled: true }));
const isDirty = computed(() => JSON.stringify(formData.value) !== originalFormData.value);
useUnsavedGuard(isDirty);

useFocusTrap(exportModalRef, showExportModal);

const RULE_TYPES: RuleType[] = ['pre_check', 'post_check', 'validation'];

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  pre_check: 'Pre-Check',
  post_check: 'Post-Check',
  validation: 'Validation',
};

const ruleTypeDescriptions: Record<RuleType, string> = {
  pre_check: 'Runs before an action. Use to validate preconditions or setup.',
  post_check: 'Runs after an action. Use to verify outcomes or cleanup.',
  validation: 'Validates inputs or outputs. Use for data integrity checks.',
};

async function loadExistingRule() {
  if (!ruleId.value) return;
  isLoadingEdit.value = true;
  try {
    const rule = await ruleApi.get(ruleId.value);
    formData.value.name = rule.name;
    formData.value.rule_type = rule.rule_type;
    formData.value.description = rule.description || '';
    formData.value.condition = rule.condition || '';
    formData.value.action = rule.action || '';
    formData.value.enabled = !!rule.enabled;
    originalFormData.value = JSON.stringify(formData.value);
  } catch (e) {
    showToast('Failed to load rule for editing', 'error');
  } finally {
    isLoadingEdit.value = false;
  }
}

async function createRule() {
  if (!formData.value.name.trim()) {
    showToast('Rule name is required', 'error');
    return;
  }

  isCreating.value = true;
  try {
    if (isEditMode.value && ruleId.value) {
      await ruleApi.update(ruleId.value, {
        name: formData.value.name,
        rule_type: formData.value.rule_type,
        description: formData.value.description || undefined,
        condition: formData.value.condition || undefined,
        action: formData.value.action || undefined,
        enabled: formData.value.enabled,
      });
      originalFormData.value = JSON.stringify(formData.value);
      showToast(`Rule "${formData.value.name}" updated`, 'success');
      router.push({ name: 'rules' });
    } else {
      const result = await ruleApi.create({
        name: formData.value.name,
        rule_type: formData.value.rule_type,
        description: formData.value.description || undefined,
        condition: formData.value.condition || undefined,
        action: formData.value.action || undefined,
        enabled: formData.value.enabled,
      });
      createdRuleId.value = result.rule.id;
      showToast(`Rule "${formData.value.name}" created`, 'success');
      showExportModal.value = true;
    }
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(isEditMode.value ? 'Failed to update rule' : 'Failed to create rule', 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function exportToLibrary() {
  const exportData = {
    name: formData.value.name,
    rule_type: formData.value.rule_type,
    description: formData.value.description,
    condition: formData.value.condition,
    action: formData.value.action,
  };

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `rule-${formData.value.name.replace(/\s+/g, '-').toLowerCase()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Rule exported', 'success');
}

function createAnother() {
  formData.value = {
    name: '',
    rule_type: 'validation',
    description: '',
    condition: '',
    action: '',
    enabled: true,
  };
  originalFormData.value = JSON.stringify(formData.value);
  createdRuleId.value = null;
  showExportModal.value = false;
}

function handleFormDone() {
  router.push({ name: 'rules' });
}

// Chat Mode State (via shared composable)
interface ParsedRuleConfig {
  name: string;
  rule_type: string;
  description: string;
  condition: string;
  action: string;
  enabled: boolean;
}

const conversation = useConversation<ParsedRuleConfig>(ruleConversationApi, createConfigParser<ParsedRuleConfig>('---RULE_CONFIG---'));

useWebMcpTool({
  name: 'agented_rule_design_get_state',
  description: 'Returns the current state of the RuleDesignPage',
  page: 'RuleDesignPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'RuleDesignPage',
        isEditMode: isEditMode.value,
        ruleId: ruleId.value ?? null,
        designMode: designMode.value,
        formName: formData.value.name,
        formRuleType: formData.value.rule_type,
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

const ruleTypeBadge: Record<string, { bg: string; color: string; label: string }> = {
  pre_check: { bg: 'rgba(0, 212, 255, 0.15)', color: '#00d4ff', label: 'Pre-Check' },
  post_check: { bg: 'rgba(0, 255, 136, 0.15)', color: '#00ff88', label: 'Post-Check' },
  validation: { bg: 'rgba(136, 85, 255, 0.15)', color: '#8855ff', label: 'Validation' },
};

const RULE_ICON_PATHS = [
  'M9 11l3 3L22 4',
  'M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
];

async function finalizeRule() {
  const result = await conversation.finalize();
  if (result) {
    showToast(`Rule "${(result.rule as { name: string }).name}" created successfully!`, 'success');
    router.push({ name: 'rules' });
  }
}

// Check for active conversations on mount and load existing rule for edit mode
onMounted(() => {
  conversation.checkActiveConversations();
  if (isEditMode.value) {
    loadExistingRule();
  }
});

// Start conversation only when switching to chat mode
watch(designMode, (newMode) => {
  if (newMode === 'chat' && !conversation.chatStarted.value) {
    if (conversation.activeConversations.value.length > 0) {
      conversation.resumeConversation(conversation.activeConversations.value[0].id);
    } else {
      conversation.startConversation();
    }
  }
});

function handleBack() {
  if (designMode.value === 'chat' && conversation.conversationId.value) {
    conversation.abandonConversation();
  }
  router.push({ name: 'rules' });
}
</script>

<template>
  <PageLayout :breadcrumbs="[
    { label: 'Rules', action: () => handleBack() },
    { label: isEditMode ? 'Edit Rule' : 'Design Rule' },
  ]" fullHeight maxWidth="100%">
  <div class="design-page">
    <div class="design-header">
      <DesignModeToggle v-model="designMode" />
      <div class="header-title">
        <h1>{{ isEditMode ? 'Edit Rule' : 'Design a Rule' }}</h1>
        <p>{{ designMode === 'form' ? (isEditMode ? 'Edit an existing validation or check rule' : 'Create a new validation or check rule') : 'Chat with Claude to design your validation rule' }}</p>
      </div>
      <button
        v-if="designMode === 'chat' && conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizeRule"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Rule' }}
      </button>
    </div>

    <!-- FORM MODE -->
    <div v-if="designMode === 'form'" class="design-content">
      <div class="design-form">
        <div class="form-section">
          <h3>Rule Configuration</h3>

          <div class="form-group">
            <label for="rule-name">Name *</label>
            <input id="rule-name" v-model="formData.name" type="text" placeholder="my-validation-rule" />
          </div>

          <div class="form-group">
            <label for="rule-type">Rule Type *</label>
            <select id="rule-type" v-model="formData.rule_type">
              <option v-for="ruleType in RULE_TYPES" :key="ruleType" :value="ruleType">
                {{ RULE_TYPE_LABELS[ruleType] }}
              </option>
            </select>
            <p class="form-hint">{{ ruleTypeDescriptions[formData.rule_type] }}</p>
          </div>

          <div class="form-group">
            <label for="rule-description">Description</label>
            <input id="rule-description" v-model="formData.description" type="text" placeholder="What does this rule check or validate?" />
          </div>

          <div class="form-group">
            <label for="rule-condition">Condition</label>
            <textarea
              id="rule-condition"
              v-model="formData.condition"
              rows="6"
              placeholder="# Condition to check

Define when this rule applies:
- Pattern to match
- Regular expression
- Value comparison

Example:
file_extension == '.ts' AND contains('import')"
            ></textarea>
            <p class="form-hint">Specify the condition that triggers this rule</p>
          </div>

          <div class="form-group">
            <label for="rule-action">Action</label>
            <textarea
              id="rule-action"
              v-model="formData.action"
              rows="6"
              placeholder="# Action to take

Define what happens when the condition is met:
- block: Prevent the action
- warn: Show a warning
- transform: Modify the input/output
- log: Record for auditing

Example:
warn('Consider using TypeScript strict mode')"
            ></textarea>
            <p class="form-hint">Specify what action to take when the condition is met</p>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input type="checkbox" v-model="formData.enabled" />
              Enabled
            </label>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn" @click="router.push({ name: 'rules' })">Cancel</button>
          <button class="btn btn-primary" @click="createRule" :disabled="isCreating">
            {{ isCreating ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Rule' : 'Create Rule') }}
          </button>
        </div>
      </div>

      <div class="design-preview">
        <h3>Preview</h3>
        <div class="preview-card">
          <div class="preview-header">
            <span class="preview-name">{{ formData.name || 'rule-name' }}</span>
            <span class="preview-type" :class="formData.rule_type">{{ RULE_TYPE_LABELS[formData.rule_type] }}</span>
          </div>
          <p class="preview-description">{{ formData.description || 'No description' }}</p>
          <div class="preview-section" v-if="formData.condition">
            <div class="section-label">Condition</div>
            <pre>{{ formData.condition.slice(0, 100) }}{{ formData.condition.length > 100 ? '...' : '' }}</pre>
          </div>
          <div class="preview-section" v-if="formData.action">
            <div class="section-label">Action</div>
            <pre>{{ formData.action.slice(0, 100) }}{{ formData.action.length > 100 ? '...' : '' }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- CHAT MODE -->
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
        :assistant-icon-paths="RULE_ICON_PATHS"
        input-placeholder="Describe your rule or answer Claude's questions..."
        entity-label="rule"
        banner-title="Rule Ready to Create!"
        banner-button-label="Create Rule Now"
        :detected-entity-name="conversation.detectedConfig.value?.name"
        @update:input-message="conversation.inputMessage.value = $event"
        @update:selected-backend="conversation.setBackend($event)"
        @update:selected-account-id="conversation.setAccountId($event)"
        @update:selected-model="conversation.setModel($event)"
        @send="conversation.sendMessage"
        @keydown="conversation.handleKeyDown"
        @finalize="finalizeRule"
      />

      <ConfigPreviewSidebar
        :has-config="!!conversation.detectedConfig.value"
        :empty-icon-paths="RULE_ICON_PATHS"
        empty-text="Rule configuration will appear here as you chat with Claude"
      >
        <template v-if="conversation.detectedConfig.value">
          <div class="config-field">
            <div class="config-label">Name</div>
            <div class="config-value">{{ conversation.detectedConfig.value.name }}</div>
          </div>
          <div class="config-field">
            <div class="config-label">Rule Type</div>
            <div class="config-value">
              <span
                class="rule-type-badge"
                :style="{
                  background: (ruleTypeBadge[conversation.detectedConfig.value.rule_type] || ruleTypeBadge.validation).bg,
                  color: (ruleTypeBadge[conversation.detectedConfig.value.rule_type] || ruleTypeBadge.validation).color,
                }"
              >
                {{ (ruleTypeBadge[conversation.detectedConfig.value.rule_type] || ruleTypeBadge.validation).label }}
              </span>
            </div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.description">
            <div class="config-label">Description</div>
            <div class="config-value config-description">{{ conversation.detectedConfig.value.description }}</div>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.condition">
            <div class="config-label">Condition</div>
            <pre class="config-code">{{ conversation.detectedConfig.value.condition.slice(0, 300) }}{{ conversation.detectedConfig.value.condition.length > 300 ? '...' : '' }}</pre>
          </div>
          <div class="config-field" v-if="conversation.detectedConfig.value.action">
            <div class="config-label">Action</div>
            <pre class="config-code">{{ conversation.detectedConfig.value.action.slice(0, 300) }}{{ conversation.detectedConfig.value.action.length > 300 ? '...' : '' }}</pre>
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

    <!-- Export Modal (Form mode) -->
    <Teleport to="body">
      <div v-if="showExportModal" ref="exportModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-rule-created" tabindex="-1" @click.self="showExportModal = false" @keydown.escape="showExportModal = false">
        <div class="modal export-modal">
          <div class="modal-icon success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
          </div>
          <h2 id="modal-title-rule-created">Rule Created!</h2>
          <p>Your rule "<strong>{{ formData.name }}</strong>" has been created successfully.</p>
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

/* Rule-specific: form preview */
.preview-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.preview-type { font-size: 11px; font-weight: 500; padding: 2px 8px; border-radius: 4px; }
.preview-type.pre_check { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.preview-type.post_check { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.preview-type.validation { background: var(--accent-violet-dim); color: var(--accent-violet); }
.preview-section { background: var(--bg-tertiary); border-radius: 6px; padding: 12px; margin-bottom: 8px; }
.preview-section:last-child { margin-bottom: 0; }
.section-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
.preview-section pre { margin: 0; font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }

/* Rule-specific: chat sidebar */
.rule-type-badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
</style>
