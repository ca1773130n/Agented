import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { PrHistoryPoint } from '../../../services/api'

// Capture chart constructor calls
let chartConstructorCalls: any[] = []
const mockDestroy = vi.fn()

// Mock Chart.js with a proper class
vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn()
    destroy: () => void
    options: any
    data: any
    type: string

    constructor(canvas: any, config: any) {
      this.type = config.type
      this.data = config.data
      this.options = config.options
      this.destroy = mockDestroy
      chartConstructorCalls.push({ canvas, config, instance: this })
    }
  }

  return {
    Chart: MockChart,
    registerables: []
  }
})

// Import after mock
import PrHistoryChart from '../PrHistoryChart.vue'
import { Chart } from 'chart.js'

describe('PrHistoryChart', () => {
  const mockHistory: PrHistoryPoint[] = [
    { date: '2024-01-15', created: 5, merged: 3, closed: 1 },
    { date: '2024-01-16', created: 8, merged: 4, closed: 2 },
    { date: '2024-01-17', created: 3, merged: 6, closed: 0 }
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    chartConstructorCalls = []
  })

  function mountComponent(history = mockHistory) {
    return mount(PrHistoryChart, {
      props: { history }
    })
  }

  describe('rendering', () => {
    it('renders canvas element', () => {
      const wrapper = mountComponent()

      expect(wrapper.find('canvas').exists()).toBe(true)
    })

    it('renders chart container with correct class', () => {
      const wrapper = mountComponent()

      expect(wrapper.find('.chart-container').exists()).toBe(true)
    })
  })

  describe('chart initialization', () => {
    it('registers Chart.js components', () => {
      mountComponent()

      expect(Chart.register).toHaveBeenCalled()
    })

    it('creates chart on mount', async () => {
      mountComponent()
      await flushPromises()

      expect(chartConstructorCalls.length).toBeGreaterThan(0)
    })

    it('creates line chart', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.type).toBe('line')
    })

    it('passes correct datasets for PR status', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      expect(datasets).toHaveLength(3)
      expect(datasets[0].label).toBe('Created')
      expect(datasets[1].label).toBe('Merged')
      expect(datasets[2].label).toBe('Closed')
    })

    it('sorts history by date', async () => {
      const unsortedHistory = [
        { date: '2024-01-20', created: 5, merged: 3, closed: 1 },
        { date: '2024-01-10', created: 8, merged: 4, closed: 2 }
      ]

      mountComponent(unsortedHistory)
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      // First label should be from the earlier date
      expect(labels[0]).toContain('Jan 10')
    })

    it('extracts correct data values from history', async () => {
      const history = [
        { date: '2024-01-15', created: 10, merged: 5, closed: 2 }
      ]

      mountComponent(history)
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      expect(datasets[0].data).toContain(10) // Created
      expect(datasets[1].data).toContain(5)  // Merged
      expect(datasets[2].data).toContain(2)  // Closed
    })
  })

  describe('chart labels', () => {
    it('formats dates correctly', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      // Should contain date in format like "Jan 15"
      expect(labels[0]).toMatch(/[A-Z][a-z]{2} \d+/)
    })
  })

  describe('chart options', () => {
    it('configures chart as responsive', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.options?.responsive).toBe(true)
    })

    it('configures y-axis to begin at zero', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const yScale = chartCall.config.options?.scales?.y

      expect(yScale?.beginAtZero).toBe(true)
    })

    it('configures legend at top', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const legend = chartCall.config.options?.plugins?.legend

      expect(legend?.position).toBe('top')
    })

    it('configures line tension for smooth curves', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      datasets.forEach((dataset: { tension?: number }) => {
        expect(dataset.tension).toBe(0.3)
      })
    })

    it('configures fill for area chart effect', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      datasets.forEach((dataset: { fill?: boolean }) => {
        expect(dataset.fill).toBe(true)
      })
    })
  })

  describe('chart updates', () => {
    it('destroys previous chart before creating new one', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      // Update props to trigger re-render
      await wrapper.setProps({
        history: [...mockHistory, { date: '2024-01-18', created: 4, merged: 2, closed: 1 }]
      })
      await flushPromises()

      expect(mockDestroy).toHaveBeenCalled()
    })

    it('recreates chart when history changes', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      const initialCallCount = chartConstructorCalls.length

      await wrapper.setProps({
        history: [...mockHistory, { date: '2024-01-18', created: 4, merged: 2, closed: 1 }]
      })
      await flushPromises()

      expect(chartConstructorCalls.length).toBeGreaterThan(initialCallCount)
    })
  })

  describe('empty state', () => {
    it('handles empty history array', async () => {
      mountComponent([])
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.data.labels).toHaveLength(0)
    })
  })

  describe('color configuration', () => {
    it('uses distinct colors for each status', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      const colors = datasets.map((d: { borderColor: string }) => d.borderColor)
      const uniqueColors = new Set(colors)

      // All 3 status types should have unique colors
      expect(uniqueColors.size).toBe(3)
    })

    it('configures semi-transparent background fill', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      datasets.forEach((dataset: { backgroundColor: string }) => {
        // Background should end with alpha value (e.g., "20")
        expect(dataset.backgroundColor).toMatch(/20$/)
      })
    })
  })

  describe('interaction configuration', () => {
    it('configures index interaction mode', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const interaction = chartCall.config.options?.interaction

      expect(interaction?.mode).toBe('index')
      expect(interaction?.intersect).toBe(false)
    })
  })
})
