import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { clearRegistry, getManifest } from '../tool-registry'
import { registerGenericTools, clearConsoleErrors } from '../generic-tools'

describe('generic-tools', () => {
  const mockRegisterTool = vi.fn()
  /** Stores tool definitions captured from registerTool calls. */
  const capturedTools: Array<{
    name: string
    description: string
    execute: (args: Record<string, unknown>) => Promise<unknown>
  }> = []

  beforeEach(() => {
    vi.clearAllMocks()
    clearRegistry()
    clearConsoleErrors()
    capturedTools.length = 0
    mockRegisterTool.mockImplementation((tool: any) => {
      capturedTools.push(tool)
    })
    vi.stubGlobal('navigator', {
      modelContext: { registerTool: mockRegisterTool },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearRegistry()
  })

  function callRegisterAndCapture() {
    registerGenericTools()
  }

  function getToolByName(name: string) {
    return capturedTools.find((t) => t.name === name)
  }

  it('registers all 5 tools', () => {
    callRegisterAndCapture()
    expect(mockRegisterTool).toHaveBeenCalledTimes(5)
  })

  it('registers tools with correct names', () => {
    callRegisterAndCapture()
    const expectedNames = [
      'agented_get_page_info',
      'agented_check_console_errors',
      'agented_navigate_to',
      'agented_get_health_status',
      'agented_list_registered_tools',
    ]
    const registeredNames = mockRegisterTool.mock.calls.map((call: any) => call[0].name)
    expect(registeredNames).toEqual(expectedNames)
  })

  it('registers all tools in the manifest', () => {
    callRegisterAndCapture()
    const manifest = getManifest()
    expect(manifest).toHaveLength(5)
    expect(manifest.every((e) => e.page === 'generic')).toBe(true)
  })

  describe('agented_get_page_info', () => {
    it('returns page title, URL, and view in ToolResponse shape', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_get_page_info')
      expect(tool).toBeDefined()

      // happy-dom provides document.title and window.location
      document.title = 'Agented Dashboard'
      const result = (await tool!.execute({})) as any
      expect(result).toHaveProperty('content')
      expect(result.content).toHaveLength(1)
      expect(result.content[0].type).toBe('text')

      const data = JSON.parse(result.content[0].text)
      expect(data.title).toBe('Agented Dashboard')
      expect(data).toHaveProperty('url')
      expect(data).toHaveProperty('view')
    })
  })

  describe('agented_check_console_errors', () => {
    it('captures console.error calls and returns them', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_check_console_errors')

      // console.error should now be intercepted
      console.error('test error one')
      console.error('test error two')

      const result = (await tool!.execute({})) as any
      const data = JSON.parse(result.content[0].text)
      expect(data.count).toBeGreaterThanOrEqual(2)
      expect(data.errors).toContain('test error one')
      expect(data.errors).toContain('test error two')
    })

    it('clears errors when clear=true', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_check_console_errors')

      console.error('to be cleared')
      const result1 = (await tool!.execute({ clear: true })) as any
      const data1 = JSON.parse(result1.content[0].text)
      expect(data1.count).toBeGreaterThanOrEqual(1)

      // After clearing, the next call should return 0
      const result2 = (await tool!.execute({})) as any
      const data2 = JSON.parse(result2.content[0].text)
      expect(data2.count).toBe(0)
      expect(data2.errors).toEqual([])
    })

    it('returns ToolResponse shape', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_check_console_errors')
      const result = (await tool!.execute({})) as any
      expect(result).toHaveProperty('content')
      expect(Array.isArray(result.content)).toBe(true)
      expect(result.content[0]).toHaveProperty('type', 'text')
      expect(result.content[0]).toHaveProperty('text')
    })
  })

  describe('agented_navigate_to', () => {
    it('sets window.location.href to the given path', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_navigate_to')
      expect(tool).toBeDefined()

      const result = (await tool!.execute({ path: '/projects' })) as any
      expect(result.content[0].type).toBe('text')
      const data = JSON.parse(result.content[0].text)
      expect(data.success).toBe(true)
      expect(data).toHaveProperty('new_url')
    })

    it('returns ToolResponse shape', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_navigate_to')
      const result = (await tool!.execute({ path: '/agents' })) as any
      expect(result).toHaveProperty('content')
      expect(result.content).toHaveLength(1)
      expect(result.content[0].type).toBe('text')
    })
  })

  describe('agented_get_health_status', () => {
    it('fetches /health/readiness and returns status', async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        status: 200,
        ok: true,
        json: async () => ({ status: 'ready' }),
      })
      vi.stubGlobal('fetch', mockFetch)

      callRegisterAndCapture()
      const tool = getToolByName('agented_get_health_status')
      const result = (await tool!.execute({})) as any
      const data = JSON.parse(result.content[0].text)

      expect(mockFetch).toHaveBeenCalledWith('/health/readiness')
      expect(data.status).toBe(200)
      expect(data.backend_connected).toBe(true)
      expect(data.details).toEqual({ status: 'ready' })
    })

    it('handles network failure gracefully', async () => {
      vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))

      callRegisterAndCapture()
      const tool = getToolByName('agented_get_health_status')
      const result = (await tool!.execute({})) as any
      const data = JSON.parse(result.content[0].text)

      expect(data.status).toBe(0)
      expect(data.backend_connected).toBe(false)
      expect(data.error).toBe('Connection refused')
    })

    it('returns ToolResponse shape', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue({
          status: 200,
          ok: true,
          json: async () => ({ status: 'ready' }),
        })
      )

      callRegisterAndCapture()
      const tool = getToolByName('agented_get_health_status')
      const result = (await tool!.execute({})) as any
      expect(result).toHaveProperty('content')
      expect(result.content[0]).toHaveProperty('type', 'text')
    })
  })

  describe('agented_list_registered_tools', () => {
    it('returns manifest entries from the tool registry', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_list_registered_tools')
      const result = (await tool!.execute({})) as any
      const data = JSON.parse(result.content[0].text)

      expect(data.count).toBe(5) // The 5 generic tools themselves
      expect(data.tools).toHaveLength(5)
      expect(data.tools.map((t: any) => t.name)).toContain('agented_get_page_info')
      expect(data.tools.map((t: any) => t.name)).toContain('agented_list_registered_tools')
    })

    it('returns ToolResponse shape', async () => {
      callRegisterAndCapture()
      const tool = getToolByName('agented_list_registered_tools')
      const result = (await tool!.execute({})) as any
      expect(result).toHaveProperty('content')
      expect(Array.isArray(result.content)).toBe(true)
      expect(result.content[0]).toHaveProperty('type', 'text')
    })
  })

  describe('feature detection', () => {
    it('no-ops when navigator.modelContext is absent', () => {
      vi.stubGlobal('navigator', {})
      registerGenericTools()
      expect(mockRegisterTool).not.toHaveBeenCalled()
      expect(getManifest()).toHaveLength(0)
    })
  })
})
