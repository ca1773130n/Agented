/**
 * Single source of truth for tour step definitions.
 *
 * Consumed by:
 * - App.vue (TOUR_STEP_META, STEP_NUMBER_MAP)
 * - useTourChecklist.ts (CHECKLIST_DEFS)
 * - TourCompletionScreen.vue (STEP_META)
 */

export interface TourStepDefinition {
  /** Machine state key, e.g. 'workspace' or 'backends.claude' */
  key: string
  /** i18n locale key suffix under `tour.steps.*` */
  localeKey: string
  /** Human-readable label shown in checklists and completion screen */
  label: string
  /** CSS selector for the tour spotlight target */
  target: string
  /** Tour tooltip title */
  title: string
  /** Tour tooltip message */
  message: string
  /** Whether this step can be skipped */
  skippable: boolean
  /** Route path to navigate to */
  route: string
  /** Optional hash fragment for the route */
  routeHash?: string
  /** Step group number (1-based) for progress display */
  stepNumber: number
  /** Substep label if this step is part of a multi-step group */
  substepLabel?: string
  /** Toast message substring that triggers auto-advance when matched */
  autoAdvanceOnToast?: string
}

export const TOUR_STEP_DEFINITIONS: TourStepDefinition[] = [
  {
    key: 'workspace',
    localeKey: 'workspace',
    label: 'Workspace Directory',
    target: '[data-tour="workspace-root"]',
    title: 'Workspace Directory',
    message: 'Set the root directory where repos will be cloned for your agent teams.',
    skippable: false,
    route: '/settings',
    routeHash: '#general',
    stepNumber: 1,
    autoAdvanceOnToast: 'Workspace root saved',
  },
  {
    key: 'backends.claude',
    localeKey: 'claude',
    label: 'Claude Code',
    target: '[data-tour="add-account-btn"]',
    title: 'AI Backend Accounts',
    message: "Register a Claude Code account. Click 'Add Account' to enter your Anthropic credentials.",
    skippable: true,
    route: '/backends/backend-claude',
    stepNumber: 2,
    substepLabel: 'Claude Code (1/4)',
    autoAdvanceOnToast: 'Account saved',
  },
  {
    key: 'backends.codex',
    localeKey: 'codex',
    label: 'Codex CLI',
    target: '[data-tour="add-account-btn"]',
    title: 'AI Backend Accounts',
    message: "Register a Codex CLI account for OpenAI integration (optional). Click 'Add Account' to configure.",
    skippable: true,
    route: '/backends/backend-codex',
    stepNumber: 2,
    substepLabel: 'Codex CLI (2/4)',
    autoAdvanceOnToast: 'Account saved',
  },
  {
    key: 'backends.gemini',
    localeKey: 'gemini',
    label: 'Gemini CLI',
    target: '[data-tour="add-account-btn"]',
    title: 'AI Backend Accounts',
    message: "Register a Gemini CLI account for Google AI (optional). Click 'Add Account' to configure.",
    skippable: true,
    route: '/backends/backend-gemini',
    stepNumber: 2,
    substepLabel: 'Gemini CLI (3/4)',
    autoAdvanceOnToast: 'Account saved',
  },
  {
    key: 'backends.opencode',
    localeKey: 'opencode',
    label: 'OpenCode',
    target: '[data-tour="opencode-info"]',
    title: 'AI Backend Accounts',
    message: 'OpenCode routes through other AI backends. No separate account needed if you registered one above.',
    skippable: true,
    route: '/backends/backend-opencode',
    stepNumber: 2,
    substepLabel: 'OpenCode (4/4)',
  },
  {
    key: 'monitoring',
    localeKey: 'monitoring',
    label: 'Token Monitoring',
    target: '[data-tour="token-monitoring"]',
    title: 'Token Monitoring',
    message: 'Configure rate limit monitoring to track token usage across your AI backend accounts.',
    skippable: true,
    route: '/settings',
    routeHash: '#general',
    stepNumber: 3,
    autoAdvanceOnToast: 'Monitoring settings saved',
  },
  {
    key: 'verification',
    localeKey: 'verification',
    label: 'Harness Verification',
    target: '[data-tour="harness-plugins"]',
    title: 'Harness Verification',
    message: 'Verify the harness integration plugin is configured for deploying skills to your marketplace.',
    skippable: true,
    route: '/settings',
    routeHash: '#harness',
    stepNumber: 4,
  },
  {
    key: 'create_product',
    localeKey: 'product',
    label: 'First Product',
    target: '[data-tour="create-product"]',
    title: 'Create Your First Product',
    message: 'Products group related projects under a shared context. Click to create your first product.',
    skippable: true,
    route: '/products',
    stepNumber: 5,
  },
  {
    key: 'create_project',
    localeKey: 'project',
    label: 'First Project',
    target: '[data-tour="create-project"]',
    title: 'Create Your First Project',
    message: 'Projects track work within a product. Click to add your first project.',
    skippable: true,
    route: '/products',
    stepNumber: 6,
  },
  {
    key: 'create_team',
    localeKey: 'team',
    label: 'Assign Teams',
    target: '[data-tour="assign-teams"]',
    title: 'Assign Teams to Project',
    message: 'Bundled teams with pre-configured super agents are ready to use — just assign them here. You can create custom teams and agents later.',
    skippable: true,
    route: '/projects',
    stepNumber: 7,
  },
]

/** Lookup map by step key for O(1) access */
export const TOUR_STEP_MAP: Record<string, TourStepDefinition> = Object.fromEntries(
  TOUR_STEP_DEFINITIONS.map(d => [d.key, d]),
)

/** Total number of distinct step groups */
export const TOTAL_TOUR_STEPS = Math.max(...TOUR_STEP_DEFINITIONS.map(d => d.stepNumber))
