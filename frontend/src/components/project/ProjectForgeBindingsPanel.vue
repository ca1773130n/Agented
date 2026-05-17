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
import { ref, computed, onMounted } from 'vue';
import { projectApi, ApiError } from '../../services/api';
import type {
  ForgeBinding,
  ForgeBindingKind,
} from '../../services/api/projects';
import { useToast } from '../../composables/useToast';

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

onMounted(load);
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
      <input
        v-model="newAssetId"
        type="text"
        placeholder="asset id (e.g. 42, skill-name, mcp-server-id)"
        :disabled="isSubmitting"
        @keydown.enter.prevent="addBinding"
      />
      <button
        type="button"
        class="btn btn-primary"
        :disabled="isSubmitting"
        @click="addBinding"
      >
        Add binding
      </button>
    </div>
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
