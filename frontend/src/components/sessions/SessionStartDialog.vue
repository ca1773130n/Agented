<script setup lang="ts">
/**
 * Pre-flight dialog shown when the user clicks "Start session" on
 * the project Sessions panel (v0.7.57).
 *
 * Captures, in one place:
 *   * **Session name** + **auto-title** toggle — when auto is on, the
 *     name input is disabled and the backend fills the title (today
 *     a simple fallback; a follow-up will replace it with a short
 *     claude-generated summary).
 *   * **Yolo mode** toggle — appends ``--dangerously-skip-permissions``
 *     and bypasses the (forthcoming) per-project allowed-accounts
 *     whitelist. Defaults to the user's
 *     ``session_default_yolo`` setting on dialog open.
 *   * **Execution type** — direct / ralph_loop / team_spawn. Replaces
 *     the inline ``ExecutionTypeSelector`` chip on the panel header
 *     for new sessions.
 *
 * Emits ``confirm`` with the resolved configuration. The parent panel
 * is responsible for actually calling ``session.startSession`` —
 * separating the dialog from the start logic keeps this component
 * reusable for any future "kick off a new session" entry point.
 */
import { ref, computed, watch, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useFocusTrap } from '../../composables/useFocusTrap';
import {
  settingsApi,
  grdApi,
  projectApi,
  listGroupedBackends,
  getGroupedBackend,
} from '../../services/api';
import type {
  ForgeAttachment,
  ForgeBinding,
  ForgeBindingKind,
} from '../../services/api/projects';
import SessionContextTray from './SessionContextTray.vue';

const props = defineProps<{
  visible: boolean;
  projectId: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (
    e: 'confirm',
    payload: {
      name: string | null;
      autoTitle: boolean;
      yoloMode: boolean;
      executionType: 'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop';
      accountId: string | null;
      // v0.7.73 — Forge context picks. ``forgeOverrides`` rides
      // into ``create_session`` via ``request.forge_context`` so
      // bindings compile into ``--append-system-prompt`` + overlay
      // for the first turn. ``firstPromptAttachments`` flows into
      // the panel's ``pendingAttachments`` so they prepend the
      // first user message — claude's chat session is stream-json
      // over stdin, so per-prompt context must arrive via the
      // input route, not via the spawn argv.
      forgeOverrides: {
        disabled_binding_ids: number[];
        additions: Array<{
          kind: ForgeBindingKind;
          asset_id: string;
          role?: string | null;
        }>;
      };
      firstPromptAttachments: ForgeAttachment[];
      // v0.7.74 — only populated when executionType === 'goal_loop'.
      goalLoopConfig: {
        goal: string;
        checkCmd: string | null;
        maxIterations: number;
        maxWallSeconds: number;
        judgeBackendKind: 'claude' | 'codex' | 'gemini' | 'opencode';
        judgeModelOverride: string | null;
        // v0.7.87 — Ouroboros mode. Default true (matches the
        // backend default); operator can untick to fall back to
        // the legacy plain-continue judge.
        ouroboros: boolean;
      } | null;
    },
  ): void;
}>();

const { t } = useI18n();

const dialogRef = ref<HTMLElement | null>(null);
const isOpen = computed(() => props.visible);
useFocusTrap(dialogRef, isOpen);

const name = ref('');
const autoTitle = ref(true);
const yoloMode = ref(false);
const executionType = ref<'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop'>('direct');

// v0.7.74 — goal-loop config. Defaults match the spec; only sent
// when execution type is ``goal_loop`` (other types ignore the
// field server-side, but we omit it client-side for tidiness).
const goalText = ref('');
const goalCheckCmd = ref('');
const goalMaxIterations = ref(20);
const goalMaxWallMinutes = ref(30);
const goalJudgeBackend = ref<'claude' | 'codex' | 'gemini' | 'opencode'>('claude');
const goalJudgeModelOverride = ref('');
// v0.7.87 — Ouroboros mode toggle. Default true so newly-created
// goal-loop sessions inherit the hypothesis-driven judge loop.
// Operators can untick to fall back to the legacy binary judge
// (useful when the agent backend doesn't follow markdown markers
// reliably).
const goalOuroboros = ref(true);

const isGoalLoop = computed(() => executionType.value === 'goal_loop');
const goalCanSubmit = computed(() => {
  if (!isGoalLoop.value) return true;
  if (goalText.value.trim().length < 5) return false;
  if (goalMaxIterations.value < 1 || goalMaxIterations.value > 100) return false;
  if (goalMaxWallMinutes.value < 1 || goalMaxWallMinutes.value > 240) return false;
  return true;
});
const userDefaultYolo = ref(false);
const isLoadingDefaults = ref(false);

// v0.7.58 — account picker (shown when yolo is off). The list comes
// from ``listAllowedAccounts`` for this project; backend rejects
// non-yolo sessions whose ``account_id`` isn't whitelisted, so the
// dialog stays in sync with the canonical gate.
interface AccountOption {
  id: string;
  account_name: string;
  backend_type: string;
}
const allowedAccountIds = ref<string[]>([]);
const allAccounts = ref<AccountOption[]>([]);
const accountId = ref<string>('');
const isLoadingAccounts = ref(false);

const allowedAccountOptions = computed<AccountOption[]>(() => {
  const idSet = new Set(allowedAccountIds.value);
  return allAccounts.value.filter((a) => idSet.has(a.id));
});

// v0.7.73 — Forge context state. Sticky project bindings are
// loaded fresh on each open; the operator can opt out per-binding
// (the toggle flips the binding ID into ``disabledBindingIds``)
// and can add session-only extras (kept in ``sessionOnlyAdditions``,
// never persisted). First-prompt attachments use the same shape as
// the per-prompt tray so the operator sees one consistent UX.
const inheritedBindings = ref<ForgeBinding[]>([]);
const isLoadingBindings = ref(false);
const disabledBindingIds = ref<Set<number>>(new Set());
const sessionOnlyAdditions = ref<
  Array<{ kind: ForgeBindingKind; asset_id: string; role?: string | null }>
>([]);
const firstPromptAttachments = ref<ForgeAttachment[]>([]);
const addBindingKind = ref<ForgeBindingKind>('rule');
const addBindingAssetId = ref('');

const FORGE_KIND_LABELS = computed<Record<ForgeBindingKind, string>>(() => ({
  rule: t('sessionStartDialog.forgeKind.rule'),
  skill: t('sessionStartDialog.forgeKind.skill'),
  hook: t('sessionStartDialog.forgeKind.hook'),
  command: t('sessionStartDialog.forgeKind.command'),
  mcp_server: 'MCP Server',
  plugin: t('sessionStartDialog.forgeKind.plugin'),
}));

const hasAnyForgeState = computed(
  () =>
    inheritedBindings.value.length > 0 ||
    sessionOnlyAdditions.value.length > 0 ||
    firstPromptAttachments.value.length > 0,
);

function toggleBinding(b: ForgeBinding) {
  const next = new Set(disabledBindingIds.value);
  if (next.has(b.id)) next.delete(b.id);
  else next.add(b.id);
  disabledBindingIds.value = next;
}

function isBindingEnabled(b: ForgeBinding) {
  return !disabledBindingIds.value.has(b.id);
}

function addSessionOnlyBinding() {
  const asset = addBindingAssetId.value.trim();
  if (!asset) return;
  sessionOnlyAdditions.value = [
    ...sessionOnlyAdditions.value,
    { kind: addBindingKind.value, asset_id: asset },
  ];
  addBindingAssetId.value = '';
}

function removeSessionOnlyAt(idx: number) {
  const next = sessionOnlyAdditions.value.slice();
  next.splice(idx, 1);
  sessionOnlyAdditions.value = next;
}

async function loadForgeBindings() {
  isLoadingBindings.value = true;
  try {
    const res = await projectApi.listForgeBindings(props.projectId);
    inheritedBindings.value = res.bindings;
  } catch {
    inheritedBindings.value = [];
  } finally {
    isLoadingBindings.value = false;
  }
}

const canSubmit = computed(() => {
  if (isLoadingDefaults.value || isLoadingAccounts.value) return false;
  // When yolo is off, an account must be picked AND it must be in
  // the project's whitelist (the select only offers those, but a
  // race where the whitelist becomes empty mid-flight would leave
  // accountId empty).
  if (!yoloMode.value && !accountId.value) return false;
  // v0.7.74 — goal-loop validation gates Start until the goal is
  // non-empty and the caps are in range.
  if (!goalCanSubmit.value) return false;
  return true;
});

/** Refresh dialog state from the user's stored defaults every time
 * the dialog opens — so toggling the ``session_default_yolo`` setting
 * on the Settings page takes effect on the very next start without
 * requiring a page reload. */
async function hydrateDefaults() {
  isLoadingDefaults.value = true;
  try {
    const result = await settingsApi.get('session_default_yolo');
    // Settings come back as strings — empty / "false" / "0" → off,
    // anything truthy → on. Conservative: any non-empty non-falsy
    // string opts in.
    const raw = (result.value || '').trim().toLowerCase();
    userDefaultYolo.value = raw === 'true' || raw === '1' || raw === 'yes';
  } catch {
    userDefaultYolo.value = false;
  } finally {
    isLoadingDefaults.value = false;
  }
}

async function loadAccounts() {
  isLoadingAccounts.value = true;
  try {
    const [whitelistRes, backendsRes] = await Promise.all([
      grdApi.listAllowedAccounts(props.projectId),
      listGroupedBackends(),
    ]);
    allowedAccountIds.value = (whitelistRes.allowed_accounts ?? []).map(
      (a) => a.account_id,
    );
    // Same fan-out as ProjectAllowedAccountsPanel: friendly names
    // come from the sidecar's backend list, not from the whitelist
    // (which only has account_ids).
    const detailResults = await Promise.all(
      (backendsRes.backends || []).map((b) => getGroupedBackend(b.id).catch(() => null)),
    );
    const flat: AccountOption[] = [];
    detailResults.forEach((detail, idx) => {
      if (!detail) return;
      for (const acct of detail.accounts || []) {
        flat.push({
          id: acct.id,
          account_name: acct.account_name,
          backend_type: backendsRes.backends[idx].type,
        });
      }
    });
    allAccounts.value = flat;
    // Auto-pick the first whitelisted account so the user doesn't
    // have to make a second click when there's only one option.
    const options = flat.filter((a) => allowedAccountIds.value.includes(a.id));
    accountId.value = options.length === 1 ? options[0].id : '';
  } catch {
    allowedAccountIds.value = [];
    allAccounts.value = [];
    accountId.value = '';
  } finally {
    isLoadingAccounts.value = false;
  }
}

watch(
  () => props.visible,
  (open) => {
    if (open) {
      // Reset form for the new start.
      name.value = '';
      autoTitle.value = true;
      executionType.value = 'direct';
      accountId.value = '';
      disabledBindingIds.value = new Set();
      sessionOnlyAdditions.value = [];
      firstPromptAttachments.value = [];
      addBindingKind.value = 'rule';
      addBindingAssetId.value = '';
      goalText.value = '';
      goalCheckCmd.value = '';
      goalMaxIterations.value = 20;
      goalMaxWallMinutes.value = 30;
      goalJudgeBackend.value = 'claude';
      goalJudgeModelOverride.value = '';
      goalOuroboros.value = true;
      hydrateDefaults().then(() => {
        yoloMode.value = userDefaultYolo.value;
      });
      loadAccounts();
      loadForgeBindings();
    }
  },
);

onMounted(() => {
  // Prefetch so the first time the dialog opens we already know the
  // yolo default + the project's whitelist + the inherited bindings.
  hydrateDefaults();
  loadAccounts();
  loadForgeBindings();
});

function onSubmit() {
  // When auto-title is on, blank out the name field — the backend
  // treats null as "please auto-fill". An auto-title-on session that
  // somehow lands with text is treated as user-provided (defensive).
  const resolvedName = autoTitle.value ? null : name.value.trim() || null;
  emit('confirm', {
    name: resolvedName,
    autoTitle: autoTitle.value,
    yoloMode: yoloMode.value,
    executionType: executionType.value,
    // Yolo bypasses the whitelist on the server too — no need to
    // send account_id; backend will auto-pick.
    accountId: yoloMode.value ? null : accountId.value || null,
    forgeOverrides: {
      disabled_binding_ids: Array.from(disabledBindingIds.value),
      additions: sessionOnlyAdditions.value.slice(),
    },
    firstPromptAttachments: firstPromptAttachments.value.slice(),
    goalLoopConfig: isGoalLoop.value
      ? {
          goal: goalText.value.trim(),
          checkCmd: goalCheckCmd.value.trim() || null,
          maxIterations: goalMaxIterations.value,
          maxWallSeconds: goalMaxWallMinutes.value * 60,
          judgeBackendKind: goalJudgeBackend.value,
          judgeModelOverride: goalJudgeModelOverride.value.trim() || null,
          ouroboros: goalOuroboros.value,
        }
      : null,
  });
}
</script>

<template>
  <div
    v-if="visible"
    ref="dialogRef"
    class="modal-overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title-session-start"
    tabindex="-1"
    @click.self="emit('close')"
    @keydown.escape="emit('close')"
  >
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
        </div>
        <div>
          <h3 id="modal-title-session-start">{{ t('sessionStartDialog.title') }}</h3>
          <p class="modal-subtitle">
            {{ t('sessionStartDialog.subtitle') }}
          </p>
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <form @submit.prevent="onSubmit">
        <div class="form-group">
          <div class="label-row">
            <label for="session-name-input">{{ t('sessionStartDialog.sessionName') }}</label>
            <label class="inline-toggle">
              <input type="checkbox" v-model="autoTitle" />
              <span>{{ t('sessionStartDialog.autoTitle') }}</span>
            </label>
          </div>
          <input
            id="session-name-input"
            type="text"
            v-model="name"
            :disabled="autoTitle"
            :placeholder="t('sessionStartDialog.namePlaceholder')"
          />
          <p class="form-hint">
            {{ t('sessionStartDialog.nameHint') }}
          </p>
        </div>

        <div class="form-group">
          <label>{{ t('sessionStartDialog.executionType') }}</label>
          <select v-model="executionType">
            <option value="direct">{{ t('sessionStartDialog.execDirect') }}</option>
            <option value="ralph_loop">{{ t('sessionStartDialog.execRalph') }}</option>
            <option value="team_spawn">{{ t('sessionStartDialog.execTeam') }}</option>
            <option value="goal_loop">{{ t('sessionStartDialog.execGoal') }}</option>
          </select>
          <p v-if="executionType === 'ralph_loop'" class="form-hint">
            {{ t('sessionStartDialog.ralphHintPre') }} <code>ralph-wiggum</code> {{ t('sessionStartDialog.ralphHintPost') }}
          </p>
          <p v-else-if="executionType === 'team_spawn'" class="form-hint">
            {{ t('sessionStartDialog.teamHintPre') }}
            <code>CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1</code> {{ t('sessionStartDialog.teamHintPost') }}
          </p>
          <p v-else-if="executionType === 'goal_loop'" class="form-hint">
            {{ t('sessionStartDialog.goalHint') }}
          </p>
        </div>

        <!-- v0.7.74 — Goal-loop config. Reveals when the execution
             type is ``goal_loop``; collapses otherwise so the
             dialog stays compact for the common direct case. -->
        <div v-if="isGoalLoop" class="form-group goal-loop-config">
          <label for="goal-text">{{ t('sessionStartDialog.goal') }}</label>
          <textarea
            id="goal-text"
            v-model="goalText"
            class="goal-textarea"
            :placeholder="t('sessionStartDialog.goalPlaceholder')"
            rows="3"
          ></textarea>
          <p v-if="goalText.trim().length > 0 && goalText.trim().length < 5"
             class="form-hint goal-error">
            {{ t('sessionStartDialog.goalMinLength') }}
          </p>

          <label for="goal-check-cmd" class="goal-secondary-label">
            {{ t('sessionStartDialog.checkCommand') }}
          </label>
          <input
            id="goal-check-cmd"
            v-model="goalCheckCmd"
            class="goal-mono-input"
            type="text"
            :placeholder="t('sessionStartDialog.checkCommandPlaceholder')"
          />
          <p class="form-hint">
            {{ t('sessionStartDialog.checkCommandHint') }}
          </p>

          <div class="goal-caps-row">
            <div class="goal-cap-field">
              <label for="goal-max-iter">{{ t('sessionStartDialog.maxIterations') }}</label>
              <input
                id="goal-max-iter"
                v-model.number="goalMaxIterations"
                type="number"
                min="1"
                max="100"
              />
            </div>
            <div class="goal-cap-field">
              <label for="goal-max-wall">{{ t('sessionStartDialog.maxWallTime') }}</label>
              <input
                id="goal-max-wall"
                v-model.number="goalMaxWallMinutes"
                type="number"
                min="1"
                max="240"
              />
            </div>
          </div>

          <label for="goal-judge-backend" class="goal-secondary-label">
            {{ t('sessionStartDialog.judgeBackend') }}
          </label>
          <select id="goal-judge-backend" v-model="goalJudgeBackend">
            <option value="claude">Claude (claude-haiku-4-5)</option>
            <option value="codex">Codex (o4-mini)</option>
            <option value="gemini">Gemini (gemini-2.5-flash)</option>
            <option value="opencode">OpenCode (auto)</option>
          </select>
          <input
            v-model="goalJudgeModelOverride"
            class="goal-mono-input goal-model-override"
            type="text"
            :placeholder="t('sessionStartDialog.modelOverridePlaceholder')"
          />
          <p class="form-hint">
            {{ t('sessionStartDialog.judgeBackendHint') }}
          </p>
        </div>

        <!-- v0.7.87 — Ouroboros mode toggle. Default-on so the
             frontend-created session matches the backend's
             v0.7.87 default; operator can untick to fall back to
             the legacy binary judge. -->
        <div class="form-group toggle-group">
          <label class="row-toggle">
            <input type="checkbox" v-model="goalOuroboros" />
            <span class="toggle-body">
              <span class="toggle-title">{{ t('sessionStartDialog.ouroborosTitle') }}</span>
              <span class="toggle-sub">
                {{ t('sessionStartDialog.ouroborosPre') }}
                <code>**Hypothesis:**</code> +
                <code>**Predicted outcome:**</code> {{ t('sessionStartDialog.ouroborosPost') }}
              </span>
            </span>
          </label>
        </div>

        <div class="form-group toggle-group">
          <label class="row-toggle">
            <input type="checkbox" v-model="yoloMode" />
            <span class="toggle-body">
              <span class="toggle-title">{{ t('sessionStartDialog.yoloTitle') }}</span>
              <span class="toggle-sub">
                {{ t('sessionStartDialog.yoloPre') }} <code>--dangerously-skip-permissions</code> {{ t('sessionStartDialog.yoloPost') }}
                <template v-if="userDefaultYolo">
                  {{ t('sessionStartDialog.yoloDefaultOn') }}
                </template>
              </span>
            </span>
          </label>
        </div>

        <div v-if="!yoloMode" class="form-group">
          <label>{{ t('sessionStartDialog.aiAccount') }}</label>
          <select
            v-model="accountId"
            :disabled="isLoadingAccounts || allowedAccountOptions.length === 0"
          >
            <option value="" disabled>
              {{
                isLoadingAccounts
                  ? t('sessionStartDialog.loadingAccounts')
                  : allowedAccountOptions.length === 0
                  ? t('sessionStartDialog.noAccountsWhitelisted')
                  : t('sessionStartDialog.pickAccount')
              }}
            </option>
            <option v-for="a in allowedAccountOptions" :key="a.id" :value="a.id">
              {{ a.account_name }} ({{ a.backend_type }})
            </option>
          </select>
          <p class="form-hint">
            {{ t('sessionStartDialog.accountHint') }}
          </p>
        </div>

        <!-- v0.7.73 — Forge context wire-up. Inherited bindings from
             the project (toggleable, per-session opt-out), session-
             only additions (volatile), and first-prompt attachments
             that ride into the first user message. Empty inherited
             list + no extras renders as a compact empty state so
             the dialog doesn't grow for projects without bindings. -->
        <div class="form-group forge-section">
          <label>{{ t('sessionStartDialog.forgeContext') }}</label>

          <details class="forge-disclosure" :open="hasAnyForgeState">
            <summary class="forge-summary">
              <span v-if="isLoadingBindings">{{ t('sessionStartDialog.loadingBindings') }}</span>
              <span v-else-if="!hasAnyForgeState">
                {{ t('sessionStartDialog.forgeEmpty') }}
              </span>
              <span v-else>
                {{ t('sessionStartDialog.forgeSummary', {
                  inherited: inheritedBindings.length,
                  sessionOnly: sessionOnlyAdditions.length,
                  attachments: firstPromptAttachments.length,
                }) }}
              </span>
            </summary>

            <div v-if="inheritedBindings.length" class="forge-block">
              <h4 class="forge-heading">{{ t('sessionStartDialog.inheritedFromProject') }}</h4>
              <ul class="forge-binding-list">
                <li
                  v-for="b in inheritedBindings"
                  :key="b.id"
                  class="forge-binding-row"
                >
                  <label class="inline-toggle">
                    <input
                      type="checkbox"
                      :checked="isBindingEnabled(b)"
                      @change="toggleBinding(b)"
                    />
                    <span class="forge-binding-kind">
                      {{ FORGE_KIND_LABELS[b.kind] }}
                    </span>
                    <code class="forge-binding-id">{{ b.asset_id }}</code>
                  </label>
                </li>
              </ul>
            </div>

            <div class="forge-block">
              <h4 class="forge-heading">{{ t('sessionStartDialog.addSessionOnlyBinding') }}</h4>
              <div class="forge-add-row">
                <select v-model="addBindingKind" class="forge-add-kind">
                  <option
                    v-for="(label, kind) in FORGE_KIND_LABELS"
                    :key="kind"
                    :value="kind"
                  >
                    {{ label }}
                  </option>
                </select>
                <input
                  v-model="addBindingAssetId"
                  type="text"
                  class="forge-add-asset"
                  :placeholder="t('sessionStartDialog.assetIdPlaceholder')"
                  @keydown.enter.prevent="addSessionOnlyBinding"
                />
                <button
                  type="button"
                  class="btn btn-secondary forge-add-btn"
                  @click="addSessionOnlyBinding"
                >
                  {{ t('common.add') }}
                </button>
              </div>
              <ul v-if="sessionOnlyAdditions.length" class="forge-binding-list">
                <li
                  v-for="(b, idx) in sessionOnlyAdditions"
                  :key="`session-${idx}`"
                  class="forge-binding-row session-only"
                >
                  <span class="forge-binding-kind">
                    {{ FORGE_KIND_LABELS[b.kind] }}
                  </span>
                  <code class="forge-binding-id">{{ b.asset_id }}</code>
                  <span class="forge-session-flag">{{ t('sessionStartDialog.sessionOnlyFlag') }}</span>
                  <button
                    type="button"
                    class="forge-binding-remove"
                    :aria-label="t('sessionStartDialog.removeSessionOnlyBinding')"
                    @click="removeSessionOnlyAt(idx)"
                  >
                    ×
                  </button>
                </li>
              </ul>
            </div>

            <div class="forge-block">
              <h4 class="forge-heading">{{ t('sessionStartDialog.firstPromptAttachments') }}</h4>
              <SessionContextTray
                v-model:attachments="firstPromptAttachments"
              />
              <p class="form-hint forge-hint">
                {{ t('sessionStartDialog.firstPromptHint') }}
              </p>
            </div>
          </details>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="emit('close')">
            {{ t('common.cancel') }}
          </button>
          <button type="submit" class="btn btn-primary" :disabled="!canSubmit">
            {{ t('sessionStartDialog.startSession') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
}

.modal {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  max-width: 520px;
  width: 100%;
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--border-default);
}
.modal-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 188, 212, 0.12);
  color: var(--accent-cyan);
  border-radius: 8px;
  flex-shrink: 0;
}
.modal-icon svg {
  width: 18px;
  height: 18px;
}
.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.close-btn {
  margin-left: auto;
  background: transparent;
  border: 0;
  color: var(--text-muted);
  cursor: pointer;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
}
.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}
.close-btn svg {
  width: 16px;
  height: 16px;
}

form {
  padding: 16px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.label-row label {
  margin: 0;
}

.form-group > label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.form-group input[type='text'],
.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  outline: none;
}
.form-group input:focus,
.form-group select:focus {
  border-color: var(--accent-cyan);
}
.form-group input:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.form-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.form-hint code {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.inline-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: none;
  letter-spacing: normal;
  cursor: pointer;
  font-weight: 500;
}

.row-toggle {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
}
.row-toggle input {
  margin-top: 3px;
}
.toggle-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.toggle-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.toggle-sub {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.toggle-sub code {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 4px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.btn {
  padding: 8px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent-cyan);
  color: #002;
  border-color: var(--accent-cyan);
  font-weight: 600;
}
.btn-primary:hover {
  filter: brightness(1.08);
}
.btn-primary:disabled {
  opacity: 0.55;
  cursor: wait;
}
.btn-secondary:hover {
  background: var(--bg-secondary);
}

/* v0.7.73 — Forge context section */
.forge-disclosure {
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-tertiary);
  padding: 8px 12px;
  font-size: 12px;
}
.forge-summary {
  cursor: pointer;
  list-style: none;
  color: var(--text-secondary);
  padding: 4px 0;
}
.forge-summary::-webkit-details-marker {
  display: none;
}
.forge-block {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-default);
}
.forge-heading {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 0 0 6px 0;
  font-weight: 500;
}
.forge-binding-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.forge-binding-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 4px;
  background: var(--bg-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
}
.forge-binding-row.session-only {
  background: var(--bg-secondary);
  opacity: 0.95;
}
.forge-binding-kind {
  color: var(--text-tertiary);
  min-width: 70px;
}
.forge-binding-id {
  color: var(--text-primary);
  background: transparent;
  padding: 0;
  flex: 1;
}
.forge-session-flag {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.forge-binding-remove {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 4px;
}
.forge-binding-remove:hover {
  color: var(--accent-red);
}
.forge-add-row {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}
.forge-add-kind {
  flex: 0 0 auto;
  padding: 4px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: 4px;
}
.forge-add-asset {
  flex: 1;
  padding: 4px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: 4px;
  font-family: 'Geist Mono', monospace;
}
.forge-add-btn {
  flex: 0 0 auto;
  padding: 4px 12px;
  font-size: 12px;
}
.forge-hint {
  margin-top: 6px;
}

/* v0.7.74 — goal-loop config */
.goal-loop-config {
  border-left: 2px solid var(--accent-cyan);
  padding-left: 12px;
}
.goal-textarea {
  width: 100%;
  font-family: inherit;
  font-size: 13px;
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  resize: vertical;
}
.goal-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}
.goal-mono-input {
  width: 100%;
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
}
.goal-mono-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}
.goal-secondary-label {
  display: block;
  margin-top: 10px;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
.goal-caps-row {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}
.goal-cap-field {
  flex: 1;
}
.goal-cap-field label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}
.goal-cap-field input {
  width: 100%;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
}
.goal-cap-field input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}
.goal-model-override {
  margin-top: 6px;
}
.goal-error {
  color: var(--accent-red, #ff6464);
}
</style>
