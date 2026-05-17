<script setup lang="ts">
/**
 * SkillCreatePreviewDrawer
 *
 * Slide-over panel shown between the wizard's Create button and
 * the actual finalize call. Calls ``preview-finalize`` to render
 * the exact file tree that would land on disk + DB, then lets
 * the operator inspect each file (collapsed by default; click to
 * expand) before committing.
 *
 * Same focus-trap + token-guard + close-clears-state hygiene as
 * ``ContextPreviewDrawer`` since both expose the same UX
 * surface (operator inspects compiled output before send).
 *
 * v0.7.77.
 */
import { ref, toRef, watch } from 'vue';
import { skillConversationApi } from '../../services/api';
import type {
  SkillPackagePreview,
  SkillPackageFile,
} from '../../services/api/skills';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  open: boolean;
  conversationId: string | null;
  isFinalizing: boolean;
  // v0.7.77 (codex BLOCK 7) — the wizard passes
  // ``conversation.messages.value.length`` so the drawer
  // re-fetches the preview whenever claude finishes a new turn
  // while the drawer is open. Otherwise the operator could
  // commit a config that's no longer the latest one.
  messageCount: number;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  // v0.7.77 (codex BLOCK 4) — pass the previewed config hash up
  // so the wizard threads it into the finalize call. Backend
  // re-extracts the latest config and 409s on mismatch.
  (e: 'create', expectedConfigHash: string): void;
}>();

const preview = ref<SkillPackagePreview | null>(null);
const loading = ref(false);
const errorMessage = ref<string | null>(null);

// Token-guarded fetch (same pattern as ContextPreviewDrawer):
// rapid open → close → open before a slow response is race-safe.
let loadToken = 0;

async function load() {
  if (!props.conversationId) {
    errorMessage.value = 'No conversation to preview yet.';
    return;
  }
  loadToken += 1;
  const token = loadToken;
  loading.value = true;
  errorMessage.value = null;
  preview.value = null;
  try {
    const res = await skillConversationApi.previewFinalize(props.conversationId);
    if (token !== loadToken || !props.open) return;
    preview.value = res;
  } catch (err) {
    if (token !== loadToken || !props.open) return;
    errorMessage.value =
      err instanceof Error ? err.message : 'Failed to render preview';
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

// v0.7.77 (codex BLOCK 7) — also watch ``messageCount``. When a
// new assistant message lands while the drawer is open, re-fetch
// the preview so the operator never commits a stale config.
// Token guard handles the rapid case (multiple deltas → single
// effective render).
watch(
  [() => props.open, () => props.messageCount],
  ([isOpen], [wasOpen]) => {
    if (isOpen) {
      load();
    } else if (wasOpen) {
      // Clear so the next open doesn't briefly flash the previous
      // preview, and invalidate any in-flight request.
      preview.value = null;
      errorMessage.value = null;
      loadToken += 1;
    }
  },
  { immediate: true },
);

const drawerEl = ref<HTMLElement | null>(null);
useFocusTrap(drawerEl, toRef(props, 'open'));

// Tree state: each path → expanded boolean. SKILL.md defaults to
// open (the operator's primary check); helpers/references default
// to closed so the operator can scan the list first. The drawer
// must respect operator collapse-clicks, so we resolve via a
// computed default-by-path instead of the previous
// ``|| true`` (which prevented SKILL.md from ever collapsing).
const expanded = ref<Record<string, boolean>>({});

function isExpanded(path: string): boolean {
  if (path in expanded.value) return expanded.value[path];
  // Default: SKILL.md is open, everything else is closed.
  return path.endsWith('/SKILL.md');
}

function toggle(path: string) {
  expanded.value = { ...expanded.value, [path]: !isExpanded(path) };
}

// Group helper files by their first path segment so the tree
// renders ``scripts/``, ``references/``, ``assets/`` as folder
// headers above their contents.
function fileSegments(files: SkillPackageFile[]) {
  const groups: Record<string, SkillPackageFile[]> = {};
  for (const f of files) {
    const rel = f.path.replace(/^\.claude\/skills\/[^/]+\//, '');
    const seg = rel.split('/')[0];
    groups[seg] = groups[seg] || [];
    groups[seg].push(f);
  }
  return groups;
}

function fileLabel(file: SkillPackageFile): string {
  return file.path.replace(/^\.claude\/skills\/[^/]+\//, '');
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function onCreate() {
  if (preview.value) {
    emit('create', preview.value.config_hash);
  }
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit('close');
}

function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close');
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="preview-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="skill-preview-title"
      tabindex="-1"
      @click="onBackdropClick"
      @keydown="onEscape"
    >
      <aside
        ref="drawerEl"
        class="preview-drawer"
        tabindex="-1"
        @click.stop
      >
        <header class="preview-header">
          <div>
            <h3 id="skill-preview-title">Skill package preview</h3>
            <p class="preview-subtitle">
              These files will be written to
              <code>{{ preview?.skill_md_path?.replace(/\/SKILL\.md$/, '') ?? '.claude/skills/&lt;name&gt;' }}/</code>.
              Click any file to inspect contents before creating.
            </p>
          </div>
          <button
            type="button"
            class="preview-close"
            aria-label="Close preview"
            @click="emit('close')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div class="preview-body">
          <div v-if="loading" class="preview-state">Rendering preview…</div>
          <div v-else-if="errorMessage" class="preview-state preview-error">
            {{ errorMessage }}
          </div>
          <div v-else-if="preview" class="preview-tree">
            <!-- SKILL.md is always present, always shown first.
                 Default-open via ``isExpanded`` (which knows
                 SKILL.md special-cases to true) — NOT via
                 ``|| true`` which would force the file to stay
                 open and ignore the operator's collapse click. -->
            <details
              class="preview-file"
              :open="isExpanded(preview.skill_md_path)"
              @toggle.prevent="toggle(preview.skill_md_path)"
            >
              <summary class="preview-file-summary">
                <span class="preview-file-icon">📄</span>
                <code class="preview-file-name">SKILL.md</code>
                <span class="preview-file-size">
                  {{ formatBytes(preview.skill_md_content.length) }}
                </span>
              </summary>
              <pre class="preview-file-content">{{ preview.skill_md_content }}</pre>
            </details>

            <div
              v-for="(group, seg) in fileSegments(preview.files)"
              :key="seg"
              class="preview-folder"
            >
              <h4 class="preview-folder-name">📁 {{ seg }}/</h4>
              <details
                v-for="file in group"
                :key="file.path"
                class="preview-file preview-file-nested"
                :open="isExpanded(file.path)"
                @toggle.prevent="toggle(file.path)"
              >
                <summary class="preview-file-summary">
                  <span class="preview-file-icon">📄</span>
                  <code class="preview-file-name">
                    {{ fileLabel(file).split('/').slice(1).join('/') }}
                  </code>
                  <span class="preview-file-size">
                    {{ formatBytes(file.size_bytes) }}
                  </span>
                </summary>
                <pre class="preview-file-content">{{ file.content }}</pre>
              </details>
            </div>

            <div v-if="!preview.files.length" class="preview-empty-note">
              No helpers or references — this skill is SKILL.md only.
            </div>

            <div v-if="preview.warnings.length" class="preview-warnings">
              <h4 class="preview-warnings-heading">Warnings</h4>
              <ul>
                <li v-for="(w, i) in preview.warnings" :key="i">{{ w }}</li>
              </ul>
            </div>
          </div>
        </div>

        <footer class="preview-footer">
          <button
            type="button"
            class="btn btn-secondary"
            @click="emit('close')"
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="!preview || props.isFinalizing"
            @click="onCreate"
          >
            {{ props.isFinalizing ? 'Creating…' : 'Create skill package' }}
          </button>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 50;
  display: flex;
  justify-content: flex-end;
}
.preview-drawer {
  width: min(640px, 92vw);
  height: 100%;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.25);
  font-family: 'Geist', system-ui, sans-serif;
}
.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  gap: 12px;
}
.preview-header h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  color: var(--text-primary);
}
.preview-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.preview-subtitle code {
  font-size: 11px;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 3px;
}
.preview-close {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  width: 28px;
  height: 28px;
  border-radius: 4px;
  cursor: pointer;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
}
.preview-close svg { width: 16px; height: 16px; }
.preview-close:hover { color: var(--text-primary); background: var(--bg-tertiary); }

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.preview-state {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.preview-error { color: var(--accent-red, #ff6464); }

.preview-tree {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.preview-folder {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview-folder-name {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 8px 0 4px 0;
  font-weight: 600;
}
.preview-file {
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-tertiary);
  overflow: hidden;
}
.preview-file-nested { margin-left: 12px; }
.preview-file-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  list-style: none;
  font-size: 12px;
}
.preview-file-summary::-webkit-details-marker { display: none; }
.preview-file-icon { font-size: 13px; }
.preview-file-name {
  flex: 1;
  font-family: 'Geist Mono', monospace;
  color: var(--text-primary);
  background: transparent;
  padding: 0;
}
.preview-file-size {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: 'Geist Mono', monospace;
}
.preview-file-content {
  margin: 0;
  padding: 10px 12px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
}
.preview-empty-note {
  padding: 10px;
  color: var(--text-tertiary);
  font-style: italic;
  font-size: 12px;
}
.preview-warnings {
  border-left: 2px solid var(--accent-amber, #ffb454);
  padding-left: 10px;
  margin-top: 12px;
}
.preview-warnings-heading {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent-amber, #ffb454);
  margin: 0 0 4px 0;
}
.preview-warnings ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.preview-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-default);
}
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent-violet, #b48cff);
  color: #fff;
  border-color: transparent;
  font-weight: 600;
}
.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn-secondary:hover { background: var(--bg-primary); }
</style>
