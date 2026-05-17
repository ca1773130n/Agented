<script setup lang="ts">
/**
 * ContextPreviewDrawer
 *
 * Slide-over panel that shows the operator what claude will
 * actually see when their next message is sent. Calls the
 * existing ``POST /admin/projects/{id}/forge-context/preview``
 * route with the same ``session_overrides`` + ``attachments``
 * the session would use, then renders the compiled
 * ``system_prompt_text``, ``prompt_prepend``, ``overlay_files``
 * keys, ``mcp_servers`` keys, and which bindings resolved /
 * skipped.
 *
 * The drawer is unstyled scrollable content inside a fixed-
 * position right-edge panel so it doesn't disturb the underlying
 * session view. Closes on backdrop click, Escape, or the X
 * button.
 *
 * v0.7.75.
 */
import { ref, toRef, watch } from 'vue';
import { projectApi } from '../../services/api';
import type {
  ForgeAttachment,
  ForgeBundlePreview,
  ForgeSessionOverrides,
} from '../../services/api/projects';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  open: boolean;
  projectId: string;
  // Same payload shapes the create_session / session_input
  // routes accept, so the preview is faithful to what would
  // actually get sent.
  sessionOverrides?: ForgeSessionOverrides;
  attachments?: ForgeAttachment[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const bundle = ref<ForgeBundlePreview | null>(null);
const loading = ref(false);
const errorMessage = ref<string | null>(null);

// v0.7.75 (codex BLOCK 1) — token-guarded fetch. Rapid
// open → close → open used to let a slow earlier response land
// after a fresh one, overwriting the new state. Each ``load()``
// stamps a monotonically increasing id; the response writes only
// if its id is still current AND ``props.open`` is still true.
// AbortController would also work but the route is cheap and a
// stale-write guard is the smaller patch.
let loadToken = 0;

async function load() {
  loadToken += 1;
  const token = loadToken;
  loading.value = true;
  errorMessage.value = null;
  bundle.value = null;
  try {
    const res = await projectApi.previewForgeContext(props.projectId, {
      session_overrides: props.sessionOverrides,
      attachments: props.attachments,
    });
    if (token !== loadToken || !props.open) return;
    bundle.value = res.bundle;
  } catch (err) {
    if (token !== loadToken || !props.open) return;
    errorMessage.value =
      err instanceof Error ? err.message : 'Failed to load preview';
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      load();
    } else {
      // Drawer hygiene: clear state on close so the next open
      // doesn't briefly flash the previous bundle.
      bundle.value = null;
      errorMessage.value = null;
      // Invalidate any in-flight request whose late response
      // would otherwise repopulate the cleared state.
      loadToken += 1;
    }
  },
);

// v0.7.75 (codex BLOCK 2) — focus trap. Matches what
// SessionStartDialog and other modal-overlay components do; the
// composable handles initial focus, restore-on-close, and tab
// cycling so keyboard users aren't dropped behind the drawer.
const drawerEl = ref<HTMLElement | null>(null);
useFocusTrap(drawerEl, toRef(props, 'open'));

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit('close');
}

function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close');
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open"
      class="preview-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-title"
      tabindex="-1"
      @click="onBackdropClick"
      @keydown="onEscape"
    >
      <aside
        ref="drawerEl"
        class="preview-drawer"
        tabindex="-1"
        @click.stop
      >
        <header class="preview-header">
          <div>
            <h3 id="preview-title">Context preview</h3>
            <p class="preview-subtitle">
              What claude will see in the system prompt + the next
              user message, given current project bindings, session
              overrides, and attachments.
            </p>
          </div>
          <button
            type="button"
            class="preview-close"
            aria-label="Close preview"
            @click="emit('close')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div class="preview-body">
          <div v-if="loading" class="preview-state">Loading preview…</div>
          <div v-else-if="errorMessage" class="preview-state preview-error">
            {{ errorMessage }}
          </div>
          <div v-else-if="bundle" class="preview-sections">
            <section class="preview-section">
              <h4 class="preview-heading">
                <code>--append-system-prompt</code> text
              </h4>
              <p v-if="!bundle.system_prompt_text" class="preview-empty">
                (empty — no rules / skills bound, or none enabled)
              </p>
              <pre v-else class="preview-pre">{{ bundle.system_prompt_text }}</pre>
            </section>

            <section class="preview-section">
              <h4 class="preview-heading">User-message prepend</h4>
              <p v-if="!bundle.prompt_prepend" class="preview-empty">
                (empty — no per-prompt attachments)
              </p>
              <pre v-else class="preview-pre">{{ bundle.prompt_prepend }}</pre>
            </section>

            <section
              v-if="bundle.overlay_files.length || bundle.overlay_symlinks.length"
              class="preview-section"
            >
              <h4 class="preview-heading">
                Overlay files
                <span class="preview-count">
                  {{ bundle.overlay_files.length + bundle.overlay_symlinks.length }}
                </span>
              </h4>
              <ul class="preview-list">
                <li v-for="path in bundle.overlay_files" :key="path">
                  <code>{{ path }}</code>
                </li>
                <li
                  v-for="path in bundle.overlay_symlinks"
                  :key="`s-${path}`"
                  class="preview-list-symlink"
                >
                  <code>{{ path }} →</code>
                </li>
              </ul>
            </section>

            <section
              v-if="bundle.mcp_servers.length"
              class="preview-section"
            >
              <h4 class="preview-heading">
                MCP servers
                <span class="preview-count">{{ bundle.mcp_servers.length }}</span>
              </h4>
              <ul class="preview-list">
                <li v-for="name in bundle.mcp_servers" :key="name">
                  <code>{{ name }}</code>
                </li>
              </ul>
            </section>

            <section
              v-if="bundle.resolved_bindings.length"
              class="preview-section"
            >
              <h4 class="preview-heading">
                Resolved bindings
                <span class="preview-count">{{ bundle.resolved_bindings.length }}</span>
              </h4>
              <ul class="preview-list preview-list-bindings">
                <li v-for="(b, idx) in bundle.resolved_bindings" :key="idx">
                  <span class="preview-binding-kind">{{ b.kind }}</span>
                  <code>{{ b.asset_id }}</code>
                </li>
              </ul>
            </section>

            <section
              v-if="bundle.skipped_bindings.length"
              class="preview-section preview-section-warn"
            >
              <h4 class="preview-heading">
                Skipped bindings
                <span class="preview-count">{{ bundle.skipped_bindings.length }}</span>
              </h4>
              <ul class="preview-list preview-list-bindings">
                <li v-for="(b, idx) in bundle.skipped_bindings" :key="idx">
                  <span class="preview-binding-kind">{{ b.kind }}</span>
                  <code>{{ b.asset_id }}</code>
                  <span class="preview-binding-reason">{{ b.reason }}</span>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 50;
  display: flex;
  justify-content: flex-end;
}
.preview-drawer {
  width: min(540px, 90vw);
  height: 100%;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.25);
  font-family: 'Geist', system-ui, sans-serif;
}
.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  gap: 12px;
}
.preview-header h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  color: var(--text-primary);
}
.preview-subtitle {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.preview-close {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  width: 28px;
  height: 28px;
  border-radius: 4px;
  cursor: pointer;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
}
.preview-close svg {
  width: 16px;
  height: 16px;
}
.preview-close:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.preview-state {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
.preview-error {
  color: var(--accent-red, #ff6464);
}

.preview-sections {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.preview-section-warn {
  border-left: 2px solid var(--accent-amber, #ffb454);
  padding-left: 8px;
}
.preview-heading {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 0 0 6px 0;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.preview-heading code {
  font-size: 11px;
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 3px;
  color: var(--text-primary);
  text-transform: none;
  letter-spacing: 0;
}
.preview-count {
  font-size: 10px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 2px 6px;
  border-radius: 999px;
}
.preview-empty {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
}
.preview-pre {
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 10px 12px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}
.preview-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview-list li {
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
  color: var(--text-primary);
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}
.preview-list code {
  background: transparent;
  padding: 0;
  color: inherit;
}
.preview-list-bindings li {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.preview-binding-kind {
  font-family: 'Geist', sans-serif;
  text-transform: uppercase;
  font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  min-width: 70px;
}
.preview-binding-reason {
  font-family: 'Geist', sans-serif;
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
}
.preview-list-symlink {
  color: var(--text-secondary);
  font-style: italic;
}
</style>
