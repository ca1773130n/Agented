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
      executionType: 'direct' | 'ralph_loop' | 'team_spawn';
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
    },
  ): void;
}>();

const dialogRef = ref<HTMLElement | null>(null);
const isOpen = computed(() => props.visible);
useFocusTrap(dialogRef, isOpen);

const name = ref('');
const autoTitle = ref(true);
const yoloMode = ref(false);
const executionType = ref<'direct' | 'ralph_loop' | 'team_spawn'>('direct');
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

const FORGE_KIND_LABELS: Record<ForgeBindingKind, string> = {
  rule: 'Rule',
  skill: 'Skill',
  hook: 'Hook',
  command: 'Command',
  mcp_server: 'MCP Server',
  plugin: 'Plugin',
};

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
          <h3 id="modal-title-session-start">Start a new session</h3>
          <p class="modal-subtitle">
            Configure how this claude subprocess runs in the project's worktree.
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
            <label for="session-name-input">Session name</label>
            <label class="inline-toggle">
              <input type="checkbox" v-model="autoTitle" />
              <span>Auto title</span>
            </label>
          </div>
          <input
            id="session-name-input"
            type="text"
            v-model="name"
            :disabled="autoTitle"
            placeholder="e.g. 'Refactor auth middleware'"
          />
          <p class="form-hint">
            When auto title is on, an empty name is filled by the backend after
            the first turn (placeholder today, claude-generated summary in a
            follow-up).
          </p>
        </div>

        <div class="form-group">
          <label>Execution type</label>
          <select v-model="executionType">
            <option value="direct">Direct — interactive claude chat</option>
            <option value="ralph_loop">Ralph loop — autonomous iteration</option>
            <option value="team_spawn">Team spawn — multi-agent</option>
          </select>
          <p v-if="executionType === 'ralph_loop'" class="form-hint">
            Requires <code>ralph-wiggum</code> plugin.
          </p>
          <p v-else-if="executionType === 'team_spawn'" class="form-hint">
            Requires
            <code>CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1</code> in the environment.
          </p>
        </div>

        <div class="form-group toggle-group">
          <label class="row-toggle">
            <input type="checkbox" v-model="yoloMode" />
            <span class="toggle-body">
              <span class="toggle-title">Yolo mode</span>
              <span class="toggle-sub">
                Appends <code>--dangerously-skip-permissions</code> and bypasses
                the project's allowed-accounts whitelist.
                <template v-if="userDefaultYolo">
                  Default-on per your Settings.
                </template>
              </span>
            </span>
          </label>
        </div>

        <div v-if="!yoloMode" class="form-group">
          <label>AI account</label>
          <select
            v-model="accountId"
            :disabled="isLoadingAccounts || allowedAccountOptions.length === 0"
          >
            <option value="" disabled>
              {{
                isLoadingAccounts
                  ? 'Loading accounts…'
                  : allowedAccountOptions.length === 0
                  ? 'No accounts whitelisted — add one in project settings'
                  : 'Pick an account…'
              }}
            </option>
            <option v-for="a in allowedAccountOptions" :key="a.id" :value="a.id">
              {{ a.account_name }} ({{ a.backend_type }})
            </option>
          </select>
          <p class="form-hint">
            Sessions must use a whitelisted account unless Yolo is on. Manage the
            whitelist on the project's settings page.
          </p>
        </div>

        <!-- v0.7.73 — Forge context wire-up. Inherited bindings from
             the project (toggleable, per-session opt-out), session-
             only additions (volatile), and first-prompt attachments
             that ride into the first user message. Empty inherited
             list + no extras renders as a compact empty state so
             the dialog doesn't grow for projects without bindings. -->
        <div class="form-group forge-section">
          <label>Forge context</label>

          <details class="forge-disclosure" :open="hasAnyForgeState">
            <summary class="forge-summary">
              <span v-if="isLoadingBindings">Loading bindings…</span>
              <span v-else-if="!hasAnyForgeState">
                No project bindings or first-prompt attachments.
                Click to add session-only context.
              </span>
              <span v-else>
                {{ inheritedBindings.length }} inherited
                · {{ sessionOnlyAdditions.length }} session-only
                · {{ firstPromptAttachments.length }} attachments
              </span>
            </summary>

            <div v-if="inheritedBindings.length" class="forge-block">
              <h4 class="forge-heading">Inherited from project</h4>
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
              <h4 class="forge-heading">Add session-only binding</h4>
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
                  placeholder="asset id (e.g. 42, skill-name)"
                  @keydown.enter.prevent="addSessionOnlyBinding"
                />
                <button
                  type="button"
                  class="btn btn-secondary forge-add-btn"
                  @click="addSessionOnlyBinding"
                >
                  Add
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
                  <span class="forge-session-flag">session only</span>
                  <button
                    type="button"
                    class="forge-binding-remove"
                    aria-label="Remove session-only binding"
                    @click="removeSessionOnlyAt(idx)"
                  >
                    ×
                  </button>
                </li>
              </ul>
            </div>

            <div class="forge-block">
              <h4 class="forge-heading">First-prompt attachments</h4>
              <SessionContextTray
                v-model:attachments="firstPromptAttachments"
              />
              <p class="form-hint forge-hint">
                These attach to the first message you send. After
                that, use the tray above the chat input for
                subsequent turns.
              </p>
            </div>
          </details>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" class="btn btn-primary" :disabled="!canSubmit">
            Start session
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
</style>
