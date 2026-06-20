<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { competitorIntelApi, ApiError } from '../services/api';
import type { CompetitorSource, DetectedSignal, AuthenticatedEventSource } from '../services/api';
import { useToast } from '../composables/useToast';

const { t } = useI18n();
const showToast = useToast();

const props = defineProps<{
  projectId?: string;
}>();

const projectId = computed(() => props.projectId ?? '');

// --- Add-source form state -------------------------------------------------
const url = ref('');
const label = ref('');
const adding = ref(false);

// Submit is gated ONLY on a non-empty URL — an empty optional label must NEVER
// block the add (REQ-27 / wizard-defaults rule).
const canSubmit = computed(() => url.value.trim().length > 0 && !adding.value);

// --- Data ------------------------------------------------------------------
const sources = ref<CompetitorSource[]>([]);
const signals = ref<DetectedSignal[]>([]);
const loadingSignals = ref(false);

let signalStream: AuthenticatedEventSource | null = null;

function kindLabel(kind: string | null | undefined): string {
  switch (kind) {
    case 'github_repo':
      return t('competitorIntel.kindGithub');
    case 'arxiv':
      return t('competitorIntel.kindArxiv');
    case 'product_url':
      return t('competitorIntel.kindProduct');
    default:
      return kind ?? t('competitorIntel.kindUnknown');
  }
}

async function loadSources() {
  if (!projectId.value) return;
  try {
    const res = await competitorIntelApi.listSources(projectId.value);
    sources.value = res.sources;
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  }
}

async function loadSignals() {
  if (!projectId.value) return;
  loadingSignals.value = true;
  try {
    const res = await competitorIntelApi.listSignals(projectId.value);
    signals.value = res.signals;
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    loadingSignals.value = false;
  }
}

async function submitSource() {
  if (!canSubmit.value || !projectId.value) return;
  adding.value = true;
  try {
    // label may be empty — pass undefined so the backend stores NULL.
    const trimmedLabel = label.value.trim();
    const res = await competitorIntelApi.addSource(
      projectId.value,
      url.value.trim(),
      trimmedLabel || undefined,
    );
    sources.value = [res.source, ...sources.value];
    url.value = '';
    label.value = '';
    showToast(t('competitorIntel.addedToast', { kind: kindLabel(res.source.kind) }), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.addError'), 'error');
  } finally {
    adding.value = false;
  }
}

// --- Live SSE: prepend new ranked signals ----------------------------------
function onSignalFrame(event: MessageEvent) {
  try {
    const row = JSON.parse(event.data) as DetectedSignal;
    if (signals.value.some((s) => s.id === row.id)) return;
    // Insert so the list stays ordered by score desc (the backend's ranking).
    const next = [row, ...signals.value];
    next.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    signals.value = next;
  } catch {
    // Ignore malformed frames.
  }
}

function closeStream() {
  if (signalStream) {
    signalStream.close();
    signalStream = null;
  }
}

function openStream() {
  if (!projectId.value || signalStream) return;
  const es = competitorIntelApi.streamSignals(projectId.value);
  es.addEventListener('signal', onSignalFrame);
  es.addEventListener('done', () => {
    closeStream();
  });
  es.onerror = () => {
    closeStream();
  };
  signalStream = es;
}

async function refreshAll() {
  closeStream();
  void loadSources();
  // Await the signal backlog BEFORE opening the stream: an SSE frame arriving
  // mid-load would otherwise be overwritten by loadSignals' array replacement.
  await loadSignals();
  openStream();
}

watch(projectId, () => refreshAll());

onMounted(() => {
  refreshAll();
});

onUnmounted(() => {
  closeStream();
});
</script>

<template>
  <section class="competitor-intel">
    <header class="ci-header">
      <h1 class="ci-title">{{ t('competitorIntel.title') }}</h1>
      <p class="ci-subtitle">{{ t('competitorIntel.subtitle') }}</p>
    </header>

    <!-- Add a source -->
    <form class="ci-add-form" @submit.prevent="submitSource">
      <label class="ci-field">
        <span class="ci-field-label">{{ t('competitorIntel.urlLabel') }}</span>
        <input
          v-model="url"
          type="url"
          class="ci-input"
          :placeholder="t('competitorIntel.urlPlaceholder')"
          :aria-label="t('competitorIntel.urlLabel')"
        />
      </label>
      <label class="ci-field">
        <span class="ci-field-label">{{ t('competitorIntel.labelOptional') }}</span>
        <input
          v-model="label"
          type="text"
          class="ci-input"
          :placeholder="t('competitorIntel.labelPlaceholder')"
          :aria-label="t('competitorIntel.labelOptional')"
        />
      </label>
      <button type="submit" class="ci-submit" :disabled="!canSubmit">
        {{ adding ? t('competitorIntel.adding') : t('competitorIntel.submit') }}
      </button>
    </form>

    <!-- Watched sources -->
    <div class="ci-sources">
      <h2 class="ci-section-title">{{ t('competitorIntel.sourcesTitle') }}</h2>
      <p v-if="sources.length === 0" class="ci-empty">{{ t('competitorIntel.sourcesEmpty') }}</p>
      <ul v-else class="ci-source-list">
        <li v-for="s in sources" :key="s.id" class="ci-source">
          <span class="ci-kind" :data-kind="s.kind">{{ kindLabel(s.kind) }}</span>
          <span class="ci-source-url">{{ s.label || s.url }}</span>
        </li>
      </ul>
    </div>

    <!-- Ranked signals -->
    <div class="ci-signals">
      <h2 class="ci-section-title">{{ t('competitorIntel.signalsTitle') }}</h2>
      <p v-if="loadingSignals && signals.length === 0" class="ci-empty">
        {{ t('competitorIntel.loading') }}
      </p>
      <p v-else-if="signals.length === 0" class="ci-empty">
        {{ t('competitorIntel.signalsEmpty') }}
      </p>
      <ul v-else class="ci-signal-list">
        <li v-for="sig in signals" :key="sig.id" class="ci-signal">
          <div class="ci-signal-head">
            <span class="ci-signal-type">{{ sig.signal_type || t('competitorIntel.kindUnknown') }}</span>
            <span class="ci-signal-score">
              {{ t('competitorIntel.scoreLabel') }}: {{ (sig.score ?? 0).toFixed(2) }}
            </span>
          </div>
          <p class="ci-signal-summary">{{ sig.summary || t('competitorIntel.noSummary') }}</p>
          <span class="ci-signal-source">{{ sig.label || sig.url }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.competitor-intel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  max-width: 880px;
  margin: 0 auto;
}
.ci-title {
  font-size: 1.4rem;
  font-weight: 600;
  margin: 0;
}
.ci-subtitle {
  color: var(--text-secondary, #9aa0a6);
  margin: 0.25rem 0 0;
}
.ci-add-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: flex-end;
  padding: 1rem;
  border: 1px solid var(--border-color, #2a2a2a);
  border-radius: 8px;
  background: var(--surface-1, #1a1a1a);
}
.ci-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1 1 200px;
}
.ci-field-label {
  font-size: 0.8rem;
  color: var(--text-secondary, #9aa0a6);
}
.ci-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-color, #2a2a2a);
  border-radius: 6px;
  background: var(--surface-2, #111);
  color: var(--text-primary, #eee);
}
.ci-submit {
  padding: 0.55rem 1.1rem;
  border-radius: 6px;
  border: none;
  background: var(--accent, #4f8cff);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}
.ci-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ci-section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 0.5rem;
}
.ci-empty {
  color: var(--text-secondary, #9aa0a6);
  font-style: italic;
}
.ci-source-list,
.ci-signal-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.ci-source {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.ci-kind,
.ci-signal-type {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  background: var(--surface-2, #222);
  color: var(--text-secondary, #9aa0a6);
}
.ci-signal {
  padding: 0.75rem;
  border: 1px solid var(--border-color, #2a2a2a);
  border-radius: 8px;
  background: var(--surface-1, #1a1a1a);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.ci-signal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ci-signal-score {
  font-size: 0.8rem;
  color: var(--accent, #4f8cff);
}
.ci-signal-summary {
  margin: 0;
  color: var(--text-primary, #eee);
}
.ci-signal-source {
  font-size: 0.8rem;
  color: var(--text-secondary, #9aa0a6);
}
</style>
