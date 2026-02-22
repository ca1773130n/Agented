<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import type { SuperAgentDocument, DocumentType } from '../../services/api';
import { superAgentDocumentApi } from '../../services/api';
import ConfirmModal from '../base/ConfirmModal.vue';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  superAgentId: string;
}>();

const showToast = useToast();

const DOC_TYPES: DocumentType[] = ['SOUL', 'IDENTITY', 'MEMORY', 'ROLE'];
const activeTab = ref<DocumentType>('SOUL');
const documents = ref<SuperAgentDocument[]>([]);
const editContent = ref('');
const isDirty = ref(false);
const isSaving = ref(false);
const isLoading = ref(true);
const showPreview = ref(false);

// Confirm discard state for unsaved tab switches
const showDiscardConfirm = ref(false);
const pendingTabSwitch = ref<DocumentType | null>(null);

async function loadDocuments() {
  isLoading.value = true;
  try {
    const result = await superAgentDocumentApi.list(props.superAgentId);
    documents.value = result.documents || [];
    // Load content for active tab
    loadTabContent();
  } catch {
    showToast('Failed to load documents', 'error');
  } finally {
    isLoading.value = false;
  }
}

function loadTabContent() {
  const doc = documents.value.find(d => d.doc_type === activeTab.value);
  editContent.value = doc?.content || '';
  isDirty.value = false;
}

function switchTab(docType: DocumentType) {
  if (isDirty.value) {
    pendingTabSwitch.value = docType;
    showDiscardConfirm.value = true;
    return;
  }
  activeTab.value = docType;
  loadTabContent();
}

function confirmDiscard() {
  showDiscardConfirm.value = false;
  if (pendingTabSwitch.value) {
    activeTab.value = pendingTabSwitch.value;
    pendingTabSwitch.value = null;
    loadTabContent();
  }
}

function cancelDiscard() {
  showDiscardConfirm.value = false;
  pendingTabSwitch.value = null;
}

async function saveDocument() {
  isSaving.value = true;
  try {
    const doc = documents.value.find(d => d.doc_type === activeTab.value);
    if (doc) {
      await superAgentDocumentApi.update(props.superAgentId, doc.id, {
        content: editContent.value,
      });
    } else {
      await superAgentDocumentApi.create(props.superAgentId, {
        doc_type: activeTab.value,
        title: activeTab.value,
        content: editContent.value,
      });
    }
    await loadDocuments();
    showToast(`${activeTab.value} document saved`, 'success');
  } catch {
    showToast('Failed to save document', 'error');
  } finally {
    isSaving.value = false;
  }
}

function onContentChange() {
  isDirty.value = true;
}

function hasDocument(docType: DocumentType): boolean {
  return documents.value.some(d => d.doc_type === docType);
}

function renderMarkdown(md: string): string {
  if (!md) return '<p style="color:var(--text-tertiary)">No content</p>';
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // Code blocks (fenced)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold and italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  // Paragraphs (double newline)
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean up empty paragraphs around block elements
  html = html.replace(/<p>\s*(<h[1-3]>)/g, '$1');
  html = html.replace(/(<\/h[1-3]>)\s*<\/p>/g, '$1');
  html = html.replace(/<p>\s*(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)\s*<\/p>/g, '$1');
  html = html.replace(/<p>\s*(<ul>)/g, '$1');
  html = html.replace(/(<\/ul>)\s*<\/p>/g, '$1');
  return html;
}

const renderedMarkdown = computed(() => renderMarkdown(editContent.value));

// Reload documents when superAgentId changes
watch(() => props.superAgentId, () => {
  loadDocuments();
});

onMounted(loadDocuments);
</script>

<template>
  <div class="document-editor">
    <div class="editor-tabs">
      <button
        v-for="docType in DOC_TYPES"
        :key="docType"
        :class="['editor-tab', { active: activeTab === docType }]"
        @click="switchTab(docType)"
      >
        {{ docType }}
        <span v-if="activeTab === docType && isDirty" class="dirty-dot"></span>
        <span v-if="hasDocument(docType)" class="doc-exists-dot"></span>
      </button>
    </div>

    <div v-if="isLoading" class="editor-loading">
      <div class="loading-spinner"></div>
      <span>Loading documents...</span>
    </div>

    <template v-else>
      <div class="editor-toolbar">
        <button
          :class="['toolbar-btn', { active: showPreview }]"
          @click="showPreview = !showPreview"
        >
          {{ showPreview ? 'Edit' : 'Preview' }}
        </button>
        <button
          class="toolbar-btn save-btn"
          :disabled="!isDirty || isSaving"
          @click="saveDocument"
        >
          {{ isSaving ? 'Saving...' : 'Save' }}
        </button>
      </div>

      <div class="editor-content">
        <textarea
          v-if="!showPreview"
          v-model="editContent"
          class="editor-textarea"
          :placeholder="`Write ${activeTab} document content (Markdown supported)...`"
          @input="onContentChange"
        ></textarea>
        <div v-else class="editor-preview">
          <div class="preview-content markdown-body" v-html="renderedMarkdown"></div>
        </div>
      </div>
    </template>

    <ConfirmModal
      :open="showDiscardConfirm"
      title="Unsaved Changes"
      message="You have unsaved changes. Discard them?"
      confirm-label="Discard"
      variant="danger"
      @confirm="confirmDiscard"
      @cancel="cancelDiscard"
    />
  </div>
</template>

<style scoped>
.document-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.editor-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border-default);
  padding: 0 4px;
}

.editor-tab {
  position: relative;
  padding: 8px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: -1px;
}

.editor-tab:hover {
  color: var(--text-secondary);
}

.editor-tab.active {
  color: var(--accent-violet);
  border-bottom-color: var(--accent-violet);
}

.dirty-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--accent-amber, #f59e0b);
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
}

.doc-exists-dot {
  display: inline-block;
  width: 4px;
  height: 4px;
  background: var(--accent-emerald, #00ff88);
  border-radius: 50%;
  margin-left: 4px;
  vertical-align: middle;
}

.editor-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: var(--text-secondary);
  font-size: 14px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-violet);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.editor-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid var(--border-default);
}

.toolbar-btn {
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
  color: var(--text-primary);
}

.toolbar-btn.active {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet);
  border-color: var(--accent-violet);
}

.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.save-btn:not(:disabled) {
  background: var(--accent-violet);
  color: #fff;
  border-color: var(--accent-violet);
}

.save-btn:not(:disabled):hover {
  background: #9966ff;
}

.editor-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.editor-textarea {
  width: 100%;
  height: 100%;
  padding: 12px;
  background: var(--bg-secondary);
  border: none;
  color: var(--text-primary);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.editor-textarea::placeholder {
  color: var(--text-tertiary);
}

.editor-preview {
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  background: var(--bg-secondary);
}

.preview-content {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.preview-content :deep(h1),
.preview-content :deep(h2),
.preview-content :deep(h3) {
  color: var(--text-primary);
  margin: 0.8em 0 0.4em 0;
}
.preview-content :deep(h1) { font-size: 1.4em; }
.preview-content :deep(h2) { font-size: 1.2em; }
.preview-content :deep(h3) { font-size: 1.05em; }
.preview-content :deep(strong) { color: var(--text-primary); }
.preview-content :deep(code) {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.9em;
}
.preview-content :deep(pre) {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
}
.preview-content :deep(pre code) {
  background: transparent;
  padding: 0;
}
.preview-content :deep(ul) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.preview-content :deep(a) {
  color: var(--accent-cyan);
  text-decoration: none;
}
.preview-content :deep(a:hover) {
  text-decoration: underline;
}
.preview-content :deep(p) {
  margin: 0.5em 0;
}
</style>
