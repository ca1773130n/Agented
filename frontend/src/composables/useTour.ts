import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { driver, type DriveStep, type Config } from 'driver.js'
import 'driver.js/dist/driver.css'

const STORAGE_KEY = 'agented-tour-state'
const TOTAL_DISPLAY_STEPS = 8 // 1 welcome + 7 tour steps (backends counted as 1)

interface PersistedTourState {
  tourComplete?: boolean
}

interface TourStepGroup {
  route: string
  steps: DriveStep[]
}

function loadState(): PersistedTourState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function markComplete() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ tourComplete: true }))
}

/**
 * Wait for an element to appear in the DOM (handles lazy-loaded pages).
 * Returns true if found, false if timeout.
 */
function waitForElement(selector: string, timeoutMs = 10000): Promise<boolean> {
  return new Promise((resolve) => {
    const el = document.querySelector(selector)
    if (el) { resolve(true); return }

    let resolved = false
    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        resolved = true
        observer.disconnect()
        resolve(true)
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })

    setTimeout(() => {
      if (!resolved) {
        observer.disconnect()
        resolve(false)
      }
    }, timeoutMs)
  })
}

export function useTour() {
  const router = useRouter()
  const saved = loadState()
  const active = ref(false)
  const tourComplete = ref(saved?.tourComplete ?? false)

  // Common driver.js config for dark theme
  const driverConfig: Config = {
    animate: true,
    overlayColor: '#000',
    overlayOpacity: 0.75,
    stagePadding: 12,
    stageRadius: 10,
    allowClose: false,
    smoothScroll: true,
    showProgress: true,
    progressText: 'Step {{current}} of {{total}}',
    nextBtnText: 'Next',
    prevBtnText: 'Back',
    doneBtnText: 'Done',
    popoverClass: 'agented-tour-popover',
  }

  // Define step groups — each group navigates to a route, then runs driver.js steps on that page
  const stepGroups: TourStepGroup[] = [
    // Group 1: Settings > General — workspace + monitoring
    {
      route: '/settings#general',
      steps: [
        {
          element: '[data-tour="workspace-root"]',
          popover: {
            title: 'Workspace Directory',
            description: 'Set the root directory where project repos will be cloned and managed by your agent teams.',
            side: 'bottom',
            align: 'center',
          },
        },
      ],
    },
    // Group 2: Claude Code backend
    {
      route: '/backends/backend-claude',
      steps: [
        {
          element: '[data-tour="add-account-btn"]',
          popover: {
            title: 'Claude Code — Add Account',
            description: 'Register your Anthropic account. Click "Add Account" to enter your account name, email, and config path.',
            side: 'left',
            align: 'start',
          },
        },
      ],
    },
    // Group 3: Codex backend
    {
      route: '/backends/backend-codex',
      steps: [
        {
          element: '[data-tour="add-account-btn"]',
          popover: {
            title: 'Codex CLI — Add Account',
            description: 'Register your OpenAI account for Codex CLI.',
            side: 'left',
            align: 'start',
          },
        },
      ],
    },
    // Group 4: Gemini backend
    {
      route: '/backends/backend-gemini',
      steps: [
        {
          element: '[data-tour="add-account-btn"]',
          popover: {
            title: 'Gemini CLI — Add Account',
            description: 'Register your Google account for Gemini CLI.',
            side: 'left',
            align: 'start',
          },
        },
      ],
    },
    // Group 5: OpenCode backend
    {
      route: '/backends/backend-opencode',
      steps: [
        {
          element: '[data-tour="add-account-btn"]',
          popover: {
            title: 'OpenCode — Add Account',
            description: 'Register an account for OpenCode.',
            side: 'left',
            align: 'start',
          },
        },
      ],
    },
    // Group 6: Token monitoring
    {
      route: '/settings#general',
      steps: [
        {
          element: '[data-tour="token-monitoring"]',
          popover: {
            title: 'Token Monitoring',
            description: 'Turn on token monitoring to predict usage and hand off between accounts before hitting rate limits.',
            side: 'top',
            align: 'center',
          },
        },
      ],
    },
    // Group 7: Harness plugins
    {
      route: '/settings#harness',
      steps: [
        {
          element: '[data-tour="harness-plugins"]',
          popover: {
            title: 'Harness Plugins',
            description: 'Verify bundled plugins are installed — HarnessSync, GRD, and Everything Claude Code.',
            side: 'bottom',
            align: 'center',
          },
        },
      ],
    },
    // Group 8: Products
    {
      route: '/products',
      steps: [
        {
          element: '[data-tour="create-product"]',
          popover: {
            title: 'Create Your First Product',
            description: 'Create a product — this is what your agent teams will build. You can skip this for now.',
            side: 'bottom',
            align: 'end',
          },
        },
      ],
    },
  ]

  async function runGroup(index: number) {
    if (index >= stepGroups.length) {
      endTour()
      return
    }

    const group = stepGroups[index]

    // Navigate to the route
    await router.push(group.route)

    // Wait for the first element to appear in DOM
    const firstSelector = typeof group.steps[0].element === 'string' ? group.steps[0].element : ''
    if (firstSelector) {
      const found = await waitForElement(firstSelector)
      if (!found) {
        // Element not found — skip this group
        runGroup(index + 1)
        return
      }
    }

    // Small delay for rendering
    await new Promise(r => setTimeout(r, 200))

    // Create driver instance for this group
    const driverObj = driver({
      ...driverConfig,
      steps: group.steps,
      onDestroyStarted: () => {
        // User clicked close or done
        driverObj.destroy()
        runGroup(index + 1)
      },
      onNextClick: () => {
        // If more steps in this group, advance. Otherwise go to next group.
        if (!driverObj.isLastStep()) {
          driverObj.moveNext()
        } else {
          driverObj.destroy()
          runGroup(index + 1)
        }
      },
    })

    driverObj.drive()
  }

  function startTour() {
    if (tourComplete.value) return
    active.value = true
    runGroup(0)
  }

  function endTour() {
    active.value = false
    tourComplete.value = true
    markComplete()
    router.push('/')
  }

  // Inject custom dark-theme CSS for driver.js popovers
  if (typeof document !== 'undefined' && !document.getElementById('agented-tour-driver-css')) {
    const style = document.createElement('style')
    style.id = 'agented-tour-driver-css'
    style.textContent = `
      .agented-tour-popover {
        background: #1a1a2e !important;
        border: 1px solid rgba(129, 140, 248, 0.3) !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 20px rgba(99, 102, 241, 0.15) !important;
        color: #e4e4e7 !important;
        font-family: 'Geist', 'Inter', -apple-system, system-ui, sans-serif !important;
        max-width: 340px !important;
      }
      .agented-tour-popover .driver-popover-title {
        color: #f4f4f5 !important;
        font-size: 15px !important;
        font-weight: 600 !important;
        letter-spacing: -0.3px !important;
      }
      .agented-tour-popover .driver-popover-description {
        color: #a1a1aa !important;
        font-size: 13px !important;
        line-height: 1.5 !important;
      }
      .agented-tour-popover .driver-popover-progress-text {
        color: #71717a !important;
        font-size: 11px !important;
      }
      .agented-tour-popover .driver-popover-prev-btn {
        background: transparent !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: #a1a1aa !important;
        border-radius: 6px !important;
        font-size: 13px !important;
        padding: 6px 14px !important;
      }
      .agented-tour-popover .driver-popover-prev-btn:hover {
        border-color: rgba(255, 255, 255, 0.2) !important;
        color: #e4e4e7 !important;
      }
      .agented-tour-popover .driver-popover-next-btn,
      .agented-tour-popover .driver-popover-done-btn {
        background: #6366f1 !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        padding: 6px 16px !important;
      }
      .agented-tour-popover .driver-popover-next-btn:hover,
      .agented-tour-popover .driver-popover-done-btn:hover {
        background: #818cf8 !important;
      }
      .agented-tour-popover .driver-popover-close-btn {
        color: #71717a !important;
      }
      .agented-tour-popover .driver-popover-close-btn:hover {
        color: #e4e4e7 !important;
      }
      .agented-tour-popover .driver-popover-arrow-side-left .driver-popover-arrow,
      .agented-tour-popover .driver-popover-arrow-side-right .driver-popover-arrow,
      .agented-tour-popover .driver-popover-arrow-side-top .driver-popover-arrow,
      .agented-tour-popover .driver-popover-arrow-side-bottom .driver-popover-arrow {
        background: #1a1a2e !important;
        border-color: rgba(129, 140, 248, 0.3) !important;
      }
    `
    document.head.appendChild(style)
  }

  return {
    active,
    tourComplete,
    startTour,
    endTour,
    // Keep these for backward compat with App.vue template
    currentStep: ref(null),
    effectiveTarget: ref(null),
    substepLabel: ref(null),
    displayStepNumber: ref(0),
    totalSteps: TOTAL_DISPLAY_STEPS,
    currentStepIndex: ref(0),
    currentSubstepIndex: ref(0),
    completed: ref<string[]>([]),
    nextStep: () => {},
    skipStep: () => {},
    updateStepRoute: () => {},
    steps: [],
  }
}
