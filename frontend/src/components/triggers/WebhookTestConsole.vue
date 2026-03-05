<script setup lang="ts">
import { ref, computed } from 'vue';
import type { PreviewPromptFullResponse } from '../../services/api';
import { triggerApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  triggerId: string;
}>();

const showToast = useToast();

const defaultPayload = JSON.stringify(
  {
    message: 'Test webhook message',
    paths: '/path/to/project',
    event: {},
  },
  null,
  2
);

const payloadText = ref(defaultPayload);
const previewResult = ref<PreviewPromptFullResponse | null>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

const isValidJson = computed(() => {
  try {
    JSON.parse(payloadText.value);
    return true;
  } catch {
    return false;
  }
});

async function runPreview() {
  if (!isValidJson.value) return;
  isLoading.value = true;
  error.value = null;
  previewResult.value = null;
  try {
    const payload = JSON.parse(payloadText.value);
    previewResult.value = await triggerApi.previewPromptFull(props.triggerId, payload);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Failed to preview prompt';
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}
</script>

<template>
  <div class="test-console">
    <div class="section-header">
      <h3>Webhook Payload Test Console</h3>
    </div>

    <div class="dry-run-notice">
      This is a dry-run preview. No bot execution will be triggered.
    </div>

    <div class="console-layout">
      <!-- Left panel: JSON editor -->
      <div class="panel editor-panel">
        <div class="panel-header">
          <span class="panel-title">Payload</span>
          <span class="json-indicator" :class="isValidJson ? 'valid' : 'invalid'">
            {{ isValidJson ? 'Valid JSON' : 'Invalid JSON' }}
          </span>
        </div>
        <textarea
          v-model="payloadText"
          class="json-editor"
          spellcheck="false"
          placeholder="Enter JSON payload..."
        ></textarea>
        <div class="editor-actions">
          <button
            class="preview-btn"
            :disabled="!isValidJson || isLoading"
            @click="runPreview"
          >
            {{ isLoading ? 'Previewing...' : 'Preview' }}
          </button>
        </div>
      </div>

      <!-- Right panel: Preview results -->
      <div class="panel results-panel">
        <div class="panel-header">
          <span class="panel-title">Preview Results</span>
        </div>

        <div v-if="isLoading" class="loading-state">
          <span class="spinner"></span>
          Generating preview...
        </div>

        <div v-else-if="error" class="error-state">
          <p>{{ error }}</p>
        </div>

        <div v-else-if="!previewResult" class="empty-results">
          <p>Click "Preview" to see the rendered prompt and CLI command.</p>
        </div>

        <div v-else class="results-content">
          <!-- Warnings -->
          <div v-if="previewResult.unresolved_placeholders.length > 0" class="warning-box">
            <span class="warning-icon">&#9888;</span>
            <div>
              <strong>Unresolved Placeholders</strong>
              <ul>
                <li v-for="p in previewResult.unresolved_placeholders" :key="p">{{ p }}</li>
              </ul>
            </div>
          </div>

          <div v-if="previewResult.unresolved_snippets.length > 0" class="warning-box">
            <span class="warning-icon">&#9888;</span>
            <div>
              <strong>Unresolved Snippets</strong>
              <ul>
                <li v-for="s in previewResult.unresolved_snippets" :key="s">{{ s }}</li>
              </ul>
            </div>
          </div>

          <!-- Backend info -->
          <div class="result-section">
            <span class="result-label">Backend</span>
            <div class="backend-info">
              <span class="meta-pill">{{ previewResult.backend_type }}</span>
              <span v-if="previewResult.model" class="meta-pill model">{{ previewResult.model }}</span>
            </div>
          </div>

          <!-- Rendered prompt -->
          <div class="result-section">
            <span class="result-label">Rendered Prompt</span>
            <pre class="code-block prompt-block">{{ previewResult.rendered_prompt }}</pre>
          </div>

          <!-- CLI Command -->
          <div class="result-section">
            <span class="result-label">CLI Command</span>
            <pre class="code-block cli-block">{{ previewResult.cli_command }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.test-console {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.dry-run-notice {
  padding: 10px 14px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border: 1px solid var(--accent-cyan);
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  opacity: 0.9;
}

.console-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .console-layout {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-secondary);
}

.panel-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.json-indicator {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.json-indicator.valid {
  color: var(--accent-emerald);
  background: var(--accent-emerald-dim);
}

.json-indicator.invalid {
  color: var(--accent-crimson);
  background: var(--accent-crimson-dim);
}

.json-editor {
  flex: 1;
  min-height: 200px;
  padding: 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: none;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
}

.json-editor::placeholder {
  color: var(--text-muted);
}

.editor-actions {
  padding: 10px 14px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  justify-content: flex-end;
}

.preview-btn {
  padding: 8px 20px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-violet));
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 600;
  transition: all 0.15s ease;
}

.preview-btn:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-cyan);
  transform: translateY(-1px);
}

.preview-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 14px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state {
  padding: 24px 14px;
  color: var(--accent-crimson);
  font-size: 0.85rem;
}

.empty-results {
  padding: 24px 14px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.results-content {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
}

.warning-box {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  background: var(--accent-amber-dim);
  border: 1px solid var(--accent-amber);
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--accent-amber);
}

.warning-icon {
  font-size: 1.1rem;
  flex-shrink: 0;
}

.warning-box ul {
  margin: 4px 0 0 16px;
  padding: 0;
}

.warning-box li {
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

.result-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.result-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.backend-info {
  display: flex;
  gap: 8px;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.meta-pill.model {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.code-block {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.6;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  color: var(--text-secondary);
}

.prompt-block {
  max-height: 200px;
  overflow-y: auto;
}

.cli-block {
  color: var(--accent-emerald);
}
</style>
