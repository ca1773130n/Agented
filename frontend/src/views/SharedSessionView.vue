<script setup lang="ts">
/**
 * SharedSessionView — a teammate attaches a shared session by URL token (Phase 25).
 *
 * 25-01 (live-share): opens an authenticated SSE stream against
 * `/api/shared-sessions/{token}/stream` (the token is the credential; the path
 * is auth-bypassed server-side) and renders the operator's live deltas
 * READ-ONLY. A read-scope token has no write path.
 *
 * 25-02 (co-drive): a chat-scope token additionally shows a message input that
 * POSTs to `/api/shared-sessions/{token}/send`; that message is policy-checked
 * server-side BEFORE it reaches the operator's session (a DENY surfaces here).
 */
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { createAuthenticatedEventSource, sessionShareApi } from '../services/api';
import type { AuthenticatedEventSource } from '../services/api';

const route = useRoute();
const { t } = useI18n();

const token = computed(() => String(route.params.token || ''));
// Scope hint from the share URL (?scope=chat). Server is the source of truth;
// this only decides whether to OFFER the co-drive input (25-02).
const scope = computed(() => (route.query.scope === 'chat' ? 'chat' : 'read'));

const lines = ref<string[]>([]);
const status = ref<'connecting' | 'open' | 'error'>('connecting');
const drivers = ref<string[]>([]);

// Co-drive (25-02) — only offered for a chat-scope share.
const canCoDrive = computed(() => scope.value === 'chat');
const draft = ref('');
// idle | sending (blocks server-side through the policy gate; an ASK holds here)
const sendState = ref<'idle' | 'sending' | 'denied' | 'sent'>('idle');
const sendError = ref('');

async function sendCoDrive() {
  const text = draft.value.trim();
  if (!text || sendState.value === 'sending') return;
  sendState.value = 'sending';
  sendError.value = '';
  try {
    await sessionShareApi.coDrive(token.value, text);
    draft.value = '';
    sendState.value = 'sent';
  } catch (err: unknown) {
    // A DENY / never-approved ASK / read-token surfaces as a 4xx here.
    sendState.value = 'denied';
    sendError.value = err instanceof Error ? err.message : String(err);
  }
}

let source: AuthenticatedEventSource | null = null;

function appendLine(raw: string) {
  try {
    const data = JSON.parse(raw);
    if (typeof data.line === 'string') lines.value.push(data.line);
  } catch {
    lines.value.push(raw);
  }
}

onMounted(() => {
  source = createAuthenticatedEventSource(
    `/api/shared-sessions/${token.value}/stream`,
  );
  source.onopen = () => {
    status.value = 'open';
  };
  source.onerror = () => {
    status.value = 'error';
  };
  source.addEventListener('output', (e: MessageEvent) => {
    status.value = 'open';
    appendLine(e.data);
  });
  source.addEventListener('co_drive', (e: MessageEvent) => {
    // Attribution: show WHO co-drove (broadcast by the backend on ALLOW).
    try {
      const d = JSON.parse(e.data);
      if (d.actor_user_id) drivers.value.push(String(d.actor_user_id));
    } catch {
      /* ignore malformed attribution frame */
    }
  });
});

onBeforeUnmount(() => {
  source?.close();
  source = null;
});
</script>

<template>
  <div class="shared-session">
    <header class="shared-session__header">
      <h1>{{ t('sharedSession.title') }}</h1>
      <span class="shared-session__badge">
        {{ canCoDrive ? t('coDrive.title') : t('sharedSession.readOnly') }}
      </span>
    </header>

    <p v-if="drivers.length" class="shared-session__drivers">
      {{ t('coDrive.driverLabel') }}: {{ drivers[drivers.length - 1] }}
    </p>

    <p v-if="status === 'connecting'" class="shared-session__status">
      {{ t('sharedSession.connecting') }}
    </p>
    <p v-else-if="status === 'error'" class="shared-session__status shared-session__status--error">
      {{ t('sharedSession.expired') }}
    </p>

    <pre v-if="lines.length" class="shared-session__output">{{ lines.join('\n') }}</pre>
    <p v-else-if="status === 'open'" class="shared-session__status">
      {{ t('sharedSession.waiting') }}
    </p>

    <!-- Co-drive input — chat-scope only. A read-scope share cannot drive. -->
    <div v-if="canCoDrive" class="shared-session__codrive">
      <textarea
        v-model="draft"
        class="shared-session__input"
        :placeholder="t('coDrive.inputPlaceholder')"
        :disabled="sendState === 'sending'"
        @keydown.enter.exact.prevent="sendCoDrive"
      />
      <button
        class="shared-session__send"
        :disabled="sendState === 'sending' || !draft.trim()"
        @click="sendCoDrive"
      >
        {{ sendState === 'sending' ? t('coDrive.sending') : t('coDrive.send') }}
      </button>
      <p v-if="sendState === 'sending'" class="shared-session__status">
        {{ t('coDrive.waitingApproval') }}
      </p>
      <p v-else-if="sendState === 'sent'" class="shared-session__status">
        {{ t('coDrive.sent') }}
      </p>
      <p v-else-if="sendState === 'denied'" class="shared-session__status shared-session__status--error">
        {{ t('coDrive.denied') }}<span v-if="sendError"> — {{ sendError }}</span>
      </p>
    </div>
    <p v-else class="shared-session__note">{{ t('sharedSession.attachedReadOnly') }}</p>
  </div>
</template>

<style scoped>
.shared-session {
  padding: 1.5rem;
  max-width: 960px;
  margin: 0 auto;
}
.shared-session__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.shared-session__badge {
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border: 1px solid var(--border, #333);
  border-radius: 4px;
  color: var(--text-muted, #999);
}
.shared-session__status {
  color: var(--text-muted, #999);
}
.shared-session__status--error {
  color: var(--danger, #e5484d);
}
.shared-session__output {
  background: var(--surface, #111);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  padding: 1rem;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono, monospace);
  font-size: 0.85rem;
  max-height: 70vh;
  overflow-y: auto;
}
.shared-session__note {
  margin-top: 1rem;
  font-size: 0.8rem;
  color: var(--text-muted, #999);
}
.shared-session__drivers {
  font-size: 0.8rem;
  color: var(--text-muted, #999);
  margin-bottom: 0.5rem;
}
.shared-session__codrive {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.shared-session__input {
  width: 100%;
  min-height: 3rem;
  background: var(--surface, #111);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  padding: 0.5rem;
  color: inherit;
  font-family: inherit;
  resize: vertical;
}
.shared-session__send {
  align-self: flex-start;
  padding: 0.4rem 1rem;
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  background: var(--accent, #3b82f6);
  color: #fff;
  cursor: pointer;
}
.shared-session__send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
