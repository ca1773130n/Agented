<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { AuditRecord } from '../../services/api';
import { auditApi, resolveApi, ApiError } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  auditHistory: AuditRecord[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'resolved'): void;
}>();

const resolveModalRef = ref<HTMLElement | null>(null);
const alwaysOpen = ref(true);
useFocusTrap(resolveModalRef, alwaysOpen);

const isLoading = ref(true);
const isResolving = ref(false);
const projectPaths = ref<string[]>([]);
const auditSummary = ref('');
const statusMessage = ref('');
const statusType = ref<'success' | 'error'>('success');
const showStatus = ref(false);

async function buildSummary() {
  isLoading.value = true;
  try {
    // Get latest audit per project
    const latestByProject: Record<string, AuditRecord> = {};
    for (const audit of props.auditHistory) {
      const existing = latestByProject[audit.project_path];
      if (!existing || audit.audit_date > existing.audit_date) {
        latestByProject[audit.project_path] = audit;
      }
    }

    const summary: string[] = [];
    const paths: string[] = [];

    for (const [path, audit] of Object.entries(latestByProject)) {
      if (audit.total_findings > 0) {
        paths.push(path);
        summary.push(`Project: ${path}`);
        summary.push(`  Critical: ${audit.critical}, High: ${audit.high}, Medium: ${audit.medium}, Low: ${audit.low}`);

        try {
          const detail = await auditApi.getDetail(audit.audit_id);
          for (const finding of (detail.findings || [])) {
            summary.push(`  - ${finding.package} (${finding.severity}): ${finding.installed_version || finding.current_version} -> ${finding.recommended_version || 'latest'}`);
          }
        } catch {
          // Ignore
        }
        summary.push('');
      }
    }

    projectPaths.value = paths;
    auditSummary.value = summary.join('\n');
  } catch {
    auditSummary.value = 'Unable to load findings summary';
  } finally {
    isLoading.value = false;
  }
}

async function runResolve() {
  if (!auditSummary.value || projectPaths.value.length === 0) {
    setStatus('No findings or projects to resolve', 'error');
    return;
  }

  isResolving.value = true;
  showStatus.value = false;

  try {
    await resolveApi.resolveIssues(auditSummary.value, projectPaths.value);
    setStatus(
      'Resolution process started. Claude is now working on fixing the issues. This may take several minutes. Run another security scan afterwards to verify fixes.',
      'success'
    );
    setTimeout(() => {
      emit('resolved');
    }, 5000);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to start resolution';
    setStatus(message, 'error');
    isResolving.value = false;
  }
}

function setStatus(message: string, type: 'success' | 'error') {
  statusMessage.value = message;
  statusType.value = type;
  showStatus.value = true;
}

onMounted(buildSummary);
</script>

<template>
  <div ref="resolveModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-resolve-issues" tabindex="-1" @click.self="emit('close')" @keydown.escape="emit('close')">
    <div class="modal">
      <div class="modal-header danger">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <path d="M12 9v4M12 17h.01"/>
          </svg>
        </div>
        <div>
          <h3 id="modal-title-resolve-issues">Warning: Edit Access Required</h3>
          <p class="modal-subtitle">Claude will modify your project files</p>
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div class="modal-body">
        <div class="warning-box">
          <div class="warning-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div class="warning-content">
            <p class="warning-title">This action will give Claude edit access to your project files.</p>
            <p class="warning-text">
              Claude will attempt to automatically fix security vulnerabilities by modifying
              your code. This includes updating dependencies, patching vulnerable code, and
              making other necessary changes.
            </p>
          </div>
        </div>

        <div class="info-section">
          <div class="info-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span>Projects to Modify</span>
          </div>
          <div class="info-content">
            <template v-if="isLoading">
              <div class="loading-inline">
                <div class="loading-spinner"></div>
                <span>Loading projects...</span>
              </div>
            </template>
            <template v-else-if="projectPaths.length > 0">
              <div v-for="path in projectPaths" :key="path" class="path-entry">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M9 18l6-6-6-6"/>
                </svg>
                {{ path }}
              </div>
            </template>
            <template v-else>
              <div class="empty-text">No projects with findings to resolve</div>
            </template>
          </div>
        </div>

        <div class="info-section">
          <div class="info-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <span>Issues Summary</span>
          </div>
          <div class="summary-content">
            <template v-if="isLoading">
              <div class="loading-inline">
                <div class="loading-spinner"></div>
                <span>Loading findings summary...</span>
              </div>
            </template>
            <template v-else>
              {{ auditSummary || 'Unable to load findings summary' }}
            </template>
          </div>
        </div>

        <div v-if="showStatus" class="status-message" :class="statusType">
          <svg v-if="statusType === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M15 9l-6 6M9 9l6 6"/>
          </svg>
          {{ statusMessage }}
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
        <button
          class="btn btn-danger"
          :disabled="isResolving || isLoading || projectPaths.length === 0"
          @click="runResolve"
        >
          <svg v-if="isResolving" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
          </svg>
          {{ isResolving ? 'Resolution Started' : 'I Understand, Resolve Issues' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>

@keyframes overlayFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  width: 90%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
  animation: modalSlideIn 0.3s ease;
  box-shadow: var(--shadow-lg);
}

@keyframes modalSlideIn {
  from { opacity: 0; transform: translateY(-20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-header.danger {
  background: linear-gradient(180deg, var(--accent-crimson-dim), transparent);
}

.modal-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-crimson-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent-crimson);
}

.modal-header h3 {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--accent-crimson);
  margin-bottom: 4px;
}

.modal-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.close-btn {
  margin-left: auto;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-tertiary);
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.warning-box {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--accent-crimson-dim);
  border: 1px solid rgba(255, 51, 102, 0.3);
  border-radius: 10px;
  margin-bottom: 20px;
}

.warning-icon {
  width: 40px;
  height: 40px;
  background: rgba(255, 51, 102, 0.2);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.warning-icon svg {
  width: 20px;
  height: 20px;
  color: var(--accent-crimson);
}

.warning-content {
  flex: 1;
}

.warning-title {
  color: var(--accent-crimson);
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 0.9rem;
}

.warning-text {
  color: rgba(255, 51, 102, 0.8);
  font-size: 0.85rem;
  line-height: 1.5;
}

.info-section {
  margin-bottom: 20px;
}

.info-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.info-header svg {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
}

.info-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px 16px;
}

.path-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.path-entry:last-child {
  border-bottom: none;
}

.path-entry svg {
  width: 12px;
  height: 12px;
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.loading-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  padding: 8px 0;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.empty-text {
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 8px 0;
}

.summary-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px 16px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}

.status-message {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  font-size: 0.875rem;
  line-height: 1.5;
}

.status-message svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 1px;
}

.status-message.success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
  border: 1px solid rgba(0, 255, 136, 0.2);
}

.status-message.error {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  border: 1px solid rgba(255, 51, 102, 0.2);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-danger {
  background: var(--accent-crimson);
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #e6294f;
}

.spinner {
  animation: spin 1s linear infinite;
}
</style>
