<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { healthApi } from '../services/api';
import { setApiKey } from '../services/api/client';
import { resetAuthGuard } from '../router/guards';
import { useTourMachine } from '../composables/useTourMachine';
import { SUPPORTED_LOCALES, setLocale } from '../i18n';

const router = useRouter();
const { t, locale } = useI18n();

function onLocaleChange(e: Event) {
  const lang = (e.target as HTMLSelectElement).value as 'en' | 'ko' | 'ja' | 'zh';
  setLocale(lang);
}
const tourMachine = useTourMachine();

// First-run page — clear any stale tour/key state from previous installs
onMounted(() => {
  localStorage.removeItem('agented-tour-state');
  localStorage.removeItem('agented-tour-machine-state');
  localStorage.removeItem('agented-api-key');
});

type Phase = 'welcome' | 'keygen';
const phase = ref<Phase>('welcome');
const generatedKey = ref('');
const generating = ref(false);
const error = ref('');
const copied = ref(false);

function beginSetup() {
  tourMachine.startTour(); // idle -> welcome
  phase.value = 'keygen';
}

async function generateKey() {
  generating.value = true;
  error.value = '';
  try {
    const result = await healthApi.setup('Admin');
    generatedKey.value = result.api_key;
  } catch (err) {
    error.value = t('welcome.generateFailed');
  } finally {
    generating.value = false;
  }
}

async function copyKey() {
  try {
    await navigator.clipboard.writeText(generatedKey.value);
  } catch {
    // Clipboard API may fail (non-HTTPS, no focus, etc.) — use fallback
    const el = document.querySelector('.key-value') as HTMLElement | null;
    if (el) {
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
  }
  // Always show visual feedback — stays until user navigates away
  copied.value = true;
}

function continueToApp() {
  setApiKey(generatedKey.value);
  resetAuthGuard(); // Clear the "needs setup" state so router guard allows navigation
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
            <span class="logo-version">v0.4.0</span>
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
            <span class="bento-desc" v-html="t('welcome.bento.teamsDesc', { command: '<span class=\'hl\'>Command</span>', dev: '<span class=\'hl\'>Dev</span>', research: '<span class=\'hl\'>Research</span>', ops: '<span class=\'hl\'>Ops</span>', qa: '<span class=\'hl\'>QA</span>' })"></span>
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

    <!-- Keygen phase -->
    <Transition name="phase-fade">
      <div v-if="phase === 'keygen'" key="keygen" class="keygen-content">
        <div class="keygen-card">
          <h2 class="keygen-heading">{{ t('welcome.generateKeyHeading') }}</h2>
          <p class="keygen-explanation">{{ t('welcome.generateKeyExplanation') }}</p>

          <div v-if="!generatedKey && !error" class="keygen-action">
            <button
              data-test="generate-key-btn"
              class="generate-btn"
              :disabled="generating"
              @click="generateKey"
            >
              <svg v-if="generating" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              {{ generating ? t('welcome.generating') : t('welcome.generateKey') }}
            </button>
          </div>

          <div v-if="error" class="keygen-error">
            <p>{{ error }}</p>
            <button data-test="generate-key-btn" class="generate-btn" @click="generateKey">{{ t('welcome.tryAgain') }}</button>
          </div>

          <div v-if="generatedKey" class="keygen-result">
            <div class="key-display">
              <code class="key-value">{{ generatedKey }}</code>
              <button class="copy-btn" :class="{ 'copy-btn--copied': copied }" @click="copyKey">
                <svg v-if="copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>
                {{ copied ? t('welcome.copied') : t('welcome.copyKey') }}
              </button>
            </div>
            <button data-test="continue-btn" class="continue-btn" @click="continueToApp">{{ t('welcome.continue') }}</button>
          </div>
        </div>
      </div>
    </Transition>
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
.phase-fade-enter-active {
  transition: opacity 300ms ease, transform 300ms ease;
}
.phase-fade-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
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

/* Key result */
.keygen-result {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.key-display {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 14px 16px;
}

.key-value {
  flex: 1;
  font-family: 'SF Mono', 'Monaco', 'Cascadia Code', monospace;
  font-size: 13px;
  color: #e4e4e7;
  word-break: break-all;
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.08);
  color: #a1a1aa;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease;
  white-space: nowrap;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

.copy-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fafafa;
}

.copy-btn--copied {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
  border-color: rgba(34, 197, 94, 0.3);
}

.copy-btn--copied svg {
  flex-shrink: 0;
}

.copy-btn--copied:hover {
  background: rgba(34, 197, 94, 0.2);
  color: #4ade80;
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
