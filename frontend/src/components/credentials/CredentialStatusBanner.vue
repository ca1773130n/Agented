<script setup lang="ts">
/**
 * CredentialStatusBanner — surfaces accounts the poller can't
 * resolve a token for, so the Token Usage Dashboard isn't
 * silently missing rows and operators don't have to grep
 * backend logs (the original v0.7.93 trigger).
 *
 * The banner is self-fetching (one GET on mount) so it can be
 * dropped onto any page that wants to nudge the operator
 * toward fixing missing credentials. Renders nothing when all
 * accounts are OK or when the request fails (errors go to a
 * console warning — this is an advisory surface, not a blocker).
 *
 * Each missing row shows a copy-pasteable shell command derived
 * from the account's config_path, e.g.
 * ``CLAUDE_CONFIG_DIR=~/.claude-personal2 claude``, plus the
 * keychain entry / file path that was actually checked.
 */
import { onMounted, ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { monitoringApi, type CredentialStatusRow } from '../../services/api';
import { useToast } from '../../composables/useToast';

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    /** Optional backend_type filter — used by the AI Backends
     *  page to only surface the kind the operator is viewing. */
    backendFilter?: string;
    /** Compact mode = one-line summary + click-to-expand list.
     *  Default false = always expanded (dashboard use). */
    compact?: boolean;
  }>(),
  { backendFilter: '', compact: false },
);

const rows = ref<CredentialStatusRow[]>([]);
const loading = ref(false);
const expanded = ref(!props.compact);
const showToast = useToast();

const missing = computed(() =>
  rows.value.filter(
    r =>
      r.credential_status === 'missing' &&
      (!props.backendFilter || r.backend_type === props.backendFilter),
  ),
);

async function load() {
  loading.value = true;
  try {
    const res = await monitoringApi.getCredentials();
    rows.value = res.accounts;
  } catch (e) {
    // Advisory surface — failure shouldn't break the page.
    // eslint-disable-next-line no-console
    console.warn('CredentialStatusBanner: load failed', e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function copy(text: string) {
  // ``navigator.clipboard`` is undefined on insecure (http://)
  // origins and on some browsers when the window isn't focused.
  // Use the deprecated ``execCommand('copy')`` via a hidden
  // textarea as a fallback so the Copy button still works in
  // local-dev HTTP setups.
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else if (!fallbackCopy(text)) {
      throw new Error('clipboard unavailable');
    }
    showToast(t('credentialStatusBanner.copied'), 'success');
  } catch {
    showToast(t('credentialStatusBanner.copyFailed'), 'error');
  }
}

function fallbackCopy(text: string): boolean {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}
</script>

<template>
  <div
    v-if="missing.length > 0"
    class="cred-banner"
    role="status"
    data-testid="credential-status-banner"
  >
    <div class="banner-head" @click="expanded = !expanded">
      <span class="banner-icon" aria-hidden="true">⚠</span>
      <span class="banner-title">
        {{ missing.length === 1 ? t('credentialStatusBanner.missingTitle', { count: missing.length }) : t('credentialStatusBanner.missingTitlePlural', { count: missing.length }) }}
        <span class="banner-subtitle">
          {{ t('credentialStatusBanner.subtitle') }}
        </span>
      </span>
      <button
        v-if="props.compact"
        class="banner-toggle"
        type="button"
        :aria-expanded="expanded"
      >
        {{ expanded ? '−' : '+' }}
      </button>
    </div>

    <ul v-if="expanded" class="cred-list">
      <li v-for="r in missing" :key="r.account_id" class="cred-row">
        <div class="cred-row-head">
          <span class="cred-account">
            <span class="cred-backend">{{ r.backend_type }}</span>
            <span class="cred-name">{{ r.account_name || t('credentialStatusBanner.accountFallback', { id: r.account_id }) }}</span>
          </span>
          <span v-if="r.expected_location" class="cred-location" :title="r.expected_location">
            {{ t('credentialStatusBanner.checked') }} <code>{{ r.expected_location }}</code>
          </span>
        </div>
        <div v-if="r.remediation" class="cred-fix">
          <code class="cred-cmd">{{ r.remediation }}</code>
          <button
            class="cred-copy"
            type="button"
            :aria-label="t('credentialStatusBanner.copyAriaLabel', { account: r.account_name || r.account_id })"
            @click="copy(r.remediation!)"
          >
            {{ t('credentialStatusBanner.copy') }}
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.cred-banner {
  background: var(--bg-secondary, #1a1a20);
  border: 1px solid var(--accent-amber, #d97706);
  border-left-width: 4px;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 13px;
}
.banner-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.banner-icon {
  color: var(--accent-amber, #d97706);
  font-size: 16px;
  line-height: 1;
}
.banner-title {
  color: var(--text-primary);
  font-weight: 500;
  flex: 1;
}
.banner-subtitle {
  color: var(--text-tertiary);
  font-weight: 400;
}
.banner-toggle {
  background: none;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  width: 22px;
  height: 22px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.cred-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cred-row {
  background: var(--bg-primary, #101015);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 8px 10px;
}
.cred-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.cred-account {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cred-backend {
  font-size: 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  padding: 2px 6px;
}
.cred-name {
  color: var(--text-primary);
  font-weight: 500;
}
.cred-location {
  font-size: 11px;
  color: var(--text-tertiary);
}
.cred-location code {
  color: var(--text-secondary);
  background: transparent;
}
.cred-fix {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cred-cmd {
  flex: 1;
  display: block;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  padding: 6px 8px;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
  font-size: 11px;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: nowrap;
}
.cred-copy {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 11px;
}
.cred-copy:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}
</style>
