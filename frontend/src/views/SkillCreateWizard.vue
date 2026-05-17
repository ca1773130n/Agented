<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { skillConversationApi } from '../services/api';
import { useConversation, createConfigParser } from '../composables/useConversation';
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { useAuth } from '../composables/useAuth';
import SkillCreatePreviewDrawer from '../components/skills/SkillCreatePreviewDrawer.vue';

const router = useRouter();
const showToast = useToast();

// v0.7.77 — config shape now matches the multi-file Anthropic
// Skills schema the backend emits via SKILL_CREATION_SYSTEM_PROMPT.
// Only ``skill_name`` is read by the wizard UI (for the detected-
// entity banner); the rest is opaque pass-through to finalize.
interface SkillConfig {
  skill_name: string;
  frontmatter?: {
    description?: string;
    license?: string;
    allowed_tools?: string[];
    tags?: string[];
  };
  body?: string;
  files?: Array<{ path: string; content: string }>;
  // Legacy fields kept on the type so a mid-flight conversation
  // emitting the v0.7.75 schema doesn't break parsing.
  description?: string;
  triggers?: string[];
  instructions?: string;
  examples?: string[];
}

const conversation = useConversation<SkillConfig>(
  skillConversationApi,
  createConfigParser<SkillConfig>('---SKILL_CONFIG---'),
);

// v0.7.77 — preview drawer state. Clicking the Create button no
// longer finalizes directly; it opens the drawer which renders the
// rendered tree via ``preview-finalize`` and lets the operator
// inspect each file before committing.
const showPreview = ref(false);

useWebMcpTool({
  name: 'agented_skill_create_get_state',
  description: 'Returns the current state of the SkillCreateWizard',
  page: 'SkillCreateWizard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SkillCreateWizard',
        conversationId: conversation.conversationId.value,
        messagesCount: conversation.messages.value.length,
        isProcessing: conversation.isProcessing.value,
        canFinalize: conversation.canFinalize.value,
        isFinalizing: conversation.isFinalizing.value,
        detectedConfigName: conversation.detectedConfig.value?.skill_name ?? null,
        selectedBackend: conversation.selectedBackend.value,
      }),
    }],
  }),
  deps: [conversation.conversationId, conversation.messages, conversation.isProcessing, conversation.canFinalize, conversation.isFinalizing, conversation.detectedConfig],
});

const SKILL_ICON_PATHS = [
  'M12 2L2 7l10 5 10-5-10-5z',
  'M2 17l10 5 10-5',
  'M2 12l10 5 10-5',
];

function openPreview() {
  // v0.7.77 — the wizard's Create button now opens the preview
  // drawer instead of finalizing directly. The drawer's own
  // Create button runs ``commitFinalize`` below.
  showPreview.value = true;
}

// v0.7.79 — native ``title`` tooltip mirrored from the visible
// hint underneath the button, so a screen reader or hover lands
// the same explanation. We branch on ``canFinalize`` instead of
// always showing the long copy so a ready-to-create operator
// doesn't see a no-op nag tooltip.
const finalizeTooltip = computed(() =>
  conversation.canFinalize.value
    ? 'Open the preview to review and create your skill'
    : "Keep chatting — Claude needs more details before the skill can be created. Tell it the skill's name, what triggers it, and what it should do.",
);

async function commitFinalize(expectedConfigHash: string) {
  // v0.7.77 (codex BLOCK 4) — the drawer passes the hash of the
  // config it rendered; backend 409s if claude has emitted a
  // newer one since. On mismatch, useConversation's toast
  // already surfaces the 409 message; the drawer stays open so
  // the operator can re-preview (the watcher on messageCount
  // will have already re-fetched).
  const result = await conversation.finalize(expectedConfigHash);
  if (result) {
    showPreview.value = false;
    // v0.7.78 — conv is finalized; clear localStorage so the
    // next visit starts fresh instead of trying to resume a
    // dead conv.
    rememberConvId(null);
    showToast(
      `Skill "${(result.skill as { skill_name: string }).skill_name}" created successfully!`,
      'success',
    );
    router.push({ name: 'skill-detail', params: { skillId: result.skill_id as string } });
  }
}

// v0.7.78 — auto-resume the wizard's chat after page refresh /
// backend restart. Resolution order:
//   1. localStorage ``agented_skill_conv_id:<user>`` (per-browser
//      + per-user ref) — try to resume that conv. 404 means the
//      row was finalized or stale-purged; fall through.
//   2. Server's most-recent active conv (``listActive``). Lets a
//      different browser / fresh-cache load still pick up an
//      in-flight conversation the operator started elsewhere.
//   3. Brand-new conversation via ``startConversation``.
// localStorage is updated whenever the conversation_id changes
// (start success or resume), and cleared on finalize / abandon
// so the next page load doesn't try to resume a finalized conv.
//
// v0.7.78 (codex BLOCK 3) — the storage key is namespaced by the
// authenticated user id (or "anon" when unauthenticated) so a
// shared-browser logout/login swap doesn't try to resume the
// previous operator's wizard conv (which the backend now also
// refuses via ownership check, but the client shouldn't even ask).
const SKILL_CONV_LOCALSTORAGE_PREFIX = 'agented_skill_conv_id';

const { currentUser } = useAuth();

function namespacedKey(): string {
  // Use the authenticated user id when available; fall back to
  // ``anon`` for bootstrap / unauthenticated mode. Reading
  // ``currentUser`` here (not at module load) means we pick up
  // the id as soon as ``useAuth.restore()`` resolves it — which
  // happens during app boot before SkillCreateWizard mounts.
  const uid = currentUser.value?.id;
  return `${SKILL_CONV_LOCALSTORAGE_PREFIX}:${uid ?? 'anon'}`;
}

function rememberConvId(id: string | null) {
  const key = namespacedKey();
  try {
    if (id) localStorage.setItem(key, id);
    else localStorage.removeItem(key);
  } catch {
    // localStorage may be disabled in private mode; tolerate it.
  }
}

function migrateLegacyKey(): string | null {
  // v0.7.78 — one-time migration of the unnamespaced key written
  // by 0.7.78-pre. We move it under the current user's namespace
  // so a logged-in operator doesn't lose their in-flight conv,
  // then delete the legacy entry so a later login as a different
  // user can't inherit it.
  //
  // v0.7.78 (codex WARN C / 2nd pass) — only migrate when we
  // actually know who the user is. Migrating into the ``anon``
  // namespace would strand the conv there: the next mount with
  // a resolved ``currentUser`` looks under ``:<user_id>``, not
  // ``:anon``, and the legacy key has already been deleted so we
  // can't try again. The deferred ``watch(currentUser)`` below
  // picks up the resolution and migrates from the anon namespace
  // when login completes.
  if (!currentUser.value?.id) return null;
  try {
    const legacy = localStorage.getItem(SKILL_CONV_LOCALSTORAGE_PREFIX);
    if (legacy) {
      localStorage.setItem(namespacedKey(), legacy);
      localStorage.removeItem(SKILL_CONV_LOCALSTORAGE_PREFIX);
      return legacy;
    }
  } catch {
    // Best-effort migration; if storage throws, just skip.
  }
  return null;
}

function migrateFromAnon(userId: string) {
  // v0.7.78 (codex WARN C / 2nd pass) — when ``currentUser``
  // resolves AFTER mount (auth restore raced the wizard), the
  // legacy migration may have parked a conv under ``:anon`` OR
  // the wizard itself wrote a ``:anon`` entry before the user
  // id arrived. Move that conv under the resolved user key so
  // a subsequent mount picks it up. The anon entry is deleted
  // so the next anon visitor can't inherit it.
  const anonKey = `${SKILL_CONV_LOCALSTORAGE_PREFIX}:anon`;
  const userKey = `${SKILL_CONV_LOCALSTORAGE_PREFIX}:${userId}`;
  try {
    const cached = localStorage.getItem(anonKey);
    if (!cached) return;
    // Don't overwrite a real value that the user namespace
    // already holds; just drop the anon entry.
    if (!localStorage.getItem(userKey)) {
      localStorage.setItem(userKey, cached);
    }
    localStorage.removeItem(anonKey);
  } catch {
    // Best-effort.
  }
}

watch(
  () => currentUser.value?.id,
  (uid, prev) => {
    if (uid && !prev) {
      // v0.7.78 (codex WARN C / 3rd pass) — also retry the
      // legacy-key migration here. ``onMounted`` may have
      // skipped it because ``currentUser`` was still resolving;
      // without this branch the legacy unnamespaced key stays
      // on disk and gets shadowed by future user-keyed entries.
      migrateLegacyKey();
      migrateFromAnon(uid);
    }
  },
  { immediate: true },
);

async function tryResume(convId: string): Promise<boolean> {
  try {
    await conversation.resumeConversation(convId);
    return !!conversation.conversationId.value;
  } catch {
    return false;
  }
}

onMounted(async () => {
  // (1) localStorage (per-user key) — falling back to migrating
  // a legacy unnamespaced key written by an earlier build.
  let cached: string | null = null;
  try {
    cached = localStorage.getItem(namespacedKey()) ?? migrateLegacyKey();
  } catch {
    cached = null;
  }
  if (cached && (await tryResume(cached))) {
    rememberConvId(cached);
    return;
  }
  // (2) server's most-recent active
  try {
    const res = await skillConversationApi.listActive();
    const newest = res.active_conversations?.[0];
    if (newest && (await tryResume(newest.id))) {
      rememberConvId(newest.id);
      return;
    }
  } catch {
    // Auth or network failure — fall through to fresh start.
  }
  // (3) fresh start
  rememberConvId(null);
  await conversation.startConversation();
  rememberConvId(conversation.conversationId.value);
});
</script>

<template>
  <div class="wizard-page">
    <div class="wizard-header">
      <div class="header-title">
        <h1>Design a Skill</h1>
        <p>Chat with Claude to design your custom skill</p>
      </div>
      <!-- v0.7.79 — the Create button is always visible. When the
           conversation isn't ready yet (Claude hasn't emitted the
           SKILL_CONFIG block that ``createConfigParser`` watches
           for), it's disabled and the hint underneath tells the
           operator exactly what's missing. Previously the button
           was ``v-if``'d out, so newcomers couldn't tell whether
           it was missing, broken, or just not ready. -->
      <div class="finalize-control">
        <button
          class="btn btn-primary btn-finalize"
          :disabled="!conversation.canFinalize.value || conversation.isFinalizing.value"
          :title="finalizeTooltip"
          :aria-describedby="conversation.canFinalize.value ? undefined : 'finalize-hint'"
          @click="openPreview"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
          {{ conversation.isFinalizing.value ? 'Creating...' : 'Create Skill' }}
        </button>
        <p
          v-if="!conversation.canFinalize.value"
          id="finalize-hint"
          class="finalize-hint"
        >
          Keep chatting — once Claude has the skill's name, what
          triggers it, and what it should do, this button activates
          and opens a preview before anything is written.
        </p>
      </div>
    </div>

    <AiChatPanel
      :messages="conversation.messages.value"
      :is-processing="conversation.isProcessing.value"
      :streaming-content="conversation.streamingContent.value"
      :input-message="conversation.inputMessage.value"
      :conversation-id="conversation.conversationId.value"
      :can-finalize="conversation.canFinalize.value"
      :is-finalizing="conversation.isFinalizing.value"
      :init-streaming-parser="conversation.initStreamingParser"
      show-backend-selector
      :use-smart-scroll="true"
      :selected-backend="conversation.selectedBackend.value"
      :selected-account-id="conversation.selectedAccountId.value"
      :selected-model="conversation.selectedModel.value"
      :assistant-icon-paths="SKILL_ICON_PATHS"
      input-placeholder="Describe your skill or answer Claude's questions..."
      entity-label="skill"
      banner-title="Skill Ready to Create!"
      banner-button-label="Create Skill Now"
      :detected-entity-name="conversation.detectedConfig.value?.skill_name"
      @update:input-message="conversation.inputMessage.value = $event"
      @update:selected-backend="conversation.setBackend($event)"
      @update:selected-account-id="conversation.setAccountId($event)"
      @update:selected-model="conversation.setModel($event)"
      @send="conversation.sendMessage"
      @keydown="conversation.handleKeyDown"
      @finalize="openPreview"
    />

    <!-- v0.7.77 — slide-over preview of the rendered skill
         package (SKILL.md + helpers/references). Operator
         inspects each file before clicking Create, which
         triggers the actual ``finalize`` POST. -->
    <SkillCreatePreviewDrawer
      :open="showPreview"
      :conversation-id="conversation.conversationId.value"
      :is-finalizing="conversation.isFinalizing.value"
      :message-count="conversation.messages.value.length"
      @close="showPreview = false"
      @create="commitFinalize"
    />
  </div>
</template>

<style scoped>
.wizard-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.wizard-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.header-title {
  flex: 1;
}

.header-title h1 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.header-title p {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.finalize-control {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  max-width: 320px;
}

.finalize-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-tertiary);
  text-align: right;
}

.btn-finalize {
  padding: 10px 20px;
}

.btn-primary {
  background: var(--accent-violet);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: #9966ff;
}

.btn-primary:disabled {
  background: var(--bg-tertiary, #2a2a30);
  color: var(--text-tertiary, #8a8a92);
  cursor: not-allowed;
  opacity: 0.85;
}

.btn-primary svg {
  width: 16px;
  height: 16px;
}
</style>
