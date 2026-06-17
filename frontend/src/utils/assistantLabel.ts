/**
 * Display-name helpers for the answering AI backend + model.
 *
 * Chat surfaces label the assistant by *who actually answered* — the
 * backend (Claude / Codex / Gemini / OpenCode) plus, when known, the
 * model — instead of a generic "AI". Surfaces that render their own
 * bubbles (e.g. the team-leader chat) use these; the shared AiChatPanel
 * bubbles get the same treatment inside `@ai-accounts/vue-styled`.
 */

const BACKEND_DISPLAY_NAMES: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  gemini: 'Gemini',
  opencode: 'OpenCode',
};

/**
 * Human label for a backend kind. Returns '' for a missing kind or the
 * placeholder `'auto'` (no concrete backend resolved yet) so callers can
 * fall back to a generic name.
 */
export function backendDisplayName(backend?: string | null): string {
  if (!backend || backend === 'auto') return '';
  return (
    BACKEND_DISPLAY_NAMES[backend] ??
    backend.charAt(0).toUpperCase() + backend.slice(1)
  );
}

const MODEL_DISPLAY_NAMES: Record<string, string> = {
  opus: 'Opus',
  sonnet: 'Sonnet',
  haiku: 'Haiku',
  codex: 'Codex',
  zen: 'Zen',
};

/**
 * Human label for a model id. Known short ids are capitalized; anything
 * else (full model strings like `gpt-5.1` or `claude-opus-4-8`) passes
 * through unchanged. Returns '' for a missing model.
 */
export function modelDisplayName(model?: string | null): string {
  if (!model) return '';
  return MODEL_DISPLAY_NAMES[model] ?? model;
}

/**
 * Author label for a chat message role. Assistants are labelled by the
 * resolved backend (falling back to a generic "Assistant"); users get
 * "You"; everything else (system) passes through unchanged.
 */
export function authorName(role: string, backend?: string | null): string {
  if (role === 'user') return 'You';
  if (role === 'assistant') return backendDisplayName(backend) || 'Assistant';
  return role;
}
