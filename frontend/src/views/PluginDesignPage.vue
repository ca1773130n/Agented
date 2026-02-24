<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { pluginConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import ConfigPreviewSidebar from '../components/plugins/ConfigPreviewSidebar.vue';
import PageLayout from '../components/base/PageLayout.vue';
import { useToast } from '../composables/useToast';
import { useUnsavedGuard } from '../composables/useUnsavedGuard';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

// Component tree state
interface PluginComponent {
  name: string;
  type: string;
  content: string;
}

interface ParsedPluginConfig {
  name: string;
  description: string;
  version: string;
  components: PluginComponent[];
}

const conversation = useConversation<ParsedPluginConfig>(pluginConversationApi, createConfigParser<ParsedPluginConfig>('---PLUGIN_CONFIG---'));

// Unsaved changes guard -- dirty when user has sent messages in the conversation
const isDirty = computed(() => conversation.messages.value.some((m: { role: string }) => m.role === 'user'));
useUnsavedGuard(isDirty);

useWebMcpTool({
  name: 'agented_plugin_design_get_state',
  description: 'Returns the current state of the PluginDesignPage',
  page: 'PluginDesignPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'PluginDesignPage',
        conversationId: conversation.conversationId.value,
        messagesCount: conversation.messages.value.length,
        isProcessing: conversation.isProcessing.value,
        canFinalize: conversation.canFinalize.value,
        isFinalizing: conversation.isFinalizing.value,
        isDirty: isDirty.value,
        detectedConfigName: conversation.detectedConfig.value?.name ?? null,
        componentsCount: conversation.detectedConfig.value?.components?.length ?? 0,
        selectedBackend: conversation.selectedBackend.value,
      }),
    }],
  }),
  deps: [conversation.conversationId, conversation.messages, conversation.isProcessing, conversation.canFinalize, conversation.isFinalizing, isDirty, conversation.detectedConfig],
});

const selectedComponent = ref<PluginComponent | null>(null);

const componentsByType = computed(() => {
  if (!conversation.detectedConfig.value) return {};
  const grouped: Record<string, PluginComponent[]> = {};
  for (const comp of conversation.detectedConfig.value.components) {
    if (!grouped[comp.type]) grouped[comp.type] = [];
    grouped[comp.type].push(comp);
  }
  return grouped;
});

function selectComponent(comp: PluginComponent) {
  selectedComponent.value = comp;
}

const typeLabels: Record<string, string> = {
  skill: 'Skills',
  command: 'Commands',
  hook: 'Hooks',
  rule: 'Rules',
  agent: 'Agents',
};

const typeIcons: Record<string, string> = {
  skill: 'M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5',
  command: 'M4 17l6-6-6-6 M12 19h8',
  hook: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71',
  rule: 'M9 11l3 3L22 4 M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11',
  agent: 'M12 8a4 4 0 100-8 4 4 0 000 8zM6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2',
};

const PLUGIN_ICON_PATHS = [
  'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z',
];

async function copyComponentContent() {
  if (!selectedComponent.value?.content) return;
  try {
    await navigator.clipboard.writeText(selectedComponent.value.content);
  } catch {
    // Silent fail for copy
  }
}

async function finalizePlugin() {
  const result = await conversation.finalize();
  if (result) {
    showToast(`Plugin "${(result.plugin as { name: string }).name}" created successfully!`, 'success');
    router.push({ name: 'plugin-detail', params: { pluginId: result.plugin_id as string } });
  }
}

function abandonAndCancel() {
  conversation.abandonConversation();
  router.push({ name: 'plugins' });
}

onMounted(() => {
  conversation.startConversation();
});
</script>

<template>
  <PageLayout :breadcrumbs="[
    { label: 'Plugins', action: () => abandonAndCancel() },
    { label: 'Design Plugin' },
  ]" fullHeight maxWidth="100%">
  <div class="design-page">
    <div class="design-header">
      <div class="header-title">
        <h1>Design a Plugin</h1>
        <p>Chat with Claude to design your plugin with multiple components</p>
      </div>
      <button
        v-if="conversation.canFinalize.value"
        class="btn btn-primary btn-finalize"
        :disabled="conversation.isFinalizing.value"
        @click="finalizePlugin"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
        {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Plugin' }}
      </button>
    </div>

    <div class="design-body">
      <!-- Left Sidebar: Component Tree -->
      <div class="sidebar-left">
        <div class="sidebar-header">
          <h3>Components</h3>
        </div>
        <div v-if="!conversation.detectedConfig.value" class="sidebar-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          <p>Components will appear here as you design your plugin</p>
        </div>
        <div v-else class="component-tree">
          <div class="plugin-info">
            <div class="plugin-name">{{ conversation.detectedConfig.value.name }}</div>
            <div class="plugin-version">v{{ conversation.detectedConfig.value.version }}</div>
          </div>
          <div v-for="(comps, type) in componentsByType" :key="type" class="type-group">
            <div class="type-header">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path :d="typeIcons[type as string] || typeIcons.skill"/>
              </svg>
              <span>{{ typeLabels[type as string] || type }}</span>
              <span class="type-count">{{ comps.length }}</span>
            </div>
            <div
              v-for="comp in comps"
              :key="comp.name"
              class="component-item"
              :class="{ active: selectedComponent?.name === comp.name && selectedComponent?.type === comp.type }"
              @click="selectComponent(comp)"
            >
              <span class="comp-name">{{ comp.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Center: Chat -->
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
        :assistant-icon-paths="PLUGIN_ICON_PATHS"
        input-placeholder="Describe your plugin or answer Claude's questions..."
        entity-label="plugin"
        banner-title="Plugin Ready to Create!"
        banner-button-label="Create Plugin Now"
        :detected-entity-name="conversation.detectedConfig.value?.name"
        @update:input-message="conversation.inputMessage.value = $event"
        @update:selected-backend="conversation.setBackend($event)"
        @update:selected-account-id="conversation.setAccountId($event)"
        @update:selected-model="conversation.setModel($event)"
        @send="conversation.sendMessage"
        @keydown="conversation.handleKeyDown"
        @finalize="finalizePlugin"
      />

      <!-- Right Sidebar: Component Preview -->
      <ConfigPreviewSidebar
        :has-config="!!selectedComponent"
        :empty-icon-paths="['M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122']"
        empty-text="Select a component from the tree to preview its details"
        title="Component Preview"
      >
        <template v-if="selectedComponent">
          <div class="preview-header">
            <div class="preview-type-badge" :class="selectedComponent.type">
              {{ selectedComponent.type }}
            </div>
            <h4>{{ selectedComponent.name }}</h4>
          </div>
          <div class="preview-content">
            <div class="preview-label">Content</div>
            <div class="code-block">
              <div class="code-header">
                <span class="code-lang">{{ selectedComponent.type }}</span>
                <button class="code-copy-btn" @click="copyComponentContent" title="Copy content">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                  </svg>
                </button>
              </div>
              <pre class="code-content"><code>{{ selectedComponent.content }}</code></pre>
            </div>
          </div>
        </template>
      </ConfigPreviewSidebar>
    </div>
  </div>
  </PageLayout>
</template>

<style scoped>
/* Design-page scoped overrides (violet-themed buttons) */
.btn-primary { background: var(--accent-violet); color: #fff; }
.btn-primary:hover { background: #9966ff; }
.btn-primary svg { width: 16px; height: 16px; }

/* Plugin-specific: left sidebar with component tree */
.sidebar-left {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-secondary);
}

.sidebar-header { padding: 16px; border-bottom: 1px solid var(--border-default); }
.sidebar-header h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-primary); }
.sidebar-empty { display: flex; flex-direction: column; align-items: center; padding: 40px 20px; text-align: center; color: var(--text-tertiary); }
.sidebar-empty svg { width: 40px; height: 40px; margin-bottom: 12px; opacity: 0.5; }
.sidebar-empty p { margin: 0; font-size: 13px; line-height: 1.5; }

/* Component tree */
.component-tree { padding: 12px; }
.plugin-info { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 12px; }
.plugin-name { font-size: 14px; font-weight: 600; color: var(--text-primary); flex: 1; }
.plugin-version { font-size: 12px; color: var(--text-tertiary); background: var(--bg-elevated, var(--bg-primary)); padding: 2px 8px; border-radius: 4px; }
.type-group { margin-bottom: 8px; }
.type-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--text-tertiary); letter-spacing: 0.5px; }
.type-header svg { width: 14px; height: 14px; }
.type-count { margin-left: auto; background: var(--bg-tertiary); padding: 1px 6px; border-radius: 4px; font-size: 11px; }
.component-item { padding: 8px 12px 8px 34px; font-size: 13px; color: var(--text-secondary); border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.component-item:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.component-item.active { background: rgba(136, 85, 255, 0.15); color: var(--accent-violet); }
.comp-name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Component preview (sidebar slot content) */
.preview-header { margin-bottom: 16px; }
.preview-type-badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; background: var(--bg-tertiary); color: var(--text-secondary); }
.preview-type-badge.skill { background: rgba(136, 85, 255, 0.15); color: var(--accent-violet); }
.preview-type-badge.command { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan); }
.preview-type-badge.hook { background: rgba(255, 170, 51, 0.15); color: #ffaa33; }
.preview-type-badge.rule { background: rgba(0, 200, 83, 0.15); color: #00c853; }
.preview-type-badge.agent { background: rgba(0, 255, 136, 0.15); color: var(--accent-emerald, #00ff88); }
.preview-header h4 { margin: 0; font-size: 16px; color: var(--text-primary); }
.preview-content { margin-top: 12px; }
.preview-label { font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 8px; letter-spacing: 0.5px; }
.code-block {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-primary);
}
.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}
.code-lang {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-tertiary);
  letter-spacing: 0.5px;
}
.code-copy-btn {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.code-copy-btn:hover {
  color: var(--text-primary);
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
}
.code-copy-btn svg {
  width: 14px;
  height: 14px;
}
.code-content {
  margin: 0;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
  tab-size: 2;
}
.code-content code {
  font-family: inherit;
  color: inherit;
}
</style>
