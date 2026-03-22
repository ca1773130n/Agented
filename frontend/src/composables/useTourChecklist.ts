import { computed } from 'vue'
import { useTourMachine } from './useTourMachine'

export interface ChecklistItem {
  key: string
  label: string
  completed: boolean
  link: string
  linkHash?: string
}

const CHECKLIST_DEFS: Array<{ key: string; label: string; link: string; linkHash?: string }> = [
  { key: 'workspace', label: 'Workspace Directory', link: '/settings', linkHash: '#general' },
  { key: 'backends.claude', label: 'Claude Code', link: '/backends/backend-claude' },
  { key: 'backends.codex', label: 'Codex CLI', link: '/backends/backend-codex' },
  { key: 'backends.gemini', label: 'Gemini CLI', link: '/backends/backend-gemini' },
  { key: 'backends.opencode', label: 'OpenCode', link: '/backends/backend-opencode' },
  { key: 'monitoring', label: 'Token Monitoring', link: '/settings', linkHash: '#general' },
  { key: 'verification', label: 'Harness Verification', link: '/settings', linkHash: '#harness' },
]

export function useTourChecklist() {
  const tour = useTourMachine()

  const checklistItems = computed<ChecklistItem[]>(() =>
    CHECKLIST_DEFS.map(def => ({
      ...def,
      completed: tour.context.value.completedSteps.includes(def.key),
    }))
  )

  const completedCount = computed(() => checklistItems.value.filter(i => i.completed).length)
  const totalCount = computed(() => CHECKLIST_DEFS.length)

  // Show checklist when tour has any completed steps or is in complete state
  const showChecklist = computed(() => {
    const s = tour.state.value
    return s === 'complete' || tour.context.value.completedSteps.length > 0
  })

  return { checklistItems, completedCount, totalCount, showChecklist }
}
