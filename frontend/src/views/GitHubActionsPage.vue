<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

const botId = ref('bot-security');

const baseUrl = computed(() => {
  return typeof window !== 'undefined' ? window.location.origin : 'https://your-agented-host';
});

const generatedWebhookUrl = computed(() => {
  return `${baseUrl.value}/api/webhooks/github`;
});

const yamlSnippet = computed(() => `name: Agented Bot Analysis

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  agented-analysis:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Agented Bot
        uses: actions/github-script@v7
        with:
          script: |
            const response = await fetch('${generatedWebhookUrl.value}', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': '\${{ secrets.AGENTED_API_KEY }}'
              },
              body: JSON.stringify({
                bot_id: '${botId.value}',
                pr_url: context.payload.pull_request.html_url,
                ref: context.payload.pull_request.head.sha
              })
            });
            if (!response.ok) {
              core.setFailed(\`Agented trigger failed: \${response.status}\`);
            }
`);

function copyYaml() {
  navigator.clipboard.writeText(yamlSnippet.value).then(() => {
    showToast('YAML snippet copied to clipboard', 'success');
  });
}

function copyWebhookUrl() {
  navigator.clipboard.writeText(generatedWebhookUrl.value).then(() => {
    showToast('Webhook URL copied', 'success');
  });
}
</script>

<template>
  <div class="github-actions-page">
    <AppBreadcrumb :items="[{ label: 'Integrations' }, { label: 'GitHub Actions' }]" />

    <div class="page-title-row">
      <div>
        <h2>GitHub Actions Integration</h2>
        <p class="subtitle">Embed Agented bot analysis in your CI/CD pipelines</p>
      </div>
    </div>

    <div class="config-grid">
      <!-- Generator controls -->
      <div class="card">
        <div class="card-header">
          <h3>Configuration</h3>
        </div>

        <div class="field-group">
          <label class="field-label">Bot ID</label>
          <input
            v-model="botId"
            class="field-input"
            type="text"
            placeholder="bot-security"
          />
          <p class="field-hint">Which bot to trigger on each PR or push event</p>
        </div>

        <div class="field-group">
          <label class="field-label">Webhook URL (generated)</label>
          <div class="copy-row">
            <input
              :value="generatedWebhookUrl"
              class="field-input copy-input"
              readonly
            />
            <button class="btn btn-secondary btn-sm" @click="copyWebhookUrl">Copy</button>
          </div>
        </div>

        <div class="field-group">
          <label class="field-label">Store API Key as GitHub Secret</label>
          <div class="secret-info card-inner">
            <span class="secret-name">AGENTED_API_KEY</span>
            <p class="field-hint">
              Add this secret in your repo under Settings &gt; Secrets and variables &gt; Actions
            </p>
          </div>
        </div>
      </div>

      <!-- How it works -->
      <div class="card">
        <div class="card-header">
          <h3>How it works</h3>
        </div>
        <ol class="steps-list">
          <li>A PR or push triggers the GitHub Actions workflow</li>
          <li>The workflow calls your Agented webhook endpoint</li>
          <li>Agented dispatches the configured bot with PR context</li>
          <li>The bot runs its prompt and reports findings</li>
          <li>Results are visible in the Agented execution logs</li>
        </ol>
      </div>
    </div>

    <!-- YAML snippet -->
    <div class="card snippet-card">
      <div class="card-header">
        <h3>Workflow YAML Snippet</h3>
        <button class="btn btn-secondary btn-sm" @click="copyYaml">Copy YAML</button>
      </div>
      <pre class="yaml-code">{{ yamlSnippet }}</pre>
    </div>
  </div>
</template>

<style scoped>
.github-actions-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 800px) {
  .config-grid { grid-template-columns: 1fr; }
}

.card {
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.field-group {
  margin-bottom: 18px;
}

.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.field-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  box-sizing: border-box;
}

.field-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.field-hint {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}

.copy-row {
  display: flex;
  gap: 8px;
}

.copy-input {
  flex: 1;
}

.card-inner {
  padding: 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}

.secret-name {
  font-family: 'Geist Mono', monospace;
  font-size: 0.85rem;
  color: var(--accent-cyan);
  display: block;
  margin-bottom: 6px;
}

.steps-list {
  padding-left: 20px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.steps-list li {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.snippet-card {
  background: var(--bg-secondary);
}

.yaml-code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--accent-cyan);
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 16px;
  white-space: pre;
  overflow-x: auto;
  margin: 0;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 0.8rem;
}
</style>
