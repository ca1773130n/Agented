<script setup lang="ts">
/**
 * SessionContextTray
 *
 * Per-prompt attachment tray that sits above the chat input in
 * ProjectSessionPanel. Operator picks repo files, pastes snippets,
 * drops URLs, or @-mentions project entities. Each attachment
 * shows as a chip; clearing the input also clears the chips.
 *
 * The tray is purely local state. ``ProjectSessionPanel`` reads
 * ``v-model:attachments`` and forwards the array to
 * ``useProjectSession.sendInput()``. Backend compiles the bundle.
 *
 * v0.7.70.
 */
import { ref } from 'vue';
import type { ForgeAttachment } from '../../services/api/projects';

const props = defineProps<{
  attachments: ForgeAttachment[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:attachments', value: ForgeAttachment[]): void;
}>();

const showSnippetEditor = ref(false);
const snippetLabel = ref('');
const snippetText = ref('');
const showFileEditor = ref(false);
const filePath = ref('');
const showUrlEditor = ref(false);
const urlValue = ref('');
const urlSummary = ref('');
const showEntityEditor = ref(false);
const entityRef = ref('');
const entityPayload = ref('');

function commit(next: ForgeAttachment[]) {
  emit('update:attachments', next);
}

function removeAt(idx: number) {
  const next = props.attachments.slice();
  next.splice(idx, 1);
  commit(next);
}

function addFile() {
  const path = filePath.value.trim();
  if (!path) {
    showFileEditor.value = false;
    return;
  }
  commit([...props.attachments, { kind: 'file', path }]);
  filePath.value = '';
  showFileEditor.value = false;
}

function addSnippet() {
  const text = snippetText.value.trim();
  if (!text) {
    showSnippetEditor.value = false;
    return;
  }
  commit([
    ...props.attachments,
    {
      kind: 'snippet',
      label: snippetLabel.value.trim() || undefined,
      text,
    },
  ]);
  snippetText.value = '';
  snippetLabel.value = '';
  showSnippetEditor.value = false;
}

function addUrl() {
  const url = urlValue.value.trim();
  if (!url) {
    showUrlEditor.value = false;
    return;
  }
  commit([
    ...props.attachments,
    {
      kind: 'url',
      url,
      summary: urlSummary.value.trim() || undefined,
    },
  ]);
  urlValue.value = '';
  urlSummary.value = '';
  showUrlEditor.value = false;
}

function addEntity() {
  const ref_ = entityRef.value.trim();
  if (!ref_) {
    showEntityEditor.value = false;
    return;
  }
  let payload: unknown = entityPayload.value.trim();
  if (payload) {
    try {
      payload = JSON.parse(String(payload));
    } catch {
      // Leave as raw text if not valid JSON — backend treats both.
    }
  } else {
    payload = null;
  }
  commit([...props.attachments, { kind: 'entity', ref: ref_, payload }]);
  entityRef.value = '';
  entityPayload.value = '';
  showEntityEditor.value = false;
}

function chipLabel(att: ForgeAttachment): string {
  switch (att.kind) {
    case 'file':
      return `📎 ${att.path}`;
    case 'snippet':
      return `💬 ${att.label || 'note'}`;
    case 'url':
      return `🔗 ${att.url}`;
    case 'entity':
      return `@ ${att.ref}`;
    default:
      return 'attachment';
  }
}
</script>

<template>
  <div class="session-context-tray" data-testid="session-context-tray">
    <div v-if="props.attachments.length" class="chip-row">
      <span
        v-for="(att, idx) in props.attachments"
        :key="idx"
        class="chip"
        :data-kind="att.kind"
      >
        <span class="chip-label">{{ chipLabel(att) }}</span>
        <button
          type="button"
          class="chip-remove"
          :aria-label="`Remove ${chipLabel(att)}`"
          :disabled="props.disabled"
          @click="removeAt(idx)"
        >
          ×
        </button>
      </span>
    </div>

    <div class="action-row">
      <button
        type="button"
        class="action-btn"
        :disabled="props.disabled"
        title="Attach a repo file (path relative to project root)"
        @click="showFileEditor = true"
      >
        📎 File
      </button>
      <button
        type="button"
        class="action-btn"
        :disabled="props.disabled"
        title="Attach a free-form snippet (notes, error logs, specs)"
        @click="showSnippetEditor = true"
      >
        💬 Snippet
      </button>
      <button
        type="button"
        class="action-btn"
        :disabled="props.disabled"
        title="Attach a URL (backend fetches + summarizes)"
        @click="showUrlEditor = true"
      >
        🔗 URL
      </button>
      <button
        type="button"
        class="action-btn"
        :disabled="props.disabled"
        title="Reference a project entity (@product/foo, @team/bar)"
        @click="showEntityEditor = true"
      >
        @ Entity
      </button>
    </div>

    <div v-if="showFileEditor" class="editor" data-testid="file-editor">
      <input
        v-model="filePath"
        placeholder="src/components/Foo.vue"
        @keydown.enter.prevent="addFile"
      />
      <button type="button" @click="addFile">Add</button>
      <button type="button" class="ghost" @click="showFileEditor = false">
        Cancel
      </button>
    </div>

    <div v-if="showSnippetEditor" class="editor" data-testid="snippet-editor">
      <input v-model="snippetLabel" placeholder="label (optional)" />
      <textarea
        v-model="snippetText"
        rows="3"
        placeholder="Paste text, error log, etc."
        @keydown.ctrl.enter.prevent="addSnippet"
        @keydown.meta.enter.prevent="addSnippet"
      ></textarea>
      <div class="editor-actions">
        <button type="button" @click="addSnippet">Add</button>
        <button type="button" class="ghost" @click="showSnippetEditor = false">
          Cancel
        </button>
      </div>
    </div>

    <div v-if="showUrlEditor" class="editor" data-testid="url-editor">
      <input v-model="urlValue" placeholder="https://example.com/spec" />
      <input v-model="urlSummary" placeholder="optional summary" />
      <div class="editor-actions">
        <button type="button" @click="addUrl">Add</button>
        <button type="button" class="ghost" @click="showUrlEditor = false">
          Cancel
        </button>
      </div>
    </div>

    <div v-if="showEntityEditor" class="editor" data-testid="entity-editor">
      <input v-model="entityRef" placeholder="@team/foo or prod-abc123" />
      <textarea
        v-model="entityPayload"
        rows="3"
        placeholder='JSON or free text (e.g. {"id":"team-1","name":"Core"})'
      ></textarea>
      <div class="editor-actions">
        <button type="button" @click="addEntity">Add</button>
        <button type="button" class="ghost" @click="showEntityEditor = false">
          Cancel
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-context-tray {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 16px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
  font-family: 'Geist', system-ui, sans-serif;
  font-size: 12px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
  max-width: 280px;
}

.chip-label {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.chip-remove {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  line-height: 1;
}
.chip-remove:hover:not(:disabled) {
  color: var(--text-primary);
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.action-btn {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.action-btn:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}
.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.editor {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-tertiary);
}
.editor input,
.editor textarea {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  padding: 4px 6px;
  border-radius: 4px;
  font: inherit;
}
.editor-actions {
  display: flex;
  gap: 6px;
}
.editor button {
  padding: 3px 10px;
  border: 1px solid var(--border-default);
  background: var(--accent-cyan);
  color: var(--bg-primary);
  border-radius: 4px;
  cursor: pointer;
}
.editor button.ghost {
  background: transparent;
  color: var(--text-secondary);
}
</style>
