import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { mockAuditRecords } from '../../../test/fixtures/audits'

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
import FindingsChart from '../FindingsChart.vue'
import { Chart } from 'chart.js'

describe('FindingsChart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    chartConstructorCalls = []
  })

  function mountComponent(audits = mockAuditRecords) {
    return mount(FindingsChart, {
      props: { audits }
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

    it('creates stacked bar chart', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.type).toBe('bar')
    })

    it('passes correct datasets for severity levels', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      expect(datasets).toHaveLength(4)
      expect(datasets[0].label).toBe('Critical')
      expect(datasets[1].label).toBe('High')
      expect(datasets[2].label).toBe('Medium')
      expect(datasets[3].label).toBe('Low')
    })

    it('sorts audits by date', async () => {
      const unsortedAudits = [
        { ...mockAuditRecords[0], audit_date: '2024-01-20' },
        { ...mockAuditRecords[1], audit_date: '2024-01-10' }
      ]

      mountComponent(unsortedAudits)
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      // First label should be from the earlier date
      expect(labels[0]).toContain('Jan 10')
    })

    it('extracts correct data values from audits', async () => {
      const audits = [
        {
          ...mockAuditRecords[0],
          critical: 3,
          high: 5,
          medium: 2,
          low: 1
        }
      ]

      mountComponent(audits)
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      expect(datasets[0].data).toContain(3) // Critical
      expect(datasets[1].data).toContain(5) // High
      expect(datasets[2].data).toContain(2) // Medium
      expect(datasets[3].data).toContain(1) // Low
    })
  })

  describe('chart labels', () => {
    it('uses project name in label', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      expect(labels[0]).toContain('project1')
    })

    it('truncates long project names', async () => {
      const audits = [
        {
          ...mockAuditRecords[0],
          project_name: 'very-long-project-name-that-exceeds-limit'
        }
      ]

      mountComponent(audits)
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      expect(labels[0]).toContain('...')
      expect(labels[0].length).toBeLessThan('very-long-project-name-that-exceeds-limit'.length + 20)
    })

    it('includes formatted date in label', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const labels = chartCall.config.data.labels as string[]

      // Should contain date in format like "Jan 15"
      expect(labels[0]).toMatch(/\([A-Z][a-z]{2} \d+\)/)
    })
  })

  describe('chart options', () => {
    it('configures chart as responsive', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.options?.responsive).toBe(true)
    })

    it('configures stacked scales', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const scales = chartCall.config.options?.scales

      expect(scales?.x?.stacked).toBe(true)
      expect(scales?.y?.stacked).toBe(true)
    })

    it('configures legend at top', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const legend = chartCall.config.options?.plugins?.legend

      expect(legend?.position).toBe('top')
    })
  })

  describe('chart updates', () => {
    it('destroys previous chart before creating new one', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      // Update props to trigger re-render
      await wrapper.setProps({ audits: [...mockAuditRecords, mockAuditRecords[0]] })
      await flushPromises()

      expect(mockDestroy).toHaveBeenCalled()
    })

    it('recreates chart when audits change', async () => {
      const wrapper = mountComponent()
      await flushPromises()

      const initialCallCount = chartConstructorCalls.length

      await wrapper.setProps({
        audits: [
          ...mockAuditRecords,
          {
            ...mockAuditRecords[0],
            audit_id: 'new-audit'
          }
        ]
      })
      await flushPromises()

      expect(chartConstructorCalls.length).toBeGreaterThan(initialCallCount)
    })
  })

  describe('empty state', () => {
    it('handles empty audits array', async () => {
      mountComponent([])
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      expect(chartCall.config.data.labels).toHaveLength(0)
    })
  })

  describe('color configuration', () => {
    it('uses distinct colors for severity levels', async () => {
      mountComponent()
      await flushPromises()

      const chartCall = chartConstructorCalls[0]
      const datasets = chartCall.config.data.datasets

      const colors = datasets.map((d: { backgroundColor: string }) => d.backgroundColor)
      const uniqueColors = new Set(colors)

      // All 4 severity levels should have unique colors
      expect(uniqueColors.size).toBe(4)
    })
  })
})
