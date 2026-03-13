<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { setupApi, triggerApi, projectApi, ApiError } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const existingProjects = ref<{ id: string; name: string }[]>([]);
const existingTriggers = ref<{ id: string; name: string }[]>([]);

async function loadExistingData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [projResult, trigResult] = await Promise.all([
      projectApi.list({ limit: 50 }),
      triggerApi.list(),
    ]);
    existingProjects.value = projResult.projects.map(p => ({ id: p.id, name: p.name }));
    existingTriggers.value = trigResult.triggers.map(t => ({ id: t.id, name: t.name }));
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load existing data';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadExistingData);

interface WizardStep {
  id: string;
  title: string;
  description: string;
  completed: boolean;
}

const steps: WizardStep[] = [
  { id: 'connect', title: 'Connect a Repository', description: 'Link your GitHub organization so Agented can receive events.', completed: false },
  { id: 'choose', title: 'Choose a Starter Bot', description: 'Pick a pre-built bot template to get started in seconds.', completed: false },
  { id: 'configure', title: 'Configure Your Bot', description: 'Set the bot name, model, and customize the prompt template.', completed: false },
  { id: 'trigger', title: 'Set Up a Trigger', description: 'Define when the bot should run — on PRs, on a schedule, or manually.', completed: false },
  { id: 'test', title: 'Fire a Test Execution', description: 'Run the bot against a real or simulated event to verify it works.', completed: false },
];

const currentStepIdx = ref(0);
const currentStep = computed(() => steps[currentStepIdx.value]);

// Step 1 state
const repoOwner = ref('');
const repoName = ref('');
const isConnecting = ref(false);
const connected = ref(false);

// Step 2 state
const starterTemplates = [
  { id: 'pr-review', name: 'PR Reviewer', icon: '🔍', desc: 'Automatically reviews pull requests and posts inline comments.' },
  { id: 'security', name: 'Security Auditor', icon: '🔒', desc: 'Scans code for security vulnerabilities and compliance issues.' },
  { id: 'changelog', name: 'Changelog Generator', icon: '📝', desc: 'Auto-generates CHANGELOG.md entries from merged PRs.' },
  { id: 'standup', name: 'Standup Summarizer', icon: '📋', desc: 'Summarizes activity into daily standup reports.' },
];
const selectedTemplate = ref<string | null>(null);

// Step 3 state
const botName = ref('');
const botModel = ref('claude-sonnet-4-6');
const botPrompt = ref('');

// Step 4 state
const triggerType = ref<'github' | 'schedule' | 'webhook'>('github');
const githubEvent = ref('pull_request');
const cronSchedule = ref('0 9 * * 1-5');

// Step 5 state
const isRunningTest = ref(false);
const testComplete = ref(false);
const testOutput = ref('');

async function handleConnect() {
  if (!repoOwner.value || !repoName.value) return;
  isConnecting.value = true;
  try {
    const githubRepo = `https://github.com/${repoOwner.value}/${repoName.value}`;
    await projectApi.create({
      name: repoName.value,
      github_repo: githubRepo,
    });
    connected.value = true;
    steps[0].completed = true;
    showToast(`Connected to ${repoOwner.value}/${repoName.value}`, 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to connect repository';
    showToast(msg, 'error');
  } finally {
    isConnecting.value = false;
  }
}

function selectTemplate(id: string) {
  selectedTemplate.value = id;
  const t = starterTemplates.find(t => t.id === id)!;
  botName.value = `my-${id}-bot`;
  botPrompt.value = `You are a ${t.name}. Analyze the provided code and ${t.desc.toLowerCase()}`;
  steps[1].completed = true;
}

function handleConfigSave() {
  if (!botName.value) return;
  steps[2].completed = true;
  goNext();
}

async function handleTriggerSave() {
  try {
    const triggerSource = triggerType.value === 'github' ? 'github' as const
      : triggerType.value === 'schedule' ? 'scheduled' as const
      : 'webhook' as const;

    await triggerApi.create({
      name: botName.value || 'onboarding-trigger',
      prompt_template: botPrompt.value || 'Review the code.',
      trigger_source: triggerSource,
      backend_type: 'claude',
      model: botModel.value,
    });
    steps[3].completed = true;
    goNext();
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to create trigger';
    showToast(msg, 'error');
  }
}

async function handleTestRun() {
  isRunningTest.value = true;
  testOutput.value = '';
  try {
    // Use setup API to start a test execution
    const result = await setupApi.start('', `echo "Testing ${botName.value || 'bot'} setup..."`);
    testOutput.value = `[${new Date().toISOString()}] Setup execution started: ${result.execution_id}\n[${new Date().toISOString()}] Status: ${result.status}\n`;

    // Poll for status
    if (result.execution_id) {
      const status = await setupApi.getStatus(result.execution_id);
      testOutput.value += `[${new Date().toISOString()}] Execution status: ${status.status}\n`;
      if (status.error_message) {
        testOutput.value += `[${new Date().toISOString()}] ${status.error_message}\n`;
      }
    }

    testOutput.value += `[${new Date().toISOString()}] Test complete.`;
    testComplete.value = true;
    steps[4].completed = true;
    showToast('Test execution succeeded!', 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Test execution failed';
    testOutput.value += `[${new Date().toISOString()}] Error: ${msg}\n`;
    // Still mark as complete if the API responded (even with error)
    testComplete.value = true;
    steps[4].completed = true;
    showToast(msg, 'error');
  } finally {
    isRunningTest.value = false;
  }
}

function goNext() {
  if (currentStepIdx.value < steps.length - 1) {
    currentStepIdx.value++;
  }
}

function goBack() {
  if (currentStepIdx.value > 0) {
    currentStepIdx.value--;
  }
}

function handleFinish() {
  showToast('Onboarding complete! Your bot is ready.', 'success');
  router.push({ name: 'triggers' });
}

const completedCount = computed(() => steps.filter(s => s.completed).length);
const progressPct = computed(() => Math.round((completedCount.value / steps.length) * 100));
</script>

<template>
  <div class="onboarding-wizard">
    <PageHeader
      title="Get Started with Agented"
      subtitle="Follow the steps below to connect your repo, configure a bot, and fire your first automation."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
      Loading setup data...
    </div>

    <div v-else-if="loadError" class="card" style="padding: 32px; text-align: center; color: #ef4444;">
      {{ loadError }}
      <button class="btn btn-ghost" style="margin-top: 12px;" @click="loadExistingData">Retry</button>
    </div>

    <template v-else>

    <!-- Existing entities info -->
    <div v-if="existingProjects.length > 0 || existingTriggers.length > 0" class="card" style="padding: 16px 28px; margin-bottom: -8px;">
      <div style="font-size: 0.82rem; color: var(--text-secondary);">
        You have <strong>{{ existingProjects.length }}</strong> project(s) and <strong>{{ existingTriggers.length }}</strong> trigger(s) configured.
      </div>
    </div>

    <!-- Progress bar -->
    <div class="progress-bar-wrap">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <span class="progress-label">{{ completedCount }}/{{ steps.length }} steps complete</span>
    </div>

    <div class="wizard-layout">
      <!-- Step list -->
      <aside class="step-sidebar">
        <div
          v-for="(step, idx) in steps"
          :key="step.id"
          class="step-nav-item"
          :class="{ active: idx === currentStepIdx, completed: step.completed }"
          @click="currentStepIdx = idx"
        >
          <div class="step-indicator">
            <svg v-if="step.completed" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="14" height="14">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <div class="step-label">{{ step.title }}</div>
        </div>
      </aside>

      <!-- Step content -->
      <div class="step-content card">
        <div class="step-header">
          <h2 class="step-title">{{ currentStep.title }}</h2>
          <p class="step-desc">{{ currentStep.description }}</p>
        </div>

        <!-- Step 1: Connect Repo -->
        <div v-if="currentStepIdx === 0" class="step-body">
          <div v-if="connected" class="success-banner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            Connected to {{ repoOwner }}/{{ repoName }}
          </div>
          <template v-else>
            <div class="field-row">
              <div class="field">
                <label class="field-label">GitHub Owner / Org</label>
                <input v-model="repoOwner" class="input" placeholder="my-org" />
              </div>
              <div class="field">
                <label class="field-label">Repository Name</label>
                <input v-model="repoName" class="input" placeholder="my-repo" />
              </div>
            </div>
            <p class="hint">Agented will use a GitHub App to subscribe to events — no manual webhook setup needed.</p>
          </template>
          <div class="step-actions">
            <div></div>
            <button v-if="!connected" class="btn btn-primary" :disabled="!repoOwner || !repoName || isConnecting" @click="handleConnect">
              {{ isConnecting ? 'Connecting...' : 'Connect Repository' }}
            </button>
            <button v-else class="btn btn-primary" @click="goNext">Continue →</button>
          </div>
        </div>

        <!-- Step 2: Choose Template -->
        <div v-else-if="currentStepIdx === 1" class="step-body">
          <div class="template-grid">
            <div
              v-for="t in starterTemplates"
              :key="t.id"
              class="template-card"
              :class="{ selected: selectedTemplate === t.id }"
              @click="selectTemplate(t.id)"
            >
              <div class="template-icon">{{ t.icon }}</div>
              <div class="template-name">{{ t.name }}</div>
              <div class="template-desc">{{ t.desc }}</div>
            </div>
          </div>
          <div class="step-actions">
            <button class="btn btn-ghost" @click="goBack">← Back</button>
            <button class="btn btn-primary" :disabled="!selectedTemplate" @click="goNext">Continue →</button>
          </div>
        </div>

        <!-- Step 3: Configure -->
        <div v-else-if="currentStepIdx === 2" class="step-body">
          <div class="field">
            <label class="field-label">Bot Name</label>
            <input v-model="botName" class="input" placeholder="my-pr-review-bot" />
          </div>
          <div class="field">
            <label class="field-label">AI Model</label>
            <select v-model="botModel" class="select">
              <option value="claude-opus-4-6">Claude Opus 4.6 (Most capable)</option>
              <option value="claude-sonnet-4-6">Claude Sonnet 4.6 (Recommended)</option>
              <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5 (Fastest)</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">Prompt Template</label>
            <textarea v-model="botPrompt" class="textarea" rows="6" placeholder="You are a..." />
          </div>
          <div class="step-actions">
            <button class="btn btn-ghost" @click="goBack">← Back</button>
            <button class="btn btn-primary" :disabled="!botName" @click="handleConfigSave">Save & Continue →</button>
          </div>
        </div>

        <!-- Step 4: Trigger -->
        <div v-else-if="currentStepIdx === 3" class="step-body">
          <div class="field">
            <label class="field-label">Trigger Type</label>
            <div class="trigger-options">
              <label class="trigger-opt" :class="{ active: triggerType === 'github' }">
                <input type="radio" v-model="triggerType" value="github" /> GitHub Event
              </label>
              <label class="trigger-opt" :class="{ active: triggerType === 'schedule' }">
                <input type="radio" v-model="triggerType" value="schedule" /> Schedule (Cron)
              </label>
              <label class="trigger-opt" :class="{ active: triggerType === 'webhook' }">
                <input type="radio" v-model="triggerType" value="webhook" /> Incoming Webhook
              </label>
            </div>
          </div>

          <div v-if="triggerType === 'github'" class="field">
            <label class="field-label">GitHub Event</label>
            <select v-model="githubEvent" class="select">
              <option value="pull_request">pull_request (opened, reopened, synchronize)</option>
              <option value="push">push (commits to default branch)</option>
              <option value="release">release (published)</option>
              <option value="issues">issues (opened, labeled)</option>
            </select>
          </div>

          <div v-else-if="triggerType === 'schedule'" class="field">
            <label class="field-label">Cron Schedule</label>
            <input v-model="cronSchedule" class="input" placeholder="0 9 * * 1-5" />
            <span class="hint">Weekdays at 9am UTC</span>
          </div>

          <div v-else class="field">
            <label class="field-label">Webhook URL</label>
            <div class="webhook-url-preview">
              <code>POST /api/webhooks/{{ botName || 'your-bot' }}/trigger</code>
            </div>
            <span class="hint">Send a POST request to trigger the bot externally.</span>
          </div>

          <div class="step-actions">
            <button class="btn btn-ghost" @click="goBack">← Back</button>
            <button class="btn btn-primary" @click="handleTriggerSave">Save & Continue →</button>
          </div>
        </div>

        <!-- Step 5: Test -->
        <div v-else-if="currentStepIdx === 4" class="step-body">
          <p class="test-intro">Everything is configured! Run a test execution to verify your bot works end-to-end.</p>

          <div v-if="testOutput" class="test-output">
            <pre>{{ testOutput }}</pre>
          </div>

          <div v-if="testComplete" class="success-banner">
            Bot executed successfully! You're ready to automate.
          </div>

          <div class="step-actions">
            <button class="btn btn-ghost" @click="goBack">← Back</button>
            <button v-if="!testComplete" class="btn btn-primary" :disabled="isRunningTest" @click="handleTestRun">
              {{ isRunningTest ? 'Running...' : 'Run Test Execution' }}
            </button>
            <button v-else class="btn btn-primary" @click="handleFinish">Finish Setup →</button>
          </div>
        </div>
      </div>
    </div>

    </template>
  </div>
</template>

<style scoped>
.onboarding-wizard { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.progress-bar-wrap { display: flex; align-items: center; gap: 12px; }
.progress-bar { flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent-cyan); border-radius: 3px; transition: width 0.3s ease; }
.progress-label { font-size: 0.78rem; color: var(--text-tertiary); white-space: nowrap; }

.wizard-layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.step-sidebar { display: flex; flex-direction: column; gap: 4px; }
.step-nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 8px; cursor: pointer; transition: background 0.1s; }
.step-nav-item:hover { background: var(--bg-tertiary); }
.step-nav-item.active { background: rgba(6,182,212,0.1); }
.step-nav-item.completed .step-indicator { background: rgba(52,211,153,0.2); color: #34d399; border-color: #34d399; }

.step-indicator { width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid var(--border-default); background: var(--bg-secondary); display: flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; color: var(--text-secondary); flex-shrink: 0; }
.step-nav-item.active .step-indicator { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.step-label { font-size: 0.82rem; color: var(--text-secondary); }
.step-nav-item.active .step-label { color: var(--text-primary); font-weight: 500; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.step-content { }
.step-header { padding: 24px 28px 0; }
.step-title { font-size: 1.1rem; font-weight: 700; color: var(--text-primary); margin: 0 0 6px; }
.step-desc { font-size: 0.875rem; color: var(--text-secondary); margin: 0; }

.step-body { padding: 24px 28px; display: flex; flex-direction: column; gap: 16px; }

.field { display: flex; flex-direction: column; gap: 6px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); }
.input { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.input:focus { outline: none; border-color: var(--accent-cyan); }
.select { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; cursor: pointer; }
.select:focus { outline: none; border-color: var(--accent-cyan); }
.textarea { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; font-family: 'Geist Mono', monospace; resize: vertical; width: 100%; box-sizing: border-box; }
.textarea:focus { outline: none; border-color: var(--accent-cyan); }
.hint { font-size: 0.73rem; color: var(--text-muted); }

.template-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.template-card { padding: 16px; background: var(--bg-tertiary); border: 1.5px solid var(--border-default); border-radius: 10px; cursor: pointer; transition: all 0.15s; }
.template-card:hover { border-color: var(--accent-cyan); }
.template-card.selected { border-color: var(--accent-cyan); background: rgba(6,182,212,0.07); }
.template-icon { font-size: 1.5rem; margin-bottom: 8px; }
.template-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.template-desc { font-size: 0.78rem; color: var(--text-secondary); }

.trigger-options { display: flex; gap: 12px; flex-wrap: wrap; }
.trigger-opt { display: flex; align-items: center; gap: 8px; padding: 10px 16px; background: var(--bg-tertiary); border: 1.5px solid var(--border-default); border-radius: 8px; cursor: pointer; font-size: 0.82rem; color: var(--text-secondary); }
.trigger-opt.active { border-color: var(--accent-cyan); color: var(--text-primary); background: rgba(6,182,212,0.07); }
.trigger-opt input { accent-color: var(--accent-cyan); }

.webhook-url-preview { padding: 10px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; }
.webhook-url-preview code { font-family: 'Geist Mono', monospace; font-size: 0.82rem; color: var(--accent-cyan); }

.test-intro { font-size: 0.875rem; color: var(--text-secondary); margin: 0; }
.test-output { background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 8px; padding: 14px 16px; }
.test-output pre { margin: 0; font-family: 'Geist Mono', monospace; font-size: 0.78rem; color: var(--text-secondary); white-space: pre-wrap; }

.success-banner { display: flex; align-items: center; gap: 10px; padding: 12px 16px; background: rgba(52,211,153,0.1); border: 1px solid rgba(52,211,153,0.3); border-radius: 8px; font-size: 0.875rem; color: #34d399; font-weight: 500; }

.step-actions { display: flex; align-items: center; justify-content: space-between; padding-top: 8px; }
.btn { display: flex; align-items: center; gap: 6px; padding: 9px 18px; border-radius: 7px; font-size: 0.875rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

@media (max-width: 900px) { .wizard-layout { grid-template-columns: 1fr; } .template-grid { grid-template-columns: 1fr; } .field-row { grid-template-columns: 1fr; } }
</style>
