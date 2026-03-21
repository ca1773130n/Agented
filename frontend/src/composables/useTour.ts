import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { driver, type DriveStep, type Config } from 'driver.js'
import 'driver.js/dist/driver.css'

const STORAGE_KEY = 'agented-tour-state'

// ---------------------------------------------------------------------------
// Auto-discovery: scan a container for .form-group elements and generate
// driver.js steps for each label+input pair automatically.
// ---------------------------------------------------------------------------

/**
 * Scan a container element for .form-group children and return driver.js
 * steps that highlight each field in order.
 */
function discoverFormSteps(containerSelector: string): DriveStep[] {
  const container = document.querySelector(containerSelector)
  if (!container) return []

  const groups = container.querySelectorAll('.form-group')
  const steps: DriveStep[] = []

  groups.forEach((group) => {
    const label = group.querySelector('label')
    const input = group.querySelector('input, select, textarea')
    if (!input) return

    const labelText = label?.textContent?.trim() || 'Field'
    const helpEl = group.querySelector('small, .help-text, .form-help, p')
    const helpText = helpEl?.textContent?.trim() || `Enter the ${labelText.toLowerCase()}`

    // Use the input's id for precise targeting, fall back to the form-group itself
    steps.push({
      element: input.id ? `#${input.id}` : (input as HTMLElement),
      popover: {
        title: labelText,
        description: helpText,
        side: 'bottom',
        align: 'start',
      },
    })
  })

  // Also discover the submit button
  const submitBtn = container.querySelector('.btn.btn-primary, button[type="submit"]')
  if (submitBtn) {
    const btnText = submitBtn.textContent?.trim() || 'Submit'
    steps.push({
      element: submitBtn as HTMLElement,
      popover: {
        title: btnText,
        description: `Click to ${btnText.toLowerCase()}`,
        side: 'top',
        align: 'end',
      },
    })
  }

  return steps
}

// ---------------------------------------------------------------------------
// Wait for element utility
// ---------------------------------------------------------------------------

function waitForElement(selector: string, timeoutMs = 10000): Promise<boolean> {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) { resolve(true); return }
    let done = false
    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        done = true
        observer.disconnect()
        resolve(true)
      }
    })
    observer.observe(document.body, { childList: true, subtree: true })
    setTimeout(() => { if (!done) { observer.disconnect(); resolve(false) } }, timeoutMs)
  })
}

// ---------------------------------------------------------------------------
// Driver.js dark theme + glow CSS
// ---------------------------------------------------------------------------

function injectTourStyles() {
  if (typeof document === 'undefined' || document.getElementById('agented-tour-css')) return
  const style = document.createElement('style')
  style.id = 'agented-tour-css'
  style.textContent = `
    /* Dark theme popover */
    .agented-tour-popover {
      background: #1a1a2e !important;
      border: 1px solid rgba(129,140,248,0.3) !important;
      border-radius: 12px !important;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5), 0 0 20px rgba(99,102,241,0.15) !important;
      color: #e4e4e7 !important;
      font-family: 'Geist','Inter',-apple-system,system-ui,sans-serif !important;
      max-width: 360px !important;
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
      line-height: 1.55 !important;
    }
    .agented-tour-popover .driver-popover-progress-text {
      color: #71717a !important;
      font-size: 11px !important;
    }
    .agented-tour-popover .driver-popover-prev-btn {
      background: transparent !important;
      border: 1px solid rgba(255,255,255,0.1) !important;
      color: #a1a1aa !important;
      border-radius: 6px !important;
      font-size: 13px !important;
      padding: 6px 14px !important;
    }
    .agented-tour-popover .driver-popover-prev-btn:hover {
      border-color: rgba(255,255,255,0.2) !important;
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
      border-color: rgba(129,140,248,0.3) !important;
    }

    /* Pulsing glow on highlighted element */
    @keyframes agented-tour-glow {
      0%, 100% { box-shadow: 0 0 15px 4px rgba(99,102,241,0.4); }
      50% { box-shadow: 0 0 30px 8px rgba(99,102,241,0.6); }
    }
    .driver-active-element {
      animation: agented-tour-glow 1.5s ease-in-out infinite !important;
      outline: 2px solid #818cf8 !important;
      outline-offset: 4px !important;
    }
  `
  document.head.appendChild(style)
}

// ---------------------------------------------------------------------------
// Tour step groups — each group navigates to a route, then runs steps.
// A group can use explicit steps OR auto-discover form fields.
// ---------------------------------------------------------------------------

interface StepGroup {
  route: string
  // Explicit steps to show
  steps?: DriveStep[]
  // OR: click a trigger element, wait for a container, then auto-discover its form fields
  triggerClick?: string       // CSS selector of button to click to open form
  discoverContainer?: string  // CSS selector of the form container to scan
  discoverTitle?: string      // Title for the auto-discovered section
  // Shared config
  introStep?: DriveStep       // Optional intro step before form fields (e.g., highlight the section)
}

function buildStepGroups(): StepGroup[] {
  return [
    // Step 2: Workspace directory
    {
      route: '/settings#general',
      steps: [
        {
          element: '[data-tour="workspace-root"] input.form-input',
          popover: {
            title: 'Workspace Root',
            description: 'Set the root directory where GitHub repos will be cloned for your agent teams. For example: <code>/home/user/workspace</code>',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '[data-tour="workspace-root"] .btn.btn-primary',
          popover: {
            title: 'Save Workspace',
            description: 'Click Save after entering your workspace path.',
            side: 'top',
            align: 'end',
          },
        },
      ],
    },
    // Step 3a: Claude Code — Add Account
    {
      route: '/backends/backend-claude',
      introStep: {
        element: '[data-tour="add-account-btn"]',
        popover: {
          title: 'Claude Code — Add Account',
          description: 'Click "Add Account" to register your Anthropic account.',
          side: 'left',
          align: 'start',
        },
      },
      triggerClick: '[data-tour="add-account-btn"]',
      discoverContainer: '.inline-account-form',
      discoverTitle: 'Claude Code Account',
    },
    // Step 3b: Codex CLI
    {
      route: '/backends/backend-codex',
      introStep: {
        element: '[data-tour="add-account-btn"]',
        popover: {
          title: 'Codex CLI — Add Account',
          description: 'Click "Add Account" to register your OpenAI account.',
          side: 'left',
          align: 'start',
        },
      },
      triggerClick: '[data-tour="add-account-btn"]',
      discoverContainer: '.inline-account-form',
      discoverTitle: 'Codex CLI Account',
    },
    // Step 3c: Gemini CLI
    {
      route: '/backends/backend-gemini',
      introStep: {
        element: '[data-tour="add-account-btn"]',
        popover: {
          title: 'Gemini CLI — Add Account',
          description: 'Click "Add Account" to register your Google account.',
          side: 'left',
          align: 'start',
        },
      },
      triggerClick: '[data-tour="add-account-btn"]',
      discoverContainer: '.inline-account-form',
      discoverTitle: 'Gemini CLI Account',
    },
    // Step 3d: OpenCode
    {
      route: '/backends/backend-opencode',
      introStep: {
        element: '[data-tour="add-account-btn"]',
        popover: {
          title: 'OpenCode — Add Account',
          description: 'Click "Add Account" to register an OpenCode account.',
          side: 'left',
          align: 'start',
        },
      },
      triggerClick: '[data-tour="add-account-btn"]',
      discoverContainer: '.inline-account-form',
      discoverTitle: 'OpenCode Account',
    },
    // Step 4: Token monitoring
    {
      route: '/settings#general',
      steps: [
        {
          element: '[data-tour="token-monitoring"]',
          popover: {
            title: 'Token Monitoring',
            description: 'Enable rate limit monitoring to track token usage and predict when to hand off between accounts.',
            side: 'top',
            align: 'center',
          },
        },
      ],
    },
    // Step 5: Harness plugins
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
    // Step 6: Products
    {
      route: '/products',
      steps: [
        {
          element: '[data-tour="create-product"]',
          popover: {
            title: 'Create Your First Product',
            description: 'Products organize your projects. Create one to get started, or skip for now.',
            side: 'bottom',
            align: 'end',
          },
        },
      ],
    },
  ]
}

// ---------------------------------------------------------------------------
// Main composable
// ---------------------------------------------------------------------------

export function useTour() {
  const router = useRouter()
  const saved = loadState()
  const active = ref(false)
  const tourComplete = ref(saved?.tourComplete ?? false)

  injectTourStyles()

  const driverConfig: Config = {
    animate: true,
    overlayColor: '#000',
    overlayOpacity: 0.75,
    stagePadding: 10,
    stageRadius: 8,
    allowClose: true,
    smoothScroll: true,
    showProgress: true,
    progressText: '{{current}} / {{total}}',
    nextBtnText: 'Next →',
    prevBtnText: '← Back',
    doneBtnText: 'Got it',
    popoverClass: 'agented-tour-popover',
  }

  const stepGroups = buildStepGroups()

  async function runGroup(index: number) {
    if (index >= stepGroups.length) {
      endTour()
      return
    }

    const group = stepGroups[index]

    // Navigate to the route
    await router.push(group.route)
    await new Promise(r => setTimeout(r, 200))

    let steps: DriveStep[] = []

    if (group.steps) {
      // Explicit steps — wait for first element
      const firstSel = typeof group.steps[0].element === 'string' ? group.steps[0].element : ''
      if (firstSel) {
        const found = await waitForElement(firstSel)
        if (!found) { runGroup(index + 1); return }
      }
      steps = group.steps
    } else if (group.triggerClick && group.discoverContainer) {
      // Auto-discover: first show intro step, then click trigger, then scan form

      // Wait for the trigger button
      if (group.introStep) {
        const triggerSel = typeof group.introStep.element === 'string' ? group.introStep.element : ''
        if (triggerSel) {
          const found = await waitForElement(triggerSel)
          if (!found) { runGroup(index + 1); return }
        }
        // Show intro step as a single highlight
        await new Promise(r => setTimeout(r, 200))

        const introDriver = driver({
          ...driverConfig,
          showProgress: false,
          steps: [group.introStep],
          onDestroyStarted: () => {
            introDriver.destroy()
          },
          onNextClick: () => {
            introDriver.destroy()
          },
        })
        introDriver.drive()

        // Wait for user to click "Got it" on the intro
        await new Promise<void>((resolve) => {
          const check = setInterval(() => {
            if (!introDriver.isActive()) {
              clearInterval(check)
              resolve()
            }
          }, 100)
        })
      }

      // Click the trigger to open the form
      const triggerEl = document.querySelector(group.triggerClick) as HTMLElement
      if (triggerEl) {
        triggerEl.click()
        // Wait for the form container to appear
        const found = await waitForElement(group.discoverContainer)
        if (!found) { runGroup(index + 1); return }
        await new Promise(r => setTimeout(r, 300))

        // Auto-discover form fields
        steps = discoverFormSteps(group.discoverContainer)
        if (steps.length === 0) { runGroup(index + 1); return }
      } else {
        runGroup(index + 1)
        return
      }
    }

    if (steps.length === 0) { runGroup(index + 1); return }

    // Run driver.js with the steps
    const driverObj = driver({
      ...driverConfig,
      steps,
      onDestroyStarted: () => {
        driverObj.destroy()
        runGroup(index + 1)
      },
      onNextClick: () => {
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
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ tourComplete: true }))
    router.push('/')
  }

  function loadState(): { tourComplete?: boolean } | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      return raw ? JSON.parse(raw) : null
    } catch { return null }
  }

  return {
    active,
    tourComplete,
    startTour,
    endTour,
    // Backward compat stubs (TourOverlay removed but App.vue may reference)
    currentStep: ref(null),
    effectiveTarget: ref(null),
    substepLabel: ref(null),
    displayStepNumber: ref(0),
    totalSteps: 8,
    currentStepIndex: ref(0),
    currentSubstepIndex: ref(0),
    completed: ref<string[]>([]),
    nextStep: () => {},
    skipStep: () => {},
    updateStepRoute: () => {},
    steps: [],
  }
}
