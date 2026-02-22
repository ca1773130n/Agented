<script setup lang="ts">
import { ref, computed } from 'vue';
import type { ProductDecision } from '../../services/api';
import { productApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  decisions: ProductDecision[];
  productId: string;
}>();

const emit = defineEmits<{
  (e: 'refresh'): void;
}>();

const showToast = useToast();

// Filter state
const statusFilter = ref('all');

const filteredDecisions = computed(() => {
  if (statusFilter.value === 'all') return props.decisions;
  return props.decisions.filter(d => d.status === statusFilter.value);
});

// Modal state
const showModal = ref(false);
const modalTitle = ref('');
const modalDescription = ref('');
const modalRationale = ref('');
const modalDecisionType = ref('technical');
const modalTags = ref('');
const isSubmitting = ref(false);
const modalOverlay = ref<HTMLElement | null>(null);
useFocusTrap(modalOverlay, showModal);

function openAddModal() {
  modalTitle.value = '';
  modalDescription.value = '';
  modalRationale.value = '';
  modalDecisionType.value = 'technical';
  modalTags.value = '';
  isSubmitting.value = false;
  showModal.value = true;
}

async function submitDecision() {
  if (!modalTitle.value.trim()) return;
  isSubmitting.value = true;
  try {
    const tags = modalTags.value.trim()
      ? modalTags.value.split(',').map(t => t.trim()).filter(Boolean)
      : undefined;
    await productApi.createDecision(props.productId, {
      title: modalTitle.value.trim(),
      description: modalDescription.value.trim() || undefined,
      rationale: modalRationale.value.trim() || undefined,
      decision_type: modalDecisionType.value,
      tags,
    });
    showToast('Decision created', 'success');
    showModal.value = false;
    emit('refresh');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create decision';
    showToast(message, 'error');
  } finally {
    isSubmitting.value = false;
  }
}

async function updateStatus(decision: ProductDecision, newStatus: string) {
  try {
    await productApi.updateDecision(props.productId, decision.id, { status: newStatus });
    showToast('Status updated', 'success');
    emit('refresh');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update status';
    showToast(message, 'error');
  }
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'proposed': return 'badge-proposed';
    case 'approved': return 'badge-approved';
    case 'rejected': return 'badge-rejected';
    case 'superseded': return 'badge-superseded';
    default: return 'badge-proposed';
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function parseTags(tagsJson?: string): string[] {
  if (!tagsJson) return [];
  try {
    const parsed = JSON.parse(tagsJson);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Decision Log</h3>
        <span class="card-count">{{ filteredDecisions.length }}</span>
      </div>
      <div class="header-actions">
        <select v-model="statusFilter" class="filter-select">
          <option value="all">All</option>
          <option value="proposed">Proposed</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="superseded">Superseded</option>
        </select>
        <button class="add-btn" @click="openAddModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Add Decision
        </button>
      </div>
    </div>

    <div v-if="filteredDecisions.length === 0" class="empty-state">
      <p>No decisions recorded yet</p>
    </div>

    <div v-else class="decision-list">
      <div v-for="decision in filteredDecisions" :key="decision.id" class="decision-row">
        <div class="decision-main">
          <div class="decision-title-row">
            <span class="decision-title">{{ decision.title }}</span>
            <select
              class="status-select"
              :class="getStatusBadgeClass(decision.status)"
              :value="decision.status"
              @change="updateStatus(decision, ($event.target as HTMLSelectElement).value)"
            >
              <option value="proposed">Proposed</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="superseded">Superseded</option>
            </select>
          </div>
          <p v-if="decision.rationale" class="decision-rationale">
            {{ truncate(decision.rationale, 120) }}
          </p>
          <div class="decision-meta">
            <span v-if="decision.decided_by" class="meta-item">by {{ decision.decided_by }}</span>
            <span v-if="decision.decided_at" class="meta-item">{{ formatDate(decision.decided_at) }}</span>
            <span class="meta-item type-badge">{{ decision.decision_type }}</span>
            <span v-for="tag in parseTags(decision.tags_json)" :key="tag" class="tag-pill">{{ tag }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Decision Modal -->
    <div v-if="showModal" ref="modalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-decision" tabindex="-1" @click.self="showModal = false" @keydown.escape="showModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3 id="modal-title-add-decision">Add Decision</h3>
          <button class="modal-close" @click="showModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">Title <span class="required">*</span></label>
            <input v-model="modalTitle" type="text" class="form-input" placeholder="Decision title..." />
          </div>
          <div class="form-group">
            <label class="form-label">Description</label>
            <textarea v-model="modalDescription" class="form-textarea" placeholder="What is this decision about?" rows="3"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">Rationale</label>
            <textarea v-model="modalRationale" class="form-textarea" placeholder="Why this decision was made..." rows="3"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">Type</label>
            <select v-model="modalDecisionType" class="form-input">
              <option value="technical">Technical</option>
              <option value="strategic">Strategic</option>
              <option value="tactical">Tactical</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Tags</label>
            <input v-model="modalTags" type="text" class="form-input" placeholder="Comma-separated tags..." />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showModal = false">Cancel</button>
          <button class="btn btn-primary" :disabled="!modalTitle.trim() || isSubmitting" @click="submitDecision">
            <span v-if="isSubmitting">Creating...</span>
            <span v-else>Create Decision</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
  appearance: auto;
}

.filter-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.add-btn svg {
  width: 14px;
  height: 14px;
}

.add-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.empty-state p {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.decision-list {
  display: flex;
  flex-direction: column;
}

.decision-row {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.decision-row:last-child {
  border-bottom: none;
}

.decision-row:hover {
  background: rgba(255, 255, 255, 0.02);
}

.decision-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.decision-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.decision-title {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

.status-select {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  border: none;
  cursor: pointer;
  appearance: auto;
}

.badge-proposed {
  background: rgba(0, 136, 255, 0.2);
  color: #0088ff;
}

.badge-approved {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.badge-rejected {
  background: rgba(255, 64, 129, 0.2);
  color: #ff4081;
}

.badge-superseded {
  background: rgba(128, 128, 128, 0.2);
  color: #888;
}

.decision-rationale {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.decision-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 0.7rem;
  color: var(--text-tertiary);
}

.type-badge {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.tag-pill {
  font-size: 0.65rem;
  padding: 2px 8px;
  background: rgba(136, 85, 255, 0.15);
  color: #8855ff;
  border-radius: 10px;
  font-weight: 500;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 20px 0;
}

.modal-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 0 20px 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-label .required {
  color: var(--accent-crimson, #ff4081);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: inherit;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.btn {
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--accent-cyan, #00d4ff);
  color: var(--bg-primary, #0a0a14);
  font-weight: 600;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}
</style>
