<script setup lang="ts">
/**
 * Render an interactive permission prompt (v0.7.69).
 *
 * When the Agented permission hook intercepts a ``PreToolUse``, the
 * backend pushes a ``permission_request`` SSE event with the tool
 * name + input. This card surfaces an Approve / Deny pair to the
 * user; their click answers the parked hook so claude can proceed.
 *
 * Different from the read-only hook badge (v0.7.66): this card
 * BLOCKS claude until the user decides. The user's claude
 * subprocess is literally sitting in ``urllib.request.urlopen``
 * inside the hook script.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { PermissionRequestPayload } from '../../composables/useProjectSession';

const { t } = useI18n();

const props = defineProps<{
  request: PermissionRequestPayload;
}>();

const emit = defineEmits<{
  (e: 'allow'): void;
  (e: 'deny'): void;
}>();

// Pretty-print the tool input. Bash gets the command on its own
// line; everything else gets a 2-space-indented JSON dump so the
// user can audit the full payload before approving.
const previewLine = computed<string>(() => {
  const input = props.request.tool_input as Record<string, unknown>;
  if (props.request.tool_name === 'Bash' && typeof input.command === 'string') {
    return input.command;
  }
  const firstArg =
    (input.file_path as string) ||
    (input.path as string) ||
    (input.pattern as string) ||
    (input.url as string) ||
    (input.query as string) ||
    '';
  return firstArg;
});

const fullPayload = computed(() => {
  try {
    return JSON.stringify(props.request.tool_input, null, 2);
  } catch {
    return String(props.request.tool_input);
  }
});
</script>

<template>
  <div class="pp-card">
    <div class="pp-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
      <span>{{ t('permissionPromptCard.header') }}</span>
    </div>

    <div class="pp-body">
      <div class="pp-tool-row">
        <span class="pp-tool-name">{{ request.tool_name }}</span>
        <code v-if="previewLine" class="pp-preview">{{ previewLine }}</code>
      </div>
      <details class="pp-full">
        <summary>{{ t('permissionPromptCard.fullInput') }}</summary>
        <pre class="pp-json">{{ fullPayload }}</pre>
      </details>
      <p v-if="request.cwd" class="pp-cwd">{{ t('permissionPromptCard.in') }} <code>{{ request.cwd }}</code></p>
    </div>

    <div class="pp-actions">
      <button type="button" class="pp-btn pp-btn-deny" @click="emit('deny')">
        {{ t('permissionPromptCard.deny') }}
      </button>
      <button type="button" class="pp-btn pp-btn-allow" @click="emit('allow')">
        {{ t('permissionPromptCard.approve') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.pp-card {
  margin: 12px 0;
  border: 1px solid var(--accent-yellow, #ffcc80);
  border-radius: 10px;
  background: linear-gradient(
    to bottom,
    rgba(255, 204, 128, 0.08),
    var(--bg-secondary)
  );
  overflow: hidden;
}

.pp-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(255, 204, 128, 0.12);
  border-bottom: 1px solid rgba(255, 204, 128, 0.3);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-yellow, #ffcc80);
  letter-spacing: 0.02em;
}
.pp-header svg {
  width: 14px;
  height: 14px;
}

.pp-body {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pp-tool-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.pp-tool-name {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
  font-size: 13px;
  color: var(--accent-cyan, #00bcd4);
  background: rgba(0, 188, 212, 0.12);
  padding: 2px 8px;
  border-radius: 4px;
}
.pp-preview {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pp-full {
  margin-top: 4px;
  font-size: 12px;
}
.pp-full > summary {
  cursor: pointer;
  color: var(--text-muted);
  user-select: none;
}
.pp-json {
  margin: 6px 0 0 0;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  overflow-x: auto;
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
}

.pp-cwd {
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
}
.pp-cwd code {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.pp-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
}
.pp-btn {
  padding: 7px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: filter 0.12s, background 0.12s;
}
.pp-btn-allow {
  background: var(--accent-green, #4caf50);
  color: #001a08;
  border-color: var(--accent-green, #4caf50);
  font-weight: 600;
}
.pp-btn-allow:hover {
  filter: brightness(1.08);
}
.pp-btn-deny {
  background: transparent;
  border-color: rgba(255, 100, 100, 0.4);
  color: var(--accent-red, #ff6464);
}
.pp-btn-deny:hover {
  background: rgba(255, 100, 100, 0.08);
}
</style>
