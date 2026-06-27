<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { competitorIntelApi, lookalikeApi, ApiError } from '../services/api';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
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
// --- Delete-source confirm state (shared ConfirmModal pattern) -------------
// `sourceToDelete` holds the row awaiting confirmation (drives the modal copy);
// `deletingId` guards/labels the in-flight delete on that row's button.
const sourceToDelete = ref<CompetitorSource | null>(null);
const deletingId = ref<string | null>(null);
const signals = ref<DetectedSignal[]>([]);
const loadingSignals = ref(false);

// --- GLOBAL scheduled auto-check config ------------------------------------
// This is an INSTANCE-WIDE setting: one scheduled job polls every active source
// across ALL projects, so enabling it here turns on auto-checking everywhere.
const autoCheckEnabled = ref(false);
const autoCheckInterval = ref(15);
// The scheduled-poll config is admin-only; the toggle is hidden when getConfig
// 403s for a non-admin (or the backend is unreachable).
const autoCheckAvailable = ref(true);
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

/** Open the delete-confirm modal for a source (no mutation until confirmed). */
function confirmDeleteSource(source: CompetitorSource) {
  strategyToAutoImplement.value = null; // only one confirm modal open at a time
  sourceToDelete.value = source;
}

/**
 * Delete the confirmed source. Optimistically removes the source AND its
 * (server-cascaded) signals from the local lists; on error, reverts both and
 * surfaces an error toast.
 */
async function deleteSource() {
  const target = sourceToDelete.value;
  if (!target || !projectId.value || deletingId.value) return;
  deletingId.value = target.id;
  // Snapshot for revert-on-error (the server cascades snapshots + signals).
  const prevSources = sources.value;
  const prevSignals = signals.value;
  sources.value = sources.value.filter((s) => s.id !== target.id);
  signals.value = signals.value.filter((sig) => sig.source_id !== target.id);
  sourceToDelete.value = null;
  try {
    await competitorIntelApi.deleteSource(projectId.value, target.id);
    showToast(t('competitorIntel.sourceDeletedToast'), 'success');
  } catch (err) {
    // Revert the optimistic removal.
    sources.value = prevSources;
    signals.value = prevSignals;
    showToast(
      err instanceof ApiError ? err.message : t('competitorIntel.sourceDeleteError'),
      'error',
    );
  } finally {
    deletingId.value = null;
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
    // 403 for non-admins (the config is admin-gated), or the backend is down:
    // hide the toggle rather than show a control the user can't use.
    autoCheckAvailable.value = false;
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

// Why is Implement disabled? It needs Approve THEN the 7-item §5B legal checklist.
// Empty string = no hint (already implementing/done, or fully ready).
function implementHint(st: Strategy): string {
  if (st.status === 'proposed') return t('competitorIntel.implementHintApprove');
  if (st.status === 'approved' && !st.legal_cleared_at) return t('competitorIntel.implementHintLegal');
  return '';
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
    const res = await competitorIntelApi.generateStrategy(projectId.value, signalIds);
    await loadStrategies();
    // Degraded = the strategy LLM backend (CLIProxyAPI) was unreachable, so the
    // body is a placeholder. Tell the operator so they don't mistake it for a
    // real proposal (the row is still created and approvable).
    if (res?.strategy?.degraded) {
      showToast(t('competitorIntel.degradedWarning'), 'infrastructure');
    }
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

// Auto-implement: hand a MATERIALIZED strategy to the autonomous coding agent.
// This is the dangerous step — it spawns a goal-loop agent that writes code in an
// isolated git worktree — so it goes through an explicit confirm modal here, on top
// of the triple backend gate (AGENTED_STRATEGY_AUTOIMPLEMENT env flag + §5B legal
// clearance + confirm token).
const strategyToAutoImplement = ref<Strategy | null>(null);

// Eligibility for the dangerous auto-implement path: materialized (plan exists),
// §5B-cleared, and not already running an agent. Used for BOTH the button
// visibility and the confirm-time revalidation.
function canAutoImplement(st: Strategy): boolean {
  return st.status === 'implementing' && !!st.plan_id && !!st.legal_cleared_at && !st.session_id;
}

function confirmAutoImplement(st: Strategy) {
  sourceToDelete.value = null; // only one confirm modal open at a time
  strategyToAutoImplement.value = st;
}

async function autoImplementStrategy() {
  const target = strategyToAutoImplement.value;
  strategyToAutoImplement.value = null;
  if (!target || !projectId.value || strategyInFlight.value) return;
  // Re-validate against the LIVE row at confirm time — the modal may be stale
  // (an agent started elsewhere, clearance got revoked, an edit reset §5B). This
  // is the dangerous path, so never POST on a now-ineligible strategy.
  const st = strategies.value.find((s) => s.id === target.id);
  if (!st || !canAutoImplement(st)) {
    showToast(t('competitorIntel.autoImplementNotEligible'), 'error');
    return;
  }
  strategyInFlight.value = st.id;
  try {
    // The backend only requires a NON-EMPTY token (operator-confirmed signal).
    const token = globalThis.crypto?.randomUUID?.() ?? `confirm-${st.id}`;
    const res = await competitorIntelApi.autoimplementStrategy(projectId.value, st.id, token);
    showToast(t('competitorIntel.autoImplementStarted', { id: res.session_id }), 'success');
    await loadStrategies();
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : t('competitorIntel.strategyError'), 'error');
  } finally {
    strategyInFlight.value = null;
  }
}

// Status badge: 'implementing' means MATERIALIZED (a plan exists). Only once an
// agent session has actually been launched (session_id) does it read as the agent
// running — so the badge never implies work that isn't happening.
function strategyStatusLabel(st: Strategy): string {
  if (st.status === 'implementing') {
    return st.session_id
      ? t('competitorIntel.statusImplementing')
      : t('competitorIntel.statusMaterialized');
  }
  return statusLabel(st.status);
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
  <PageLayout>
    <PageHeader :title="t('competitorIntel.title')" :subtitle="t('competitorIntel.subtitle')" />

    <!-- Add a source — titled card so it matches the section rhythm -->
    <section class="ci-card">
      <div class="ci-card-head">
        <h2 class="ci-card-title">{{ t('competitorIntel.addSourceTitle') }}</h2>
      </div>
      <form class="ci-toolbar" @submit.prevent="submitSource">
      <div class="form-group">
        <label for="ci-kind">{{ t('competitorIntel.kindLabel') }}</label>
        <select id="ci-kind" v-model="kind" :aria-label="t('competitorIntel.kindLabel')">
          <option value="">{{ t('competitorIntel.kindAuto') }}</option>
          <option value="hn_query">{{ t('competitorIntel.kindHnQuery') }}</option>
        </select>
      </div>
      <div class="form-group">
        <label for="ci-url">{{
          isQuery ? t('competitorIntel.queryLabel') : t('competitorIntel.urlLabel')
        }}</label>
        <input
          id="ci-url"
          v-model="url"
          :type="isQuery ? 'text' : 'url'"
          :placeholder="
            isQuery ? t('competitorIntel.queryPlaceholder') : t('competitorIntel.urlPlaceholder')
          "
          :aria-label="isQuery ? t('competitorIntel.queryLabel') : t('competitorIntel.urlLabel')"
        />
      </div>
      <div class="form-group">
        <label for="ci-label">{{ t('competitorIntel.labelOptional') }}</label>
        <input
          id="ci-label"
          v-model="label"
          type="text"
          :placeholder="t('competitorIntel.labelPlaceholder')"
          :aria-label="t('competitorIntel.labelOptional')"
        />
      </div>
      <button type="submit" class="btn btn-primary" :disabled="!canSubmit">
        {{ adding ? t('competitorIntel.adding') : t('competitorIntel.submit') }}
      </button>
      </form>
    </section>

    <!-- Monitor row: watched sources + the discovery queue they seed -->
    <div class="ci-grid">
    <!-- Watched sources -->
    <section class="ci-card">
      <div class="ci-card-head">
        <h2 class="ci-card-title">
          {{ t('competitorIntel.sourcesTitle') }}
          <span v-if="sources.length" class="ci-count">{{
            t('competitorIntel.sourceCount', { count: sources.length })
          }}</span>
        </h2>
        <div class="ci-card-actions">
          <!-- GLOBAL auto-check toggle: one scheduled job polls every active
               source across ALL projects, so this is an instance-wide setting. -->
          <div v-if="autoCheckAvailable" class="ci-autocheck">
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
              class="ci-autocheck-interval"
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
            class="btn btn-secondary btn-sm"
            :disabled="polling"
            @click="pollNow"
          >
            {{ polling ? t('competitorIntel.polling') : t('competitorIntel.pollNow') }}
          </button>
        </div>
      </div>
      <EmptyState
        v-if="sources.length === 0"
        :title="t('competitorIntel.sourcesEmpty')"
      />
      <ul v-else class="ci-source-list">
        <li v-for="s in sources" :key="s.id" class="ci-source">
          <span class="ci-kind" :data-kind="s.kind">{{ kindLabel(s.kind) }}</span>
          <span
            class="ci-source-status"
            :class="{ 'is-active': s.last_polled_at }"
            :title="s.last_polled_at ? t('competitorIntel.lastChecked', { time: formatChecked(s.last_polled_at) }) : t('competitorIntel.neverChecked')"
            aria-hidden="true"
          ></span>
          <div class="ci-source-body">
            <span class="ci-source-name">{{ s.label || s.url }}</span>
            <span v-if="s.label" class="ci-source-sub">{{ s.url }}</span>
            <span
              v-if="s.last_polled_at"
              class="ci-source-checked"
            >{{ t('competitorIntel.lastChecked', { time: formatChecked(s.last_polled_at) }) }}</span>
            <span v-else class="ci-source-checked ci-source-unchecked">
              {{ t('competitorIntel.neverChecked') }}
            </span>
          </div>
          <button
            type="button"
            class="btn btn-icon btn-danger ci-source-delete"
            :aria-label="t('competitorIntel.deleteSource')"
            :title="t('competitorIntel.deleteSource')"
            :disabled="deletingId === s.id"
            @click="confirmDeleteSource(s)"
          >
            <span v-if="deletingId === s.id" class="ci-btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
          </button>
        </li>
      </ul>
    </section>

    <!-- Discovery review queue: suggested competitors awaiting accept/dismiss -->
    <section class="ci-card">
      <div class="ci-card-head">
        <h2 class="ci-card-title">{{ t('competitorIntel.suggestionsTitle') }}</h2>
        <button type="button" class="btn btn-secondary btn-sm" :disabled="scanning" @click="runDiscovery">
          {{ scanning ? t('competitorIntel.adding') : t('competitorIntel.runDiscovery') }}
        </button>
      </div>
      <EmptyState
        v-if="loadingSuggestions && suggestions.length === 0"
        :title="t('competitorIntel.loading')"
      />
      <EmptyState
        v-else-if="suggestions.length === 0"
        :title="t('competitorIntel.suggestionsEmpty')"
      />
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
              class="btn btn-primary btn-sm"
              :disabled="acceptingId === sug.id"
              @click="acceptSuggestion(sug.id)"
            >
              {{ acceptingId === sug.id ? t('competitorIntel.accepting') : t('competitorIntel.accept') }}
            </button>
            <button type="button" class="btn btn-sm" @click="dismissSuggestion(sug.id)">
              {{ t('competitorIntel.dismiss') }}
            </button>
          </div>
        </li>
      </ul>
    </section>
    </div>

    <!-- Delete-source confirmation (shared ConfirmModal, danger variant) -->
    <ConfirmModal
      :open="sourceToDelete !== null"
      :title="t('competitorIntel.deleteSourceTitle')"
      :message="
        t('competitorIntel.deleteSourceConfirm', {
          name: sourceToDelete?.label || sourceToDelete?.url || '',
        })
      "
      :confirm-label="t('competitorIntel.deleteSource')"
      variant="danger"
      @confirm="deleteSource"
      @cancel="sourceToDelete = null"
    />

    <!-- Auto-implement confirmation — this launches an autonomous coding agent. -->
    <ConfirmModal
      :open="strategyToAutoImplement !== null"
      :title="t('competitorIntel.autoImplementConfirmTitle')"
      :message="t('competitorIntel.autoImplementConfirmMsg')"
      :confirm-label="t('competitorIntel.autoImplement')"
      variant="danger"
      @confirm="autoImplementStrategy"
      @cancel="strategyToAutoImplement = null"
    />

    <!-- Strategy review queue (full width — the complex approve→legal→implement flow) -->
    <section class="ci-card ci-card-wide">
      <div class="ci-card-head">
        <h2 class="ci-card-title">{{ t('competitorIntel.strategiesTitle') }}</h2>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          :disabled="generatingStrategy"
          @click="generateStrategy"
        >
          {{ generatingStrategy ? t('competitorIntel.adding') : t('competitorIntel.generateStrategy') }}
        </button>
      </div>
      <EmptyState
        v-if="loadingStrategies && strategies.length === 0"
        :title="t('competitorIntel.loading')"
      />
      <EmptyState
        v-else-if="strategies.length === 0"
        :title="t('competitorIntel.strategiesEmpty')"
      />
      <ul v-else class="ci-strategy-list">
        <li v-for="st in strategies" :key="st.id" class="ci-strategy">
          <div class="ci-strategy-head">
            <span
              class="ci-kind"
              :data-kind="st.status === 'implementing' && !st.session_id ? 'materialized' : st.status"
            >{{ strategyStatusLabel(st) }}</span>
            <span class="ci-strategy-title">{{ st.title || t('competitorIntel.noSummary') }}</span>
          </div>
          <textarea
            class="ci-strategy-body"
            :value="st.body || ''"
            :aria-label="t('competitorIntel.editStrategy')"
            @blur="saveStrategyBody(st.id, ($event.target as HTMLTextAreaElement).value)"
          ></textarea>
          <div class="ci-strategy-actions">
            <button
              type="button"
              class="btn btn-primary btn-sm"
              :disabled="strategyInFlight === st.id || st.status !== 'proposed'"
              @click="approveStrategy(st.id)"
            >
              {{ t('competitorIntel.approve') }}
            </button>
            <button
              type="button"
              class="btn btn-sm"
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
              class="btn btn-primary btn-sm"
              :disabled="!st.legal_cleared_at || strategyInFlight === st.id || st.status !== 'approved'"
              :title="implementHint(st) || ''"
              @click="materializeStrategy(st.id)"
            >
              {{ t('competitorIntel.implement') }}
            </button>
            <p v-if="implementHint(st)" class="ci-implement-hint">{{ implementHint(st) }}</p>

            <!-- Auto-implement: only for a materialized + cleared strategy that is
                 not already running an agent. Danger styling — it launches an
                 autonomous coding agent (behind a confirm modal + backend gates). -->
            <div
              v-if="st.status === 'implementing' && st.plan_id && st.legal_cleared_at"
              class="ci-autoimpl"
            >
              <button
                v-if="canAutoImplement(st)"
                type="button"
                class="btn btn-danger btn-sm"
                :disabled="strategyInFlight === st.id"
                @click="confirmAutoImplement(st)"
              >
                {{ t('competitorIntel.autoImplement') }}
              </button>
              <span v-else class="ci-autoimpl-running">{{ t('competitorIntel.autoImplementRunning') }}</span>
              <p class="ci-implement-hint">{{ t('competitorIntel.autoImplementHint') }}</p>
            </div>
          </div>
        </li>
      </ul>
    </section>

    <!-- Discovery row: market lookalikes + the live signal feed -->
    <div class="ci-grid">
    <!-- Market lookalikes (phase 27 P5): provider-pluggable scan→review→accept.
         THREE states: (1) provider===null → "configure a provider" CTA (the
         dominant default-install state — no scan button, no fake rows); (2)
         provider set + empty → empty line + Scan button; (3) provider set +
         populated → the review queue. -->
    <section class="ci-card">
      <div class="ci-card-head">
        <h2 class="ci-card-title">{{ t('competitorIntel.lookalikes.title') }}</h2>
        <button
          v-if="lookalikeProvider !== null"
          type="button"
          class="btn btn-secondary btn-sm"
          :disabled="scanningLookalikes"
          @click="runLookalikeScan"
        >
          {{ scanningLookalikes ? t('competitorIntel.lookalikes.scanning') : t('competitorIntel.lookalikes.scan') }}
        </button>
      </div>

      <!-- State 1: no provider keyed — the graceful-degradation CTA -->
      <EmptyState
        v-if="lookalikeProvider === null"
        :title="t('competitorIntel.lookalikes.notConfigured.title')"
        :description="t('competitorIntel.lookalikes.notConfigured.hint')"
      >
        <template #actions>
          <a
            class="btn btn-secondary"
            href="https://docs.apistemic.com"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('competitorIntel.lookalikes.notConfigured.docsLink') }}
          </a>
        </template>
      </EmptyState>

      <!-- State 2: provider keyed, queue empty -->
      <EmptyState
        v-else-if="loadingLookalikes && lookalikes.length === 0"
        :title="t('competitorIntel.loading')"
      />
      <!-- State 2b: a scan ran but the project has no product_url source to seed
           from — surface the hint so the operator knows the next step. -->
      <EmptyState
        v-else-if="lookalikeNoSeed && lookalikes.length === 0"
        :title="t('competitorIntel.lookalikes.noSeedHint')"
      />
      <EmptyState
        v-else-if="lookalikes.length === 0"
        :title="t('competitorIntel.lookalikes.empty')"
      />

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
              class="btn btn-primary btn-sm"
              :disabled="acceptingLookalikeId === la.id"
              @click="acceptLookalike(la.id)"
            >
              {{ acceptingLookalikeId === la.id ? t('competitorIntel.lookalikes.accepting') : t('competitorIntel.lookalikes.accept') }}
            </button>
            <button type="button" class="btn btn-sm" @click="dismissLookalike(la.id)">
              {{ t('competitorIntel.lookalikes.dismiss') }}
            </button>
          </div>
        </li>
      </ul>
    </section>

    <!-- Ranked signals -->
    <section class="ci-card">
      <div class="ci-card-head">
        <h2 class="ci-card-title">{{ t('competitorIntel.signalsTitle') }}</h2>
      </div>
      <EmptyState
        v-if="loadingSignals && signals.length === 0"
        :title="t('competitorIntel.loading')"
      />
      <EmptyState
        v-else-if="signals.length === 0"
        :title="t('competitorIntel.signalsEmpty')"
      />
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
    </section>
    </div>
  </PageLayout>
</template>

<style scoped>
/* --- Add-source form: layout only; the surrounding .ci-card is the surface --- */
.ci-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}
.ci-toolbar .form-group {
  flex: 1 1 200px;
  margin-bottom: 0;
}

/* --- Responsive section grid: the standard repeat(auto-fit, minmax) manner the
       other management pages use, so related sections sit side-by-side at full
       width and stack on narrow viewports. --- */
.ci-grid {
  display: grid;
  /* min(380px, 100%) so the track can shrink below 380px on narrow viewports and
     collapse to one column instead of overflowing horizontally. */
  grid-template-columns: repeat(auto-fit, minmax(min(380px, 100%), 1fr));
  gap: 24px;
  margin-bottom: 24px;
  align-items: start;
}
/* Cards own their bottom margin in the stacked flow; inside a grid the gap owns
   the spacing, so neutralize it to keep rows aligned. */
.ci-grid > .ci-card {
  margin-bottom: 0;
}

/* --- Section card: same bordered surface the standard pages use --- */
.ci-card {
  margin-bottom: 24px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
}
.ci-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.ci-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.ci-card-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
  padding: 6px 10px;
  font-size: 0.82rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
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
.ci-count {
  margin-left: 0.5rem;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-tertiary);
}
.ci-source {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
}
.ci-source-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-tertiary);
  opacity: 0.5;
}
.ci-source-status.is-active {
  background: var(--accent-cyan);
  opacity: 1;
}
.ci-source-body {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
  flex: 1 1 auto;
}
.ci-source-name {
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 500;
  word-break: break-all;
}
.ci-source-sub {
  font-size: 0.75rem;
  color: var(--text-secondary);
  word-break: break-all;
}
.ci-source-checked {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.ci-source-unchecked {
  font-style: italic;
}
.ci-source-delete {
  flex-shrink: 0;
}
.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
}
.btn-icon svg {
  width: 16px;
  height: 16px;
}
.ci-btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: ci-spin 0.7s linear infinite;
}
@keyframes ci-spin {
  to {
    transform: rotate(360deg);
  }
}
.ci-kind,
.ci-signal-type {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.ci-signal {
  padding: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
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
  color: var(--accent-cyan);
}
.ci-signal-summary {
  margin: 0;
  color: var(--text-primary);
}
.ci-signal-source {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
/* --- Discovery review queue --- */
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
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
}
.ci-suggestion-main {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  min-width: 0;
}
.ci-suggestion-url {
  color: var(--text-primary);
  font-size: 0.9rem;
  word-break: break-all;
}
/* The "why" chip — styled off .ci-kind but accented to read as an explanation. */
.ci-reason {
  font-size: 0.75rem;
  padding: 0.1rem 0.45rem;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
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
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
}
.ci-strategy-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.ci-strategy-title {
  color: var(--text-primary);
  font-weight: 600;
}
.ci-strategy-body {
  width: 100%;
  min-height: 4rem;
  resize: vertical;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 14px;
  box-sizing: border-box;
}
.ci-strategy-body:focus {
  border-color: var(--accent-cyan);
}
.ci-strategy-actions {
  display: flex;
  gap: 0.5rem;
}
.ci-implement-hint {
  margin: 0.375rem 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.ci-autoimpl {
  margin-top: 0.6rem;
  padding-top: 0.6rem;
  border-top: 1px dashed var(--border-default);
}
.ci-autoimpl-running {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-cyan);
}
/* 'Materialized' (plan created, nothing running) reads calmer than the active
   states so it doesn't imply work in progress. */
.ci-kind[data-kind='materialized'] {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.ci-legal {
  border-top: 1px solid var(--border-default);
  padding-top: 0.5rem;
}
.ci-legal-title {
  font-size: 0.85rem;
  font-weight: 600;
  margin: 0 0 0.4rem;
}
.ci-legal-list {
  list-style: none;
  margin: 0 0 0.75rem;
  padding: 0;
  /* Multi-column at full width so the 7-item gate reads as a compact checklist
     rather than a tall single column; collapses to one column on narrow. */
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
  gap: 0.3rem 1.25rem;
}
.ci-legal-label {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}
.ci-legal .btn {
  align-self: flex-start;
}
</style>
