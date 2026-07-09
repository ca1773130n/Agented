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
  /** Toast message substring that triggers auto-advance when matched.
   *  NOTE: this is the raw English string. It only matches when the UI is in
   *  English — prefer `autoAdvanceI18nKey`, which is resolved against the
   *  active locale so auto-advance works in ko/ja/zh too. */
  autoAdvanceOnToast?: string
  /** i18n key whose resolved translation (in the current locale) triggers
   *  auto-advance when the success toast contains it. Locale-independent. */
  autoAdvanceI18nKey?: string
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
    autoAdvanceI18nKey: 'settings.general.toastWorkspaceSaved',
  },
  // NOTE: the per-backend register steps (backends.claude/codex/gemini/opencode)
  // were removed — onboarding now auto-detects & imports accounts in the
  // WelcomePage `discover` phase. Step numbers were recomputed accordingly.
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
    stepNumber: 2,
    autoAdvanceOnToast: 'Monitoring settings saved',
    autoAdvanceI18nKey: 'settings.general.toastMonitoringSaved',
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
    stepNumber: 3,
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
    stepNumber: 4,
  },
  {
    key: 'create_team',
    localeKey: 'team',
    label: 'Assign Teams',
    target: '[data-tour="assign-teams"]',
    title: 'Assign Teams to Project',
    message: 'Bundled teams with pre-configured super agents are ready to use. Click into any project on this page to assign them — you can create custom teams and agents later.',
    skippable: true,
    route: '/projects',
    stepNumber: 5,
  },
]

/** Lookup map by step key for O(1) access */
export const TOUR_STEP_MAP: Record<string, TourStepDefinition> = Object.fromEntries(
  TOUR_STEP_DEFINITIONS.map(d => [d.key, d]),
)

/** Total number of distinct step groups */
export const TOTAL_TOUR_STEPS = Math.max(...TOUR_STEP_DEFINITIONS.map(d => d.stepNumber))
