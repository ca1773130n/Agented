<script setup lang="ts">
import { ref, watch, computed, toRef, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { utilityApi } from '../../services/api';
import type { DirectoryEntry } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  modelValue: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
  (e: 'close'): void;
}>();

const { t } = useI18n();
const modalRef = ref<HTMLElement | null>(null);
const isOpen = toRef(props, 'visible');
useFocusTrap(modalRef, isOpen);

// State
const currentPath = ref('');
const parentPath = ref<string | null>(null);
const entries = ref<DirectoryEntry[]>([]);
const loading = ref(false);
const error = ref('');

// New folder creation
const creatingFolder = ref(false);
const newFolderName = ref('');
const newFolderError = ref('');
const newFolderInputRef = ref<HTMLInputElement | null>(null);

// Breadcrumb segments from current path
const breadcrumbs = computed(() => {
  if (!currentPath.value) return [];
  const parts = currentPath.value.split('/').filter(Boolean);
  const segments: Array<{ name: string; path: string }> = [];
  let accumulated = '';
  for (const part of parts) {
    accumulated += '/' + part;
    segments.push({ name: part, path: accumulated });
  }
  return segments;
});

async function loadDirectory(path?: string) {
  loading.value = true;
  error.value = '';
  try {
    const data = await utilityApi.browseDirectory(path);
    currentPath.value = data.current_path;
    parentPath.value = data.parent_path;
    entries.value = data.entries;
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to load directory';
    error.value = message;
    entries.value = [];
  } finally {
    loading.value = false;
  }
}

function navigateTo(path: string) {
  loadDirectory(path);
}

function navigateUp() {
  if (parentPath.value) {
    loadDirectory(parentPath.value);
  }
}

function selectCurrent() {
  emit('update:modelValue', currentPath.value);
  emit('close');
}

function cancel() {
  emit('close');
}

function startCreateFolder() {
  creatingFolder.value = true;
  newFolderName.value = '';
  newFolderError.value = '';
  nextTick(() => {
    newFolderInputRef.value?.focus();
  });
}

function cancelCreateFolder() {
  creatingFolder.value = false;
  newFolderName.value = '';
  newFolderError.value = '';
}

async function confirmCreateFolder() {
  const name = newFolderName.value.trim();
  if (!name) {
    newFolderError.value = 'Folder name is required';
    return;
  }
  if (name.includes('/') || name.includes('\\')) {
    newFolderError.value = 'Folder name cannot contain path separators';
    return;
  }

  const fullPath = currentPath.value.endsWith('/')
    ? currentPath.value + name
    : currentPath.value + '/' + name;

  try {
    await utilityApi.createDirectory(fullPath);
    creatingFolder.value = false;
    newFolderName.value = '';
    newFolderError.value = '';
    // Reload current directory to show the new folder
    await loadDirectory(currentPath.value);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to create folder';
    newFolderError.value = message;
  }
}

// Load directory when modal becomes visible
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      creatingFolder.value = false;
      newFolderName.value = '';
      newFolderError.value = '';
      // Start at modelValue if set, otherwise default (home dir)
      const startPath = props.modelValue || undefined;
      loadDirectory(startPath);
    }
  },
);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="modalRef"
      class="modal-overlay dir-browser-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Browse directories"
      tabindex="-1"
      @click.self="cancel"
      @keydown.escape="cancel"
    >
      <div class="modal dir-browser-modal">
        <!-- Header -->
        <div class="dir-browser-header">
          <h2 class="dir-browser-title">{{ t('directoryBrowser.title') }}</h2>
          <button class="dir-browser-close" aria-label="Close" @click="cancel">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </button>
        </div>

        <!-- Breadcrumbs -->
        <div class="dir-browser-breadcrumbs">
          <button
            class="breadcrumb-segment breadcrumb-root"
            @click="navigateTo('/')"
            title="Root"
          >
            /
          </button>
          <template v-for="(crumb, idx) in breadcrumbs" :key="crumb.path">
            <span class="breadcrumb-sep">/</span>
            <button
              :class="['breadcrumb-segment', { 'breadcrumb-current': idx === breadcrumbs.length - 1 }]"
              @click="navigateTo(crumb.path)"
            >
              {{ crumb.name }}
            </button>
          </template>
        </div>

        <!-- Content area -->
        <div class="dir-browser-content">
          <!-- Loading -->
          <div v-if="loading" class="dir-browser-loading">
            <div class="dir-spinner"></div>
            <span>{{ t('common.loading') }}</span>
          </div>

          <!-- Error -->
          <div v-else-if="error" class="dir-browser-error">
            <span class="dir-error-icon">!</span>
            <span>{{ error }}</span>
          </div>

          <!-- Directory listing -->
          <div v-else class="dir-browser-list">
            <!-- Go up entry -->
            <button
              v-if="parentPath"
              class="dir-entry dir-entry-up"
              @click="navigateUp"
            >
              <svg class="dir-entry-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 12V4M8 4L4 8M8 4L12 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span class="dir-entry-name">..</span>
            </button>

            <!-- Directory entries -->
            <button
              v-for="entry in entries"
              :key="entry.path"
              class="dir-entry"
              @click="navigateTo(entry.path)"
            >
              <svg class="dir-entry-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M1.5 3.5C1.5 2.94772 1.94772 2.5 2.5 2.5H6L7.5 4.5H13.5C14.0523 4.5 14.5 4.94772 14.5 5.5V12.5C14.5 13.0523 14.0523 13.5 13.5 13.5H2.5C1.94772 13.5 1.5 13.0523 1.5 12.5V3.5Z" stroke="currentColor" stroke-width="1.2"/>
              </svg>
              <span class="dir-entry-name">{{ entry.name }}</span>
            </button>

            <!-- Empty state -->
            <div v-if="entries.length === 0 && !parentPath" class="dir-browser-empty">
              {{ t('directoryBrowser.emptyDir') }}
            </div>
            <div v-else-if="entries.length === 0 && parentPath" class="dir-browser-empty">
              {{ t('directoryBrowser.emptyDir') }}
            </div>
          </div>
        </div>

        <!-- New folder creation -->
        <div v-if="creatingFolder" class="dir-browser-new-folder">
          <div class="new-folder-row">
            <input
              ref="newFolderInputRef"
              v-model="newFolderName"
              type="text"
              class="new-folder-input"
              :placeholder="t('directoryBrowser.enterFolderName')"
              @keydown.enter="confirmCreateFolder"
              @keydown.escape="cancelCreateFolder"
            />
            <button class="btn btn-sm btn-primary" @click="confirmCreateFolder">{{ t('directoryBrowser.createFolder') }}</button>
            <button class="btn btn-sm btn-ghost" @click="cancelCreateFolder">{{ t('common.cancel') }}</button>
          </div>
          <p v-if="newFolderError" class="new-folder-error">{{ newFolderError }}</p>
        </div>

        <!-- Footer -->
        <div class="dir-browser-footer">
          <button
            v-if="!creatingFolder"
            class="btn btn-ghost btn-sm"
            @click="startCreateFolder"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style="margin-right: 4px">
              <path d="M7 2V12M2 7H12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            {{ t('directoryBrowser.newFolder') }}
          </button>
          <span v-else></span>
          <div class="dir-browser-actions">
            <button class="btn btn-secondary btn-sm" @click="cancel">{{ t('common.cancel') }}</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!currentPath"
              @click="selectCurrent"
            >
              {{ t('directoryBrowser.selectThis') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dir-browser-overlay {
  z-index: var(--z-tour-progress, 10004) !important;
}

.dir-browser-modal {
  max-width: 560px;
  width: 90%;
  padding: 0;
  display: flex;
  flex-direction: column;
  max-height: 70vh;
}

.dir-browser-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border-default);
}

.dir-browser-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin: 0;
}

.dir-browser-close {
  background: none;
  border: none;
  color: var(--text-tertiary, #666);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s;
}

.dir-browser-close:hover {
  color: var(--text-primary, #f0f0f5);
}

/* Breadcrumbs */
.dir-browser-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 10px 20px;
  background: var(--bg-tertiary, #1a1a24);
  font-size: 0.8rem;
  overflow-x: auto;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-default);
}

.breadcrumb-segment {
  background: none;
  border: none;
  color: var(--text-secondary, #888);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 0.8rem;
  transition: color 0.15s, background 0.15s;
  font-family: var(--font-mono, 'SF Mono', monospace);
}

.breadcrumb-segment:hover {
  color: var(--accent-cyan, #00d4ff);
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
}

.breadcrumb-current {
  color: var(--text-primary, #f0f0f5);
  font-weight: 500;
}

.breadcrumb-sep {
  color: var(--text-tertiary, #444);
  font-size: 0.8rem;
  user-select: none;
}

/* Content area */
.dir-browser-content {
  flex: 1;
  overflow-y: auto;
  min-height: 200px;
  max-height: 350px;
}

.dir-browser-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  gap: 0.75rem;
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
}

.dir-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  animation: dir-spin 0.8s linear infinite;
}

@keyframes dir-spin {
  to { transform: rotate(360deg); }
}

.dir-browser-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem 20px;
  color: var(--accent-crimson, #ff4081);
  font-size: 0.85rem;
}

.dir-error-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(255, 64, 129, 0.15);
  color: var(--accent-crimson, #ff4081);
  font-size: 0.7rem;
  font-weight: 700;
  flex-shrink: 0;
}

/* Directory listing */
.dir-browser-list {
  display: flex;
  flex-direction: column;
}

.dir-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 20px;
  background: none;
  border: none;
  color: var(--text-primary, #f0f0f5);
  cursor: pointer;
  font-size: 0.85rem;
  text-align: left;
  transition: background 0.12s;
  width: 100%;
}

.dir-entry:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.dir-entry-up {
  color: var(--text-secondary, #888);
  border-bottom: 1px solid var(--border-default);
}

.dir-entry-icon {
  flex-shrink: 0;
  color: var(--accent-cyan, #00d4ff);
  opacity: 0.7;
}

.dir-entry-up .dir-entry-icon {
  color: var(--text-tertiary, #666);
}

.dir-entry-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dir-browser-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2.5rem 20px;
  color: var(--text-tertiary, #666);
  font-size: 0.85rem;
}

/* New folder creation */
.dir-browser-new-folder {
  padding: 10px 20px;
  border-top: 1px solid var(--border-default);
}

.new-folder-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.new-folder-input {
  flex: 1;
  padding: 6px 10px;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 5px;
  color: var(--text-primary, #f0f0f5);
  font-size: 0.85rem;
  outline: none;
  transition: border-color 0.15s;
}

.new-folder-input:focus {
  border-color: var(--accent-cyan, #00d4ff);
}

.new-folder-error {
  color: var(--accent-crimson, #ff4081);
  font-size: 0.75rem;
  margin-top: 4px;
  margin-bottom: 0;
}

/* Footer */
.dir-browser-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border-default);
}

.dir-browser-actions {
  display: flex;
  gap: 8px;
}

/* Button size modifier */
.btn-sm {
  padding: 6px 12px;
  font-size: 0.8rem;
}

.btn-ghost {
  background: none;
  border: 1px solid transparent;
  color: var(--text-secondary, #888);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  transition: color 0.15s;
}

.btn-ghost:hover {
  color: var(--text-primary, #f0f0f5);
}
</style>
