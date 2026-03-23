import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const STORAGE_KEY = 'agented-tour-state'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TourStep {
  id: string
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  substeps?: TourSubstep[]
}

export interface TourSubstep {
  id: string
  route: string
  target: string
  label: string
  message: string
  skippable: boolean
}

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

const STEPS: TourStep[] = [
  {
    id: 'workspace',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="workspace-root"]',
    title: 'Workspace Directory',
    message: 'Set the root directory where repos will be cloned for your agent teams.',
    skippable: false,
  },
  {
    id: 'backends',
    route: '/backends/backend-claude',
    target: '[data-tour="add-account-btn"]',
    title: 'AI Backend Accounts',
    message: 'Register accounts for each AI backend.',
    skippable: true,
    substeps: [
      {
        id: 'claude',
        route: '/backends/backend-claude',
        target: '[data-tour="add-account-btn"]',
        label: 'Claude Code (1/4)',
        message: 'Register your Anthropic account for Claude Code.',
        skippable: true,
      },
      {
        id: 'codex',
        route: '/backends/backend-codex',
        target: '[data-tour="add-account-btn"]',
        label: 'Codex CLI (2/4)',
        message: 'Register your OpenAI account for Codex CLI.',
        skippable: true,
      },
      {
        id: 'gemini',
        route: '/backends/backend-gemini',
        target: '[data-tour="add-account-btn"]',
        label: 'Gemini CLI (3/4)',
        message: 'Register your Google account for Gemini CLI.',
        skippable: true,
      },
      {
        id: 'opencode',
        route: '/backends/backend-opencode',
        target: '[data-tour="add-account-btn"]',
        label: 'OpenCode (4/4)',
        message: 'Register an account for OpenCode.',
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
    message: 'Enable rate limit monitoring to track token usage.',
    skippable: false,
  },
  {
    id: 'harness',
    route: '/settings',
    routeHash: '#harness',
    target: '[data-tour="harness-plugins"]',
    title: 'Harness Plugins',
    message: 'Verify bundled plugins are installed.',
    skippable: false,
  },
  {
    id: 'product',
    route: '/products',
    target: '[data-tour="create-product"]',
    title: 'Create Your First Product',
    message: 'Products organize your projects. Create one to get started.',
    skippable: true,
  },
  {
    id: 'project',
    route: '/products',
    target: '[data-tour="create-project"]',
    title: 'Create a Project',
    message: 'Connect a GitHub repo as a project.',
    skippable: true,
  },
  {
    id: 'teams',
    route: '/products',
    target: '[data-tour="assign-teams"]',
    title: 'Assign Teams',
    message: 'Assign agent teams to your project.',
    skippable: true,
  },
]

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

interface SavedState {
  active?: boolean
  currentStepIndex?: number
  currentSubstepIndex?: number
  completed?: string[]
  tourComplete?: boolean
}

function loadState(): SavedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useTour() {
  const router = useRouter()
  const saved = loadState()

  const active = ref(saved.active ?? false)
  const tourComplete = ref(saved.tourComplete ?? false)
  const currentStepIndex = ref(saved.currentStepIndex ?? 0)
  const currentSubstepIndex = ref(saved.currentSubstepIndex ?? 0)
  const completed = ref<string[]>(saved.completed ?? [])

  const currentStep = computed(() => {
    if (!active.value) return null
    return STEPS[currentStepIndex.value] ?? null
  })

  const effectiveTarget = computed(() => {
    if (!active.value) return null
    const step = STEPS[currentStepIndex.value]
    if (!step) return null
    if (step.substeps?.[currentSubstepIndex.value]) {
      return step.substeps[currentSubstepIndex.value]
    }
    return step
  })

  const substepLabel = computed(() => {
    if (!active.value) return null
    const step = STEPS[currentStepIndex.value]
    if (!step?.substeps) return null
    return step.substeps[currentSubstepIndex.value]?.label ?? null
  })

  // +2: step 1 is the welcome page (handled by WelcomePage, not this composable)
  const displayStepNumber = computed(() => currentStepIndex.value + 2)

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      active: active.value,
      currentStepIndex: currentStepIndex.value,
      currentSubstepIndex: currentSubstepIndex.value,
      completed: completed.value,
      tourComplete: tourComplete.value,
    }))
  }

  function navigateToStep() {
    const step = STEPS[currentStepIndex.value]
    if (!step) return

    if (step.substeps?.[currentSubstepIndex.value]) {
      router.push(step.substeps[currentSubstepIndex.value].route)
    } else {
      const dest: { path: string; hash?: string } = { path: step.route }
      if (step.routeHash) dest.hash = step.routeHash
      router.push(dest)
    }
  }

  function startTour() {
    if (tourComplete.value) return
    active.value = true
    currentStepIndex.value = 0
    currentSubstepIndex.value = 0
    persist()
    navigateToStep()
  }

  function nextStep() {
    if (!active.value) return
    const step = STEPS[currentStepIndex.value]
    if (!step) return

    if (step.substeps && currentSubstepIndex.value < step.substeps.length - 1) {
      currentSubstepIndex.value++
    } else {
      completed.value.push(step.id)
      currentStepIndex.value++
      currentSubstepIndex.value = 0
      if (currentStepIndex.value >= STEPS.length) {
        endTour()
        return
      }
    }
    persist()
    navigateToStep()
  }

  function skipStep() {
    if (!active.value) return
    const step = STEPS[currentStepIndex.value]
    if (!step?.skippable) return

    completed.value.push(step.id)
    currentStepIndex.value++
    currentSubstepIndex.value = 0
    if (currentStepIndex.value >= STEPS.length) {
      endTour()
      return
    }
    persist()
    navigateToStep()
  }

  function endTour() {
    active.value = false
    tourComplete.value = true
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ tourComplete: true }))
    router.push('/')
  }

  function updateStepRoute() {
    navigateToStep()
  }

  return {
    active,
    tourComplete,
    currentStep,
    effectiveTarget,
    substepLabel,
    displayStepNumber,
    totalSteps: STEPS.length + 1, // +1 for welcome step
    currentStepIndex,
    currentSubstepIndex,
    completed,
    startTour,
    nextStep,
    skipStep,
    endTour,
    updateStepRoute,
    steps: STEPS,
  }
}
