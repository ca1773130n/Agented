import { computed } from 'vue'
import { useTourMachine } from './useTourMachine'
import { TOUR_STEP_DEFINITIONS } from '../constants/tourSteps'

export interface ChecklistItem {
  key: string
  label: string
  completed: boolean
  link: string
  linkHash?: string
}

export function useTourChecklist() {
  const tour = useTourMachine()

  const checklistItems = computed<ChecklistItem[]>(() =>
    TOUR_STEP_DEFINITIONS.map(def => ({
      key: def.key,
      label: def.label,
      link: def.route,
      linkHash: def.routeHash,
      completed: tour.context.value.completedSteps.includes(def.key),
    }))
  )

  const completedCount = computed(() => checklistItems.value.filter(i => i.completed).length)
  const totalCount = computed(() => TOUR_STEP_DEFINITIONS.length)

  // Show checklist when tour has any completed steps or is in complete state
  const showChecklist = computed(() => {
    const s = tour.state.value
    return s === 'complete' || tour.context.value.completedSteps.length > 0
  })

  return { checklistItems, completedCount, totalCount, showChecklist }
}
