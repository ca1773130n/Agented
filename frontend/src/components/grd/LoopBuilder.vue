<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  grdApi,
  ApiError,
  type CreateSessionRequest,
  type CreateRalphSessionRequest,
  type GoalLoopConfig,
  type QualityGate,
  type LoopGate,
  type RalphConfig,
} from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';
import { LOOP_TEMPLATES, type LoopTemplate } from '../../const/loopTemplates';

const props = defineProps<{ projectId: string; cwd?: string }>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'launched', sessionId: string): void;
}>();

const { t } = useI18n();
const showToast = useToast();

const modalRef = ref<HTMLElement | null>(null);
const alwaysOpen = ref(true);
useFocusTrap(modalRef, alwaysOpen);

// The stream-json claude argv — mirrors ProjectSessionPanel.vue:640-660.
// The create_session route requires a non-empty cmd list; goal-loop uses
// the same chat-style stream-json command shape as direct.
const GOAL_LOOP_CMD = [
  'claude',
  '--print',
  '--input-format',
  'stream-json',
  '--output-format',
  'stream-json',
  '--verbose',
  '--include-hook-events',
  '--include-partial-messages',
];

// --- Template / execution-type switch ---------------------------------
const selectedTemplateId = ref<LoopTemplate['id'] | null>(null);
const executionType = ref<'goal_loop' | 'ralph_loop'>('goal_loop');
const isGoalLoop = computed(() => executionType.value === 'goal_loop');

// --- Form refs --------------------------------------------------------
// Goal/task
const goal = ref('');
const taskDescription = ref('');
const checkCmd = ref('');

// Exit budgets. ``v-model`` on a ``type="number"`` input casts to a
// number; an empty input stays the empty string. Type the refs as the
// union so both states are valid and ``numOrUndef`` handles each.
const maxIterations = ref<string | number>('');
const maxWallSeconds = ref<string | number>('');
const maxCostUsd = ref<string | number>('');
const maxTokens = ref<string | number>('');
const stagnationNoProgressFor = ref<string | number>('');

// Ralph-only
const completionPromise = ref('COMPLETE');

// Quality gate
const gateKind = ref<QualityGate['kind']>('llm_judge');
const metricName = ref('');
const threshold = ref<string | number>('');
const comparator = ref<NonNullable<QualityGate['comparator']>>('>=');
const rubric = ref('');
const judgeVersion = ref('');
const minConfidence = ref<string | number>('');

// State & context
const contextPolicy = ref<'carry' | 'reset'>('carry');
const sandbox = ref<'isolated' | 'inherit'>('isolated');
const humanGateMode = ref<LoopGate['mode']>('off');
const gateEveryN = ref<string | number>('');

// Judge
const judgeBackendKind = ref<NonNullable<GoalLoopConfig['judge_backend_kind']>>('claude');
const judgeModelOverride = ref('');

// Account (goal_loop only)
const allowedAccounts = ref<{ account_id: string; created_at: string }[]>([]);
const selectedAccountId = ref('');
const yolo = ref(false);

const isSubmitting = ref(false);

// --- Helpers ----------------------------------------------------------
// v-model on ``<input type="number">`` casts the value to a number, so
// these refs can hold either a string (text inputs) or a number. Coerce
// to a string before trimming so both paths are safe.
function numOrUndef(s: string | number): number | undefined {
  if (typeof s === 'number') return Number.isFinite(s) ? s : undefined;
  const v = String(s).trim();
  if (!v) return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function strOrUndef(s: string | number): string | undefined {
  const v = String(s).trim();
  return v ? v : undefined;
}

function applyTemplate(tpl: LoopTemplate) {
  selectedTemplateId.value = tpl.id;
  executionType.value = tpl.executionType;

  if (tpl.executionType === 'ralph_loop') {
    const c = tpl.config as Partial<RalphConfig>;
    taskDescription.value = c.task_description ?? '';
    maxIterations.value = c.max_iterations != null ? String(c.max_iterations) : '';
    stagnationNoProgressFor.value =
      c.no_progress_threshold != null ? String(c.no_progress_threshold) : '';
    completionPromise.value = c.completion_promise ?? 'COMPLETE';
    return;
  }

  const c = tpl.config as Partial<GoalLoopConfig>;
  goal.value = c.goal ?? '';
  checkCmd.value = c.check_cmd ?? '';
  maxIterations.value = c.max_iterations != null ? String(c.max_iterations) : '';
  maxWallSeconds.value = c.max_wall_seconds != null ? String(c.max_wall_seconds) : '';
  maxCostUsd.value = c.max_cost_usd != null ? String(c.max_cost_usd) : '';
  maxTokens.value = c.max_tokens != null ? String(c.max_tokens) : '';
  stagnationNoProgressFor.value =
    c.stagnation_no_progress_for != null ? String(c.stagnation_no_progress_for) : '';
  contextPolicy.value = c.context_policy ?? 'carry';
  sandbox.value = c.sandbox ?? 'isolated';
  judgeBackendKind.value = c.judge_backend_kind ?? 'claude';
  judgeModelOverride.value = c.judge_model_override ?? '';
  humanGateMode.value = c.human_gate?.mode ?? 'off';
  gateEveryN.value = c.human_gate?.n != null ? String(c.human_gate.n) : '';

  const qg = c.quality_gate;
  gateKind.value = qg?.kind ?? 'llm_judge';
  metricName.value = qg?.metric_name ?? '';
  threshold.value = qg?.threshold != null ? String(qg.threshold) : '';
  comparator.value = qg?.comparator ?? '>=';
  rubric.value = qg?.rubric ?? '';
  judgeVersion.value = qg?.judge_version ?? '';
  minConfidence.value = qg?.min_confidence != null ? String(qg.min_confidence) : '';
}

const hasGoalOrTask = computed(() =>
  isGoalLoop.value ? goal.value.trim().length > 0 : taskDescription.value.trim().length > 0
);

const accountSatisfied = computed(
  () => !isGoalLoop.value || yolo.value || selectedAccountId.value.length > 0
);

const canLaunch = computed(
  () => selectedTemplateId.value != null && hasGoalOrTask.value && accountSatisfied.value
);

function buildGoalLoopConfig(): GoalLoopConfig {
  const cfg: GoalLoopConfig = { goal: goal.value.trim() };

  const cc = strOrUndef(checkCmd.value);
  if (cc !== undefined) cfg.check_cmd = cc;

  const mi = numOrUndef(maxIterations.value);
  if (mi !== undefined) cfg.max_iterations = mi;
  const mw = numOrUndef(maxWallSeconds.value);
  if (mw !== undefined) cfg.max_wall_seconds = mw;
  const mc = numOrUndef(maxCostUsd.value);
  if (mc !== undefined) cfg.max_cost_usd = mc;
  const mt = numOrUndef(maxTokens.value);
  if (mt !== undefined) cfg.max_tokens = mt;
  const st = numOrUndef(stagnationNoProgressFor.value);
  if (st !== undefined) cfg.stagnation_no_progress_for = st;

  cfg.context_policy = contextPolicy.value;
  cfg.sandbox = sandbox.value;
  cfg.judge_backend_kind = judgeBackendKind.value;
  const jmo = strOrUndef(judgeModelOverride.value);
  if (jmo !== undefined) cfg.judge_model_override = jmo;

  // Quality gate — only the fields relevant to the selected kind.
  const gate: QualityGate = { kind: gateKind.value };
  if (gateKind.value === 'metric') {
    const mn = strOrUndef(metricName.value);
    if (mn !== undefined) gate.metric_name = mn;
    const th = numOrUndef(threshold.value);
    if (th !== undefined) gate.threshold = th;
    gate.comparator = comparator.value;
  } else if (gateKind.value === 'llm_judge') {
    const rb = strOrUndef(rubric.value);
    if (rb !== undefined) gate.rubric = rb;
    const jv = strOrUndef(judgeVersion.value);
    if (jv !== undefined) gate.judge_version = jv;
    const conf = numOrUndef(minConfidence.value);
    if (conf !== undefined) gate.min_confidence = conf;
  }
  cfg.quality_gate = gate;

  // Human gate.
  if (humanGateMode.value === 'every_n') {
    cfg.human_gate = { mode: 'every_n', n: numOrUndef(gateEveryN.value) ?? 1 };
  } else if (humanGateMode.value === 'on_exit') {
    cfg.human_gate = { mode: 'on_exit' };
  }

  return cfg;
}

function buildRalphConfig(): RalphConfig {
  return {
    task_description: taskDescription.value.trim(),
    max_iterations: numOrUndef(maxIterations.value) ?? 50,
    no_progress_threshold: numOrUndef(stagnationNoProgressFor.value) ?? 3,
    completion_promise: strOrUndef(completionPromise.value) ?? 'COMPLETE',
  };
}

async function launch() {
  if (selectedTemplateId.value == null) return;

  if (!hasGoalOrTask.value) {
    showToast(t('loopBuilder.goalRequired'), 'error');
    return;
  }
  if (isGoalLoop.value && !accountSatisfied.value) {
    showToast(t('loopBuilder.accountRequired'), 'error');
    return;
  }

  isSubmitting.value = true;
  try {
    let sessionId: string;
    if (executionType.value === 'ralph_loop') {
      const req: CreateRalphSessionRequest = {
        ...(props.cwd ? { cwd: props.cwd } : {}),
        ralph_config: buildRalphConfig(),
      };
      const res = await grdApi.createRalphSession(props.projectId, req);
      sessionId = res.session_id;
    } else {
      const req: CreateSessionRequest = {
        cmd: GOAL_LOOP_CMD,
        execution_type: 'goal_loop',
        execution_mode: 'interactive',
        stream_json: true,
        use_pty: false,
        ...(props.cwd ? { cwd: props.cwd } : {}),
        ...(yolo.value ? { yolo_mode: true } : { account_id: selectedAccountId.value }),
        goal_loop_config: buildGoalLoopConfig(),
      };
      const res = await grdApi.createSession(props.projectId, req);
      sessionId = res.session_id;
    }
    showToast(t('loopBuilder.launched'), 'success');
    emit('launched', sessionId);
    emit('close');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('loopBuilder.launchFailed');
    showToast(message, 'error');
  } finally {
    isSubmitting.value = false;
  }
}

onMounted(async () => {
  try {
    const res = await grdApi.listAllowedAccounts(props.projectId);
    allowedAccounts.value = res.allowed_accounts ?? [];
    if (allowedAccounts.value.length > 0) {
      selectedAccountId.value = allowedAccounts.value[0].account_id;
    }
  } catch {
    allowedAccounts.value = [];
  }
});
</script>

<template>
  <div
    ref="modalRef"
    class="modal-overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title-loop-builder"
    tabindex="-1"
    @click.self="emit('close')"
    @keydown.escape="emit('close')"
  >
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 2v6h-6" />
            <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
            <path d="M3 22v-6h6" />
            <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
          </svg>
        </div>
        <div>
          <h3 id="modal-title-loop-builder">{{ t('loopBuilder.title') }}</h3>
          <p class="modal-subtitle">{{ t('loopBuilder.subtitle') }}</p>
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <form @submit.prevent="launch" novalidate>
        <!-- Template picker -->
        <div class="form-group">
          <label>{{ t('loopBuilder.pickTemplate') }}</label>
          <div class="template-grid">
            <button
              v-for="tpl in LOOP_TEMPLATES"
              :key="tpl.id"
              type="button"
              class="template-card"
              :class="{ selected: selectedTemplateId === tpl.id }"
              :data-testid="`tpl-${tpl.id}`"
              @click="applyTemplate(tpl)"
            >
              <span class="template-label">{{ t(tpl.labelKey) }}</span>
              <span class="template-desc">{{ t(tpl.descKey) }}</span>
            </button>
          </div>
        </div>

        <template v-if="selectedTemplateId">
          <!-- Goal / task -->
          <div class="form-section">
            <h4>{{ t('loopBuilder.secGoal') }}</h4>
            <div v-if="isGoalLoop" class="form-group">
              <label>{{ t('loopBuilder.goal') }}</label>
              <textarea v-model="goal" data-testid="lb-goal"></textarea>
            </div>
            <div v-else class="form-group">
              <label>{{ t('loopBuilder.task') }}</label>
              <textarea v-model="taskDescription" data-testid="lb-task"></textarea>
            </div>
            <div v-if="isGoalLoop" class="form-group">
              <label>{{ t('loopBuilder.checkCmd') }}</label>
              <input type="text" v-model="checkCmd" data-testid="lb-check-cmd" />
            </div>
          </div>

          <!-- Exit budgets -->
          <div class="form-section">
            <h4>{{ t('loopBuilder.secExit') }}</h4>
            <div class="form-row">
              <div class="form-group">
                <label>{{ t('loopConfig.stagnation') }}</label>
                <input type="number" min="0" v-model="maxIterations" data-testid="lb-max-iters" />
              </div>
              <div class="form-group">
                <label>{{ t('loopConfig.stagnation') }}</label>
                <input
                  type="number"
                  min="0"
                  v-model="stagnationNoProgressFor"
                  data-testid="lb-stagnation"
                />
              </div>
            </div>
            <div v-if="isGoalLoop" class="form-row">
              <div class="form-group">
                <label>{{ t('loopConfig.tokenBudget') }}</label>
                <input type="number" min="0" v-model="maxTokens" data-testid="lb-max-tokens" />
              </div>
              <div class="form-group">
                <label>max_wall_seconds</label>
                <input type="number" min="0" v-model="maxWallSeconds" data-testid="lb-max-wall" />
              </div>
            </div>
            <div v-if="isGoalLoop" class="form-group">
              <label>max_cost_usd</label>
              <input type="number" min="0" step="0.01" v-model="maxCostUsd" data-testid="lb-max-cost" />
            </div>
            <div v-else class="form-group">
              <label>{{ t('loopBuilder.task') }}</label>
              <input type="text" v-model="completionPromise" data-testid="lb-completion-promise" />
            </div>
          </div>

          <!-- Quality gate (goal_loop only) -->
          <div v-if="isGoalLoop" class="form-section">
            <h4>{{ t('loopBuilder.secGate') }}</h4>
            <div class="form-group">
              <label>{{ t('loopBuilder.gateKind') }}</label>
              <select v-model="gateKind" data-testid="lb-gate-kind">
                <option value="test_pass">{{ t('loopConfig.gateTestPass') }}</option>
                <option value="metric">{{ t('loopConfig.gateMetric') }}</option>
                <option value="llm_judge">{{ t('loopConfig.gateLlmJudge') }}</option>
              </select>
            </div>
            <div v-if="gateKind === 'metric'" class="form-row">
              <div class="form-group">
                <label>{{ t('loopBuilder.metricName') }}</label>
                <input type="text" v-model="metricName" data-testid="lb-metric-name" />
              </div>
              <div class="form-group">
                <label>{{ t('loopBuilder.threshold') }}</label>
                <input type="number" step="any" v-model="threshold" data-testid="lb-threshold" />
              </div>
              <div class="form-group">
                <label>{{ t('loopBuilder.comparator') }}</label>
                <select v-model="comparator" data-testid="lb-comparator">
                  <option value=">=">&gt;=</option>
                  <option value="<=">&lt;=</option>
                  <option value=">">&gt;</option>
                  <option value="<">&lt;</option>
                  <option value="==">==</option>
                </select>
              </div>
            </div>
            <template v-if="gateKind === 'llm_judge'">
              <div class="form-group">
                <label>{{ t('loopBuilder.rubric') }}</label>
                <textarea v-model="rubric" data-testid="lb-rubric"></textarea>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>{{ t('loopBuilder.judgeVersion') }}</label>
                  <input type="text" v-model="judgeVersion" data-testid="lb-judge-version" />
                </div>
                <div class="form-group">
                  <label>{{ t('loopBuilder.minConfidence') }}</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    v-model="minConfidence"
                    data-testid="lb-min-confidence"
                  />
                </div>
              </div>
            </template>
          </div>

          <!-- State & context -->
          <div class="form-section">
            <h4>{{ t('loopBuilder.secState') }}</h4>
            <div v-if="isGoalLoop" class="form-row">
              <div class="form-group">
                <label>{{ t('loopConfig.contextPolicy') }}</label>
                <select v-model="contextPolicy" data-testid="lb-context-policy">
                  <option value="carry">{{ t('loopConfig.contextCarry') }}</option>
                  <option value="reset">{{ t('loopConfig.contextReset') }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>{{ t('loopConfig.sandbox') }}</label>
                <select v-model="sandbox" data-testid="lb-sandbox">
                  <option value="isolated">{{ t('loopConfig.sandboxIsolated') }}</option>
                  <option value="inherit">{{ t('loopConfig.sandboxInherit') }}</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>{{ t('loopBuilder.humanGate') }}</label>
                <select v-model="humanGateMode" data-testid="lb-human-gate">
                  <option value="off">off</option>
                  <option value="every_n">every_n</option>
                  <option value="on_exit">on_exit</option>
                </select>
              </div>
              <div v-if="humanGateMode === 'every_n'" class="form-group">
                <label>{{ t('loopBuilder.gateEveryN') }}</label>
                <input type="number" min="1" v-model="gateEveryN" data-testid="lb-gate-n" />
              </div>
            </div>
          </div>

          <!-- Judge (goal_loop only) -->
          <div v-if="isGoalLoop" class="form-section">
            <h4>{{ t('loopBuilder.secJudge') }}</h4>
            <div class="form-row">
              <div class="form-group">
                <label>{{ t('loopBuilder.secJudge') }}</label>
                <select v-model="judgeBackendKind" data-testid="lb-judge-backend">
                  <option value="claude">claude</option>
                  <option value="codex">codex</option>
                  <option value="gemini">gemini</option>
                  <option value="opencode">opencode</option>
                </select>
              </div>
              <div class="form-group">
                <label>{{ t('loopConfig.judgeVersion') }}</label>
                <input type="text" v-model="judgeModelOverride" data-testid="lb-judge-model" />
              </div>
            </div>
          </div>

          <!-- Account (goal_loop only) -->
          <div v-if="isGoalLoop" class="form-section">
            <h4>{{ t('loopBuilder.account') }}</h4>
            <div class="form-group">
              <label>{{ t('loopBuilder.account') }}</label>
              <select v-model="selectedAccountId" :disabled="yolo" data-testid="lb-account">
                <option v-for="acc in allowedAccounts" :key="acc.account_id" :value="acc.account_id">
                  {{ acc.account_id }}
                </option>
              </select>
            </div>
            <label class="toggle-label">
              <input type="checkbox" v-model="yolo" data-testid="lb-yolo" />
              {{ t('loopBuilder.yolo') }}
            </label>
            <p v-if="!yolo && allowedAccounts.length === 0" class="field-hint">
              {{ t('loopBuilder.noAccount') }}
            </p>
          </div>
        </template>

        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" data-testid="lb-cancel" @click="emit('close')">
            {{ t('loopBuilder.cancel') }}
          </button>
          <button
            type="button"
            class="btn btn-primary"
            data-testid="lb-launch"
            :disabled="!canLaunch || isSubmitting"
            @click="launch"
          >
            {{ t('loopBuilder.launch') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 0;
  width: 90%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
}

.modal-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-cyan-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent-cyan);
}

.modal-header h3 {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
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

form {
  padding: 24px;
}

.form-section {
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  margin-bottom: 16px;
}

.form-section h4 {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  margin-bottom: 12px;
}

.form-group label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group textarea {
  min-height: 72px;
  resize: vertical;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.template-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: left;
  padding: 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.template-card:hover {
  border-color: var(--border-strong, var(--accent-cyan));
}

.template-card.selected {
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.template-label {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.template-desc {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.toggle-label input {
  width: auto;
}

.field-hint {
  margin-top: 8px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}

.btn {
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
}

.btn-primary {
  background: var(--text-secondary);
  color: var(--bg-primary);
}

.btn-primary:hover:not(:disabled) {
  background: var(--text-primary);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
</style>
