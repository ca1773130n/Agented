<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { PromptSnippet, CreateSnippetRequest, UpdateSnippetRequest } from '../services/api';
import { promptSnippetApi, ApiError } from '../services/api';
import { useToast } from '../composables/useToast';

const showToast = useToast();

const snippets = ref<PromptSnippet[]>([]);
const isLoading = ref(true);

// Modal state
const showModal = ref(false);
const editingSnippet = ref<PromptSnippet | null>(null);
const formName = ref('');
const formContent = ref('');
const formDescription = ref('');
const isSaving = ref(false);

// Delete confirmation state
const showDeleteConfirm = ref(false);
const pendingDeleteId = ref<string | null>(null);
const pendingDeleteName = ref('');

async function loadSnippets() {
  isLoading.value = true;
  try {
    const data = await promptSnippetApi.list();
    snippets.value = data.snippets || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load snippets';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

function openCreateModal() {
  editingSnippet.value = null;
  formName.value = '';
  formContent.value = '';
  formDescription.value = '';
  showModal.value = true;
}

function openEditModal(snippet: PromptSnippet) {
  editingSnippet.value = snippet;
  formName.value = snippet.name;
  formContent.value = snippet.content;
  formDescription.value = snippet.description || '';
  showModal.value = true;
}

function closeModal() {
  showModal.value = false;
  editingSnippet.value = null;
}

async function saveSnippet() {
  if (!formName.value.trim() || !formContent.value.trim()) return;
  isSaving.value = true;
  try {
    if (editingSnippet.value) {
      const data: UpdateSnippetRequest = {
        name: formName.value.trim(),
        content: formContent.value,
        description: formDescription.value.trim() || undefined,
      };
      await promptSnippetApi.update(editingSnippet.value.id, data);
      showToast('Snippet updated', 'success');
    } else {
      const data: CreateSnippetRequest = {
        name: formName.value.trim(),
        content: formContent.value,
        description: formDescription.value.trim() || undefined,
      };
      await promptSnippetApi.create(data);
      showToast('Snippet created', 'success');
    }
    closeModal();
    await loadSnippets();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save snippet';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

function confirmDelete(snippet: PromptSnippet) {
  pendingDeleteId.value = snippet.id;
  pendingDeleteName.value = snippet.name;
  showDeleteConfirm.value = true;
}

async function executeDelete() {
  if (!pendingDeleteId.value) return;
  try {
    await promptSnippetApi.delete(pendingDeleteId.value);
    showToast('Snippet deleted', 'success');
    showDeleteConfirm.value = false;
    pendingDeleteId.value = null;
    await loadSnippets();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete snippet';
    showToast(message, 'error');
  }
}

function snippetRef(name: string): string {
  return '{{' + name + '}}';
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

onMounted(loadSnippets);
</script>

<template>
  <div class="snippets-page">
    <header class="page-header">
      <div class="header-left">
        <h1>Prompt Snippets</h1>
        <p class="page-subtitle">Reusable prompt fragments that can be included in any bot template</p>
      </div>
      <button class="create-btn" @click="openCreateModal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
          <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        Create Snippet
      </button>
    </header>

    <!-- Snippet List -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <span>Loading snippets...</span>
    </div>

    <div v-else-if="snippets.length === 0" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
          <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
      </div>
      <p>No snippets yet. Create your first reusable prompt fragment.</p>
      <button class="create-btn" @click="openCreateModal">Create Snippet</button>
    </div>

    <div v-else class="snippet-table-wrapper">
      <table class="snippet-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Content</th>
            <th>Description</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="snippet in snippets" :key="snippet.id">
            <td class="snippet-name">
              <code>{{ snippetRef(snippet.name) }}</code>
            </td>
            <td class="snippet-content">
              <code>{{ truncate(snippet.content, 80) }}</code>
            </td>
            <td class="snippet-description">
              {{ snippet.description || '-' }}
            </td>
            <td class="snippet-actions">
              <button class="action-btn edit-btn" title="Edit" @click="openEditModal(snippet)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
              <button class="action-btn delete-btn" title="Delete" @click="confirmDelete(snippet)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create/Edit Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>{{ editingSnippet ? 'Edit Snippet' : 'Create Snippet' }}</h2>
            <button class="modal-close" @click="closeModal">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="snippet-name">Name</label>
              <input
                id="snippet-name"
                v-model="formName"
                type="text"
                placeholder="my-snippet-name"
                pattern="[\w][\w-]*"
              />
              <span class="form-hint">Letters, numbers, underscores, hyphens. Used as <code>{{ snippetRef('name') }}</code> in prompts.</span>
            </div>
            <div class="form-group">
              <label for="snippet-content">Content</label>
              <textarea
                id="snippet-content"
                v-model="formContent"
                rows="8"
                placeholder="Enter the snippet content..."
                class="mono-textarea"
              ></textarea>
            </div>
            <div class="form-group">
              <label for="snippet-description">Description <span class="optional">(optional)</span></label>
              <input
                id="snippet-description"
                v-model="formDescription"
                type="text"
                placeholder="Brief description of what this snippet does"
              />
            </div>
          </div>
          <div class="modal-footer">
            <button class="cancel-btn" @click="closeModal">Cancel</button>
            <button
              class="save-btn"
              :disabled="!formName.trim() || !formContent.trim() || isSaving"
              @click="saveSnippet"
            >
              <template v-if="isSaving">
                <span class="spinner-sm"></span> Saving...
              </template>
              <template v-else>
                {{ editingSnippet ? 'Update' : 'Create' }}
              </template>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
        <div class="modal-content modal-sm">
          <div class="modal-header">
            <h2>Delete Snippet</h2>
            <button class="modal-close" @click="showDeleteConfirm = false">&times;</button>
          </div>
          <div class="modal-body">
            <p>Are you sure you want to delete <strong>{{ pendingDeleteName }}</strong>? Any prompts using <code>{{ snippetRef(pendingDeleteName) }}</code> will have unresolved references.</p>
          </div>
          <div class="modal-footer">
            <button class="cancel-btn" @click="showDeleteConfirm = false">Cancel</button>
            <button class="delete-confirm-btn" @click="executeDelete">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.snippets-page {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 2rem;
  gap: 1rem;
}

.header-left h1 {
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem;
}

.page-subtitle {
  color: var(--text-secondary);
  margin: 0;
  font-size: 0.9rem;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.2s;
}

.create-btn:hover {
  opacity: 0.9;
}

/* Snippet Table */
.snippet-table-wrapper {
  overflow-x: auto;
}

.snippet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.snippet-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-default);
}

.snippet-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  vertical-align: middle;
}

.snippet-table tbody tr:hover {
  background: var(--bg-secondary);
}

.snippet-name code {
  color: var(--accent-cyan);
  font-family: 'Geist Mono', monospace;
  font-size: 0.85rem;
}

.snippet-content code {
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
}

.snippet-description {
  color: var(--text-secondary);
}

.snippet-actions {
  display: flex;
  gap: 0.5rem;
}

.action-btn {
  background: none;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  padding: 4px 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: color 0.2s, border-color 0.2s;
  display: flex;
  align-items: center;
}

.edit-btn:hover {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.delete-btn:hover {
  color: var(--accent-crimson);
  border-color: var(--accent-crimson);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-sm {
  max-width: 420px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-subtle);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 1.25rem 1.5rem;
}

.modal-body p {
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-subtle);
}

.form-group {
  margin-bottom: 1rem;
}

.form-group label {
  display: block;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.35rem;
}

.form-group .optional {
  color: var(--text-tertiary);
  font-weight: 400;
}

.form-group input,
.form-group textarea {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--text-primary);
  font-family: 'Geist', sans-serif;
  font-size: 0.9rem;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.mono-textarea {
  font-family: 'Geist Mono', monospace !important;
  font-size: 0.85rem !important;
}

.form-hint {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.form-hint code {
  color: var(--accent-cyan);
  font-family: 'Geist Mono', monospace;
}

.cancel-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  cursor: pointer;
  transition: background 0.2s;
}

.cancel-btn:hover {
  background: var(--bg-elevated);
}

.save-btn {
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 6px;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  transition: opacity 0.2s;
}

.save-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.delete-confirm-btn {
  background: var(--accent-crimson);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.delete-confirm-btn:hover {
  opacity: 0.9;
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem;
  color: var(--text-secondary);
}

.empty-icon {
  color: var(--text-tertiary);
  margin-bottom: 0.5rem;
}

/* Spinners */
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.spinner-sm {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
