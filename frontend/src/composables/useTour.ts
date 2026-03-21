import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'

export interface TourSubstep {
  id: string
  route: string
  target: string
  label: string      // e.g., "Claude Code (1/4)"
  message: string
  skippable: boolean
}

export interface TourStep {
  id: string
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  substeps?: TourSubstep[]
  waitFor?: () => boolean
  onEnter?: () => void | Promise<void>
  onComplete?: () => void
}

interface PersistedTourState {
  active: boolean
  currentStepIndex: number
  currentSubstepIndex: number
  completed: string[]
  tourComplete?: boolean
}

const STORAGE_KEY = 'agented-tour-state'

const TOUR_STEPS: TourStep[] = [
  {
    id: 'workspace',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="workspace-root"]',
    title: 'Workspace Directory',
    message: 'Set the root directory where project repos will be cloned and managed',
    skippable: false,
  },
  {
    id: 'backends',
    route: '/backends/backend-claude',
    target: '[data-tour="add-account-btn"]',
    title: 'AI Backend Accounts',
    message: 'Register your Anthropic account for Claude Code',
    skippable: true,
    substeps: [
      {
        id: 'backend-claude',
        route: '/backends/backend-claude',
        target: '[data-tour="add-account-btn"]',
        label: 'Claude Code (1/4)',
        message: 'Register your Anthropic account for Claude Code',
        skippable: true,
      },
      {
        id: 'backend-codex',
        route: '/backends/backend-codex',
        target: '[data-tour="add-account-btn"]',
        label: 'Codex CLI (2/4)',
        message: 'Register your OpenAI account for Codex CLI',
        skippable: true,
      },
      {
        id: 'backend-gemini',
        route: '/backends/backend-gemini',
        target: '[data-tour="add-account-btn"]',
        label: 'Gemini CLI (3/4)',
        message: 'Register your Google account for Gemini CLI',
        skippable: true,
      },
      {
        id: 'backend-opencode',
        route: '/backends/backend-opencode',
        target: '[data-tour="add-account-btn"]',
        label: 'OpenCode (4/4)',
        message: 'Register an account for OpenCode',
        skippable: true,
      },
    ],
  },
  {
    id: 'monitoring',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="token-monitoring"]',
    title: 'Token Monitoring',
    message: 'Turn on token monitoring to predict usage and hand off between accounts before hitting rate limits',
    skippable: false,
  },
  {
    id: 'harness',
    route: '/settings',
    routeHash: '#harness',
    target: '[data-tour="harness-plugins"]',
    title: 'Harness Plugins',
    message: 'Verifying bundled plugins are installed — HarnessSync, GRD, and Everything Claude Code',
    skippable: false,
  },
  {
    id: 'product',
    route: '/products',
    target: '[data-tour="create-product"]',
    title: 'First Product',
    message: 'Create your first product — this is what your agent teams will build',
    skippable: true,
  },
  {
    id: 'project',
    route: '',
    target: '[data-tour="create-project"]',
    title: 'First Project',
    message: 'Connect a GitHub repo as a project under your product',
    skippable: true,
  },
  {
    id: 'teams',
    route: '',
    target: '[data-tour="assign-teams"]',
    title: 'Assign Teams',
    message: 'Assign Matrix teams to your project — Command, Development, Research, Operations, or QA',
    skippable: true,
  },
]

function loadState(): PersistedTourState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveState(state: PersistedTourState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function useTour() {
  const router = useRouter()

  const saved = loadState()
  const active = ref(saved?.active ?? false)
  const currentStepIndex = ref(saved?.currentStepIndex ?? 0)
  const currentSubstepIndex = ref(saved?.currentSubstepIndex ?? 0)
  const completed = ref<string[]>(saved?.completed ?? [])
  const tourComplete = ref(saved?.tourComplete ?? false)

  const currentStep = computed<TourStep | null>(() => {
    if (!active.value) return null
    return TOUR_STEPS[currentStepIndex.value] ?? null
  })

  // The effective step/substep for display and targeting
  const effectiveTarget = computed(() => {
    const step = currentStep.value
    if (!step) return null
    if (step.substeps && step.substeps.length > 0) {
      return step.substeps[currentSubstepIndex.value] ?? step.substeps[0]
    }
    return step
  })

  const effectiveRoute = computed(() => {
    const target = effectiveTarget.value
    if (!target) return ''
    if ('routeHash' in target && target.routeHash) return target.route + target.routeHash
    return target.route
  })

  const substepLabel = computed(() => {
    const step = currentStep.value
    if (!step?.substeps) return null
    const sub = step.substeps[currentSubstepIndex.value]
    return sub?.label ?? null
  })

  const totalSteps = TOUR_STEPS.length
  const displayStepNumber = computed(() => currentStepIndex.value + 2)
  const displayTotalSteps = totalSteps + 1

  function persist() {
    saveState({
      active: active.value,
      currentStepIndex: currentStepIndex.value,
      currentSubstepIndex: currentSubstepIndex.value,
      completed: completed.value,
      tourComplete: tourComplete.value,
    })
  }

  watch([active, currentStepIndex, currentSubstepIndex, completed], persist, { deep: true })

  function startTour() {
    if (tourComplete.value) return
    active.value = true
    currentStepIndex.value = 0
    currentSubstepIndex.value = 0
    persist()
    navigateToCurrent()
  }

  function nextStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (!step) return

    // If step has substeps, try advancing substep first
    if (step.substeps && currentSubstepIndex.value < step.substeps.length - 1) {
      currentSubstepIndex.value++
      persist()
      navigateToCurrent()
      return
    }

    // Mark step complete and advance to next major step
    completed.value = [...completed.value, step.id]
    step.onComplete?.()
    currentSubstepIndex.value = 0

    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      persist()
      navigateToCurrent()
    } else {
      endTour()
    }
  }

  function skipStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (!step) return

    // Check if the current substep is skippable
    if (step.substeps) {
      const sub = step.substeps[currentSubstepIndex.value]
      if (sub?.skippable && currentSubstepIndex.value < step.substeps.length - 1) {
        // Skip just this substep
        currentSubstepIndex.value++
        persist()
        navigateToCurrent()
        return
      }
    }

    // Skip entire step (or last substep)
    if (!step.skippable) return
    currentSubstepIndex.value = 0
    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      persist()
      navigateToCurrent()
    } else {
      endTour()
    }
  }

  function endTour() {
    active.value = false
    tourComplete.value = true
    persist()
    router.push('/')
  }

  function navigateToCurrent() {
    const route = effectiveRoute.value
    if (route) router.push(route)
    currentStep.value?.onEnter?.()
  }

  function updateStepRoute(stepId: string, route: string) {
    const step = TOUR_STEPS.find((s) => s.id === stepId)
    if (step) step.route = route
  }

  return {
    active,
    currentStepIndex,
    currentSubstepIndex,
    currentStep,
    effectiveTarget,
    substepLabel,
    completed,
    totalSteps: displayTotalSteps,
    displayStepNumber,
    tourComplete,
    startTour,
    nextStep,
    skipStep,
    endTour,
    updateStepRoute,
    steps: TOUR_STEPS,
  }
}
