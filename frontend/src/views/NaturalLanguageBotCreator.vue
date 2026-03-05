<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const description = ref('');
const isGenerating = ref(false);
const isSaving = ref(false);
const generatedConfig = ref<string | null>(null);

const canGenerate = computed(() => description.value.trim().length > 20);


async function handleGenerate() {
  if (!canGenerate.value) return;
  isGenerating.value = true;
  try {
    // Simulate generation with a timeout
    await new Promise(resolve => setTimeout(resolve, 1200));
    const words = description.value.toLowerCase();
    const isScheduled = words.includes('daily') || words.includes('weekly') || words.includes('schedule');
    const isGitHub = words.includes('pr') || words.includes('pull request') || words.includes('github');

    const config = {
      name: description.value.split(' ').slice(0, 4).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') + ' Bot',
      prompt_template: `You are an AI assistant. ${description.value}\n\nContext:\n- Repository paths: {paths}\n- Trigger payload: {payload}\n\nPlease analyze and respond accordingly.`,
      trigger: {
        type: isGitHub ? 'github' : isScheduled ? 'schedule' : 'webhook',
        source: isGitHub ? 'pull_request' : 'push',
      },
      schedule: isScheduled ? '0 9 * * 1' : null,
      model: 'claude-opus-4-5',
      timeout: 300,
      tags: words.includes('security') ? ['security'] : words.includes('review') ? ['review'] : ['automation'],
    };
    generatedConfig.value = JSON.stringify(config, null, 2);
    showToast('Bot configuration generated', 'success');
  } catch {
    showToast('Failed to generate configuration', 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function handleSaveDraft() {
  if (!generatedConfig.value) return;
  isSaving.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 600));
    showToast('Bot saved as draft', 'success');
    router.push({ name: 'bots' });
  } catch {
    showToast('Failed to save draft', 'error');
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <div class="nlbot-creator">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Natural Language Creator' },
    ]" />

    <PageHeader
      title="Natural Language Bot Creator"
      subtitle="Describe what you want a bot to do in plain English and let AI generate the configuration."
    />

    <div class="creator-layout">
      <div class="card input-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            Describe Your Bot
          </h3>
        </div>
        <div class="card-body">
          <label class="field-label">What should this bot do?</label>
          <textarea
            v-model="description"
            class="text-area"
            placeholder="e.g. Every time a pull request is opened, review the changed files for security vulnerabilities and comment with findings. Focus on SQL injection, XSS, and authentication issues."
            rows="6"
          />
          <p class="hint">Be specific about triggers, actions, and expected output. Minimum 20 characters.</p>

          <div class="example-pills">
            <span class="pill-label">Examples:</span>
            <button
              class="pill"
              @click="description = 'Every Monday morning, scan the codebase for dependency vulnerabilities and create a summary report'"
            >Weekly security scan</button>
            <button
              class="pill"
              @click="description = 'When a PR is opened, review the code changes for performance issues and suggest optimizations'"
            >PR performance review</button>
            <button
              class="pill"
              @click="description = 'After each deployment webhook, run smoke tests and notify the team of results'"
            >Post-deploy tests</button>
          </div>

          <div class="actions">
            <button
              class="btn btn-primary"
              :disabled="!canGenerate || isGenerating"
              @click="handleGenerate"
            >
              <svg v-if="isGenerating" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              {{ isGenerating ? 'Generating...' : 'Generate Bot' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="generatedConfig" class="card output-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            Generated Configuration
          </h3>
          <span class="badge-success">Ready</span>
        </div>
        <div class="card-body">
          <label class="field-label">Review and edit the generated config:</label>
          <textarea
            v-model="generatedConfig"
            class="text-area code-area"
            rows="18"
            spellcheck="false"
          />
          <div class="actions">
            <button class="btn btn-secondary" @click="generatedConfig = null">
              Clear
            </button>
            <button
              class="btn btn-primary"
              :disabled="isSaving"
              @click="handleSaveDraft"
            >
              <svg v-if="isSaving" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              {{ isSaving ? 'Saving...' : 'Save as Draft' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nlbot-creator {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.creator-layout {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg {
  color: var(--accent-cyan);
}

.card-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.text-area {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  line-height: 1.6;
  resize: vertical;
  font-family: inherit;
  box-sizing: border-box;
  transition: border-color 0.15s;
}

.text-area:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.code-area {
  font-family: 'Geist Mono', 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}

.hint {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin: 0;
}

.example-pills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pill-label {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.pill {
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 20px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.15s;
}

.pill:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.85;
}

.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--text-primary);
}

.badge-success {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
