<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { triggerApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

const bots = ref<{ id: string; name: string; prompt_template?: string }[]>([]);
const selectedBotId = ref('');
const promptTemplate = ref('');
const samplePayload = ref(JSON.stringify({ action: 'opened', pull_request: { number: 42, title: 'Fix bug', body: 'Fixes #100', user: { login: 'dev' } }, repository: { full_name: 'org/repo' } }, null, 2));
const resolvedPrompt = ref('');
const dryRunOutput = ref('');
const isLoading = ref(true);
const isDryRunning = ref(false);
const payloadError = ref('');
const activeTab = ref<'resolve' | 'dry-run'>('resolve');

const selectedBot = computed(() => bots.value.find(b => b.id === selectedBotId.value));

const PLACEHOLDER_VARS: Record<string, string> = {
  '{paths}': 'src/main.py src/utils.py',
  '{message}': 'Fix authentication bug in login flow',
  '{pr_url}': 'https://github.com/org/repo/pull/42',
  '{repo}': 'org/repo',
  '{branch}': 'feature/fix-auth',
  '{sha}': 'abc1234def5678',
  '{author}': 'dev',
  '{title}': 'Fix authentication bug',
};

function resolvePrompt() {
  if (!promptTemplate.value) return;
  let resolved = promptTemplate.value;
  let payload: Record<string, unknown> = {};
  payloadError.value = '';
  try {
    payload = JSON.parse(samplePayload.value);
  } catch {
    payloadError.value = 'Invalid JSON payload';
    return;
  }
  // Replace named placeholders from payload
  function extractValues(obj: unknown, prefix = ''): void {
    if (typeof obj !== 'object' || obj === null) return;
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (typeof v === 'string' || typeof v === 'number') {
        resolved = resolved.replace(new RegExp(`\\{${key}\\}`, 'g'), String(v));
      } else if (typeof v === 'object') {
        extractValues(v, key);
      }
    }
  }
  extractValues(payload);
  // Replace standard placeholders
  for (const [k, v] of Object.entries(PLACEHOLDER_VARS)) {
    resolved = resolved.split(k).join(v);
  }
  resolvedPrompt.value = resolved;
}

async function handleDryRun() {
  if (!promptTemplate.value) return;
  isDryRunning.value = true;
  dryRunOutput.value = '';
  try {
    // Simulate dry-run by showing the resolved prompt as what would be sent
    resolvePrompt();
    await new Promise(r => setTimeout(r, 600));
    dryRunOutput.value = `[DRY RUN — no AI call made]\n\nProvider: claude\nModel: claude-3-5-sonnet\n\n--- Resolved Prompt ---\n${resolvedPrompt.value || promptTemplate.value}\n\n--- End Prompt ---\n\nThis prompt would be passed to the configured AI provider.\nToken estimate: ~${Math.ceil((resolvedPrompt.value || promptTemplate.value).length / 4)} tokens`;
    showToast('Dry run completed', 'success');
  } finally {
    isDryRunning.value = false;
  }
}

async function loadBots() {
  try {
    const res = await triggerApi.list();
    bots.value = (res.triggers ?? []).map((b: { id: string; name: string; prompt_template?: string }) => b);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load bots';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

function onBotSelect() {
  const bot = selectedBot.value;
  if (bot?.prompt_template) {
    promptTemplate.value = bot.prompt_template;
    resolvedPrompt.value = '';
    dryRunOutput.value = '';
  }
}

onMounted(loadBots);
</script>

<template>
  <div class="playground">

    <PageHeader
      title="Prompt Template Playground"
      subtitle="Paste a webhook payload, preview how placeholders resolve, and dry-run against a provider before saving."
    />

    <LoadingState v-if="isLoading" message="Loading bots..." />

    <template v-else>
      <div class="layout">
        <div class="left-panel">
          <!-- Bot picker -->
          <div class="card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <rect x="3" y="3" width="18" height="18" rx="2"/>
                  <path d="M9 9h6M9 13h4"/>
                </svg>
                Load From Bot
              </h3>
            </div>
            <div class="card-body">
              <select v-model="selectedBotId" class="select-input" @change="onBotSelect">
                <option value="">-- Select a bot (optional) --</option>
                <option v-for="b in bots" :key="b.id" :value="b.id">{{ b.name }}</option>
              </select>
            </div>
          </div>

          <!-- Template editor -->
          <div class="card grow-card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                </svg>
                Prompt Template
              </h3>
              <div class="placeholders-hint">
                <span>Available: <code>{paths}</code> <code>{message}</code> <code>{pr_url}</code> <code>{repo}</code></span>
              </div>
            </div>
            <div class="card-body">
              <textarea
                v-model="promptTemplate"
                class="code-editor"
                placeholder="Enter your prompt template here. Use {pr_url}, {repo}, {author} as placeholders..."
                rows="12"
              />
            </div>
          </div>

          <!-- Payload editor -->
          <div class="card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <path d="M20 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/>
                  <circle cx="12" cy="12" r="1"/>
                </svg>
                Sample Webhook Payload
              </h3>
            </div>
            <div class="card-body">
              <textarea
                v-model="samplePayload"
                class="code-editor"
                :class="{ 'error-border': payloadError }"
                rows="10"
                placeholder='{"action": "opened", "pull_request": {...}}'
              />
              <p v-if="payloadError" class="error-msg">{{ payloadError }}</p>
            </div>
          </div>

          <div class="actions">
            <button class="btn btn-secondary" :disabled="!promptTemplate" @click="resolvePrompt">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              Preview Resolved
            </button>
            <button class="btn btn-primary" :disabled="!promptTemplate || isDryRunning" @click="handleDryRun">
              <svg v-if="isDryRunning" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              {{ isDryRunning ? 'Running...' : 'Dry Run' }}
            </button>
          </div>
        </div>

        <div class="right-panel">
          <div class="tabs">
            <button :class="['tab', { active: activeTab === 'resolve' }]" @click="activeTab = 'resolve'">Resolved Prompt</button>
            <button :class="['tab', { active: activeTab === 'dry-run' }]" @click="activeTab = 'dry-run'">Dry Run Output</button>
          </div>

          <div class="card output-card">
            <template v-if="activeTab === 'resolve'">
              <div v-if="!resolvedPrompt" class="empty-output">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
                <p>Click "Preview Resolved" to see how placeholders resolve with your sample payload.</p>
              </div>
              <pre v-else class="output-pre">{{ resolvedPrompt }}</pre>
            </template>

            <template v-if="activeTab === 'dry-run'">
              <div v-if="!dryRunOutput" class="empty-output">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                <p>Click "Dry Run" to simulate what would be sent to the AI provider.</p>
              </div>
              <pre v-else class="output-pre">{{ dryRunOutput }}</pre>
            </template>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.playground {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

.left-panel, .right-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
  gap: 8px;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.placeholders-hint {
  font-size: 0.72rem;
  color: var(--text-tertiary);
}

.placeholders-hint code {
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--accent-cyan);
  font-size: 0.72rem;
}

.card-body { padding: 16px 20px; }

.select-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.select-input:focus { outline: none; border-color: var(--accent-cyan); }

.code-editor {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}

.code-editor:focus { outline: none; border-color: var(--accent-cyan); }

.error-border { border-color: #ef4444 !important; }

.error-msg {
  font-size: 0.78rem;
  color: #ef4444;
  margin-top: 6px;
}

.actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  width: fit-content;
}

.tab {
  padding: 6px 16px;
  border-radius: 7px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.tab.active { background: var(--bg-tertiary); color: var(--text-primary); }

.output-card { min-height: 400px; }

.empty-output {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-output p { font-size: 0.85rem; max-width: 260px; }

.output-pre {
  padding: 20px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  overflow: auto;
  max-height: 600px;
  margin: 0;
}

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
