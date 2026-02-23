/**
 * Weight configuration for the randomized test runner.
 *
 * Controls probability distribution when selecting tools to invoke.
 * Read-only tools (get_state, get_list_state) are weighted higher
 * for safety; action tools (trigger_*, perform_*, toggle_*) are
 * weighted lower to avoid rapid state mutations.
 */

export interface ToolWeight {
  /** Glob-style pattern matching tool names. */
  pattern: string;
  /** Relative weight (higher = more likely to be selected). */
  weight: number;
  /** Whether this tool is considered destructive (skipped unless opted in). */
  destructive?: boolean;
}

/** Default weight configuration. */
export const DEFAULT_WEIGHTS: ToolWeight[] = [
  // Read-only state tools — high weight (safe to call repeatedly)
  { pattern: '*_get_state', weight: 40 },
  { pattern: '*_get_list_state', weight: 40 },
  { pattern: '*_get_modal_state', weight: 20 },

  // Navigation — moderate weight
  { pattern: 'agented_navigate_to', weight: 15 },

  // Search/sort actions — moderate weight (non-destructive)
  { pattern: '*_perform_search', weight: 10 },
  { pattern: '*_perform_sort', weight: 10 },
  { pattern: '*_switch_tab', weight: 10 },

  // Modal open actions — low weight (UI changes)
  { pattern: '*_trigger_create', weight: 5 },
  { pattern: '*_toggle_*', weight: 5 },

  // Destructive actions — zero weight by default
  { pattern: '*_trigger_delete', weight: 0, destructive: true },

  // Generic tools — moderate weight
  { pattern: 'agented_get_page_info', weight: 15 },
  { pattern: 'agented_check_console_errors', weight: 10 },
  { pattern: 'agented_get_health_status', weight: 5 },
  { pattern: 'agented_list_registered_tools', weight: 20 },
  { pattern: 'agented_sidebar_get_state', weight: 10 },
];

/**
 * Simple glob matching: supports only leading/trailing `*` wildcards.
 */
function matchPattern(pattern: string, name: string): boolean {
  if (pattern === name) return true;
  if (pattern.startsWith('*') && pattern.endsWith('*')) {
    return name.includes(pattern.slice(1, -1));
  }
  if (pattern.startsWith('*')) {
    return name.endsWith(pattern.slice(1));
  }
  if (pattern.endsWith('*')) {
    return name.startsWith(pattern.slice(0, -1));
  }
  return false;
}

/**
 * Resolves the weight for a given tool name.
 * First matching pattern wins; unmatched tools get weight 1.
 */
export function getToolWeight(
  toolName: string,
  weights: ToolWeight[] = DEFAULT_WEIGHTS
): { weight: number; destructive: boolean } {
  for (const w of weights) {
    if (matchPattern(w.pattern, toolName)) {
      return { weight: w.weight, destructive: w.destructive ?? false };
    }
  }
  return { weight: 1, destructive: false };
}

/**
 * Selects a tool name from the list using weighted random selection.
 * Tools with weight 0 are excluded. Destructive tools excluded unless
 * `allowDestructive` is true.
 */
export function selectWeightedTool(
  toolNames: string[],
  opts?: { allowDestructive?: boolean; weights?: ToolWeight[] }
): string | null {
  const allowDestructive = opts?.allowDestructive ?? false;
  const weights = opts?.weights ?? DEFAULT_WEIGHTS;

  const candidates: { name: string; weight: number }[] = [];
  for (const name of toolNames) {
    const { weight, destructive } = getToolWeight(name, weights);
    if (weight <= 0) continue;
    if (destructive && !allowDestructive) continue;
    candidates.push({ name, weight });
  }

  if (candidates.length === 0) return null;

  const totalWeight = candidates.reduce((sum, c) => sum + c.weight, 0);
  let random = Math.random() * totalWeight;

  for (const c of candidates) {
    random -= c.weight;
    if (random <= 0) return c.name;
  }

  return candidates[candidates.length - 1].name;
}
