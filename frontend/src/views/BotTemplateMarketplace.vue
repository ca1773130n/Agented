<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { BotTemplate } from '../services/api';
import { botTemplateApi, triggerApi, ApiError } from '../services/api';
import { useToast } from '../composables/useToast';
import { API_BASE, getApiKey } from '../services/api/client';

const showToast = useToast();

// Template gallery state
const templates = ref<BotTemplate[]>([]);
const isLoading = ref(true);
const deployingId = ref<string | null>(null);

// NL Bot Creator state
const nlDescription = ref('');
const isGenerating = ref(false);
const streamOutput = ref('');
const generatedConfig = ref<Record<string, unknown> | null>(null);
const isDeployingGenerated = ref(false);

const categoryIcons: Record<string, string> = {
  'code-review': 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
  'security': 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z',
  'maintenance': 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z',
  'documentation': 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  'testing': 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
};

const categoryColors: Record<string, string> = {
  'code-review': 'var(--accent-cyan)',
  'security': 'var(--accent-crimson)',
  'maintenance': 'var(--accent-amber)',
  'documentation': 'var(--accent-violet)',
  'testing': 'var(--accent-emerald)',
};

function getCategoryIcon(category: string): string {
  return categoryIcons[category] || categoryIcons['maintenance'];
}

function getCategoryColor(category: string): string {
  return categoryColors[category] || 'var(--accent-cyan)';
}

async function loadTemplates() {
  isLoading.value = true;
  try {
    const data = await botTemplateApi.list();
    templates.value = data.templates || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load templates';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function deployTemplate(template: BotTemplate) {
  deployingId.value = template.id;
  try {
    const result = await botTemplateApi.deploy(template.id);
    showToast(`Deployed "${result.trigger_name}" successfully`, 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to deploy template';
    showToast(message, 'error');
  } finally {
    deployingId.value = null;
  }
}

async function generateFromDescription() {
  if (nlDescription.value.length < 10) return;
  isGenerating.value = true;
  streamOutput.value = '';
  generatedConfig.value = null;

  try {
    const apiKey = getApiKey();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['X-API-Key'] = apiKey;

    const response = await fetch(`${API_BASE}/admin/triggers/generate/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ description: nlDescription.value }),
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.error || `HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'chunk' && parsed.text) {
              streamOutput.value += parsed.text;
            } else if (parsed.type === 'progress' && parsed.data) {
              // Progress updates with partial parsing
              streamOutput.value = typeof parsed.data === 'string' ? parsed.data : JSON.stringify(parsed.data, null, 2);
            } else if (parsed.type === 'complete' && parsed.result) {
              generatedConfig.value = parsed.result;
              streamOutput.value = JSON.stringify(parsed.result, null, 2);
            } else if (parsed.type === 'error') {
              showToast(parsed.message || 'Generation failed', 'error');
            }
          } catch {
            // Non-JSON data line, append as text
            if (data.trim()) streamOutput.value += data;
          }
        }
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Generation failed';
    showToast(message, 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function deployGeneratedBot() {
  if (!generatedConfig.value) return;
  isDeployingGenerated.value = true;
  try {
    const config = generatedConfig.value as Record<string, string>;
    await triggerApi.create({
      name: config.name || 'Generated Bot',
      prompt_template: config.prompt_template || '',
      backend_type: (config.backend_type as 'claude' | 'opencode') || 'claude',
      trigger_source: (config.trigger_source as 'webhook' | 'github' | 'manual' | 'scheduled') || 'webhook',
      model: config.model,
      schedule_type: config.schedule_type,
      schedule_time: config.schedule_time,
      schedule_day: config.schedule_day ? Number(config.schedule_day) : undefined,
      schedule_timezone: config.schedule_timezone,
    });
    showToast(`Bot "${config.name || 'Generated Bot'}" created successfully`, 'success');
    generatedConfig.value = null;
    streamOutput.value = '';
    nlDescription.value = '';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create bot';
    showToast(message, 'error');
  } finally {
    isDeployingGenerated.value = false;
  }
}

onMounted(loadTemplates);
</script>

<template>
  <div class="marketplace-page">
    <header class="page-header">
      <h1>Bot Templates</h1>
      <p class="page-subtitle">Deploy pre-built bot configurations or create your own with natural language</p>
    </header>

    <!-- Template Gallery -->
    <section class="template-gallery">
      <div v-if="isLoading" class="loading-state">
        <div class="spinner"></div>
        <span>Loading templates...</span>
      </div>

      <div v-else-if="templates.length === 0" class="empty-state">
        <p>No templates available yet.</p>
      </div>

      <div v-else class="template-grid">
        <div
          v-for="template in templates"
          :key="template.id"
          class="template-card"
        >
          <div class="card-header">
            <div class="card-icon" :style="{ color: getCategoryColor(template.category) }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path :d="getCategoryIcon(template.category)" />
              </svg>
            </div>
            <span
              class="category-badge"
              :style="{ color: getCategoryColor(template.category), borderColor: getCategoryColor(template.category) }"
            >
              {{ template.category }}
            </span>
          </div>

          <h3 class="card-title">{{ template.name }}</h3>
          <p class="card-description">{{ template.description }}</p>

          <button
            class="deploy-btn"
            :disabled="deployingId === template.id"
            @click="deployTemplate(template)"
          >
            <template v-if="deployingId === template.id">
              <span class="spinner-sm"></span> Deploying...
            </template>
            <template v-else>
              Deploy
            </template>
          </button>
        </div>
      </div>
    </section>

    <!-- NL Bot Creator -->
    <section class="nl-creator">
      <h2>Create Bot from Description</h2>
      <p class="section-subtitle">Describe the bot you want and we will generate the configuration using AI</p>

      <div class="nl-input-area">
        <textarea
          v-model="nlDescription"
          placeholder="Describe the bot you want to create... (e.g., 'A bot that reviews Python pull requests for security vulnerabilities and suggests fixes')"
          rows="4"
          :disabled="isGenerating"
        ></textarea>
        <button
          class="generate-btn"
          :disabled="nlDescription.length < 10 || isGenerating"
          @click="generateFromDescription"
        >
          <template v-if="isGenerating">
            <span class="spinner-sm"></span> Generating...
          </template>
          <template v-else>
            Generate
          </template>
        </button>
      </div>

      <div v-if="streamOutput" class="stream-output">
        <div class="output-header">
          <span>Generated Configuration</span>
          <button
            v-if="generatedConfig && !isDeployingGenerated"
            class="deploy-generated-btn"
            @click="deployGeneratedBot"
          >
            Deploy Generated Bot
          </button>
          <span v-if="isDeployingGenerated" class="deploying-text">
            <span class="spinner-sm"></span> Deploying...
          </span>
        </div>
        <pre class="output-code"><code>{{ streamOutput }}</code></pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
.marketplace-page {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
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

/* Template Gallery */
.template-gallery {
  margin-bottom: 3rem;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}

@media (max-width: 900px) {
  .template-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .template-grid {
    grid-template-columns: 1fr;
  }
}

.template-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.template-card:hover {
  border-color: var(--border-default);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.card-icon {
  width: 36px;
  height: 36px;
}

.card-icon svg {
  width: 100%;
  height: 100%;
}

.category-badge {
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: 1px solid;
  border-radius: 4px;
  padding: 2px 8px;
}

.card-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.5rem;
}

.card-description {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 1rem;
  flex: 1;
}

.deploy-btn {
  align-self: flex-start;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 6px;
  padding: 0.4rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.deploy-btn:hover:not(:disabled) {
  background: rgba(0, 212, 255, 0.25);
  border-color: var(--accent-cyan);
}

.deploy-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* NL Creator Section */
.nl-creator {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.5rem;
}

.nl-creator h2 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
}

.section-subtitle {
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin: 0 0 1rem;
}

.nl-input-area {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.nl-input-area textarea {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 0.75rem;
  color: var(--text-primary);
  font-family: 'Geist', sans-serif;
  font-size: 0.9rem;
  resize: vertical;
  min-height: 80px;
}

.nl-input-area textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.nl-input-area textarea::placeholder {
  color: var(--text-tertiary);
}

.generate-btn {
  align-self: flex-start;
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.generate-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Stream Output */
.stream-output {
  margin-top: 1rem;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.deploy-generated-btn {
  background: var(--accent-emerald);
  color: var(--text-on-accent);
  border: none;
  border-radius: 4px;
  padding: 0.35rem 0.75rem;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.deploy-generated-btn:hover {
  opacity: 0.9;
}

.deploying-text {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.output-code {
  margin: 0;
  padding: 1rem;
  background: var(--bg-primary);
  color: var(--accent-emerald);
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Loading & Empty States */
.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem;
  color: var(--text-secondary);
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
