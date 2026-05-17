<script setup lang="ts">
/**
 * ProjectForgeBindingsPanel
 *
 * Per-project sticky bindings: which Forge artifacts (rules,
 * skills, hooks, commands, MCP servers, plugins) get injected
 * into every session of this project by default. The session
 * dialog inherits these; the per-prompt tray can layer volatile
 * extras on top.
 *
 * v1 is intentionally minimal — list, add by (kind, asset_id),
 * remove. The asset_id field accepts whatever the kind's table
 * uses as a primary key (integers for rules/hooks/commands; names
 * for skills; IDs for MCP servers and plugins). A richer
 * pick-from-library UI per kind is the natural Phase 2 follow-up.
 *
 * Structurally mirrors ``ProjectAllowedAccountsPanel`` — the
 * parent page owns the ``.card`` chrome (header, body padding);
 * this component renders only the inner content so the visual
 * tone matches the surrounding settings sections.
 *
 * v0.7.70.
 */
import { ref, computed, onMounted, watch } from 'vue';
import {
  projectApi,
  ruleApi,
  hookApi,
  commandApi,
  skillsApi,
  mcpServerApi,
  pluginApi,
  ApiError,
} from '../../services/api';
import type {
  ForgeBinding,
  ForgeBindingKind,
} from '../../services/api/projects';
import { useToast } from '../../composables/useToast';

// v0.7.75 — per-kind library item shape after normalization. We
// flatten each backend's list response into ``{asset_id, label}``
// so the dropdown can render a consistent option list across
// rules / skills / hooks / commands / mcp_servers / plugins —
// each of which uses a different primary-key convention server-
// side (int row id vs string id vs name).
interface LibraryItem {
  asset_id: string;
  label: string;
}

const props = defineProps<{
  projectId: string;
}>();

const showToast = useToast();
const bindings = ref<ForgeBinding[]>([]);
const isLoading = ref(false);
const errorMessage = ref<string | null>(null);

const newKind = ref<ForgeBindingKind>('rule');
const newAssetId = ref('');
const isSubmitting = ref(false);

// v0.7.75 — per-kind library cache + load state. Populated on
// kind change so the dropdown for the currently-selected kind
// reflects what the operator can actually pick. Fallback to a
// free-text input remains for cases where the library is empty
// or the fetch errors (no API for that kind on a fresh install,
// network blip, etc.).
const libraryByKind = ref<Partial<Record<ForgeBindingKind, LibraryItem[]>>>({});
const libraryLoadingByKind = ref<Partial<Record<ForgeBindingKind, boolean>>>({});
const libraryErrorByKind = ref<Partial<Record<ForgeBindingKind, string>>>({});

const KIND_LABELS: Record<ForgeBindingKind, string> = {
  rule: 'Rule',
  skill: 'Skill',
  hook: 'Hook',
  command: 'Command',
  mcp_server: 'MCP Server',
  plugin: 'Plugin',
};

const grouped = computed(() => {
  const out: Record<string, ForgeBinding[]> = {};
  for (const b of bindings.value) {
    out[b.kind] = out[b.kind] || [];
    out[b.kind].push(b);
  }
  return out;
});

async function load() {
  isLoading.value = true;
  errorMessage.value = null;
  try {
    const res = await projectApi.listForgeBindings(props.projectId);
    bindings.value = res.bindings;
  } catch (err) {
    errorMessage.value =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
        ? err.message
        : 'Failed to load bindings';
  } finally {
    isLoading.value = false;
  }
}

async function loadLibrary(kind: ForgeBindingKind) {
  // v0.7.75 (codex NIT 4) — only short-circuit on a real prior
  // success. Previously a transient failure cached ``[]`` for the
  // panel's lifetime; the operator had to remount to retry.
  // Successful loads (including empty libraries — server says
  // there are zero of this kind) still get cached so a kind
  // toggle doesn't re-fetch unnecessarily.
  const cached = libraryByKind.value[kind];
  const hadError = libraryErrorByKind.value[kind];
  if (cached !== undefined && !hadError) return;
  libraryLoadingByKind.value = { ...libraryLoadingByKind.value, [kind]: true };
  libraryErrorByKind.value = { ...libraryErrorByKind.value, [kind]: undefined };
  try {
    const items = await fetchLibraryForKind(kind);
    libraryByKind.value = { ...libraryByKind.value, [kind]: items };
  } catch (err) {
    libraryErrorByKind.value = {
      ...libraryErrorByKind.value,
      [kind]: err instanceof Error ? err.message : 'load failed',
    };
    // Do NOT cache a sentinel on error — the next kind toggle
    // back into this kind retries. The fallback text input still
    // renders because ``useLibraryDropdown`` keys off the error +
    // empty-library state, not on a cached empty.
    libraryByKind.value = { ...libraryByKind.value, [kind]: undefined };
  } finally {
    libraryLoadingByKind.value = { ...libraryLoadingByKind.value, [kind]: false };
  }
}

async function fetchLibraryForKind(kind: ForgeBindingKind): Promise<LibraryItem[]> {
  // Each backend list returns a different array shape; normalize
  // into ``LibraryItem`` here so the rest of the component doesn't
  // care. Asset id is whichever field the bindings table uses as
  // the foreign key for that kind (see ``ContextCompilerService``
  // resolution paths).
  switch (kind) {
    case 'rule': {
      const res = await ruleApi.list(props.projectId);
      return (res.rules || []).map((r) => ({
        asset_id: String(r.id),
        label: r.name || `rule ${r.id}`,
      }));
    }
    case 'hook': {
      const res = await hookApi.list(props.projectId);
      return (res.hooks || []).map((h) => ({
        asset_id: String(h.id),
        label: `${h.name || 'hook'} · ${h.event}`,
      }));
    }
    case 'command': {
      const res = await commandApi.list(props.projectId);
      return (res.commands || []).map((c) => ({
        asset_id: String(c.id),
        label: c.name || `command ${c.id}`,
      }));
    }
    case 'skill': {
      const res = await skillsApi.list();
      return (res.skills || []).map((s) => ({
        asset_id: s.name,
        label: s.name,
      }));
    }
    case 'mcp_server': {
      const res = await mcpServerApi.list();
      return (res.servers || []).map((m) => ({
        asset_id: m.id,
        label: m.name || m.id,
      }));
    }
    case 'plugin': {
      const res = await pluginApi.list();
      return (res.plugins || []).map((p) => ({
        asset_id: p.id,
        label: p.name || p.id,
      }));
    }
  }
}

watch(newKind, (kind) => {
  loadLibrary(kind);
  newAssetId.value = '';
});

const currentLibrary = computed<LibraryItem[]>(
  () => libraryByKind.value[newKind.value] ?? [],
);
const currentLibraryLoading = computed(
  () => libraryLoadingByKind.value[newKind.value] === true,
);
const currentLibraryError = computed(
  () => libraryErrorByKind.value[newKind.value] ?? null,
);
// Filter out items already bound for the selected kind so the
// dropdown only shows what can actually be added; the binding
// row list above shows the rest.
const availableLibrary = computed<LibraryItem[]>(() => {
  const bound = new Set(
    bindings.value
      .filter((b) => b.kind === newKind.value)
      .map((b) => b.asset_id),
  );
  return currentLibrary.value.filter((item) => !bound.has(item.asset_id));
});
const useLibraryDropdown = computed(
  () =>
    !currentLibraryLoading.value &&
    !currentLibraryError.value &&
    currentLibrary.value.length > 0,
);

async function addBinding() {
  const asset = newAssetId.value.trim();
  if (!asset) {
    showToast('Asset id is required', 'error');
    return;
  }
  isSubmitting.value = true;
  try {
    const res = await projectApi.addForgeBinding(props.projectId, {
      kind: newKind.value,
      asset_id: asset,
    });
    bindings.value = [...bindings.value, res.binding];
    newAssetId.value = '';
    showToast(`Bound ${res.binding.kind} ${res.binding.asset_id}`, 'success');
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to add binding',
      'error',
    );
  } finally {
    isSubmitting.value = false;
  }
}

async function removeBinding(b: ForgeBinding) {
  try {
    await projectApi.removeForgeBinding(props.projectId, b.id);
    bindings.value = bindings.value.filter((x) => x.id !== b.id);
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to remove binding',
      'error',
    );
  }
}

onMounted(() => {
  load();
  // Preload the default kind's library so the dropdown is
  // populated the moment the operator opens the form.
  loadLibrary(newKind.value);
});
</script>

<template>
  <div class="forge-bindings" data-testid="forge-bindings-panel">
    <p class="section-description">
      Sticky defaults: every session created for this project
      inherits these Forge artifacts. Rules and skills feed
      claude's system prompt; hooks / commands / MCP servers /
      plugins are materialized into the session's overlay. The
      per-prompt tray can layer volatile extras on top.
    </p>

    <div v-if="isLoading" class="state">Loading…</div>
    <div v-else-if="errorMessage" class="state state-error">
      {{ errorMessage }}
    </div>
    <div v-else-if="bindings.length === 0" class="state state-empty">
      No bindings yet. Add one below to wire Forge artifacts into
      this project's sessions.
    </div>
    <div v-else class="binding-groups">
      <div
        v-for="(items, kind) in grouped"
        :key="kind"
        class="binding-group"
      >
        <h4 class="binding-group-heading">{{ KIND_LABELS[kind as ForgeBindingKind] || kind }}</h4>
        <ul class="binding-list">
          <li v-for="b in items" :key="b.id" class="binding-row">
            <code class="binding-id">{{ b.asset_id }}</code>
            <span
              v-if="!b.enabled"
              class="binding-flag"
              title="Disabled — won't be applied"
            >
              disabled
            </span>
            <button
              type="button"
              class="btn btn-sm btn-danger"
              title="Remove binding"
              @click="removeBinding(b)"
            >
              Remove
            </button>
          </li>
        </ul>
      </div>
    </div>

    <div class="add-row">
      <select v-model="newKind" :disabled="isSubmitting">
        <option v-for="(label, k) in KIND_LABELS" :key="k" :value="k">
          {{ label }}
        </option>
      </select>

      <!-- v0.7.75 — library dropdown is the primary path. When the
           kind's library is empty / failed to load / still
           loading, fall back to the original free-text input so
           the operator can still bind by typing the asset id
           (useful for plugins not yet installed locally, or for
           mcp_servers added out-of-band). -->
      <select
        v-if="useLibraryDropdown"
        v-model="newAssetId"
        class="asset-select"
        :disabled="isSubmitting"
      >
        <option value="" disabled>
          {{ availableLibrary.length === 0
            ? `All ${KIND_LABELS[newKind].toLowerCase()}s already bound`
            : `Pick a ${KIND_LABELS[newKind].toLowerCase()}…` }}
        </option>
        <!-- v0.7.75 (codex NIT 5) — option label is a single
             string, not text+span. Native ``<option>`` strips
             child elements in most browsers, so the original
             ``<span>(id)</span>`` only rendered in some chromes. -->
        <option
          v-for="item in availableLibrary"
          :key="item.asset_id"
          :value="item.asset_id"
        >
          {{
            item.asset_id !== item.label
              ? `${item.label} (${item.asset_id})`
              : item.label
          }}
        </option>
      </select>
      <input
        v-else
        v-model="newAssetId"
        type="text"
        :placeholder="
          currentLibraryLoading
            ? 'Loading library…'
            : currentLibraryError
              ? `Library load failed — type the asset id manually`
              : `No ${KIND_LABELS[newKind].toLowerCase()}s in your library — type an asset id`
        "
        :disabled="isSubmitting || currentLibraryLoading"
        @keydown.enter.prevent="addBinding"
      />

      <button
        type="button"
        class="btn btn-primary"
        :disabled="isSubmitting || !newAssetId"
        @click="addBinding"
      >
        Add binding
      </button>
    </div>
    <p v-if="currentLibraryError" class="form-hint form-hint-warn">
      Couldn't load {{ KIND_LABELS[newKind] }} library: {{ currentLibraryError }}.
      Type the asset id manually.
    </p>
  </div>
</template>

<style scoped>
.forge-bindings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-description {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
}

.state {
  padding: 12px 14px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 13px;
}
.state-error {
  color: var(--accent-red, #ff6464);
  background: rgba(255, 100, 100, 0.06);
}
.state-empty {
  font-style: italic;
}

.binding-groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.binding-group-heading {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 0 0 6px 0;
  font-weight: 500;
}
.binding-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.binding-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
}
.binding-id {
  flex: 1;
  color: var(--text-primary);
  background: transparent;
  padding: 0;
  font-family: 'Geist Mono', monospace;
  font-size: 13px;
}
.binding-flag {
  color: var(--text-tertiary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.add-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.add-row select,
.add-row input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.add-row input {
  flex: 1;
  font-family: 'Geist Mono', monospace;
}
.add-row .asset-select {
  flex: 1;
  font-family: inherit;
}
.form-hint {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.form-hint-warn {
  color: var(--accent-amber, #ffb454);
}
.add-row select:focus,
.add-row input:focus {
  border-color: var(--accent-cyan);
}
.add-row select:disabled,
.add-row input:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent-cyan);
  color: #002;
  border-color: var(--accent-cyan);
  font-weight: 600;
}
.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.btn-danger {
  background: transparent;
  border-color: rgba(255, 100, 100, 0.4);
  color: var(--accent-red, #ff6464);
}
.btn-danger:hover {
  background: rgba(255, 100, 100, 0.1);
}
.btn-sm {
  font-size: 12px;
  padding: 4px 10px;
}
</style>
