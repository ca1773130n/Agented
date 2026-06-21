<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { competitorIntelApi, ApiError } from '../services/api';
import type {
  CompetitorSource,
  DetectedSignal,
  SuggestedCompetitor,
  AuthenticatedEventSource,
} from '../services/api';
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
// Source-kind selector. Empty string = auto-detect from the URL host (backend
// default — no `kind` sent). `'hn_query'` switches the identifier field to a
// free-text Hacker News search query (no host to detect, so kind is explicit).
const kind = ref('');
const isQuery = computed(() => kind.value === 'hn_query');

// Submit is gated ONLY on a non-empty identifier (URL or query) — an empty
// optional label must NEVER block the add (REQ-27 / wizard-defaults rule).
const canSubmit = computed(() => url.value.trim().length > 0 && !adding.value);

// --- Data ------------------------------------------------------------------
const sources = ref<CompetitorSource[]>([]);
const signals = ref<DetectedSignal[]>([]);
const loadingSignals = ref(false);

// --- Discovery review-queue state ------------------------------------------
const suggestions = ref<SuggestedCompetitor[]>([]);
const loadingSuggestions = ref(false);
const scanning = ref(false);
// Per-suggestion in-flight accept guard (drives the "Accepting…" label).
const acceptingId = ref<string | null>(null);

let signalStream: AuthenticatedEventSource | null = null;

function kindLabel(kind: string | null | undefined): string {
  switch (kind) {
    case 'github_repo':
      return t('competitorIntel.kindGithub');
    case 'arxiv':
      return t('competitorIntel.kindArxiv');
    case 'product_url':
      return t('competitorIntel.kindProduct');
    case 'hn_query':
      return t('competitorIntel.kindHnQuery');
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

async function loadSuggestions() {
  if (!projectId.value) return;
  loadingSuggestions.value = true;
  try {
    const res = await competitorIntelApi.listSuggestions(projectId.value);
    suggestions.value = res.suggestions;
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    loadingSuggestions.value = false;
  }
}

// Run the heavy discovery scan, then refresh the review queue.
async function runDiscovery() {
  if (!projectId.value || scanning.value) return;
  scanning.value = true;
  try {
    await competitorIntelApi.runDiscovery(projectId.value);
    await loadSuggestions();
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    scanning.value = false;
  }
}

async function acceptSuggestion(id: string) {
  if (!projectId.value || acceptingId.value) return;
  acceptingId.value = id;
  try {
    const res = await competitorIntelApi.acceptSuggestion(projectId.value, id);
    // Optimistic: drop from the queue and surface as a watched source.
    suggestions.value = suggestions.value.filter((s) => s.id !== id);
    sources.value = [res.source, ...sources.value];
    showToast(t('competitorIntel.acceptedToast'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.acceptError'), 'error');
  } finally {
    acceptingId.value = null;
  }
}

async function dismissSuggestion(id: string) {
  if (!projectId.value) return;
  try {
    await competitorIntelApi.dismissSuggestion(projectId.value, id);
    suggestions.value = suggestions.value.filter((s) => s.id !== id);
    showToast(t('competitorIntel.dismissedToast'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.dismissError'), 'error');
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
      // Empty kind = auto-detect; pass undefined so the backend host-detects.
      kind.value || undefined,
    );
    sources.value = [res.source, ...sources.value];
    url.value = '';
    label.value = '';
    kind.value = '';
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
  void loadSuggestions();
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
        <span class="ci-field-label">{{ t('competitorIntel.kindLabel') }}</span>
        <select v-model="kind" class="ci-input" :aria-label="t('competitorIntel.kindLabel')">
          <option value="">{{ t('competitorIntel.kindAuto') }}</option>
          <option value="hn_query">{{ t('competitorIntel.kindHnQuery') }}</option>
        </select>
      </label>
      <label class="ci-field">
        <span class="ci-field-label">{{
          isQuery ? t('competitorIntel.queryLabel') : t('competitorIntel.urlLabel')
        }}</span>
        <input
          v-model="url"
          :type="isQuery ? 'text' : 'url'"
          class="ci-input"
          :placeholder="
            isQuery ? t('competitorIntel.queryPlaceholder') : t('competitorIntel.urlPlaceholder')
          "
          :aria-label="isQuery ? t('competitorIntel.queryLabel') : t('competitorIntel.urlLabel')"
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

    <!-- Discovery review queue: suggested competitors awaiting accept/dismiss -->
    <div class="ci-suggestions">
      <div class="ci-suggestions-head">
        <h2 class="ci-section-title">{{ t('competitorIntel.suggestionsTitle') }}</h2>
        <button type="button" class="ci-submit ci-discover" :disabled="scanning" @click="runDiscovery">
          {{ scanning ? t('competitorIntel.adding') : t('competitorIntel.runDiscovery') }}
        </button>
      </div>
      <p v-if="loadingSuggestions && suggestions.length === 0" class="ci-empty">
        {{ t('competitorIntel.loading') }}
      </p>
      <p v-else-if="suggestions.length === 0" class="ci-empty">
        {{ t('competitorIntel.suggestionsEmpty') }}
      </p>
      <ul v-else class="ci-suggestion-list">
        <li v-for="sug in suggestions" :key="sug.id" class="ci-suggestion">
          <div class="ci-suggestion-main">
            <span class="ci-kind" :data-kind="sug.kind">{{ kindLabel(sug.kind) }}</span>
            <span class="ci-suggestion-url">{{ sug.candidate_url }}</span>
            <span v-if="sug.reason" class="ci-reason" :title="sug.reason">
              {{ t('competitorIntel.suggestionReason') }}: {{ sug.reason }}
            </span>
          </div>
          <div class="ci-suggestion-actions">
            <button
              type="button"
              class="ci-submit ci-accept"
              :disabled="acceptingId === sug.id"
              @click="acceptSuggestion(sug.id)"
            >
              {{ acceptingId === sug.id ? t('competitorIntel.accepting') : t('competitorIntel.accept') }}
            </button>
            <button type="button" class="ci-dismiss" @click="dismissSuggestion(sug.id)">
              {{ t('competitorIntel.dismiss') }}
            </button>
          </div>
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
/* --- Discovery review queue --- */
.ci-suggestions-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.ci-suggestions-head .ci-section-title {
  margin: 0;
}
.ci-discover {
  padding: 0.4rem 0.9rem;
  font-size: 0.85rem;
}
.ci-suggestion-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.ci-suggestion {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-color, #2a2a2a);
  border-radius: 8px;
  background: var(--surface-1, #1a1a1a);
}
.ci-suggestion-main {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  min-width: 0;
}
.ci-suggestion-url {
  color: var(--text-primary, #eee);
  font-size: 0.9rem;
  word-break: break-all;
}
/* The "why" chip — styled off .ci-kind but accented to read as an explanation. */
.ci-reason {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  background: var(--surface-2, #222);
  color: var(--accent, #4f8cff);
  max-width: 22rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ci-suggestion-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}
.ci-accept {
  padding: 0.35rem 0.8rem;
  font-size: 0.85rem;
}
.ci-dismiss {
  padding: 0.35rem 0.8rem;
  font-size: 0.85rem;
  border-radius: 6px;
  border: 1px solid var(--border-color, #2a2a2a);
  background: transparent;
  color: var(--text-secondary, #9aa0a6);
  cursor: pointer;
}
.ci-dismiss:hover {
  color: var(--text-primary, #eee);
}
</style>
