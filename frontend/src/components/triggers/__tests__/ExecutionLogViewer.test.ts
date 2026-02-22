import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ExecutionLogViewer from '../ExecutionLogViewer.vue'
import { executionApi } from '../../../services/api'

// Mock EventSource
class MockEventSource {
  listeners: Record<string, ((event: MessageEvent) => void)[]> = {}
  onError: ((event: Event) => void) | null = null

  addEventListener(event: string, callback: (event: MessageEvent) => void) {
    if (!this.listeners[event]) this.listeners[event] = []
    this.listeners[event].push(callback)
  }

  set onerror(handler: (event: Event) => void) {
    this.onError = handler
  }

  close = vi.fn()

  // Helper to emit events in tests
  emit(event: string, data: unknown) {
    this.listeners[event]?.forEach(cb =>
      cb(new MessageEvent(event, { data: JSON.stringify(data) }))
    )
  }
}

let mockEventSourceInstance: MockEventSource

vi.mock('../../../services/api', () => ({
  executionApi: {
    get: vi.fn(),
    streamLogs: vi.fn(() => {
      mockEventSourceInstance = new MockEventSource()
      return mockEventSourceInstance
    })
  }
}))

describe('ExecutionLogViewer', () => {
  const mockExecution = {
    id: 1,
    execution_id: 'exec-1',
    trigger_id: 'bot-1',
    trigger_name: 'Test Trigger',
    trigger_type: 'manual' as const,
    started_at: '2024-01-01T00:00:00Z',
    backend_type: 'claude' as const,
    status: 'success' as const,
    duration_ms: 5000,
    stdout_log: 'Line 1\nLine 2\nLine 3',
    stderr_log: ''
  }

  const mockRunningExecution = {
    ...mockExecution,
    status: 'running' as const,
    duration_ms: undefined,
    stdout_log: undefined,
    stderr_log: undefined
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountComponent(props: {
    executionId: string
    isLive?: boolean
    maxHeight?: string
    showHeader?: boolean
  } = { executionId: 'exec-1' }) {
    return mount(ExecutionLogViewer, {
      props
    })
  }

  describe('loading state', () => {
    it('shows loading state initially', () => {
      vi.mocked(executionApi.get).mockImplementation(() => new Promise(() => {}))

      const wrapper = mountComponent()

      expect(wrapper.find('.log-loading').exists()).toBe(true)
    })

    it('hides loading state after execution loads', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.log-loading').exists()).toBe(false)
    })

    it('shows error message on load failure', async () => {
      vi.mocked(executionApi.get).mockRejectedValue(new Error('Not found'))

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.log-error').exists()).toBe(true)
      expect(wrapper.text()).toContain('Not found')
    })
  })

  describe('displaying existing logs', () => {
    it('displays stdout logs', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.findAll('.log-line').length).toBeGreaterThanOrEqual(3)
      expect(wrapper.text()).toContain('Line 1')
      expect(wrapper.text()).toContain('Line 2')
      expect(wrapper.text()).toContain('Line 3')
    })

    it('displays stderr logs', async () => {
      vi.mocked(executionApi.get).mockResolvedValue({
        ...mockExecution,
        stderr_log: 'Error line'
      })

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.text()).toContain('Error line')
    })

    it('renders log viewer with correct max-height style', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.log-viewer').attributes('style')).toContain('500px')
    })
  })

  describe('live streaming', () => {
    it('starts streaming for running execution with isLive=true', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockRunningExecution)

      mountComponent({ executionId: 'exec-1', isLive: true })
      await flushPromises()

      expect(executionApi.streamLogs).toHaveBeenCalledWith('exec-1')
    })

    it('does not start streaming when isLive is false', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockRunningExecution)

      mountComponent({ executionId: 'exec-1', isLive: false })
      await flushPromises()

      expect(executionApi.streamLogs).not.toHaveBeenCalled()
    })

    it('receives log events via SSE', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockRunningExecution)

      const wrapper = mountComponent({ executionId: 'exec-1', isLive: true })
      await flushPromises()

      // Emit a log event
      mockEventSourceInstance.emit('log', {
        timestamp: '2024-01-01T00:00:01Z',
        stream: 'stdout',
        content: 'Live log line'
      })
      await flushPromises()

      expect(wrapper.text()).toContain('Live log line')
    })

    it('does not start streaming for completed execution', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution) // status is 'success'

      mountComponent({ executionId: 'exec-1', isLive: true })
      await flushPromises()

      // Should not stream for completed execution even with isLive=true
      expect(executionApi.streamLogs).not.toHaveBeenCalled()
    })
  })

  describe('max height', () => {
    it('uses default max height', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.log-viewer').attributes('style')).toContain('500px')
    })

    it('uses custom max height when provided', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent({ executionId: 'exec-1', maxHeight: '300px' })
      await flushPromises()

      expect(wrapper.find('.log-viewer').attributes('style')).toContain('300px')
    })
  })

  describe('api calls', () => {
    it('fetches execution on mount', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      mountComponent()
      await flushPromises()

      expect(executionApi.get).toHaveBeenCalledWith('exec-1')
    })

    it('fetches new execution when executionId changes', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      await wrapper.setProps({ executionId: 'exec-2' })
      await flushPromises()

      expect(executionApi.get).toHaveBeenCalledWith('exec-2')
    })
  })

  describe('log content display', () => {
    it('shows line numbers', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      const lineNumbers = wrapper.findAll('.line-number')
      expect(lineNumbers.length).toBeGreaterThan(0)
    })

    it('shows stream type indicator', async () => {
      vi.mocked(executionApi.get).mockResolvedValue(mockExecution)

      const wrapper = mountComponent()
      await flushPromises()

      const streamIndicators = wrapper.findAll('.line-stream')
      expect(streamIndicators.length).toBeGreaterThan(0)
    })

    it('shows empty state when no logs', async () => {
      vi.mocked(executionApi.get).mockResolvedValue({
        ...mockExecution,
        stdout_log: '',
        stderr_log: ''
      })

      const wrapper = mountComponent()
      await flushPromises()

      expect(wrapper.find('.log-empty').exists()).toBe(true)
    })
  })
})
