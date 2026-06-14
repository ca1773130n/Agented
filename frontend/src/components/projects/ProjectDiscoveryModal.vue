<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { projectApi, ApiError } from '../../services/api';
import type { Team, Product, DiscoveredRepo } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{ teams: Team[]; products: Product[] }>();
const emit = defineEmits<{ close: []; imported: [] }>();

const { t } = useI18n();
const showToast = useToast();

const root = ref('');
const nested = ref(false);
const maxDepth = ref(3);
const repos = ref<DiscoveredRepo[]>([]);
const selected = ref<Set<string>>(new Set());
const productId = ref('');
const teamId = ref('');
const runSetup = ref(true);
const scanning = ref(false);
const importing = ref(false);
const scanned = ref(false);
const newCount = ref(0);

const canSetup = computed(() => teamId.value !== '');
const selectedRepos = computed(() => repos.value.filter((r) => selected.value.has(r.local_path)));
const importLabel = computed(() =>
  runSetup.value && canSetup.value
    ? t('projectsDiscovery.import', { count: selectedRepos.value.length })
    : t('projectsDiscovery.importNoSetup', { count: selectedRepos.value.length }),
);

async function scan() {
  if (!root.value.trim()) {
    showToast(t('projectsDiscovery.rootRequired'), 'error');
    return;
  }
  scanning.value = true;
  try {
    const res = await projectApi.discover({
      root: root.value.trim(),
      nested: nested.value,
      max_depth: maxDepth.value,
    });
    repos.value = res.repos;
    newCount.value = res.new_count;
    selected.value = new Set(res.repos.filter((r) => !r.already_imported).map((r) => r.local_path));
    scanned.value = true;
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : t('projectsDiscovery.scanError'), 'error');
  } finally {
    scanning.value = false;
  }
}

function toggle(repo: DiscoveredRepo) {
  if (repo.already_imported) return;
  const next = new Set(selected.value);
  if (next.has(repo.local_path)) next.delete(repo.local_path);
  else next.add(repo.local_path);
  selected.value = next;
}

function selectAllNew() {
  selected.value = new Set(repos.value.filter((r) => !r.already_imported).map((r) => r.local_path));
}

async function runImport() {
  if (selectedRepos.value.length === 0) return;
  importing.value = true;
  try {
    const res = await projectApi.importRepos({
      repos: selectedRepos.value.map((r) => ({
        name: r.name,
        local_path: r.local_path,
        github_repo: r.remote_url ?? undefined,
      })),
      product_id: productId.value || undefined,
      owner_team_id: teamId.value || undefined,
      run_harness_setup: runSetup.value && canSetup.value,
    });
    showToast(
      t('projectsDiscovery.importedSummary', { count: res.imported.length }),
      'success',
    );
    emit('imported');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : t('projectsDiscovery.importError'), 'error');
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      @click.self="emit('close')"
      @keydown.escape="emit('close')"
    >
      <div class="modal">
        <div class="modal-header">
          <h2>{{ t('projectsDiscovery.title') }}</h2>
          <button class="modal-close" @click="emit('close')">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>{{ t('projectsDiscovery.folderLabel') }}</label>
            <div class="scan-row">
              <input
                v-model="root"
                data-testid="discover-root"
                type="text"
                :placeholder="t('projectsDiscovery.folderPlaceholder')"
                @keydown.enter="scan"
              />
              <button class="btn btn-primary" data-testid="discover-scan" :disabled="scanning" @click="scan">
                {{ scanning ? t('projectsDiscovery.scanning') : t('projectsDiscovery.scan') }}
              </button>
            </div>
            <label class="inline">
              <input type="checkbox" :checked="!nested" @change="nested = false" />
              {{ t('projectsDiscovery.directOnly') }}
            </label>
            <label class="inline">
              <input type="checkbox" v-model="nested" />
              {{ t('projectsDiscovery.scanNested') }}
            </label>
            <label v-if="nested" class="inline">
              {{ t('projectsDiscovery.maxDepth') }}
              <input v-model.number="maxDepth" type="number" min="1" max="8" style="width: 4rem" />
            </label>
          </div>

          <div v-if="scanned" class="results">
            <div class="results-head">
              <span>{{ t('projectsDiscovery.foundSummary', { found: repos.length, count: newCount }) }}</span>
              <button class="link" @click="selectAllNew">{{ t('projectsDiscovery.selectAllNew') }}</button>
            </div>
            <p v-if="repos.length === 0" class="muted">{{ t('projectsDiscovery.noneFound') }}</p>
            <ul v-else class="repo-list">
              <li v-for="repo in repos" :key="repo.local_path" class="repo-row">
                <label>
                  <input
                    type="checkbox"
                    :checked="selected.has(repo.local_path)"
                    :disabled="repo.already_imported"
                    @change="toggle(repo)"
                  />
                  <span class="repo-name">{{ repo.name }}</span>
                  <span v-if="repo.already_imported" class="badge badge-muted">{{ t('projectsDiscovery.importedBadge') }}</span>
                  <span v-else class="badge badge-new">{{ t('projectsDiscovery.newBadge') }}</span>
                  <span class="repo-remote">{{ repo.remote_url || t('projectsDiscovery.localOnly') }}</span>
                </label>
              </li>
            </ul>

            <div class="form-group">
              <label>{{ t('projectsDiscovery.productLabel') }}</label>
              <select v-model="productId" data-testid="discover-product">
                <option value="">{{ t('projectsDiscovery.noProduct') }}</option>
                <option v-for="p in props.products" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t('projectsDiscovery.teamLabel') }}</label>
              <select v-model="teamId" data-testid="discover-team">
                <option value="">{{ t('projectsDiscovery.noTeam') }}</option>
                <option v-for="tm in props.teams" :key="tm.id" :value="tm.id">{{ tm.name }}</option>
              </select>
            </div>
            <label class="inline">
              <input type="checkbox" v-model="runSetup" :disabled="!canSetup" />
              {{ t('projectsDiscovery.runSetup') }}
            </label>
            <p v-if="!canSetup" class="muted">{{ t('projectsDiscovery.setupNeedsTeam') }}</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('close')">{{ t('projectsDiscovery.close') }}</button>
          <button
            v-if="scanned"
            class="btn btn-primary"
            data-testid="discover-import"
            :disabled="importing || selectedRepos.length === 0"
            @click="runImport"
          >
            {{ importing ? t('projectsDiscovery.importing') : importLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.scan-row { display: flex; gap: 0.5rem; }
.scan-row input { flex: 1; }
.inline { display: inline-flex; align-items: center; gap: 0.4rem; margin-right: 1rem; font-size: 0.85rem; }
.results-head { display: flex; justify-content: space-between; align-items: center; margin: 0.75rem 0 0.25rem; }
.repo-list { list-style: none; padding: 0; margin: 0 0 1rem; max-height: 260px; overflow-y: auto; }
.repo-row { padding: 0.25rem 0; }
.repo-row label { display: flex; align-items: center; gap: 0.5rem; }
.repo-name { font-weight: 600; }
.repo-remote { color: var(--text-tertiary, #888); font-size: 0.8rem; margin-left: auto; }
.badge { font-size: 0.65rem; padding: 1px 6px; border-radius: 4px; }
.badge-new { background: rgba(34,197,94,0.15); color: #22c55e; }
.badge-muted { background: var(--bg-tertiary, rgba(255,255,255,0.06)); color: var(--text-tertiary, #888); }
.link { background: none; border: none; color: var(--accent-cyan, #60a5fa); cursor: pointer; font-size: 0.8rem; }
.muted { color: var(--text-tertiary, #888); font-size: 0.8rem; }
</style>
