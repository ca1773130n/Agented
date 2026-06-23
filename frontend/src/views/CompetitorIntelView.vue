<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { competitorIntelApi, lookalikeApi, ApiError } from '../services/api';
import type {
  CompetitorSource,
  DetectedSignal,
  SuggestedCompetitor,
  MarketLookalike,
  Strategy,
  CompetitorIntelConfig,
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
// In-flight guard for the operator "check now" force-poll (disables the button).
const polling = ref(false);
const signals = ref<DetectedSignal[]>([]);
const loadingSignals = ref(false);

// --- GLOBAL scheduled auto-check config ------------------------------------
// This is an INSTANCE-WIDE setting: one scheduled job polls every active source
// across ALL projects, so enabling it here turns on auto-checking everywhere.
const autoCheckEnabled = ref(false);
const autoCheckInterval = ref(15);
const savingAutoCheck = ref(false);
const AUTO_CHECK_INTERVALS = [5, 15, 30, 60];

// --- Discovery review-queue state ------------------------------------------
const suggestions = ref<SuggestedCompetitor[]>([]);
const loadingSuggestions = ref(false);
const scanning = ref(false);
// Per-suggestion in-flight accept guard (drives the "Accepting…" label).
const acceptingId = ref<string | null>(null);

// --- Market-lookalike review-queue state (phase 27 — the P5 loop) ----------
// `lookalikeProvider === null` is the BUY-gate signal: no provider keyed → the
// "configure a provider" CTA (the headline graceful-degradation state). A
// non-null name → the scan/review queue is live.
const lookalikes = ref<MarketLookalike[]>([]);
const lookalikeProvider = ref<string | null>(null);
const loadingLookalikes = ref(false);
const scanningLookalikes = ref(false);
// `true` once a scan returns `outcome: 'no_seed'` — the project has no product_url
// competitor_source to derive a seed from. Drives the "add a product source" hint.
const lookalikeNoSeed = ref(false);
// Per-lookalike in-flight accept guard (drives the "Accepting…" label).
const acceptingLookalikeId = ref<string | null>(null);

// --- Strategy review-queue state (phase 26 — the P4 HITL loop) -------------
const strategies = ref<Strategy[]>([]);
const loadingStrategies = ref(false);
const generatingStrategy = ref(false);
// Per-strategy in-flight verdict guard (drives the "…" labels on approve/reject).
const strategyInFlight = ref<string | null>(null);

// The 7 canonical §5B legal-checklist items — MUST match the backend
// LEGAL_CHECKLIST_ITEMS (app/db/competitor_strategies.py). Each renders as a
// toggle whose affirmation contributes to clearing the implement gate.
const LEGAL_ITEMS = [
  'clean_room',
  'no_copied_code',
  'independent_authorship',
  'license_review',
  'patent_fto',
  'trademark_clear',
  'no_confidential_source',
] as const;

// i18n key for each legal item's operator-facing label.
function legalItemLabel(key: string): string {
  switch (key) {
    case 'clean_room':
      return t('competitorIntel.legalCleanRoom');
    case 'no_copied_code':
      return t('competitorIntel.legalNoCopiedCode');
    case 'independent_authorship':
      return t('competitorIntel.legalIndependentAuthorship');
    case 'license_review':
      return t('competitorIntel.legalLicenseReview');
    case 'patent_fto':
      return t('competitorIntel.legalPatentFto');
    case 'trademark_clear':
      return t('competitorIntel.legalTrademarkClear');
    case 'no_confidential_source':
      return t('competitorIntel.legalNoConfidentialSource');
    default:
      return key;
  }
}

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
    case 'company':
      return t('competitorIntel.kindCompany');
    case 'product':
      return t('competitorIntel.kindProduct');
    default:
      return kind ?? t('competitorIntel.kindUnknown');
  }
}

function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'proposed':
      return t('competitorIntel.statusProposed');
    case 'approved':
      return t('competitorIntel.statusApproved');
    case 'rejected':
      return t('competitorIntel.statusRejected');
    case 'implementing':
      return t('competitorIntel.statusImplementing');
    case 'done':
      return t('competitorIntel.statusDone');
    default:
      return status ?? '';
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

/** Render a `last_polled_at` UTC timestamp as a short localized "checked" time. */
function formatChecked(value: string): string {
  // Backend writes a SQLite UTC timestamp ("YYYY-MM-DD HH:MM:SS"); make it an
  // explicit UTC ISO string so the Date parse isn't browser-local-ambiguous.
  const iso = value.includes('T') ? value : value.replace(' ', 'T') + 'Z';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

/**
 * Operator "check now": force-poll this project's active sources, then refresh
 * signals + sources so the operator sees monitoring work. A `changed > 0` run
 * reports how many sources moved; otherwise a reassuring "baseline captured"
 * note (monitoring IS live even when nothing changed yet).
 */
async function pollNow() {
  if (!projectId.value || polling.value) return;
  polling.value = true;
  try {
    const res = await competitorIntelApi.pollNow(projectId.value);
    await Promise.all([loadSignals(), loadSources()]);
    if (res.changed > 0) {
      showToast(t('competitorIntel.pollChanged', { count: res.changed }), 'success');
    } else {
      showToast(t('competitorIntel.pollNoChange'), 'info');
    }
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.pollError'), 'error');
  } finally {
    polling.value = false;
  }
}

/**
 * Load the GLOBAL scheduled-poll config so the toggle reflects the live
 * instance-wide setting (not per-project). Failures are non-fatal — the toggle
 * just stays at its default-disabled state.
 */
async function loadAutoCheckConfig() {
  try {
    const cfg = await competitorIntelApi.getConfig();
    autoCheckEnabled.value = !!cfg.enabled;
    if (AUTO_CHECK_INTERVALS.includes(cfg.polling_minutes)) {
      autoCheckInterval.value = cfg.polling_minutes;
    }
  } catch {
    // Non-fatal: leave the toggle at its default-disabled state.
  }
}

/**
 * Persist the GLOBAL scheduled-poll config (enable/disable + interval). Takes
 * effect at runtime (no restart). On failure, revert the optimistic UI to the
 * server's truth by reloading the config.
 */
async function saveAutoCheckConfig() {
  if (savingAutoCheck.value) return;
  savingAutoCheck.value = true;
  const payload: CompetitorIntelConfig = {
    enabled: autoCheckEnabled.value,
    polling_minutes: autoCheckInterval.value,
  };
  try {
    const cfg = await competitorIntelApi.saveConfig(payload);
    autoCheckEnabled.value = !!cfg.enabled;
    autoCheckInterval.value = cfg.polling_minutes;
    showToast(
      cfg.enabled
        ? t('competitorIntel.autoCheckOn', { minutes: cfg.polling_minutes })
        : t('competitorIntel.autoCheckOff'),
      'success',
    );
  } catch (err) {
    showToast(
      err instanceof ApiError ? err.message : t('competitorIntel.autoCheckError'),
      'error',
    );
    await loadAutoCheckConfig();
  } finally {
    savingAutoCheck.value = false;
  }
}

function toggleAutoCheck() {
  autoCheckEnabled.value = !autoCheckEnabled.value;
  void saveAutoCheckConfig();
}

function onAutoCheckIntervalChange() {
  void saveAutoCheckConfig();
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

// --- Market-lookalike handlers (clone the discovery review-queue pattern) ---
async function loadLookalikes() {
  if (!projectId.value) return;
  loadingLookalikes.value = true;
  try {
    const res = await lookalikeApi.listSuggestions(projectId.value);
    lookalikeProvider.value = res.provider;
    lookalikes.value = res.suggestions;
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    loadingLookalikes.value = false;
  }
}

// Run the provider-aware lookalike scan, then refresh the review queue. The scan
// is BUY-gated server-side: with no provider keyed it returns a 200 the UI never
// even reaches (the Scan button only renders when a provider IS configured).
async function runLookalikeScan() {
  if (!projectId.value || scanningLookalikes.value) return;
  scanningLookalikes.value = true;
  try {
    // Seedless: the server derives seed(s) from the project's product_url sources.
    const res = await lookalikeApi.scan(projectId.value);
    // `no_seed` is a graceful 200 (no product source to seed from) — surface the hint
    // instead of a toast; any other outcome clears it.
    lookalikeNoSeed.value = res.outcome === 'no_seed';
    await loadLookalikes();
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    scanningLookalikes.value = false;
  }
}

async function acceptLookalike(id: string) {
  if (!projectId.value || acceptingLookalikeId.value) return;
  acceptingLookalikeId.value = id;
  try {
    const res = await lookalikeApi.accept(projectId.value, id);
    // Optimistic: drop from the queue and surface as a watched source.
    lookalikes.value = lookalikes.value.filter((s) => s.id !== id);
    sources.value = [res.source, ...sources.value];
    showToast(t('competitorIntel.lookalikes.acceptedToast'), 'success');
  } catch (err) {
    showToast(
      err instanceof ApiError ? err.message : t('competitorIntel.lookalikes.acceptError'),
      'error',
    );
  } finally {
    acceptingLookalikeId.value = null;
  }
}

async function dismissLookalike(id: string) {
  if (!projectId.value) return;
  try {
    await lookalikeApi.dismiss(projectId.value, id);
    lookalikes.value = lookalikes.value.filter((s) => s.id !== id);
    showToast(t('competitorIntel.lookalikes.dismissedToast'), 'success');
  } catch (err) {
    showToast(
      err instanceof ApiError ? err.message : t('competitorIntel.lookalikes.dismissError'),
      'error',
    );
  }
}

// --- Strategy handlers (clone the discovery mutate pattern) ----------------
async function loadStrategies() {
  if (!projectId.value) return;
  loadingStrategies.value = true;
  try {
    const res = await competitorIntelApi.listStrategies(projectId.value);
    strategies.value = res.strategies;
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.loadError'), 'error');
  } finally {
    loadingStrategies.value = false;
  }
}

// Replace a strategy in the list with its updated row (optimistic merge).
function patchStrategy(updated: Strategy) {
  strategies.value = strategies.value.map((s) => (s.id === updated.id ? updated : s));
}

// Generate a strategy from the currently-listed signals, then refresh the queue.
async function generateStrategy() {
  if (!projectId.value || generatingStrategy.value) return;
  const signalIds = signals.value.map((s) => s.id);
  if (signalIds.length === 0) {
    showToast(t('competitorIntel.signalsEmpty'), 'error');
    return;
  }
  generatingStrategy.value = true;
  try {
    await competitorIntelApi.generateStrategy(projectId.value, signalIds);
    await loadStrategies();
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  } finally {
    generatingStrategy.value = false;
  }
}

async function approveStrategy(id: string) {
  if (!projectId.value || strategyInFlight.value) return;
  strategyInFlight.value = id;
  try {
    const res = await competitorIntelApi.approveStrategy(projectId.value, id);
    patchStrategy(res.strategy);
    showToast(t('competitorIntel.approvedToast'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  } finally {
    strategyInFlight.value = null;
  }
}

async function rejectStrategy(id: string) {
  if (!projectId.value || strategyInFlight.value) return;
  strategyInFlight.value = id;
  try {
    const res = await competitorIntelApi.rejectStrategy(projectId.value, id);
    patchStrategy(res.strategy);
    showToast(t('competitorIntel.rejectedToast'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  } finally {
    strategyInFlight.value = null;
  }
}

// Implement step: materialize an approved + §5B-cleared strategy into a ProjectPlan.
// The button is already disabled until legal_cleared_at; the dangerous agent-run
// (autoimplement) is a separate triple-gated backend route, intentionally NOT here.
async function materializeStrategy(id: string) {
  if (!projectId.value || strategyInFlight.value) return;
  strategyInFlight.value = id;
  try {
    const res = await competitorIntelApi.materializeStrategy(projectId.value, id);
    patchStrategy(res.strategy);
    showToast(t('competitorIntel.implementedToast'), 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  } finally {
    strategyInFlight.value = null;
  }
}

// Save an edited body (called on textarea blur). Resets the legal clearance
// server-side (§5B edit-resets-clearance) — the implement gate re-locks.
async function saveStrategyBody(id: string, body: string) {
  if (!projectId.value) return;
  try {
    const res = await competitorIntelApi.editStrategy(projectId.value, id, { body });
    patchStrategy(res.strategy);
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  }
}

// Toggle one §5B legal item; the returned row carries the (possibly flipped)
// legal_cleared_at so the implement affordance enables exactly at 7/7.
async function toggleLegalItem(id: string, itemKey: string, value: boolean) {
  if (!projectId.value) return;
  try {
    const res = await competitorIntelApi.recordLegalItem(projectId.value, id, itemKey, value);
    const wasCleared = strategies.value.find((s) => s.id === id)?.legal_cleared_at;
    patchStrategy(res.strategy);
    if (!wasCleared && res.strategy.legal_cleared_at) {
      showToast(t('competitorIntel.legalClearedToast'), 'success');
    }
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
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
  void loadLookalikes();
  void loadStrategies();
  // Await the signal backlog BEFORE opening the stream: an SSE frame arriving
  // mid-load would otherwise be overwritten by loadSignals' array replacement.
  await loadSignals();
  openStream();
}

watch(projectId, () => refreshAll());

onMounted(() => {
  refreshAll();
  // The auto-check config is GLOBAL (not project-scoped), so load it once.
  void loadAutoCheckConfig();
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
      <div class="ci-sources-head">
        <h2 class="ci-section-title">{{ t('competitorIntel.sourcesTitle') }}</h2>
        <div class="ci-sources-actions">
          <!-- GLOBAL auto-check toggle: one scheduled job polls every active
               source across ALL projects, so this is an instance-wide setting. -->
          <div class="ci-autocheck">
            <button
              type="button"
              class="toggle-switch ci-autocheck-switch"
              :class="{ active: autoCheckEnabled }"
              role="switch"
              :aria-checked="autoCheckEnabled"
              :aria-label="t('competitorIntel.autoCheckLabel')"
              :disabled="savingAutoCheck"
              tabindex="0"
              @click="toggleAutoCheck"
              @keydown.enter.prevent="toggleAutoCheck"
              @keydown.space.prevent="toggleAutoCheck"
            >
              <span class="toggle-knob" />
            </button>
            <span class="ci-autocheck-text">
              <span class="ci-autocheck-title">{{ t('competitorIntel.autoCheckLabel') }}</span>
              <span class="ci-autocheck-hint">{{ t('competitorIntel.autoCheckGlobalHint') }}</span>
            </span>
            <select
              v-model.number="autoCheckInterval"
              class="ci-input ci-autocheck-interval"
              :disabled="!autoCheckEnabled || savingAutoCheck"
              :aria-label="t('competitorIntel.autoCheckIntervalLabel')"
              @change="onAutoCheckIntervalChange"
            >
              <option v-for="m in AUTO_CHECK_INTERVALS" :key="m" :value="m">
                {{ t('competitorIntel.autoCheckEvery', { minutes: m }) }}
              </option>
            </select>
          </div>
          <button
            type="button"
            class="ci-submit ci-poll-now"
            :disabled="polling"
            @click="pollNow"
          >
            {{ polling ? t('competitorIntel.polling') : t('competitorIntel.pollNow') }}
          </button>
        </div>
      </div>
      <p v-if="sources.length === 0" class="ci-empty">{{ t('competitorIntel.sourcesEmpty') }}</p>
      <ul v-else class="ci-source-list">
        <li v-for="s in sources" :key="s.id" class="ci-source">
          <span class="ci-kind" :data-kind="s.kind">{{ kindLabel(s.kind) }}</span>
          <span class="ci-source-url">{{ s.label || s.url }}</span>
          <span
            v-if="s.last_polled_at"
            class="ci-source-checked"
          >{{ t('competitorIntel.lastChecked', { time: formatChecked(s.last_polled_at) }) }}</span>
          <span v-else class="ci-source-checked ci-source-unchecked">
            {{ t('competitorIntel.neverChecked') }}
          </span>
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

    <!-- Strategy review queue: generate → review → approve/reject/edit → §5B legal -->
    <div class="ci-strategies">
      <div class="ci-suggestions-head">
        <h2 class="ci-section-title">{{ t('competitorIntel.strategiesTitle') }}</h2>
        <button
          type="button"
          class="ci-submit ci-discover"
          :disabled="generatingStrategy"
          @click="generateStrategy"
        >
          {{ generatingStrategy ? t('competitorIntel.adding') : t('competitorIntel.generateStrategy') }}
        </button>
      </div>
      <p v-if="loadingStrategies && strategies.length === 0" class="ci-empty">
        {{ t('competitorIntel.loading') }}
      </p>
      <p v-else-if="strategies.length === 0" class="ci-empty">
        {{ t('competitorIntel.strategiesEmpty') }}
      </p>
      <ul v-else class="ci-strategy-list">
        <li v-for="st in strategies" :key="st.id" class="ci-strategy">
          <div class="ci-strategy-head">
            <span class="ci-kind" :data-kind="st.status">{{ statusLabel(st.status) }}</span>
            <span class="ci-strategy-title">{{ st.title || t('competitorIntel.noSummary') }}</span>
          </div>
          <textarea
            class="ci-input ci-strategy-body"
            :value="st.body || ''"
            :aria-label="t('competitorIntel.editStrategy')"
            @blur="saveStrategyBody(st.id, ($event.target as HTMLTextAreaElement).value)"
          ></textarea>
          <div class="ci-strategy-actions">
            <button
              type="button"
              class="ci-submit ci-accept"
              :disabled="strategyInFlight === st.id || st.status !== 'proposed'"
              @click="approveStrategy(st.id)"
            >
              {{ t('competitorIntel.approve') }}
            </button>
            <button
              type="button"
              class="ci-dismiss"
              :disabled="strategyInFlight === st.id"
              @click="rejectStrategy(st.id)"
            >
              {{ t('competitorIntel.reject') }}
            </button>
          </div>

          <!-- §5B legal checklist — the VISIBLE non-bypassable implement gate -->
          <div class="ci-legal">
            <h3 class="ci-legal-title">{{ t('competitorIntel.legalChecklistTitle') }}</h3>
            <ul class="ci-legal-list">
              <li v-for="item in LEGAL_ITEMS" :key="item" class="ci-legal-item">
                <label class="ci-legal-label">
                  <input
                    type="checkbox"
                    :checked="!!(st.legal_checklist && st.legal_checklist[item])"
                    @change="toggleLegalItem(st.id, item, ($event.target as HTMLInputElement).checked)"
                  />
                  <span>{{ legalItemLabel(item) }}</span>
                </label>
              </li>
            </ul>
            <button
              type="button"
              class="ci-submit ci-implement"
              :disabled="!st.legal_cleared_at || strategyInFlight === st.id || st.status !== 'approved'"
              :title="!st.legal_cleared_at ? t('competitorIntel.legalChecklistTitle') : ''"
              @click="materializeStrategy(st.id)"
            >
              {{ t('competitorIntel.implement') }}
            </button>
          </div>
        </li>
      </ul>
    </div>

    <!-- Market lookalikes (phase 27 P5): provider-pluggable scan→review→accept.
         THREE states: (1) provider===null → "configure a provider" CTA (the
         dominant default-install state — no scan button, no fake rows); (2)
         provider set + empty → empty line + Scan button; (3) provider set +
         populated → the review queue. -->
    <div class="ci-lookalikes">
      <div class="ci-suggestions-head">
        <h2 class="ci-section-title">{{ t('competitorIntel.lookalikes.title') }}</h2>
        <button
          v-if="lookalikeProvider !== null"
          type="button"
          class="ci-submit ci-discover"
          :disabled="scanningLookalikes"
          @click="runLookalikeScan"
        >
          {{ scanningLookalikes ? t('competitorIntel.lookalikes.scanning') : t('competitorIntel.lookalikes.scan') }}
        </button>
      </div>

      <!-- State 1: no provider keyed — the graceful-degradation CTA card -->
      <div v-if="lookalikeProvider === null" class="ci-lookalike-cta">
        <p class="ci-lookalike-cta-title">{{ t('competitorIntel.lookalikes.notConfigured.title') }}</p>
        <p class="ci-lookalike-cta-hint">{{ t('competitorIntel.lookalikes.notConfigured.hint') }}</p>
        <a
          class="ci-lookalike-cta-link"
          href="https://docs.apistemic.com"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ t('competitorIntel.lookalikes.notConfigured.docsLink') }}
        </a>
      </div>

      <!-- State 2: provider keyed, queue empty -->
      <p
        v-else-if="loadingLookalikes && lookalikes.length === 0"
        class="ci-empty"
      >
        {{ t('competitorIntel.loading') }}
      </p>
      <!-- State 2b: a scan ran but the project has no product_url source to seed
           from — surface the hint so the operator knows the next step. -->
      <p v-else-if="lookalikeNoSeed && lookalikes.length === 0" class="ci-empty">
        {{ t('competitorIntel.lookalikes.noSeedHint') }}
      </p>
      <p v-else-if="lookalikes.length === 0" class="ci-empty">
        {{ t('competitorIntel.lookalikes.empty') }}
      </p>

      <!-- State 3: provider keyed, populated review queue -->
      <ul v-else class="ci-suggestion-list">
        <li v-for="la in lookalikes" :key="la.id" class="ci-suggestion">
          <div class="ci-suggestion-main">
            <span class="ci-kind" :data-kind="la.kind">{{ kindLabel(la.kind) }}</span>
            <span class="ci-suggestion-url">{{ la.candidate_repo || la.candidate_url }}</span>
            <a class="ci-suggestion-url" :href="la.candidate_url" target="_blank" rel="noopener noreferrer">
              {{ la.candidate_url }}
            </a>
            <span v-if="la.reason" class="ci-reason" :title="la.reason">
              {{ t('competitorIntel.lookalikes.whyChip') }}: {{ la.reason }}
            </span>
          </div>
          <div class="ci-suggestion-actions">
            <button
              type="button"
              class="ci-submit ci-accept"
              :disabled="acceptingLookalikeId === la.id"
              @click="acceptLookalike(la.id)"
            >
              {{ acceptingLookalikeId === la.id ? t('competitorIntel.lookalikes.accepting') : t('competitorIntel.lookalikes.accept') }}
            </button>
            <button type="button" class="ci-dismiss" @click="dismissLookalike(la.id)">
              {{ t('competitorIntel.lookalikes.dismiss') }}
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
.ci-sources-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.ci-sources-head .ci-section-title {
  margin: 0;
}
.ci-sources-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.ci-autocheck {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.ci-autocheck-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.ci-autocheck-title {
  font-size: 0.85rem;
  color: var(--text-primary);
}
.ci-autocheck-hint {
  font-size: 0.72rem;
  color: var(--text-secondary);
}
.ci-autocheck-interval {
  min-width: auto;
  padding: 0.3rem 0.5rem;
  font-size: 0.82rem;
}
.ci-autocheck-interval:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.toggle-switch {
  width: 44px;
  height: 24px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 2px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  flex-shrink: 0;
}
.toggle-switch.active {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
}
.toggle-switch:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.toggle-knob {
  display: block;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}
.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
}
.ci-source {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.ci-source-checked {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--text-muted, #888);
  white-space: nowrap;
}
.ci-source-unchecked {
  font-style: italic;
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
.ci-dismiss:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
/* --- Strategy review queue + §5B legal gate --- */
.ci-strategy-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.ci-strategy {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--border-color, #2a2a2a);
  border-radius: 8px;
  background: var(--surface-1, #1a1a1a);
}
.ci-strategy-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.ci-strategy-title {
  color: var(--text-primary, #eee);
  font-weight: 600;
}
.ci-strategy-body {
  width: 100%;
  min-height: 4rem;
  resize: vertical;
  font: inherit;
}
.ci-strategy-actions {
  display: flex;
  gap: 0.5rem;
}
.ci-legal {
  border-top: 1px solid var(--border-color, #2a2a2a);
  padding-top: 0.5rem;
}
.ci-legal-title {
  font-size: 0.85rem;
  font-weight: 600;
  margin: 0 0 0.4rem;
}
.ci-legal-list {
  list-style: none;
  margin: 0 0 0.5rem;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.ci-legal-label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary, #9aa0a6);
  cursor: pointer;
}
.ci-implement {
  padding: 0.4rem 0.9rem;
  font-size: 0.85rem;
  align-self: flex-start;
}
/* Market-lookalikes "configure a provider" CTA — the graceful default state.
   Styled off the empty-state, NOT an error toast: it must read as intentional. */
.ci-lookalike-cta {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1rem;
  border: 1px dashed var(--border-color, #2a2a2a);
  border-radius: 8px;
  background: var(--surface-2, #111);
}
.ci-lookalike-cta-title {
  margin: 0;
  font-weight: 600;
  color: var(--text-primary, #eee);
}
.ci-lookalike-cta-hint {
  margin: 0;
  color: var(--text-secondary, #9aa0a6);
}
.ci-lookalike-cta-link {
  align-self: flex-start;
  color: var(--accent, #4f8cff);
  text-decoration: none;
  font-weight: 600;
}
.ci-lookalike-cta-link:hover {
  text-decoration: underline;
}
</style>
