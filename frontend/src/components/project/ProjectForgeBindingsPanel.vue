<script setup lang="ts">
/**
 * ProjectForgeBindingsPanel
 *
 * Per-project sticky bindings: which Forge artifacts (rules,
 * skills, hooks, commands, MCP servers, plugins) get injected
 * into every session of this project by default. The session
 * dialog inherits these; the per-prompt tray can add volatile
 * extras on top.
 *
 * v1 is a minimal CRUD UI — list, add by (kind, asset_id), and
 * delete. A richer "pick from your existing library" picker per
 * kind is the natural Phase 2 enhancement (the API already
 * supports it).
 *
 * v0.7.70.
 */
import { ref, computed, onMounted } from 'vue';
import { projectApi } from '../../services/api';
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
const loading = ref(false);
const errorMessage = ref<string | null>(null);

const newKind = ref<ForgeBindingKind>('rule');
const newAssetId = ref('');

const KIND_LABELS: Record<ForgeBindingKind, string> = {
  rule: 'Rule (DB id)',
  skill: 'Skill (name)',
  hook: 'Hook (DB id)',
  command: 'Command (DB id)',
  mcp_server: 'MCP Server (id)',
  plugin: 'Plugin (id)',
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
  loading.value = true;
  errorMessage.value = null;
  try {
    const res = await projectApi.listForgeBindings(props.projectId);
    bindings.value = res.bindings;
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : 'Failed to load';
  } finally {
    loading.value = false;
  }
}

async function addBinding() {
  const asset = newAssetId.value.trim();
  if (!asset) {
    showToast('Asset id is required', 'error');
    return;
  }
  try {
    const res = await projectApi.addForgeBinding(props.projectId, {
      kind: newKind.value,
      asset_id: asset,
    });
    bindings.value = [...bindings.value, res.binding];
    newAssetId.value = '';
    showToast(`Bound ${res.binding.kind}/${res.binding.asset_id}`, 'success');
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to add binding',
      'error',
    );
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
  <div class="card" data-testid="forge-bindings-panel">
    <div class="card-header">
      <h3>Forge Context Bindings</h3>
    </div>
    <div class="card-body">
      <p class="section-description">
        Sticky defaults: every session created for this project
        inherits these Forge artifacts. Rules + skills feed the
        system prompt; hooks / commands / MCP / plugins feed the
        per-session overlay. The per-prompt tray can layer
        additional context on top.
      </p>

      <div v-if="loading" class="loading">Loading…</div>
      <div v-else-if="errorMessage" class="error">{{ errorMessage }}</div>
      <div v-else>
        <div v-if="bindings.length === 0" class="empty">
          No bindings yet. Add one below to wire Forge artifacts into
          this project's sessions.
        </div>
        <div
          v-for="(items, kind) in grouped"
          :key="kind"
          class="kind-group"
        >
          <h4 class="kind-heading">{{ kind }}</h4>
          <ul class="binding-list">
            <li v-for="b in items" :key="b.id" class="binding-row">
              <span class="binding-id" :data-kind="b.kind">
                {{ b.asset_id }}
              </span>
              <span
                v-if="!b.enabled"
                class="binding-flag disabled"
                title="Disabled — won't be applied"
              >
                disabled
              </span>
              <button
                type="button"
                class="binding-remove"
                title="Remove binding"
                @click="removeBinding(b)"
              >
                ×
              </button>
            </li>
          </ul>
        </div>
      </div>

      <div class="add-row">
        <select v-model="newKind" class="kind-select">
          <option v-for="(label, k) in KIND_LABELS" :key="k" :value="k">
            {{ label }}
          </option>
        </select>
        <input
          v-model="newAssetId"
          type="text"
          class="asset-input"
          placeholder="asset id (e.g. 42, skill-name, mcp-server-id)"
          @keydown.enter.prevent="addBinding"
        />
        <button type="button" class="btn btn-primary" @click="addBinding">
          Add binding
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-description {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 12px;
}
.loading,
.error,
.empty {
  padding: 12px;
  color: var(--text-secondary);
  font-style: italic;
}
.error {
  color: var(--accent-red);
}
.kind-group {
  margin-bottom: 12px;
}
.kind-heading {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}
.binding-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.binding-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  margin-bottom: 4px;
  font-family: 'Geist Mono', monospace;
  font-size: 13px;
}
.binding-id {
  flex: 1;
  color: var(--text-primary);
}
.binding-flag.disabled {
  color: var(--text-tertiary);
  font-size: 11px;
}
.binding-remove {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 16px;
}
.binding-remove:hover {
  color: var(--accent-red);
}
.add-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 16px;
}
.kind-select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: 4px;
}
.asset-input {
  flex: 1;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  border-radius: 4px;
  font-family: 'Geist Mono', monospace;
}
</style>
