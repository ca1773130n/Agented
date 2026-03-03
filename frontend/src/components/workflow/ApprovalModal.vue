<script setup lang="ts">
/**
 * ApprovalModal -- Modal dialog for approving or rejecting a workflow approval gate.
 *
 * Shown when a workflow execution hits a pending_approval node. The user can
 * approve to continue the workflow or reject to abort downstream execution.
 */
import { ref } from 'vue'
import { workflowExecutionApi } from '../../services/api/workflows'

const props = defineProps<{
  visible: boolean
  executionId: string
  nodeId: string
  nodeLabel: string
}>()

const emit = defineEmits<{
  approve: []
  reject: []
  close: []
}>()

const comment = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

async function handleApprove() {
  isSubmitting.value = true
  errorMessage.value = null
  try {
    await workflowExecutionApi.approveNode(props.executionId, props.nodeId)
    emit('approve')
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to approve'
  } finally {
    isSubmitting.value = false
  }
}

async function handleReject() {
  isSubmitting.value = true
  errorMessage.value = null
  try {
    await workflowExecutionApi.rejectNode(props.executionId, props.nodeId)
    emit('reject')
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to reject'
  } finally {
    isSubmitting.value = false
  }
}

function handleClose() {
  comment.value = ''
  errorMessage.value = null
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      @click.self="handleClose"
      @keydown.escape="handleClose"
    >
      <div class="modal approval-modal">
        <div class="modal-header">
          <span class="modal-icon">&#x23F8;</span>
          <h2 class="modal-title">Approval Required</h2>
        </div>

        <div class="modal-body">
          <div class="node-info">
            <span class="node-info-label">Node:</span>
            <span class="node-info-value">{{ nodeLabel }}</span>
          </div>
          <div class="node-info">
            <span class="node-info-label">Execution:</span>
            <span class="node-info-value mono">{{ executionId }}</span>
          </div>

          <div class="comment-group">
            <label class="comment-label" for="approval-comment">Comment (optional)</label>
            <textarea
              id="approval-comment"
              v-model="comment"
              class="comment-input"
              placeholder="Add a note about this approval decision..."
              rows="3"
              :disabled="isSubmitting"
            />
          </div>

          <div v-if="errorMessage" class="error-message">
            {{ errorMessage }}
          </div>
        </div>

        <div class="modal-footer">
          <button
            class="btn btn-secondary"
            :disabled="isSubmitting"
            @click="handleClose"
          >
            Cancel
          </button>
          <button
            class="btn btn-reject"
            :disabled="isSubmitting"
            @click="handleReject"
          >
            Reject
          </button>
          <button
            class="btn btn-approve"
            :disabled="isSubmitting"
            @click="handleApprove"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.approval-modal {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 12px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 24px 0;
}

.modal-icon {
  font-size: 20px;
  color: #f59e0b;
}

.modal-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin: 0;
}

.modal-body {
  padding: 16px 24px;
}

.node-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.node-info-label {
  font-size: 12px;
  color: var(--text-tertiary, #606070);
  min-width: 70px;
}

.node-info-value {
  font-size: 13px;
  color: var(--text-primary, #f0f0f5);
  font-weight: 500;
}

.node-info-value.mono {
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
}

.comment-group {
  margin-top: 16px;
}

.comment-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #a0a0b0);
  margin-bottom: 6px;
}

.comment-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #f0f0f5);
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  min-height: 60px;
  box-sizing: border-box;
}

.comment-input:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.comment-input:disabled {
  opacity: 0.5;
}

.error-message {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  font-size: 12px;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 24px 20px;
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s, opacity 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary, #a0a0b0);
  border-color: var(--border-subtle, rgba(255, 255, 255, 0.06));
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-elevated, #222230);
  color: var(--text-primary, #f0f0f5);
}

.btn-approve {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.3);
}

.btn-approve:hover:not(:disabled) {
  background: #22c55e;
  color: #fff;
}

.btn-reject {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.2);
}

.btn-reject:hover:not(:disabled) {
  background: #ef4444;
  color: #fff;
}
</style>
