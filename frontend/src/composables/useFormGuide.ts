import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FormField {
  selector: string
  inputSelector: string
  label: string
  helpText: string
  isSubmit: boolean
  element: HTMLElement
}

export interface FormGuideReturn {
  fields: Ref<FormField[]>
  currentIndex: Ref<number>
  currentField: ComputedRef<FormField | null>
  isActive: Ref<boolean>
  totalFields: ComputedRef<number>
  activate: () => void
  deactivate: () => void
  nextField: () => boolean
  prevField: () => boolean
  reset: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildInputSelector(group: HTMLElement, index: number): string {
  const input = group.querySelector('input, select, textarea') as HTMLElement | null
  if (input) {
    const id = input.getAttribute('id')
    if (id) return `#${id}`
  }
  // Checkbox groups or groups without a direct input — use the group itself
  return buildGroupSelector(group, index)
}

function buildGroupSelector(group: HTMLElement, index: number): string {
  // Prefer input-id-based selector for uniqueness
  const input = group.querySelector('input, select, textarea') as HTMLElement | null
  if (input) {
    const id = input.getAttribute('id')
    if (id) return `.form-group:has(#${id})`
  }
  // Fall back to nth-of-type (1-indexed)
  return `.form-group:nth-of-type(${index + 1})`
}

function extractLabel(group: HTMLElement, index: number): string {
  const labelEl = group.querySelector('label')
  if (labelEl) {
    const text = labelEl.textContent?.trim() ?? ''
    // Strip trailing asterisks / required markers
    const cleaned = text.replace(/\s*\*+$/, '').trim()
    if (cleaned) return cleaned
  }
  return `Field ${index + 1}`
}

function extractHelpText(group: HTMLElement, label: string): string {
  // Priority 1: data-tour-help attribute
  const tourHelp = group.getAttribute('data-tour-help')
  if (tourHelp) return tourHelp

  // Priority 2: .form-help or .form-description child
  const helpEl = group.querySelector('.form-help, .form-description')
  if (helpEl) {
    const text = helpEl.textContent?.trim()
    if (text) return text
  }

  // Priority 3: <small> child (BackendDetailPage pattern)
  const smallEl = group.querySelector('small')
  if (smallEl) {
    const text = smallEl.textContent?.trim()
    if (text) return text
  }

  // Priority 4: Generated fallback
  return `Enter the ${label} for this form`
}

function isCheckboxGroup(group: HTMLElement): boolean {
  return group.classList.contains('checkbox')
}

function findSubmitButton(container: HTMLElement): HTMLElement | null {
  // 1. button[type="submit"]
  const submitBtn = container.querySelector('button[type="submit"]') as HTMLElement | null
  if (submitBtn) return submitBtn

  // 2. .btn-primary inside .inline-form-actions or form actions
  const actionsArea = container.querySelector('.inline-form-actions')
  if (actionsArea) {
    const primary = actionsArea.querySelector('.btn-primary') as HTMLElement | null
    if (primary) return primary
  }

  // 3. data-tour="submit-btn"
  const dataTour = container.querySelector('[data-tour="submit-btn"]') as HTMLElement | null
  if (dataTour) return dataTour

  return null
}

function buildSubmitSelector(btn: HTMLElement): string {
  const id = btn.getAttribute('id')
  if (id) return `#${id}`

  if (btn.getAttribute('type') === 'submit') return 'button[type="submit"]'
  if (btn.getAttribute('data-tour') === 'submit-btn') return '[data-tour="submit-btn"]'

  return '.inline-form-actions .btn-primary'
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useFormGuide(containerRef: Ref<HTMLElement | null>): FormGuideReturn {
  const fields = ref<FormField[]>([])
  const currentIndex = ref(0)
  const isActive = ref(false)

  const currentField = computed<FormField | null>(() => {
    if (!isActive.value || fields.value.length === 0) return null
    return fields.value[currentIndex.value] ?? null
  })

  const totalFields = computed(() => fields.value.length)

  function activate(): void {
    const container = containerRef.value
    if (!container) {
      fields.value = []
      return
    }

    const groups = container.querySelectorAll('.form-group')
    const discovered: FormField[] = []

    groups.forEach((node, index) => {
      const group = node as HTMLElement
      const label = extractLabel(group, index)
      const helpText = extractHelpText(group, label)
      const groupSelector = buildGroupSelector(group, index)
      const inputSelector = isCheckboxGroup(group)
        ? groupSelector
        : buildInputSelector(group, index)

      discovered.push({
        selector: groupSelector,
        inputSelector,
        label,
        helpText,
        isSubmit: false,
        element: group,
      })
    })

    // Find and append submit button
    const submitBtn = findSubmitButton(container)
    if (submitBtn) {
      discovered.push({
        selector: buildSubmitSelector(submitBtn),
        inputSelector: buildSubmitSelector(submitBtn),
        label: 'Save',
        helpText: 'Save your changes',
        isSubmit: true,
        element: submitBtn,
      })
    }

    fields.value = discovered

    if (discovered.length > 0) {
      isActive.value = true
      currentIndex.value = 0
    }
  }

  function deactivate(): void {
    isActive.value = false
    currentIndex.value = 0
    fields.value = []
  }

  function nextField(): boolean {
    if (currentIndex.value >= fields.value.length - 1) return false
    currentIndex.value++
    return true
  }

  function prevField(): boolean {
    if (currentIndex.value <= 0) return false
    currentIndex.value--
    return true
  }

  function reset(): void {
    currentIndex.value = 0
  }

  return {
    fields,
    currentIndex,
    currentField,
    isActive,
    totalFields,
    activate,
    deactivate,
    nextField,
    prevField,
    reset,
  }
}
