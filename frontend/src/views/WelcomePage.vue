<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { resetAuthGuard } from '../router/guards';
import { useAuth } from '../composables/useAuth';
import { useTourMachine } from '../composables/useTourMachine';
import { aiAccountsClient } from '../services/api/backend-management';
import { healthApi } from '../services/api/system';
import AccountLoginModal from '../components/monitoring/AccountLoginModal.vue';
import { SUPPORTED_LOCALES, setLocale } from '../i18n';

const router = useRouter();
const { t, locale } = useI18n();
const { signup } = useAuth();
const tourMachine = useTourMachine();

function onLocaleChange(e: Event) {
  const lang = (e.target as HTMLSelectElement).value as 'en' | 'ko' | 'ja' | 'zh';
  setLocale(lang);
}

// Self-registration gate: open by default, but if AGENTED_DISABLE_SIGNUP was set
// BEFORE the first admin exists, the signup form would just 403 — so surface an
// explanatory state instead of a form that can't work.
const signupEnabled = ref(true);

// First-run page — clear any stale tour/key state from previous installs
onMounted(() => {
  localStorage.removeItem('agented-tour-state');
  localStorage.removeItem('agented-tour-machine-state');
  localStorage.removeItem('agented-api-key');
  healthApi
    .authStatus()
    .then((s: { signup_enabled?: boolean }) => { signupEnabled.value = s.signup_enabled !== false; })
    .catch(() => { /* leave open; the signup call itself will surface a 403 */ });
});

type Phase = 'welcome' | 'signup' | 'discover';
const phase = ref<Phase>('welcome');

function beginSetup() {
  tourMachine.startTour(); // idle -> welcome
  phase.value = 'signup';
}

// --- Step 1: account signup (replaces the old admin-API-key mint) ----------
const email = ref('');
const password = ref('');
const displayName = ref('');
const signingUp = ref(false);
const signupError = ref('');

async function submitSignup() {
  signupError.value = '';
  if (!email.value.trim() || !password.value) {
    signupError.value = t('welcome.signup.required');
    return;
  }
  if (password.value.length < 8) {
    signupError.value = t('welcome.signup.passwordTooShort');
    return;
  }
  signingUp.value = true;
  try {
    // First registrant becomes admin; useAuth.signup stores the minted admin
    // API key as X-API-Key (also the bearer the ai-accounts sidecar accepts
    // for discovery). resetAuthGuard clears the "needs setup" gate.
    await signup(email.value.trim(), password.value, displayName.value.trim() || undefined);
    resetAuthGuard();
    phase.value = 'discover';
  } catch (e) {
    signupError.value = e instanceof Error && e.message ? e.message : t('welcome.signup.failed');
  } finally {
    signingUp.value = false;
  }
}

// --- Step 2: auto-detect & import existing AI accounts ---------------------
interface DiscoveredItem {
  kind: string;
  path: string;
  suggested_name: string;
  is_logged_in: boolean;
  error: string | null;
  backend_id: string | null;
}
const detecting = ref(false);
const detectRan = ref(false);
const detectError = ref('');
const discovered = ref<DiscoveredItem[]>([]);
const importing = ref(false);
const showManualLogin = ref(false);

// Only logged-in, not-yet-imported configs are importable; already-imported
// ones (backend_id set) are shown as done.
const importable = computed(() => discovered.value.filter((i) => i.is_logged_in && !i.backend_id));

async function detectAccounts() {
  detecting.value = true;
  detectError.value = '';
  try {
    const { items } = await aiAccountsClient.discoverConfigs();
    discovered.value = items as DiscoveredItem[];
    detectRan.value = true;
  } catch (e) {
    detectError.value = e instanceof Error && e.message ? e.message : t('welcome.discover.detectFailed');
  } finally {
    detecting.value = false;
  }
}

const importError = ref('');
async function importAll() {
  if (!importable.value.length || importing.value) return;
  importing.value = true;
  importError.value = '';
  const total = importable.value.length;
  let failed = 0;
  try {
    for (const item of importable.value) {
      try {
        await aiAccountsClient.importDiscovered({
          kind: item.kind,
          path: item.path,
          display_name: item.suggested_name,
        });
      } catch {
        // Best-effort: keep importing the rest, but COUNT the failures so the
        // operator isn't left wondering why some accounts stayed unimported.
        failed++;
      }
    }
    if (failed > 0) {
      importError.value = t('welcome.discover.importPartial', { failed, total });
    }
    await detectAccounts();
  } finally {
    importing.value = false;
  }
}

function itemStatus(item: DiscoveredItem): 'imported' | 'ready' | 'loggedout' {
  if (item.backend_id) return 'imported';
  return item.is_logged_in ? 'ready' : 'loggedout';
}

function finishOnboarding() {
  resetAuthGuard();
  // If the shared tour actor wasn't ready when beginSetup fired START (cold
  // backend → the actor is briefly null and the event is dropped), the machine
  // is still 'idle'. Start it now so the in-app tour actually begins, then
  // advance welcome -> workspace.
  if (tourMachine.currentStep.value === 'idle') tourMachine.startTour();
  tourMachine.nextStep(); // welcome -> workspace
  router.push({ path: '/settings', hash: '#general' });
}
</script>

<template>
  <div class="welcome-root">
    <!-- Background layers -->
    <div class="bg-base"></div>
    <div class="bg-mesh"></div>
    <div class="bg-grain"></div>
    <div class="bg-grid"></div>

    <!-- Welcome phase -->
    <Transition name="phase-fade">
      <div v-if="phase === 'welcome'" key="welcome" class="welcome-content">
        <!-- Top bar -->
        <header class="top-bar">
          <div class="top-bar-logo">
            <div class="logo-square">
              <span class="logo-letter">A</span>
            </div>
            <span class="logo-name">Agented</span>
            <span class="logo-version">v0.5.0</span>
          </div>
          <div class="top-bar-lang">
            <svg class="lang-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <circle cx="12" cy="12" r="10"/>
              <line x1="2" y1="12" x2="22" y2="12"/>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            <select class="lang-select" :value="locale" @change="onLocaleChange">
              <option v-for="loc in SUPPORTED_LOCALES" :key="loc.code" :value="loc.code">
                {{ loc.nativeName }}
              </option>
            </select>
          </div>
        </header>

        <!-- Hero -->
        <section class="hero">
          <div class="hero-badge">
            <span class="badge-dot"></span>
            <span>{{ t('welcome.badge') }}</span>
          </div>
          <h1 class="hero-headline">{{ t('welcome.headline') }}</h1>
          <p class="hero-subtitle">{{ t('welcome.subtitle') }}</p>
        </section>

        <!-- Bento grid -->
        <section class="bento-grid">
          <div class="bento-cell">
            <span class="bento-tag">{{ t('welcome.bento.vision') }}</span>
            <span class="bento-label">{{ t('welcome.bento.productsProjects') }}</span>
            <span class="bento-desc">{{ t('welcome.bento.productsDesc') }}</span>
          </div>
          <div class="bento-cell">
            <span class="bento-tag">{{ t('welcome.bento.workforce') }}</span>
            <span class="bento-label">{{ t('welcome.bento.agentTeams') }}</span>
            <!-- [08.M2] Use <i18n-t> slot interpolation so the translated string is
                 never fed to v-html — the <span class="hl"> markup is static
                 template, and only plain-text labels flow through translation. -->
            <i18n-t keypath="welcome.bento.teamsDesc" tag="span" class="bento-desc" scope="global">
              <template #command><span class="hl">Command</span></template>
              <template #dev><span class="hl">Dev</span></template>
              <template #research><span class="hl">Research</span></template>
              <template #ops><span class="hl">Ops</span></template>
              <template #qa><span class="hl">QA</span></template>
            </i18n-t>
          </div>
          <div class="bento-cell">
            <span class="bento-tag">{{ t('welcome.bento.autonomous') }}</span>
            <span class="bento-label">{{ t('welcome.bento.scheduling') }}</span>
            <span class="bento-desc">{{ t('welcome.bento.schedulingDesc') }}</span>
          </div>
          <div class="bento-cell">
            <span class="bento-tag">{{ t('welcome.bento.engineering') }}</span>
            <span class="bento-label">{{ t('welcome.bento.harnessPlugins') }}</span>
            <span class="bento-desc">{{ t('welcome.bento.harnessDesc') }}</span>
          </div>
        </section>

        <!-- CTA -->
        <div class="cta-area">
          <button class="cta-btn" @click="beginSetup">{{ t('welcome.beginSetup') }}</button>
          <span class="cta-hint">{{ t('welcome.stepsHint') }}</span>
        </div>
      </div>
    </Transition>

    <!-- Signup phase (step 1) -->
    <Transition name="phase-fade">
      <div v-if="phase === 'signup'" key="signup" class="keygen-content">
        <form class="keygen-card" @submit.prevent="submitSignup">
          <h2 class="keygen-heading">{{ t('welcome.signup.heading') }}</h2>
          <p class="keygen-explanation">{{ t('welcome.signup.explanation') }}</p>
          <p v-if="!signupEnabled" class="keygen-error" data-test="signup-disabled">{{ t('welcome.signup.disabled') }}</p>

          <div class="form-field">
            <label for="ob-email">{{ t('welcome.signup.emailLabel') }}</label>
            <input id="ob-email" v-model="email" data-test="signup-email" type="email" autocomplete="email"
              :placeholder="t('welcome.signup.emailPlaceholder')" />
          </div>
          <div class="form-field">
            <label for="ob-password">{{ t('welcome.signup.passwordLabel') }}</label>
            <input id="ob-password" v-model="password" data-test="signup-password" type="password" autocomplete="new-password"
              :placeholder="t('welcome.signup.passwordPlaceholder')" />
          </div>
          <div class="form-field">
            <label for="ob-name">{{ t('welcome.signup.nameLabel') }}</label>
            <input id="ob-name" v-model="displayName" data-test="signup-name" type="text" autocomplete="name"
              :placeholder="t('welcome.signup.namePlaceholder')" />
          </div>

          <p v-if="signupError" class="keygen-error" data-test="signup-error">{{ signupError }}</p>

          <button data-test="signup-submit" class="continue-btn" type="submit" :disabled="signingUp || !signupEnabled">
            <svg v-if="signingUp" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            {{ signingUp ? t('welcome.signup.submitting') : t('welcome.signup.submit') }}
          </button>
        </form>
      </div>
    </Transition>

    <!-- Discover phase (step 2) — auto-detect & import existing AI accounts -->
    <Transition name="phase-fade">
      <div v-if="phase === 'discover'" key="discover" class="keygen-content">
        <div class="keygen-card discover-card">
          <h2 class="keygen-heading">{{ t('welcome.discover.heading') }}</h2>
          <p class="keygen-explanation">{{ t('welcome.discover.explanation') }}</p>

          <div v-if="!detectRan" class="keygen-action">
            <button data-test="detect-btn" class="generate-btn" :disabled="detecting" @click="detectAccounts">
              <svg v-if="detecting" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              {{ detecting ? t('welcome.discover.detecting') : t('welcome.discover.detect') }}
            </button>
          </div>

          <p v-if="detectError" class="keygen-error" data-test="detect-error">{{ detectError }}</p>
          <p v-if="importError" class="keygen-error" data-test="import-error">{{ importError }}</p>

          <template v-if="detectRan && !detecting">
            <p v-if="discovered.length === 0" class="discover-empty" data-test="discover-empty">
              {{ t('welcome.discover.none') }}
            </p>
            <ul v-else class="discover-list" data-test="discover-list">
              <li v-for="item in discovered" :key="item.path" class="discover-item">
                <div class="discover-item__main">
                  <span class="discover-item__name">{{ item.suggested_name }}</span>
                  <span class="discover-item__kind">{{ item.kind }}</span>
                </div>
                <span class="discover-item__status" :class="`is-${itemStatus(item)}`">
                  {{ t(`welcome.discover.status.${itemStatus(item)}`) }}
                </span>
              </li>
            </ul>

            <button
              v-if="importable.length"
              data-test="import-all-btn"
              class="generate-btn import-all-btn"
              :disabled="importing"
              @click="importAll"
            >
              <svg v-if="importing" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              {{ importing ? t('welcome.discover.importing') : t('welcome.discover.importAll', { count: importable.length }) }}
            </button>

            <button data-test="rescan-btn" class="link-btn" :disabled="detecting || importing" @click="detectAccounts">
              {{ t('welcome.discover.rescan') }}
            </button>
          </template>

          <!-- Manual fallback: Gemini / Antigravity is not auto-discoverable -->
          <button data-test="manual-add-btn" class="link-btn" @click="showManualLogin = true">
            {{ t('welcome.discover.manualAdd') }}
          </button>

          <button data-test="finish-btn" class="continue-btn" @click="finishOnboarding">
            {{ t('welcome.discover.finish') }}
          </button>
        </div>
      </div>
    </Transition>

    <AccountLoginModal
      :open="showManualLogin"
      backend-id="backend-gemini"
      backend-type="gemini"
      backend-name="Gemini (Antigravity)"
      :proxy-only="true"
      @close="showManualLogin = false"
      @success="showManualLogin = false"
    />
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* === Root & background layers === */
.welcome-root {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.bg-base {
  position: fixed;
  inset: 0;
  background: #09090b;
  z-index: 0;
}

.bg-mesh {
  position: fixed;
  inset: 0;
  z-index: 1;
  background:
    radial-gradient(ellipse 80% 60% at 30% 40%, rgba(79, 70, 229, 0.15) 0%, transparent 70%),
    radial-gradient(ellipse 70% 50% at 70% 60%, rgba(147, 51, 234, 0.12) 0%, transparent 70%);
  animation: meshDrift 20s ease-in-out infinite alternate;
}

@keyframes meshDrift {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(-20px, 10px) scale(1.05); }
}

.bg-grain {
  position: fixed;
  inset: 0;
  z-index: 2;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  pointer-events: none;
}

.bg-grid {
  position: fixed;
  inset: 0;
  z-index: 3;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
  background-size: 80px 80px;
  mask-image: radial-gradient(ellipse 60% 50% at 50% 40%, black 20%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse 60% 50% at 50% 40%, black 20%, transparent 70%);
  pointer-events: none;
}

/* === Phase transition === */
/* OB-03: total welcome→keygen→tour transition stays under 500ms.
 * Enter 250ms + leave 150ms = 400ms, with a 50ms cushion in case
 * the router/tour next-step takes a frame on slower devices. */
.phase-fade-enter-active {
  transition: opacity 250ms ease, transform 250ms ease;
}
.phase-fade-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.phase-fade-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.phase-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* === Welcome content === */
.welcome-content {
  position: relative;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
  padding: 0 24px 60px;
}

/* Top bar */
.top-bar {
  width: 100%;
  max-width: 900px;
  padding: 32px 0 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.top-bar-lang {
  display: flex;
  align-items: center;
  gap: 6px;
}

.lang-icon {
  color: #71717a;
}

.lang-select {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #a1a1aa;
  font-size: 12px;
  font-weight: 500;
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2371717a' fill='none' stroke-width='1.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 24px;
}

.lang-select:hover {
  border-color: rgba(255, 255, 255, 0.2);
  color: #e4e4e7;
}

.lang-select option {
  background: #18181b;
  color: #e4e4e7;
}

.top-bar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-square {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-letter {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.logo-name {
  font-size: 16px;
  font-weight: 600;
  color: #fafafa;
  letter-spacing: -0.2px;
}

.logo-version {
  font-size: 11px;
  color: #71717a;
  font-weight: 500;
}

/* Hero */
.hero {
  text-align: center;
  max-width: 640px;
  margin-top: 80px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 100px;
  background: rgba(79, 70, 229, 0.1);
  border: 1px solid rgba(79, 70, 229, 0.2);
  margin-bottom: 24px;
  font-size: 12px;
  font-weight: 500;
  color: #a5b4fc;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4f46e5;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

.hero-headline {
  font-size: 44px;
  font-weight: 700;
  letter-spacing: -2px;
  line-height: 1.1;
  margin: 0 0 20px;
  background: linear-gradient(180deg, #fafafa 0%, #a1a1aa 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hero-subtitle {
  font-size: 15px;
  line-height: 1.65;
  color: #71717a;
  margin: 0;
}

/* Bento grid */
.bento-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  max-width: 720px;
  width: 100%;
  margin-top: 48px;
  border-radius: 16px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
}

.bento-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 24px;
  background: rgba(9, 9, 11, 0.85);
}

.bento-tag {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  color: #4f46e5;
  letter-spacing: 0.5px;
}

.bento-label {
  font-size: 13px;
  font-weight: 600;
  color: #e4e4e7;
}

.bento-desc {
  font-size: 11.5px;
  color: #52525b;
  line-height: 1.55;
}

.bento-desc .hl {
  color: #71717a;
}

/* CTA */
.cta-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 48px;
}

.cta-btn {
  padding: 14px 32px;
  background: #fafafa;
  color: #09090b;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: transform 150ms ease, box-shadow 150ms ease;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.cta-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 20px rgba(250, 250, 250, 0.15);
}

.cta-hint {
  font-size: 12px;
  color: #52525b;
}

/* === Keygen content === */
.keygen-content {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
}

.keygen-card {
  background: rgba(24, 24, 27, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 48px;
  max-width: 480px;
  width: 100%;
  backdrop-filter: blur(16px);
}

.keygen-heading {
  font-size: 22px;
  font-weight: 700;
  color: #fafafa;
  margin: 0 0 12px;
  letter-spacing: -0.5px;
}

.keygen-explanation {
  font-size: 14px;
  color: #71717a;
  line-height: 1.6;
  margin: 0 0 32px;
}

.keygen-action {
  display: flex;
  justify-content: center;
}

.generate-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  background: #4f46e5;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: background 150ms ease;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.generate-btn:hover {
  background: #4338ca;
}

.generate-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.spin-icon {
  width: 16px;
  height: 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error state */
.keygen-error {
  text-align: center;
}

.keygen-error p {
  color: #ef4444;
  font-size: 14px;
  margin: 0 0 16px;
}

.continue-btn {
  width: 100%;
  padding: 14px;
  background: #fafafa;
  color: #09090b;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: transform 150ms ease, box-shadow 150ms ease;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.continue-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 20px rgba(250, 250, 250, 0.15);
}

.continue-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.continue-btn .spin-icon {
  margin-right: 6px;
  vertical-align: -3px;
}

/* === Signup form fields === */
.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
  text-align: left;
}

.form-field label {
  font-size: 12px;
  font-weight: 500;
  color: #a1a1aa;
}

.form-field input {
  padding: 11px 14px;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: #e4e4e7;
  font-size: 14px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.form-field input:focus {
  outline: none;
  border-color: rgba(79, 70, 229, 0.6);
}

/* === Discover === */
.discover-card {
  max-width: 520px;
}

.discover-empty {
  font-size: 13px;
  color: #71717a;
  text-align: center;
  margin: 8px 0 20px;
}

.discover-list {
  list-style: none;
  margin: 0 0 20px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.discover-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
}

.discover-item__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.discover-item__name {
  font-size: 13px;
  font-weight: 600;
  color: #e4e4e7;
  word-break: break-all;
}

.discover-item__kind {
  font-size: 11px;
  color: #71717a;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.discover-item__status {
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 100px;
  white-space: nowrap;
}

.discover-item__status.is-imported {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}

.discover-item__status.is-ready {
  background: rgba(79, 70, 229, 0.15);
  color: #a5b4fc;
}

.discover-item__status.is-loggedout {
  background: rgba(255, 255, 255, 0.06);
  color: #71717a;
}

.import-all-btn {
  width: 100%;
  justify-content: center;
  margin-bottom: 12px;
}

.link-btn {
  display: block;
  width: 100%;
  background: none;
  border: none;
  color: #a1a1aa;
  font-size: 12.5px;
  font-weight: 500;
  padding: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.link-btn:hover:not(:disabled) {
  color: #e4e4e7;
}

.link-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* === Responsive === */
@media (max-width: 640px) {
  .hero-headline {
    font-size: 32px;
    letter-spacing: -1px;
  }

  .bento-grid {
    grid-template-columns: 1fr;
  }

  .hero {
    margin-top: 48px;
  }

  .keygen-card {
    padding: 32px 24px;
  }
}
</style>
