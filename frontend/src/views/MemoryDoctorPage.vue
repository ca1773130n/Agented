<script setup lang="ts">
/**
 * Memory Health — Tesserae 0.17 `doctor`: init / graph-parse / registry /
 * staleness / lock checks for this instance's knowledge graph, grouped by
 * severity. Sibling of ActivitySummaryPage / DecisionsPage.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi, friendlyMemoryReason } from '../services/api/memory-system';
import { useMemoryJob } from '../composables/useMemoryJob';
import type {
  DoctorFinding,
  DoctorResult,
  LintFinding,
  LintReport,
  MemoryConfig,
} from '../services/api/memory-system';

const { t } = useI18n();

// Doctor runs as a BACKGROUND job (it can be slow); lint + config stay sync
// (fast, independent). The operator can leave the page mid-doctor-run.
const {
  result: doctorResult,
  error: doctorJobError,
  running: doctorLoading,
  run: runDoctor,
  showLatest: showLatestDoctor,
} = useMemoryJob<DoctorResult>('doctor');

const report = computed(() => doctorResult.value?.report ?? null);
const error = computed<string | null>(() => {
  if (doctorJobError.value) return doctorJobError.value;
  if (doctorResult.value && !doctorResult.value.ok) {
    return friendlyMemoryReason(doctorResult.value.reason, t) || t('memoryDoctor.failed');
  }
  return null;
});

// Lint + config load synchronously alongside the doctor job.
const lintLoading = ref(false);

// Tesserae `lint` — graph QUALITY (loaded alongside doctor; shared Refresh).
const lint = ref<LintReport | null>(null);
const lintError = ref<string | null>(null);
const LINT_CAP = 50; // don't render 500+ dangling-link rows; surface the count instead

// Tesserae `config status` — resolved LLM backend + liveness (loaded alongside).
const config = ref<MemoryConfig | null>(null);

// Tesserae `engine --all --once` — operator-triggered coalesced recompile.
const engineRunning = ref(false);
const engineMsg = ref<string | null>(null);
let enginePoll: ReturnType<typeof setInterval> | null = null;
let alive = true;

const SEV_ORDER: Record<string, number> = { error: 0, warn: 1, ok: 2 };
const LINT_SEV_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

const findings = computed<DoctorFinding[]>(() =>
  [...(report.value?.findings || [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 3) - (SEV_ORDER[b.severity] ?? 3),
  ),
);

const counts = computed(() => {
  const c: Record<string, number> = { error: 0, warn: 0, ok: 0 };
  for (const f of report.value?.findings || []) c[f.severity] = (c[f.severity] ?? 0) + 1;
  return c;
});

const lintFindings = computed<LintFinding[]>(() =>
  [...(lint.value?.findings || [])].sort(
    (a, b) => (LINT_SEV_ORDER[a.severity] ?? 3) - (LINT_SEV_ORDER[b.severity] ?? 3),
  ),
);
const lintTotal = computed(() => lint.value?.findings.length ?? 0);
const lintShown = computed(() => Math.min(lintTotal.value, LINT_CAP));
// Ordered [code, count] pairs, most frequent first, for the breakdown pills.
const lintByCode = computed(() =>
  Object.entries(lint.value?.by_code || {}).sort((a, b) => b[1] - a[1]),
);

function sevMod(s: string): string {
  if (s === 'error') return 'error';
  if (s === 'warn') return 'warn';
  return 'ok';
}
function lintSevMod(s: string): string {
  if (s === 'error') return 'error';
  if (s === 'warning') return 'warn';
  return 'ok';
}

// Lint + config only (sync). allSettled: independent — one HTTP failure must
// not blank the other.
async function loadLintConfig(refresh = false) {
  lintLoading.value = true;
  lintError.value = null;
  const [lnt, cfg] = await Promise.allSettled([
    memorySystemApi.lint(refresh),
    memorySystemApi.config(),
  ]);
  if (lnt.status === 'fulfilled') {
    lint.value = lnt.value.report;
    if (!lnt.value.ok) lintError.value = friendlyMemoryReason(lnt.value.reason, t) || t('memoryDoctor.lint.failed');
  } else {
    lintError.value = (lnt.reason as Error)?.message || t('memoryDoctor.lint.failed');
  }
  config.value = cfg.status === 'fulfilled' ? cfg.value : null;
  lintLoading.value = false;
}

// Kick the doctor background job + refresh lint/config together.
function refresh() {
  runDoctor();
  loadLintConfig(true);
}

function stopEnginePoll() {
  if (enginePoll) { clearInterval(enginePoll); enginePoll = null; }
}

async function runEngineRefresh() {
  if (engineRunning.value) return;
  engineRunning.value = true;
  engineMsg.value = t('memoryDoctor.engine.running');
  try {
    const { job_id } = await memorySystemApi.engineRefresh();
    if (!alive) { stopEnginePoll(); return; }
    enginePoll = setInterval(async () => {
      try {
        const job = await memorySystemApi.tesseraeJobStatus(job_id);
        if (job.status === 'running') return;
        stopEnginePoll();
        engineRunning.value = false;
        engineMsg.value =
          job.status === 'completed' && job.result?.ok
            ? t('memoryDoctor.engine.done')
            : friendlyMemoryReason(job.result?.reason, t) || t('memoryDoctor.engine.failed');
      } catch (e) {
        stopEnginePoll();
        engineRunning.value = false;
        engineMsg.value = (e as Error).message || t('memoryDoctor.engine.failed');
      }
    }, 3000);
  } catch (e) {
    engineRunning.value = false;
    engineMsg.value = (e as Error).message || t('memoryDoctor.engine.failed');
  }
}

onMounted(() => {
  showLatestDoctor(); // instant last doctor result (read-later)
  loadLintConfig();
});
onUnmounted(() => { alive = false; stopEnginePoll(); });
</script>

<template>
  <div class="doctor-page">
    <PageHeader :title="t('memoryDoctor.title')" :subtitle="t('memoryDoctor.subtitle')">
      <template #actions>
        <button class="doctor-refresh" :disabled="doctorLoading || lintLoading" @click="refresh()">
          {{ doctorLoading ? t('memoryJob.running') : t('memoryDoctor.refresh') }}
        </button>
      </template>
    </PageHeader>

    <!-- Backend & Engine — Tesserae `config status` liveness + `engine --once` refresh -->
    <div class="backend-bar">
      <div v-if="config" class="backend-info">
        <span class="backend-label">{{ t('memoryDoctor.backend.label') }}</span>
        <span class="backend-provider">{{ config.provider || '—' }}</span>
        <span v-if="config.effort" class="backend-effort">{{ config.effort }}</span>
        <span
          v-if="config.liveness_ok !== null"
          class="backend-live"
          :class="config.liveness_ok ? 'backend-live--ok' : 'backend-live--down'"
        >{{ config.liveness_ok ? t('memoryDoctor.backend.live') : t('memoryDoctor.backend.down') }}</span>
      </div>
      <div class="backend-engine">
        <span v-if="engineMsg" class="backend-engine__msg">{{ engineMsg }}</span>
        <button class="doctor-refresh" :disabled="engineRunning" @click="runEngineRefresh">
          {{ engineRunning ? t('memoryDoctor.engine.running') : t('memoryDoctor.engine.button') }}
        </button>
      </div>
    </div>

    <div v-if="doctorLoading && !report" class="doctor-state">
      {{ t('memoryDoctor.loading') }}
      <p class="doctor-bg-note">{{ t('memoryJob.background') }}</p>
    </div>
    <div v-else-if="error" class="doctor-state doctor-state--error">{{ error }}</div>

    <template v-else-if="report">
      <div class="doctor-counts">
        <span class="doctor-pill doctor-pill--error">{{ counts.error }} {{ t('memoryDoctor.errors') }}</span>
        <span class="doctor-pill doctor-pill--warn">{{ counts.warn }} {{ t('memoryDoctor.warnings') }}</span>
        <span class="doctor-pill doctor-pill--ok">{{ counts.ok }} {{ t('memoryDoctor.ok') }}</span>
        <span class="doctor-root" :title="report.project_root">{{ report.project_root }}</span>
      </div>

      <ul class="doctor-findings">
        <li
          v-for="f in findings"
          :key="f.check_id"
          class="doctor-finding"
          :class="`doctor-finding--${sevMod(f.severity)}`"
        >
          <div class="doctor-finding__head">
            <span class="doctor-finding__id">{{ f.check_id }}</span>
            <span class="doctor-finding__cat">{{ f.category }}</span>
            <span v-if="f.fixable" class="doctor-finding__fixable">{{ t('memoryDoctor.fixable') }}</span>
          </div>
          <div class="doctor-finding__msg">{{ f.message }}</div>
          <div v-if="f.suggestion" class="doctor-finding__suggestion">{{ f.suggestion }}</div>
        </li>
      </ul>
    </template>

    <div v-else class="doctor-state">{{ t('memoryDoctor.empty') }}</div>

    <!-- Graph lint — QUALITY (unsupported claims, orphans, wiki drift, staleness) -->
    <section v-if="!lintLoading" class="lint-section">
      <h2 class="lint-title">{{ t('memoryDoctor.lint.title') }}</h2>
      <p class="lint-subtitle">{{ t('memoryDoctor.lint.subtitle') }}</p>

      <div v-if="lintError" class="doctor-state doctor-state--error">{{ lintError }}</div>
      <template v-else-if="lint">
        <div v-if="lintTotal === 0" class="doctor-state">{{ t('memoryDoctor.lint.clean') }}</div>
        <template v-else>
          <div class="doctor-counts">
            <span class="doctor-pill doctor-pill--error">{{ (lint.by_severity || {}).error || 0 }} {{ t('memoryDoctor.errors') }}</span>
            <span class="doctor-pill doctor-pill--warn">{{ (lint.by_severity || {}).warning || 0 }} {{ t('memoryDoctor.warnings') }}</span>
            <span class="doctor-pill doctor-pill--ok">{{ (lint.by_severity || {}).info || 0 }} {{ t('memoryDoctor.lint.info') }}</span>
          </div>

          <div class="lint-codes">
            <span v-for="[code, n] in lintByCode" :key="code" class="lint-code-pill">
              {{ code }} <b>{{ n }}</b>
            </span>
          </div>

          <ul class="doctor-findings">
            <li
              v-for="(f, i) in lintFindings.slice(0, LINT_CAP)"
              :key="`${f.code}-${i}`"
              class="doctor-finding"
              :class="`doctor-finding--${lintSevMod(f.severity)}`"
            >
              <div class="doctor-finding__head">
                <span class="doctor-finding__id">{{ f.code }}</span>
                <span v-if="f.auto_fixable" class="doctor-finding__fixable">{{ t('memoryDoctor.lint.autoFixable') }}</span>
              </div>
              <div class="doctor-finding__msg">{{ f.message }}</div>
              <div v-if="f.suggested_fix" class="doctor-finding__suggestion">{{ f.suggested_fix }}</div>
              <div v-if="f.path" class="lint-path" :title="f.path">{{ f.path }}</div>
            </li>
          </ul>
          <p v-if="lintTotal > LINT_CAP" class="lint-truncated">
            {{ t('memoryDoctor.lint.truncated', { shown: lintShown, total: lintTotal }) }}
          </p>
        </template>
      </template>
    </section>
  </div>
</template>

<style scoped>
.doctor-page {
  max-width: 920px;
}
.doctor-refresh {
  padding: 6px 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary, #e4e4e7);
  font-size: 13px;
  cursor: pointer;
}
.doctor-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.doctor-state {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary, #a1a1aa);
}
.doctor-state--error {
  color: var(--danger);
}
.doctor-bg-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
}
.doctor-counts {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 16px 0 20px;
}
.doctor-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 100px;
}
.doctor-pill--error {
  background: var(--accent-crimson-dim);
  color: var(--danger);
}
.doctor-pill--warn {
  background: var(--accent-amber-dim);
  color: var(--warning);
}
.doctor-pill--ok {
  background: var(--accent-emerald-dim);
  color: var(--success);
}
.doctor-root {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doctor-findings {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doctor-finding {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-left-width: 3px;
  border-radius: 10px;
  padding: 12px 14px;
}
.doctor-finding--error {
  border-left-color: var(--danger);
}
.doctor-finding--warn {
  border-left-color: var(--warning);
}
.doctor-finding--ok {
  border-left-color: var(--success);
}
.doctor-finding__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.doctor-finding__id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
}
.doctor-finding__cat {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary, #71717a);
}
.doctor-finding__fixable {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 100px;
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}
.doctor-finding__msg {
  font-size: 13px;
  color: var(--text-primary, #d4d4d8);
  margin-top: 4px;
}
.doctor-finding__suggestion {
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
  margin-top: 4px;
}
.lint-section {
  margin-top: 36px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 24px;
}
.lint-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  margin: 0;
}
.lint-subtitle {
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
  margin: 4px 0 12px;
}
.lint-codes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
}
.lint-code-pill {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 100px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #a1a1aa);
  font-family: var(--font-mono, monospace);
}
.lint-code-pill b {
  color: var(--text-primary, #e4e4e7);
}
.lint-path {
  font-size: 11px;
  color: var(--text-secondary, #71717a);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono, monospace);
}
.lint-truncated {
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  text-align: center;
  margin-top: 12px;
}
.backend-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 16px 0 4px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: var(--bg-tertiary, #1a1a24);
}
.backend-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.backend-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary, #71717a);
}
.backend-provider {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  font-family: var(--font-mono, monospace);
}
.backend-effort {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 100px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #a1a1aa);
}
.backend-live {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 100px;
}
.backend-live--ok {
  background: var(--accent-emerald-dim);
  color: var(--success);
}
.backend-live--down {
  background: var(--accent-crimson-dim);
  color: var(--danger);
}
.backend-engine {
  display: flex;
  align-items: center;
  gap: 10px;
}
.backend-engine__msg {
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
}
</style>
