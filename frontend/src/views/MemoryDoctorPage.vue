<script setup lang="ts">
/**
 * Memory Health — Tesserae 0.17 `doctor`: init / graph-parse / registry /
 * staleness / lock checks for this instance's knowledge graph, grouped by
 * severity. Sibling of ActivitySummaryPage / DecisionsPage.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type {
  DoctorFinding,
  DoctorReport,
  LintFinding,
  LintReport,
} from '../services/api/memory-system';

const { t } = useI18n();

const report = ref<DoctorReport | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// Tesserae `lint` — graph QUALITY (loaded alongside doctor; shared Refresh).
const lint = ref<LintReport | null>(null);
const lintError = ref<string | null>(null);
const LINT_CAP = 50; // don't render 500+ dangling-link rows; surface the count instead

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

async function load(refresh = false) {
  loading.value = true;
  error.value = null;
  lintError.value = null;
  try {
    const [doc, lnt] = await Promise.all([
      memorySystemApi.doctor(refresh),
      memorySystemApi.lint(refresh),
    ]);
    report.value = doc.report;
    if (!doc.ok) error.value = doc.reason || t('memoryDoctor.failed');
    lint.value = lnt.report;
    if (!lnt.ok) lintError.value = lnt.reason || t('memoryDoctor.lint.failed');
  } catch (e) {
    error.value = (e as Error).message || t('memoryDoctor.failed');
  } finally {
    loading.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <div class="doctor-page">
    <PageHeader :title="t('memoryDoctor.title')" :subtitle="t('memoryDoctor.subtitle')">
      <template #actions>
        <button class="doctor-refresh" :disabled="loading" @click="load(true)">
          {{ t('memoryDoctor.refresh') }}
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="doctor-state">{{ t('memoryDoctor.loading') }}</div>
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
    <section v-if="!loading" class="lint-section">
      <h2 class="lint-title">{{ t('memoryDoctor.lint.title') }}</h2>
      <p class="lint-subtitle">{{ t('memoryDoctor.lint.subtitle') }}</p>

      <div v-if="lintError" class="doctor-state doctor-state--error">{{ lintError }}</div>
      <template v-else-if="lint">
        <div v-if="lintTotal === 0" class="doctor-state">{{ t('memoryDoctor.lint.clean') }}</div>
        <template v-else>
          <div class="doctor-counts">
            <span class="doctor-pill doctor-pill--error">{{ lint.by_severity.error || 0 }} {{ t('memoryDoctor.errors') }}</span>
            <span class="doctor-pill doctor-pill--warn">{{ lint.by_severity.warning || 0 }} {{ t('memoryDoctor.warnings') }}</span>
            <span class="doctor-pill doctor-pill--ok">{{ lint.by_severity.info || 0 }} {{ t('memoryDoctor.lint.info') }}</span>
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
  padding: 24px;
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
  color: #ef4444;
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
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}
.doctor-pill--warn {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}
.doctor-pill--ok {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
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
  border-left-color: #ef4444;
}
.doctor-finding--warn {
  border-left-color: #eab308;
}
.doctor-finding--ok {
  border-left-color: #22c55e;
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
  background: rgba(79, 70, 229, 0.15);
  color: #a5b4fc;
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
</style>
