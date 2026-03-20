import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'

export interface TourStep {
  id: string
  route: string
  routeHash?: string
  target: string
  title: string
  message: string
  skippable: boolean
  waitFor?: () => boolean
  onEnter?: () => void | Promise<void>
  onComplete?: () => void
}

interface PersistedTourState {
  active: boolean
  currentStepIndex: number
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
    route: '/backends',
    target: '[data-tour="ai-backends"]',
    title: 'AI Backend Accounts',
    message:
      'Register your Anthropic, OpenAI, or other provider accounts — agents schedule work across them seamlessly',
    skippable: false,
  },
  {
    id: 'monitoring',
    route: '/settings',
    routeHash: '#general',
    target: '[data-tour="token-monitoring"]',
    title: 'Token Monitoring',
    message:
      'Turn on token monitoring to predict usage and hand off between accounts before hitting rate limits',
    skippable: false,
  },
  {
    id: 'harness',
    route: '/settings',
    routeHash: '#harness',
    target: '[data-tour="harness-plugins"]',
    title: 'Harness Plugins',
    message:
      'Verifying bundled plugins are installed — HarnessSync, GRD, and Everything Claude Code',
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
    message:
      'Assign Matrix teams to your project — Command, Development, Research, Operations, or QA',
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
  const completed = ref<string[]>(saved?.completed ?? [])
  const tourComplete = ref(saved?.tourComplete ?? false)

  const currentStep = computed<TourStep | null>(() => {
    if (!active.value) return null
    return TOUR_STEPS[currentStepIndex.value] ?? null
  })

  const totalSteps = TOUR_STEPS.length
  const displayStepNumber = computed(() => currentStepIndex.value + 2)
  const displayTotalSteps = totalSteps + 1

  function persist() {
    saveState({
      active: active.value,
      currentStepIndex: currentStepIndex.value,
      completed: completed.value,
      tourComplete: tourComplete.value,
    })
  }

  // Also watch for any external mutations to reactive state
  watch([active, currentStepIndex, completed], persist, { deep: true })

  function startTour() {
    if (tourComplete.value) return
    active.value = true
    currentStepIndex.value = 0
    persist()
    navigateToStep(0)
  }

  function nextStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (step) {
      completed.value = [...completed.value, step.id]
      step.onComplete?.()
    }
    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      persist()
      navigateToStep(currentStepIndex.value)
    } else {
      endTour()
    }
  }

  function skipStep() {
    const step = TOUR_STEPS[currentStepIndex.value]
    if (!step?.skippable) return
    if (currentStepIndex.value < TOUR_STEPS.length - 1) {
      currentStepIndex.value++
      persist()
      navigateToStep(currentStepIndex.value)
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

  function navigateToStep(index: number) {
    const step = TOUR_STEPS[index]
    if (!step) return
    const route = step.routeHash ? step.route + step.routeHash : step.route
    if (route) router.push(route)
    step.onEnter?.()
  }

  function updateStepRoute(stepId: string, route: string) {
    const step = TOUR_STEPS.find((s) => s.id === stepId)
    if (step) step.route = route
  }

  return {
    active,
    currentStepIndex,
    currentStep,
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
