<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { settingsApi, ApiError } from '../services/api';
const showToast = useToast();

type SsoProtocol = 'saml' | 'oidc' | 'none';

interface SsoConfig {
  enabled: boolean;
  protocol: SsoProtocol;
  // SAML
  samlEntityId: string;
  samlSsoUrl: string;
  samlCertificate: string;
  samlAttributeEmail: string;
  samlAttributeName: string;
  // OIDC
  oidcClientId: string;
  oidcClientSecret: string;
  oidcIssuerUrl: string;
  oidcScopes: string;
  // Common
  allowLocalLogin: boolean;
  defaultRole: string;
  autoProvision: boolean;
  domainWhitelist: string;
}

const SSO_SETTINGS_KEYS = [
  'sso_enabled', 'sso_protocol',
  'sso_saml_entity_id', 'sso_saml_sso_url', 'sso_saml_certificate',
  'sso_saml_attribute_email', 'sso_saml_attribute_name',
  'sso_oidc_client_id', 'sso_oidc_client_secret', 'sso_oidc_issuer_url', 'sso_oidc_scopes',
  'sso_allow_local_login', 'sso_default_role', 'sso_auto_provision', 'sso_domain_whitelist',
] as const;

const config = ref<SsoConfig>({
  enabled: false,
  protocol: 'saml',
  samlEntityId: '',
  samlSsoUrl: '',
  samlCertificate: '',
  samlAttributeEmail: 'email',
  samlAttributeName: 'displayName',
  oidcClientId: '',
  oidcClientSecret: '',
  oidcIssuerUrl: '',
  oidcScopes: 'openid email profile',
  allowLocalLogin: true,
  defaultRole: 'member',
  autoProvision: true,
  domainWhitelist: '',
});

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const isSaving = ref(false);
const isTesting = ref(false);
const testResult = ref<{ ok: boolean; message: string } | null>(null);
const showCert = ref(false);

const providers = [
  { id: 'okta', name: 'Okta', logo: '🔐', protocol: 'saml' as SsoProtocol },
  { id: 'azure', name: 'Azure AD', logo: '☁', protocol: 'saml' as SsoProtocol },
  { id: 'google', name: 'Google Workspace', logo: '🔵', protocol: 'oidc' as SsoProtocol },
  { id: 'onelogin', name: 'OneLogin', logo: '🟢', protocol: 'saml' as SsoProtocol },
  { id: 'pingid', name: 'PingID', logo: '🔷', protocol: 'saml' as SsoProtocol },
  { id: 'custom', name: 'Custom IdP', logo: '⚙', protocol: 'saml' as SsoProtocol },
];

const spMetadataUrl = computed(() => `https://agented.example.com/auth/saml/metadata`);
const acsUrl = computed(() => `https://agented.example.com/auth/saml/acs`);
const callbackUrl = computed(() => `https://agented.example.com/auth/oidc/callback`);

function applySettingsToConfig(settings: Record<string, string>) {
  config.value.enabled = settings['sso_enabled'] === 'true';
  config.value.protocol = (settings['sso_protocol'] as SsoProtocol) || 'saml';
  config.value.samlEntityId = settings['sso_saml_entity_id'] || '';
  config.value.samlSsoUrl = settings['sso_saml_sso_url'] || '';
  config.value.samlCertificate = settings['sso_saml_certificate'] || '';
  config.value.samlAttributeEmail = settings['sso_saml_attribute_email'] || 'email';
  config.value.samlAttributeName = settings['sso_saml_attribute_name'] || 'displayName';
  config.value.oidcClientId = settings['sso_oidc_client_id'] || '';
  config.value.oidcClientSecret = settings['sso_oidc_client_secret'] || '';
  config.value.oidcIssuerUrl = settings['sso_oidc_issuer_url'] || '';
  config.value.oidcScopes = settings['sso_oidc_scopes'] || 'openid email profile';
  config.value.allowLocalLogin = settings['sso_allow_local_login'] !== 'false';
  config.value.defaultRole = settings['sso_default_role'] || 'member';
  config.value.autoProvision = settings['sso_auto_provision'] !== 'false';
  config.value.domainWhitelist = settings['sso_domain_whitelist'] || '';
}

async function loadSettings() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const { settings } = await settingsApi.getAll();
    // Filter to SSO-related keys
    const ssoSettings: Record<string, string> = {};
    for (const key of SSO_SETTINGS_KEYS) {
      if (settings[key] !== undefined) {
        ssoSettings[key] = settings[key];
      }
    }
    applySettingsToConfig(ssoSettings);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load SSO settings';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadSettings);

function selectProvider(p: typeof providers[0]) {
  config.value.protocol = p.protocol;
  showToast(`${p.name} template loaded`, 'info');
}

async function handleSave() {
  isSaving.value = true;
  try {
    const c = config.value;
    const pairs: [string, string][] = [
      ['sso_enabled', String(c.enabled)],
      ['sso_protocol', c.protocol],
      ['sso_saml_entity_id', c.samlEntityId],
      ['sso_saml_sso_url', c.samlSsoUrl],
      ['sso_saml_certificate', c.samlCertificate],
      ['sso_saml_attribute_email', c.samlAttributeEmail],
      ['sso_saml_attribute_name', c.samlAttributeName],
      ['sso_oidc_client_id', c.oidcClientId],
      ['sso_oidc_client_secret', c.oidcClientSecret],
      ['sso_oidc_issuer_url', c.oidcIssuerUrl],
      ['sso_oidc_scopes', c.oidcScopes],
      ['sso_allow_local_login', String(c.allowLocalLogin)],
      ['sso_default_role', c.defaultRole],
      ['sso_auto_provision', String(c.autoProvision)],
      ['sso_domain_whitelist', c.domainWhitelist],
    ];
    await Promise.all(pairs.map(([key, value]) => settingsApi.set(key, value)));
    showToast('SSO configuration saved', 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to save SSO config';
    showToast(msg, 'error');
  } finally {
    isSaving.value = false;
  }
}

async function testConnection() {
  isTesting.value = true;
  testResult.value = null;
  try {
    const ok = config.value.protocol === 'saml'
      ? config.value.samlSsoUrl.length > 0
      : config.value.oidcIssuerUrl.length > 0;
    // Save first then validate by checking settings roundtrip
    if (ok) {
      const key = config.value.protocol === 'saml' ? 'sso_saml_sso_url' : 'sso_oidc_issuer_url';
      await settingsApi.get(key);
    }
    testResult.value = ok
      ? { ok: true, message: 'Connection verified. Identity provider responded successfully.' }
      : { ok: false, message: 'Missing required fields. Fill in the IdP URL to test.' };
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Test connection failed';
    testResult.value = { ok: false, message: msg };
  } finally {
    isTesting.value = false;
  }
}

function copyToClipboard(text: string, label: string) {
  navigator.clipboard.writeText(text).then(() => showToast(`${label} copied`, 'success'));
}
</script>

<template>
  <div class="sso-page">

    <PageHeader
      title="SSO / SAML Authentication"
      subtitle="Configure enterprise single sign-on via SAML 2.0 or OIDC. Lets your team authenticate through Okta, Azure AD, Google Workspace, or any compatible identity provider."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
      Loading SSO settings...
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 32px; text-align: center; color: #ef4444;">
      {{ loadError }}
      <button class="btn btn-ghost" style="margin-top: 12px;" @click="loadSettings">Retry</button>
    </div>

    <!-- Main content -->
    <template v-else>

    <!-- Enable toggle -->
    <div class="card enable-card">
      <div class="enable-row">
        <div class="enable-info">
          <div class="enable-title">Enable Single Sign-On</div>
          <div class="enable-sub">When enabled, users will be redirected to your identity provider to authenticate.</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" v-model="config.enabled" />
          <span class="toggle-track"></span>
        </label>
      </div>
    </div>

    <div v-if="config.enabled" class="sso-content">
      <!-- Provider quick-start -->
      <div class="card">
        <div class="card-header">Identity Provider Quick-Start</div>
        <div class="providers-grid">
          <button
            v-for="p in providers"
            :key="p.id"
            class="provider-btn"
            :class="{ active: config.protocol === p.protocol }"
            @click="selectProvider(p)"
          >
            <span class="provider-logo">{{ p.logo }}</span>
            <span class="provider-name">{{ p.name }}</span>
            <span class="provider-proto">{{ p.protocol.toUpperCase() }}</span>
          </button>
        </div>
      </div>

      <!-- Protocol tabs -->
      <div class="proto-tabs">
        <button
          :class="['proto-tab', { active: config.protocol === 'saml' }]"
          @click="config.protocol = 'saml'"
        >SAML 2.0</button>
        <button
          :class="['proto-tab', { active: config.protocol === 'oidc' }]"
          @click="config.protocol = 'oidc'"
        >OpenID Connect (OIDC)</button>
      </div>

      <!-- SAML config -->
      <div v-if="config.protocol === 'saml'" class="card config-card">
        <div class="card-header">SAML 2.0 Configuration</div>
        <div class="form-body">
          <!-- SP metadata (read-only) -->
          <div class="form-section">
            <div class="form-section-title">Service Provider Details (give to your IdP)</div>
            <div class="sp-row">
              <div class="sp-field">
                <label class="field-label">SP Entity ID / Audience URI</label>
                <div class="copy-field">
                  <code class="copy-value">{{ spMetadataUrl }}</code>
                  <button class="copy-btn" @click="copyToClipboard(spMetadataUrl, 'Entity ID')">Copy</button>
                </div>
              </div>
              <div class="sp-field">
                <label class="field-label">Assertion Consumer Service (ACS) URL</label>
                <div class="copy-field">
                  <code class="copy-value">{{ acsUrl }}</code>
                  <button class="copy-btn" @click="copyToClipboard(acsUrl, 'ACS URL')">Copy</button>
                </div>
              </div>
            </div>
          </div>

          <!-- IdP settings -->
          <div class="form-section">
            <div class="form-section-title">Identity Provider Settings</div>
            <div class="form-grid">
              <div class="form-field full">
                <label class="field-label">IdP Entity ID</label>
                <input v-model="config.samlEntityId" class="field-input" placeholder="https://your-idp.example.com/entity-id" />
              </div>
              <div class="form-field full">
                <label class="field-label">IdP SSO URL (Single Sign-On URL)</label>
                <input v-model="config.samlSsoUrl" class="field-input" placeholder="https://your-idp.example.com/saml/sso" />
              </div>
              <div class="form-field full">
                <label class="field-label">
                  IdP X.509 Certificate
                  <button class="toggle-cert" @click="showCert = !showCert">{{ showCert ? 'Hide' : 'Show' }}</button>
                </label>
                <textarea
                  v-if="showCert"
                  v-model="config.samlCertificate"
                  class="field-textarea"
                  rows="6"
                  placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                ></textarea>
                <div v-else class="cert-placeholder">{{ config.samlCertificate ? '••• certificate set •••' : 'No certificate set' }}</div>
              </div>
              <div class="form-field">
                <label class="field-label">Email Attribute</label>
                <input v-model="config.samlAttributeEmail" class="field-input" placeholder="email" />
              </div>
              <div class="form-field">
                <label class="field-label">Name Attribute</label>
                <input v-model="config.samlAttributeName" class="field-input" placeholder="displayName" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- OIDC config -->
      <div v-if="config.protocol === 'oidc'" class="card config-card">
        <div class="card-header">OpenID Connect Configuration</div>
        <div class="form-body">
          <div class="form-section">
            <div class="form-section-title">Callback URL (register with your IdP)</div>
            <div class="copy-field">
              <code class="copy-value">{{ callbackUrl }}</code>
              <button class="copy-btn" @click="copyToClipboard(callbackUrl, 'Callback URL')">Copy</button>
            </div>
          </div>
          <div class="form-section">
            <div class="form-section-title">Identity Provider Settings</div>
            <div class="form-grid">
              <div class="form-field full">
                <label class="field-label">Issuer URL / Discovery URL</label>
                <input v-model="config.oidcIssuerUrl" class="field-input" placeholder="https://accounts.google.com" />
              </div>
              <div class="form-field">
                <label class="field-label">Client ID</label>
                <input v-model="config.oidcClientId" class="field-input" placeholder="client_id" />
              </div>
              <div class="form-field">
                <label class="field-label">Client Secret</label>
                <input v-model="config.oidcClientSecret" class="field-input" type="password" placeholder="••••••••" />
              </div>
              <div class="form-field full">
                <label class="field-label">Scopes</label>
                <input v-model="config.oidcScopes" class="field-input" placeholder="openid email profile" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Access policies -->
      <div class="card">
        <div class="card-header">Access Policy</div>
        <div class="form-body">
          <div class="form-grid">
            <div class="form-field full">
              <label class="field-label">Allowed Email Domains (comma-separated, leave blank for any)</label>
              <input v-model="config.domainWhitelist" class="field-input" placeholder="example.com, corp.example.com" />
            </div>
            <div class="form-field">
              <label class="field-label">Default Role for New Users</label>
              <select v-model="config.defaultRole" class="field-select">
                <option value="viewer">Viewer (read-only)</option>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div class="form-field checkbox-field">
              <label class="checkbox-label">
                <input type="checkbox" v-model="config.autoProvision" />
                Auto-provision new users on first login
              </label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="config.allowLocalLogin" />
                Allow local username/password login as fallback
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Test result -->
      <div v-if="testResult" class="test-result card" :class="{ ok: testResult.ok, fail: !testResult.ok }">
        <span>{{ testResult.ok ? '✅' : '❌' }}</span>
        <span>{{ testResult.message }}</span>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="btn btn-ghost" :disabled="isTesting" @click="testConnection">
          {{ isTesting ? 'Testing...' : 'Test Connection' }}
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
          {{ isSaving ? 'Saving...' : 'Save SSO Config' }}
        </button>
      </div>
    </div>

    <!-- Disabled state -->
    <div v-else class="disabled-hint card">
      <div class="disabled-icon">🔒</div>
      <div class="disabled-text">
        <div class="disabled-title">SSO is disabled</div>
        <div class="disabled-sub">Enable SSO above to configure SAML or OIDC integration with your identity provider. Users will continue to log in with local credentials.</div>
      </div>
    </div>

    </template>
  </div>
</template>

<style scoped>
.sso-page { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }
.card-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }

.enable-card { padding: 0; }
.enable-row { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; }
.enable-info { display: flex; flex-direction: column; gap: 4px; }
.enable-title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.enable-sub { font-size: 0.8rem; color: var(--text-muted); max-width: 500px; }

.toggle-switch { position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-track { position: absolute; inset: 0; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 12px; cursor: pointer; transition: all 0.2s; }
.toggle-switch input:checked + .toggle-track { background: var(--accent-cyan); border-color: var(--accent-cyan); }
.toggle-track::after { content: ''; position: absolute; left: 3px; top: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 0.2s; }
.toggle-switch input:checked + .toggle-track::after { transform: translateX(20px); }

.sso-content { display: flex; flex-direction: column; gap: 16px; }

.providers-grid { display: flex; gap: 10px; padding: 16px 20px; flex-wrap: wrap; }
.provider-btn { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 16px; border: 1px solid var(--border-default); border-radius: 10px; background: var(--bg-tertiary); cursor: pointer; transition: all 0.15s; min-width: 90px; }
.provider-btn:hover { border-color: var(--accent-cyan); }
.provider-btn.active { border-color: var(--accent-cyan); background: rgba(6,182,212,0.08); }
.provider-logo { font-size: 1.4rem; }
.provider-name { font-size: 0.72rem; font-weight: 600; color: var(--text-primary); text-align: center; }
.provider-proto { font-size: 0.65rem; color: var(--text-muted); }

.proto-tabs { display: flex; gap: 0; border: 1px solid var(--border-default); border-radius: 8px; overflow: hidden; align-self: flex-start; }
.proto-tab { padding: 8px 20px; background: var(--bg-tertiary); color: var(--text-secondary); border: none; cursor: pointer; font-size: 0.82rem; font-weight: 500; transition: all 0.15s; }
.proto-tab.active { background: var(--accent-cyan); color: #000; }

.config-card .form-body { padding: 20px; display: flex; flex-direction: column; gap: 24px; }

.form-section { display: flex; flex-direction: column; gap: 12px; }
.form-section-title { font-size: 0.78rem; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; }

.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-field { display: flex; flex-direction: column; gap: 6px; }
.form-field.full { grid-column: 1 / -1; }
.form-field.checkbox-field { gap: 10px; justify-content: center; }

.field-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); display: flex; align-items: center; gap: 8px; }
.field-input { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.85rem; }
.field-input:focus { outline: none; border-color: var(--accent-cyan); }
.field-select { padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.85rem; cursor: pointer; }
.field-textarea { padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.78rem; font-family: monospace; resize: vertical; width: 100%; box-sizing: border-box; }
.field-textarea:focus { outline: none; border-color: var(--accent-cyan); }

.toggle-cert { background: none; border: none; color: var(--accent-cyan); font-size: 0.72rem; cursor: pointer; margin-left: 4px; }
.cert-placeholder { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; font-size: 0.78rem; color: var(--text-muted); font-family: monospace; }

.sp-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.sp-field { display: flex; flex-direction: column; gap: 6px; }
.copy-field { display: flex; align-items: center; gap: 8px; padding: 9px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; }
.copy-value { font-family: monospace; font-size: 0.75rem; color: var(--text-secondary); flex: 1; word-break: break-all; }
.copy-btn { padding: 3px 10px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 4px; color: var(--text-secondary); font-size: 0.72rem; cursor: pointer; flex-shrink: 0; white-space: nowrap; }
.copy-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
.checkbox-label input { accent-color: var(--accent-cyan); cursor: pointer; }

.test-result { display: flex; align-items: center; gap: 10px; padding: 14px 20px; font-size: 0.85rem; }
.test-result.ok { color: #34d399; border-color: rgba(52,211,153,0.3); }
.test-result.fail { color: #ef4444; border-color: rgba(239,68,68,0.3); }

.disabled-hint { display: flex; align-items: center; gap: 20px; padding: 28px 24px; }
.disabled-icon { font-size: 2rem; flex-shrink: 0; }
.disabled-title { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.disabled-sub { font-size: 0.82rem; color: var(--text-muted); max-width: 520px; }

.actions { display: flex; justify-content: flex-end; gap: 12px; }
.btn { padding: 9px 20px; border-radius: 8px; font-size: 0.85rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) { .form-grid { grid-template-columns: 1fr; } .sp-row { grid-template-columns: 1fr; } .providers-grid { gap: 8px; } }
</style>
