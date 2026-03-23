<script setup lang="ts">
/**
 * AccountWizard -- Step-by-step account registration flow.
 *
 * Replaces the raw inline form when adding a new account.
 * Steps:
 *   1) Subscription check (has account? or skip)
 *   2) CLI & Config Setup (install CLI, create config dir)
 *   3) Login (browser or CLI proxy)
 *   4) Plan & Save (choose plan, set default, save)
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { backendApi, utilityApi, BACKEND_PLAN_OPTIONS } from '../../services/api';

const props = defineProps<{
  backendId: string;
  backendType: string;
  backendName: string;
  isInstalled: boolean;
  version?: string;
}>();

const emit = defineEmits<{
  close: [];
  saved: [];
  skip: [];
  addAnother: [];
  done: []; // Close wizard AND advance tour to next backend
}>();

const { t } = useI18n();

// ---------------------------------------------------------------------------
// Wizard step management
// ---------------------------------------------------------------------------
type WizardStep = 'subscription' | 'cli' | 'login' | 'plan' | 'done';
const STEP_ORDER: WizardStep[] = ['subscription', 'cli', 'login', 'plan', 'done'];
const VISIBLE_STEPS: WizardStep[] = ['subscription', 'cli', 'login', 'plan'];
const currentStep = ref<WizardStep>('subscription');

const currentStepIndex = computed(() => STEP_ORDER.indexOf(currentStep.value));
const stepLabels: Record<WizardStep, string> = {
  subscription: 'Subscription',
  cli: 'CLI Setup',
  login: 'Login',
  plan: 'Plan & Save',
  done: 'Done',
};

function goNext() {
  const idx = currentStepIndex.value;
  if (idx < STEP_ORDER.length - 1) {
    currentStep.value = STEP_ORDER[idx + 1];
  }
}

function goPrev() {
  const idx = currentStepIndex.value;
  if (idx > 0) {
    currentStep.value = STEP_ORDER[idx - 1];
  }
}

// ---------------------------------------------------------------------------
// Step 1: Subscription Check
// ---------------------------------------------------------------------------
const hasSubscription = ref<'yes' | 'no' | ''>('');
const accountName = ref('');
const email = ref('');

const subscriptionValid = computed(() => {
  if (hasSubscription.value === 'no') return true;
  if (hasSubscription.value === 'yes') return accountName.value.trim().length > 0;
  return false;
});

function handleSubscriptionNext() {
  if (hasSubscription.value === 'no') {
    emit('skip');
    return;
  }
  goNext();
}

// ---------------------------------------------------------------------------
// Config path & env var auto-generation
// ---------------------------------------------------------------------------
const configPath = ref('');
const configPathManuallyEdited = ref(false);

function generateSlug(name: string): string {
  return name.toLowerCase().replace(/\s+/g, '').replace(/[^a-z0-9]/g, '');
}

function suggestConfigPath() {
  if (configPathManuallyEdited.value) return;
  const name = accountName.value.trim();
  if (!name) {
    configPath.value = '';
    return;
  }
  const slug = generateSlug(name);
  const dirMap: Record<string, string> = {
    claude: '.claude',
    codex: '.codex',
    gemini: '.gemini',
    opencode: '.opencode',
  };
  const base = dirMap[props.backendType] || `.${props.backendType}`;
  configPath.value = `~/${base}-${slug}`;
}

const apiKeyEnv = computed(() => {
  const name = accountName.value.trim();
  if (!name) return '';
  const envMap: Record<string, string> = {
    claude: 'ANTHROPIC',
    codex: 'OPENAI',
    gemini: 'GOOGLE',
    opencode: 'OPENCODE',
  };
  const prefix = envMap[props.backendType] || props.backendType.toUpperCase();
  const suffix = generateSlug(name).replace(/-/g, '_').toUpperCase();
  return `${prefix}_API_KEY_${suffix}`;
});

// ---------------------------------------------------------------------------
// Step 2: CLI Setup
// ---------------------------------------------------------------------------
const cliInstalled = ref(props.isInstalled);
const cliVersion = ref(props.version || '');
const isCheckingCli = ref(false);
const isInstallingCli = ref(false);
const isCreatingDir = ref(false);
const dirCreated = ref(false);
const dirError = ref('');
const installError = ref('');

async function checkCli() {
  isCheckingCli.value = true;
  try {
    const result = await backendApi.check(props.backendId);
    cliInstalled.value = result.installed;
    cliVersion.value = result.version || '';
  } catch {
    // Keep existing state
  } finally {
    isCheckingCli.value = false;
  }
}

async function installCli() {
  isInstallingCli.value = true;
  installError.value = '';
  try {
    const result = await backendApi.installCli(props.backendId);
    if (result.version) {
      cliInstalled.value = true;
      cliVersion.value = result.version;
    } else if (result.error) {
      installError.value = result.error;
    }
  } catch (e: unknown) {
    installError.value = e instanceof Error ? e.message : 'Installation failed';
  } finally {
    isInstallingCli.value = false;
  }
}

async function createConfigDir() {
  if (!configPath.value) return;
  isCreatingDir.value = true;
  dirError.value = '';
  try {
    await utilityApi.createDirectory(configPath.value);
    dirCreated.value = true;
  } catch (e: unknown) {
    dirError.value = e instanceof Error ? e.message : 'Failed to create directory';
  } finally {
    isCreatingDir.value = false;
  }
}

onMounted(() => {
  checkCli();
});

// Reset dir state when config path changes
watch(configPath, () => {
  dirCreated.value = false;
  dirError.value = '';
});

// ---------------------------------------------------------------------------
// Step 3: Login — uses PTY-based CLI connect (claude /login, codex login, etc.)
// ---------------------------------------------------------------------------
const loginStatus = ref<'idle' | 'connecting' | 'streaming' | 'completed' | 'error'>('idle');
const loginSessionId = ref('');
const loginLines = ref<string[]>([]);
const loginError = ref('');
const pendingQuestion = ref('');
const userResponse = ref('');
let loginEventSource: EventSource | null = null;

async function startCliLogin() {
  loginStatus.value = 'connecting';
  loginLines.value = [];
  loginError.value = '';
  pendingQuestion.value = '';
  try {
    const result = await backendApi.startConnect(props.backendId, configPath.value || undefined);
    loginSessionId.value = result.session_id;
    loginStatus.value = 'streaming';
    // Open SSE stream
    const streamUrl = backendApi.streamConnectUrl(props.backendId, result.session_id);
    loginEventSource = new EventSource(streamUrl);
    loginEventSource.addEventListener('output', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.text) {
        loginLines.value.push(data.text);
        scrollTerminal();
      }
    });
    loginEventSource.addEventListener('question', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      pendingQuestion.value = data.text || data.question || '';
      if (data.options) {
        loginLines.value.push(data.text || '');
        data.options.forEach((opt: string, i: number) => {
          loginLines.value.push(`  ${i + 1}. ${opt}`);
        });
      }
      scrollTerminal();
    });
    loginEventSource.addEventListener('auth_url', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (data.url) window.open(data.url, '_blank');
      loginLines.value.push(`Opening browser for authentication...`);
      scrollTerminal();
    });
    loginEventSource.addEventListener('complete', () => {
      loginStatus.value = 'completed';
      loginEventSource?.close();
      loginEventSource = null;
    });
    loginEventSource.addEventListener('error_event', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      loginError.value = data.message || 'Login failed';
      loginStatus.value = 'error';
      loginEventSource?.close();
      loginEventSource = null;
    });
    loginEventSource.onerror = () => {
      if (loginStatus.value === 'streaming') {
        // SSE closed — check if it was a normal completion
        loginStatus.value = 'completed';
      }
      loginEventSource?.close();
      loginEventSource = null;
    };
  } catch (e: unknown) {
    loginError.value = e instanceof Error ? e.message : 'Failed to start login session';
    loginStatus.value = 'error';
  }
}

async function sendResponse() {
  if (!userResponse.value.trim() || !loginSessionId.value) return;
  try {
    await backendApi.respondConnect(props.backendId, loginSessionId.value, 'wizard', { text: userResponse.value.trim() });
    loginLines.value.push(`> ${userResponse.value.trim()}`);
    userResponse.value = '';
    pendingQuestion.value = '';
    scrollTerminal();
  } catch {
    // Ignore — session may have ended
  }
}

function scrollTerminal() {
  setTimeout(() => {
    const el = document.querySelector('.login-terminal-output');
    if (el) el.scrollTop = el.scrollHeight;
  }, 50);
}

function cleanupLogin() {
  if (loginEventSource) {
    loginEventSource.close();
    loginEventSource = null;
  }
  if (loginSessionId.value) {
    backendApi.cancelConnect(props.backendId, loginSessionId.value).catch(() => {});
  }
}

onUnmounted(cleanupLogin);

// ---------------------------------------------------------------------------
// Step 4: Plan & Save
// ---------------------------------------------------------------------------
const planOptions = computed(() => BACKEND_PLAN_OPTIONS[props.backendType] || []);
const selectedPlan = ref('');
const isDefault = ref(false);
const isSaving = ref(false);
const saveError = ref('');

async function saveAccount() {
  isSaving.value = true;
  saveError.value = '';
  try {
    await backendApi.addAccount(props.backendId, {
      account_name: accountName.value.trim(),
      email: email.value.trim() || undefined,
      config_path: configPath.value.trim() || undefined,
      api_key_env: apiKeyEnv.value || undefined,
      plan: selectedPlan.value || undefined,
      is_default: isDefault.value ? 1 : 0,
    });
    currentStep.value = 'done';
    emit('saved');
  } catch (e: unknown) {
    saveError.value = e instanceof Error ? e.message : 'Failed to save account';
  } finally {
    isSaving.value = false;
  }
}

function addAnotherAccount() {
  // Reset form
  hasSubscription.value = '';
  accountName.value = '';
  email.value = '';
  configPath.value = '';
  configPathManuallyEdited.value = false;
  selectedPlan.value = '';
  isDefault.value = false;
  cleanupLogin();
  loginStatus.value = 'idle';
  loginSessionId.value = '';
  loginLines.value = [];
  loginError.value = '';
  pendingQuestion.value = '';
  userResponse.value = '';
  dirCreated.value = false;
  currentStep.value = 'subscription';
  emit('addAnother');
}
</script>

<template>
  <div class="wizard-container">
    <div class="wizard-header">
      <h3>{{ t('accountWizard.addAccount') }}</h3>
      <button class="wizard-close" @click="emit('close')">&times;</button>
    </div>

    <!-- Step indicators -->
    <div v-if="currentStep !== 'done'" class="wizard-steps">
      <div
        v-for="(step, idx) in VISIBLE_STEPS"
        :key="step"
        class="step-indicator"
        :class="{
          active: currentStep === step,
          completed: currentStepIndex > idx,
          clickable: idx < currentStepIndex,
        }"
        @click="idx < currentStepIndex ? (currentStep = step) : undefined"
      >
        <span class="step-number">
          <template v-if="currentStepIndex > idx">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="12" height="12">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </template>
          <template v-else>{{ idx + 1 }}</template>
        </span>
        <span class="step-label">{{ stepLabels[step] }}</span>
      </div>
    </div>

    <!-- Step 1: Subscription -->
    <div v-if="currentStep === 'subscription'" class="wizard-step">
      <div class="step-body">
        <p class="step-question">{{ t('accountWizard.subscription', { backend: backendName }) }}</p>

        <div class="radio-group">
          <label class="radio-card" :class="{ selected: hasSubscription === 'yes' }">
            <input type="radio" v-model="hasSubscription" value="yes" />
            <div class="radio-card-content">
              <span class="radio-card-title">{{ t('accountWizard.yesHaveAccount') }}</span>
              <span class="radio-card-desc">I have credentials and want to register this backend</span>
            </div>
          </label>
          <label class="radio-card" :class="{ selected: hasSubscription === 'no' }">
            <input type="radio" v-model="hasSubscription" value="no" />
            <div class="radio-card-content">
              <span class="radio-card-title">{{ t('accountWizard.noSkip') }}</span>
              <span class="radio-card-desc">I don't have a subscription or want to set it up later</span>
            </div>
          </label>
        </div>

        <!-- Show account fields when "yes" is selected -->
        <Transition name="slide-down">
          <div v-if="hasSubscription === 'yes'" class="account-fields">
            <div class="form-group">
              <label for="wiz-name">{{ t('accountWizard.accountName') }} <span class="required">*</span></label>
              <input
                id="wiz-name"
                v-model="accountName"
                type="text"
                :placeholder="t('accountWizard.accountNamePlaceholder')"
                autofocus
                @input="suggestConfigPath"
              />
            </div>
            <div class="form-group">
              <label for="wiz-email">{{ t('accountWizard.email') }}</label>
              <input
                id="wiz-email"
                v-model="email"
                type="email"
                :placeholder="t('accountWizard.emailPlaceholder')"
              />
              <small>Login email for this account (optional)</small>
            </div>
          </div>
        </Transition>
      </div>
      <div class="step-actions">
        <button class="btn btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button
          class="btn"
          :class="hasSubscription === 'no' ? 'btn-outline' : 'btn-primary'"
          :disabled="!subscriptionValid"
          @click="handleSubscriptionNext"
        >
          {{ hasSubscription === 'no' ? t('accountWizard.noSkip') : t('accountWizard.continueBtn') }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Step 2: CLI Setup -->
    <div v-if="currentStep === 'cli'" class="wizard-step">
      <div class="step-body">
        <!-- CLI status -->
        <div class="status-card" :class="cliInstalled ? 'status-ok' : 'status-warn'">
          <div class="status-icon">
            <template v-if="isCheckingCli">
              <div class="spinner-sm"></div>
            </template>
            <template v-else-if="cliInstalled">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
            </template>
            <template v-else>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </template>
          </div>
          <div class="status-info">
            <span class="status-title">{{ backendName }} CLI</span>
            <span v-if="cliInstalled" class="status-detail">
              {{ t('accountWizard.cliInstalled') }}{{ cliVersion ? ` (${cliVersion})` : '' }}
            </span>
            <span v-else class="status-detail">{{ t('accountWizard.cliNotInstalled') }}</span>
          </div>
          <button
            v-if="!cliInstalled && !isInstallingCli"
            class="btn btn-primary btn-sm"
            @click="installCli"
          >
            {{ t('accountWizard.installCli') }}
          </button>
          <div v-if="isInstallingCli" class="spinner-sm"></div>
        </div>
        <div v-if="installError" class="error-text">{{ installError }}</div>

        <!-- Config directory -->
        <div v-if="configPath" class="config-dir-section">
          <div class="config-dir-label">{{ t('accountWizard.configPath') }}</div>
          <div class="config-dir-path">
            <code>{{ configPath }}</code>
            <button
              v-if="!dirCreated"
              class="btn btn-outline btn-sm"
              :disabled="isCreatingDir"
              @click="createConfigDir"
            >
              {{ isCreatingDir ? t('accountWizard.creating') : t('accountWizard.createDir') }}
            </button>
            <span v-else class="dir-created-badge">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ t('accountWizard.configCreated') }}
            </span>
          </div>
          <div v-if="dirError" class="error-text">{{ dirError }}</div>

          <div class="config-path-edit">
            <button class="btn-link-sm" @click="configPathManuallyEdited = true" v-if="!configPathManuallyEdited">
              {{ t('accountWizard.customizePath') }}
            </button>
            <div v-if="configPathManuallyEdited" class="form-group compact">
              <input
                v-model="configPath"
                type="text"
                :placeholder="`e.g., ~/.${backendType}-personal`"
              />
            </div>
          </div>
        </div>

        <!-- API key env info -->
        <div v-if="apiKeyEnv" class="api-key-info">
          <span class="api-key-label">{{ t('accountWizard.apiKeyEnv') }}</span>
          <code>{{ apiKeyEnv }}</code>
        </div>
      </div>
      <div class="step-actions">
        <button class="btn btn-secondary" @click="goPrev">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {{ t('common.back') }}
        </button>
        <button class="btn btn-primary" @click="goNext">
          {{ t('accountWizard.continueBtn') }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Step 3: Login -->
    <div v-if="currentStep === 'login'" class="wizard-step">
      <div class="step-body">
        <!-- Idle — show start button -->
        <template v-if="loginStatus === 'idle'">
          <p class="step-description">Authenticate your {{ props.backendName }} account via CLI login.</p>
          <button class="btn btn-primary login-start-btn" @click="startCliLogin">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
              <polyline points="10 17 15 12 10 7"/>
              <line x1="15" y1="12" x2="3" y2="12"/>
            </svg>
            Start Login
          </button>
          <div class="skip-note">{{ t('accountWizard.loginOptional') }}</div>
        </template>

        <!-- Connecting -->
        <template v-else-if="loginStatus === 'connecting'">
          <div class="login-status login-connecting">
            <div class="spinner-sm"></div>
            <span>Starting login session...</span>
          </div>
        </template>

        <!-- Streaming — interactive terminal -->
        <template v-else-if="loginStatus === 'streaming'">
          <div class="login-terminal">
            <div class="login-terminal-output">
              <div v-for="(line, i) in loginLines" :key="i" class="terminal-line" v-html="line"></div>
            </div>
            <div v-if="pendingQuestion" class="login-terminal-input">
              <span class="terminal-prompt">&gt;</span>
              <input
                v-model="userResponse"
                class="terminal-input"
                :placeholder="pendingQuestion"
                @keydown.enter="sendResponse"
                autofocus
              />
              <button class="btn btn-sm btn-primary" @click="sendResponse">Send</button>
            </div>
          </div>
        </template>

        <!-- Completed -->
        <template v-else-if="loginStatus === 'completed'">
          <div class="login-status login-completed">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span>Login completed successfully</span>
          </div>
        </template>

        <!-- Error -->
        <template v-else-if="loginStatus === 'error'">
          <div class="login-status login-error">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <circle cx="12" cy="12" r="10"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <span>{{ loginError }}</span>
          </div>
          <button class="btn btn-secondary" style="margin-top: 12px;" @click="loginStatus = 'idle'">Try Again</button>
        </template>
      </div>
      <div class="step-actions">
        <button class="btn btn-secondary" @click="goPrev">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {{ t('common.back') }}
        </button>
        <button class="btn btn-primary" @click="goNext">
          {{ loginStatus === 'idle' ? t('common.skip') : t('accountWizard.continueBtn') }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Step 4: Plan & Save -->
    <div v-if="currentStep === 'plan'" class="wizard-step">
      <div class="step-body">
        <!-- Review card -->
        <div class="review-card">
          <div class="review-row">
            <span class="review-label">{{ t('accountWizard.accountName') }}</span>
            <span class="review-value">{{ accountName }}</span>
          </div>
          <div v-if="email" class="review-row">
            <span class="review-label">{{ t('accountWizard.email') }}</span>
            <span class="review-value">{{ email }}</span>
          </div>
          <div v-if="configPath" class="review-row">
            <span class="review-label">{{ t('accountWizard.configPath') }}</span>
            <code class="review-value">{{ configPath }}</code>
          </div>
          <div v-if="apiKeyEnv" class="review-row">
            <span class="review-label">{{ t('accountWizard.apiKeyEnv') }}</span>
            <code class="review-value">{{ apiKeyEnv }}</code>
          </div>
        </div>

        <div v-if="planOptions.length > 0" class="form-group">
          <label for="wiz-plan">{{ t('accountWizard.plan') }}</label>
          <select id="wiz-plan" v-model="selectedPlan">
            <option value="">{{ t('accountWizard.selectPlan') }}</option>
            <option v-for="opt in planOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
        <div class="form-group checkbox">
          <label>
            <input type="checkbox" v-model="isDefault" />
            {{ t('accountWizard.setDefault') }}
          </label>
        </div>
        <div v-if="saveError" class="error-text">{{ saveError }}</div>
      </div>
      <div class="step-actions">
        <button class="btn btn-secondary" @click="goPrev">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {{ t('common.back') }}
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="saveAccount">
          <div v-if="isSaving" class="spinner-sm"></div>
          {{ isSaving ? t('accountWizard.saving') : t('accountWizard.saveAccount') }}
        </button>
      </div>
    </div>

    <!-- Step 5: Done -->
    <div v-if="currentStep === 'done'" class="wizard-step">
      <div class="step-body done-body">
        <div class="done-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="40" height="40">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
        </div>
        <h4>{{ t('accountWizard.accountCreated') }}</h4>
        <p>{{ t('accountWizard.accountCreatedDesc', { name: accountName, backend: backendName }) }}</p>
        <div class="done-actions">
          <button class="btn btn-outline" @click="addAnotherAccount">
            {{ t('accountWizard.addAnother') }}
          </button>
          <button class="btn btn-primary" @click="emit('done')">
            Done — Next Backend
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wizard-container {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  animation: wizardIn 0.3s ease;
}

@keyframes wizardIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.wizard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
}

.wizard-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.wizard-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.wizard-close:hover {
  color: var(--text-primary);
}

/* Step indicators */
.wizard-steps {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 1rem;
}

.step-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  padding: 0.5rem 0;
  position: relative;
}

.step-indicator.clickable {
  cursor: pointer;
}

.step-indicator::after {
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 1px;
  background: var(--border-default);
}

.step-indicator:last-child::after {
  display: none;
}

.step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  transition: all 0.2s ease;
}

.step-indicator.active .step-number {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.step-indicator.completed .step-number {
  background: var(--accent-emerald);
  color: white;
  border-color: var(--accent-emerald);
}

.step-label {
  font-size: 0.8125rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  transition: color 0.2s ease;
}

.step-indicator.active .step-label {
  color: var(--text-primary);
  font-weight: 500;
}

.step-indicator.completed .step-label {
  color: var(--text-secondary);
}

/* Step body */
.wizard-step {
  animation: stepIn 0.25s ease;
}

@keyframes stepIn {
  from { opacity: 0; transform: translateX(12px); }
  to { opacity: 1; transform: translateX(0); }
}

.step-body {
  min-height: 160px;
}

.step-question {
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 1.25rem 0;
}

.step-description {
  color: var(--text-secondary);
  font-size: 0.875rem;
  margin: 0 0 1rem 0;
}

/* Radio card group */
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.radio-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border: 1.5px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.radio-card:hover {
  border-color: var(--primary-color);
  background: var(--bg-hover, var(--bg-secondary));
}

.radio-card.selected {
  border-color: var(--primary-color);
  background: rgba(99, 102, 241, 0.06);
}

.radio-card input[type="radio"] {
  margin-top: 2px;
  accent-color: var(--primary-color);
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.radio-card-content {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.radio-card-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.radio-card-desc {
  font-size: 0.75rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Account fields transition */
.account-fields {
  padding-top: 0.25rem;
}

.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-8px);
  max-height: 0;
}

.slide-down-enter-to,
.slide-down-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 300px;
}

/* Step actions */
.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

.step-actions .btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

/* Form groups */
.form-group {
  margin-bottom: 1rem;
}

.form-group.compact {
  margin-bottom: 0;
  margin-top: 0.5rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--accent-crimson);
}

.form-group input[type="text"],
.form-group input[type="email"] {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--primary-color);
}

.form-group small {
  display: block;
  margin-top: 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group.checkbox label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  font-weight: 400;
}

.form-group.checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

/* Status card */
.status-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  margin-bottom: 1rem;
}

.status-card.status-ok {
  border-color: rgba(52, 211, 153, 0.3);
}

.status-card.status-warn {
  border-color: rgba(251, 191, 36, 0.3);
}

.status-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.status-card.status-ok .status-icon {
  color: var(--accent-emerald);
}

.status-card.status-warn .status-icon {
  color: var(--accent-amber, #fbbf24);
}

.status-info {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.status-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.status-detail {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

/* Config dir section */
.config-dir-section {
  margin-bottom: 1rem;
}

.config-dir-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.375rem;
}

.config-dir-path {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.config-dir-path code {
  font-family: var(--font-mono, monospace);
  font-size: 0.8125rem;
  color: var(--text-primary);
  flex: 1;
}

.dir-created-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--accent-emerald);
  font-weight: 500;
}

.config-path-edit {
  margin-top: 0.375rem;
}

.btn-link-sm {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  font-family: inherit;
}

.btn-link-sm:hover {
  color: var(--text-secondary);
}

/* API key info */
.api-key-info {
  padding: 0.75rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.api-key-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.api-key-info code {
  font-family: var(--font-mono, monospace);
  font-size: 0.8125rem;
  color: var(--text-primary);
}

/* Login start button */
.login-start-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

/* Login terminal */
.login-terminal {
  background: #0a0a0f;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.login-terminal-output {
  padding: 12px 16px;
  font-family: 'Geist Mono', 'SF Mono', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #a1a1aa;
  max-height: 250px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.terminal-line {
  min-height: 1.2em;
}

.login-terminal-input {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-top: 1px solid var(--border-default);
  background: rgba(255, 255, 255, 0.02);
}

.terminal-prompt {
  color: var(--accent-cyan);
  font-family: 'Geist Mono', monospace;
  font-weight: 600;
  flex-shrink: 0;
}

.terminal-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
  outline: none;
}

.terminal-input::placeholder {
  color: #52525b;
}

.login-connecting {
  color: var(--accent-cyan);
}

/* Login options (kept for potential future use) */
.login-options {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.login-option {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.login-option:hover:not(.disabled) {
  border-color: var(--primary-color);
  background: var(--bg-hover, var(--bg-secondary));
}

.login-option.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-option-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.login-option-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.login-option-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.login-option-desc {
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.login-option-arrow {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* Login status */
.login-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.8125rem;
  margin-bottom: 0.75rem;
}

.login-started {
  background: rgba(96, 165, 250, 0.1);
  color: var(--accent-cyan, #60a5fa);
  border: 1px solid rgba(96, 165, 250, 0.2);
}

.login-error {
  background: var(--accent-crimson-dim, rgba(239, 68, 68, 0.1));
  color: var(--accent-crimson);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.login-completed {
  background: var(--accent-emerald-dim, rgba(52, 211, 153, 0.1));
  color: var(--accent-emerald);
  border: 1px solid rgba(52, 211, 153, 0.2);
}

/* Device code */
.device-code-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  margin-bottom: 0.75rem;
}

.device-code-label {
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.device-code {
  font-family: var(--font-mono, monospace);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--primary-color);
  letter-spacing: 0.1em;
  padding: 0.5rem 1rem;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.skip-note {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-align: center;
  margin-top: 0.5rem;
}

/* Review card */
.review-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.review-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8125rem;
}

.review-label {
  color: var(--text-secondary);
}

.review-value {
  color: var(--text-primary);
  font-weight: 500;
}

code.review-value {
  font-family: var(--font-mono, monospace);
  font-weight: 400;
  font-size: 0.8125rem;
}

/* Done state */
.done-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 2rem 0;
}

.done-icon {
  color: var(--accent-emerald);
  margin-bottom: 1rem;
}

.done-body h4 {
  margin: 0 0 0.5rem 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.done-body p {
  margin: 0 0 1.5rem 0;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.done-actions {
  display: flex;
  gap: 0.75rem;
}

/* Error text */
.error-text {
  font-size: 0.8125rem;
  color: var(--accent-crimson);
  margin-top: 0.375rem;
}

/* Shared button styles */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
  border: none;
}

.btn-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover, var(--bg-secondary));
}

.btn-outline {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-outline:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Spinner */
.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
