<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useToast } from '../composables/useToast';
import { triggerApi } from '../services/api';

const { t } = useI18n();
const showToast = useToast();

const triggers = ref<Array<{ id: string; name: string }>>([]);
const loading = ref(false);
const botId = ref('');

onMounted(async () => {
  loading.value = true;
  try {
    const data = await triggerApi.list();
    triggers.value = data.triggers.map((t) => ({ id: t.id, name: t.name }));
    if (triggers.value.length > 0) {
      botId.value = triggers.value[0].id;
    }
  } catch {
    // ignore — botId stays empty
  } finally {
    loading.value = false;
  }
});

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
    showToast(t('gitHubActions.toast.yamlCopied'), 'success');
  });
}

function copyWebhookUrl() {
  navigator.clipboard.writeText(generatedWebhookUrl.value).then(() => {
    showToast(t('gitHubActions.toast.webhookCopied'), 'success');
  });
}
</script>

<template>
  <div class="github-actions-page">

    <div class="page-title-row">
      <div>
        <h2>{{ t('gitHubActions.title') }}</h2>
        <p class="subtitle">{{ t('gitHubActions.subtitle') }}</p>
      </div>
    </div>

    <div class="config-grid">
      <!-- Generator controls -->
      <div class="card">
        <div class="card-header">
          <h3>{{ t('gitHubActions.configuration') }}</h3>
        </div>

        <div class="field-group">
          <label class="field-label">{{ t('gitHubActions.triggerLabel') }}</label>
          <select v-model="botId" class="field-input" :disabled="loading">
            <option v-if="loading" value="">{{ t('common.loading') }}</option>
            <option v-else-if="triggers.length === 0" value="">{{ t('gitHubActions.noTriggers') }}</option>
            <option v-for="trg in triggers" :key="trg.id" :value="trg.id">{{ trg.name }}</option>
          </select>
          <p class="field-hint">{{ t('gitHubActions.triggerHint') }}</p>
        </div>

        <div class="field-group">
          <label class="field-label">{{ t('gitHubActions.webhookUrlLabel') }}</label>
          <div class="copy-row">
            <input
              :value="generatedWebhookUrl"
              class="field-input copy-input"
              readonly
            />
            <button class="btn btn-secondary btn-sm" @click="copyWebhookUrl">{{ t('gitHubActions.copy') }}</button>
          </div>
        </div>

        <div class="field-group">
          <label class="field-label">{{ t('gitHubActions.storeSecretLabel') }}</label>
          <div class="secret-info card-inner">
            <span class="secret-name">AGENTED_API_KEY</span>
            <p class="field-hint">
              {{ t('gitHubActions.secretHint') }}
            </p>
          </div>
        </div>
      </div>

      <!-- How it works -->
      <div class="card">
        <div class="card-header">
          <h3>{{ t('gitHubActions.howItWorks') }}</h3>
        </div>
        <ol class="steps-list">
          <li>{{ t('gitHubActions.steps.step1') }}</li>
          <li>{{ t('gitHubActions.steps.step2') }}</li>
          <li>{{ t('gitHubActions.steps.step3') }}</li>
          <li>{{ t('gitHubActions.steps.step4') }}</li>
          <li>{{ t('gitHubActions.steps.step5') }}</li>
        </ol>
      </div>
    </div>

    <!-- YAML snippet -->
    <div class="card snippet-card">
      <div class="card-header">
        <h3>{{ t('gitHubActions.yamlSnippet') }}</h3>
        <button class="btn btn-secondary btn-sm" @click="copyYaml">{{ t('gitHubActions.copyYaml') }}</button>
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
