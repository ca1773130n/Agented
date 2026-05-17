/**
 * useWizardAutoResume — shared auto-resume + localStorage glue
 * for the design wizards. Extracted in v0.7.83 from the per-wizard
 * pattern that v0.7.78 first introduced for /skills/new.
 *
 * Resolution order on mount:
 *   1. localStorage ``<keyPrefix>:<user_id|anon>`` — try to resume.
 *      Misses (404) fall through.
 *   2. API ``listActive()`` — most recent active conv for this
 *      operator. Returns the wizard from a different browser /
 *      machine when localStorage is empty here.
 *   3. ``startConversation()`` — brand new conv.
 *
 * Late auth: if the user id resolves AFTER mount (auth restore
 * raced the wizard), a watcher migrates any ``:anon`` entry
 * under the resolved user namespace and re-attempts the legacy
 * unnamespaced key migration. This mirrors the codex WARN C
 * fixes from v0.7.78.
 */
import { onMounted, watch } from 'vue';
import { useAuth } from './useAuth';

interface AutoResumeConversation {
  conversationId: { value: string | null };
  startConversation: () => Promise<unknown>;
  resumeConversation: (convId: string) => Promise<unknown>;
}

interface AutoResumeApi {
  listActive: () => Promise<{
    active_conversations: Array<{ id: string; status: string; updated_at: string; message_count: number }>;
  }>;
}

/**
 * @param conversation - the object returned by useConversation()
 * @param api - the per-domain conversation API (must implement listActive)
 * @param keyPrefix - localStorage key prefix, e.g. 'agented_skill_conv_id'
 */
export function useWizardAutoResume(
  conversation: AutoResumeConversation,
  api: AutoResumeApi,
  keyPrefix: string,
): { rememberConvId: (id: string | null) => void } {
  const { currentUser } = useAuth();

  function namespacedKey(): string {
    const uid = currentUser.value?.id;
    return `${keyPrefix}:${uid ?? 'anon'}`;
  }

  function rememberConvId(id: string | null) {
    const key = namespacedKey();
    try {
      if (id) localStorage.setItem(key, id);
      else localStorage.removeItem(key);
    } catch {
      // localStorage may be disabled in private mode.
    }
  }

  function migrateLegacyKey(): string | null {
    // One-time migration of the unnamespaced legacy key written
    // by pre-namespacing builds. Only safe when we know the user
    // — otherwise we'd strand the conv under ``:anon``.
    if (!currentUser.value?.id) return null;
    try {
      const legacy = localStorage.getItem(keyPrefix);
      if (legacy) {
        localStorage.setItem(namespacedKey(), legacy);
        localStorage.removeItem(keyPrefix);
        return legacy;
      }
    } catch {
      // ignored
    }
    return null;
  }

  function migrateFromAnon(userId: string) {
    // When ``currentUser`` resolves AFTER mount, any conv parked
    // under ``:anon`` (legacy migration or wizard-during-restore)
    // should move under the resolved user key.
    const anonKey = `${keyPrefix}:anon`;
    const userKey = `${keyPrefix}:${userId}`;
    try {
      const cached = localStorage.getItem(anonKey);
      if (!cached) return;
      if (!localStorage.getItem(userKey)) {
        localStorage.setItem(userKey, cached);
      }
      localStorage.removeItem(anonKey);
    } catch {
      // ignored
    }
  }

  async function tryResume(convId: string): Promise<boolean> {
    try {
      await conversation.resumeConversation(convId);
      return !!conversation.conversationId.value;
    } catch {
      return false;
    }
  }

  watch(
    () => currentUser.value?.id,
    (uid, prev) => {
      if (uid && !prev) {
        // Drain both legacy sources once the user id is known.
        migrateLegacyKey();
        migrateFromAnon(uid);
      }
    },
    { immediate: true },
  );

  onMounted(async () => {
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
    try {
      const res = await api.listActive();
      const newest = res.active_conversations?.[0];
      if (newest && (await tryResume(newest.id))) {
        rememberConvId(newest.id);
        return;
      }
    } catch {
      // Auth or network failure — fall through.
    }
    rememberConvId(null);
    await conversation.startConversation();
    rememberConvId(conversation.conversationId.value);
  });

  return { rememberConvId };
}
