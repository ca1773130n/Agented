import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useWebMcpTool } from '../../composables/useWebMcpTool'
import { clearRegistry, getManifest, isRegistered, registerInManifest } from '../tool-registry'

describe('useWebMcpTool', () => {
  const mockUnregister = vi.fn()
  const mockRegisterTool = vi.fn().mockReturnValue({ unregister: mockUnregister })

  beforeEach(() => {
    vi.clearAllMocks()
    clearRegistry()
    vi.stubGlobal('navigator', {
      modelContext: { registerTool: mockRegisterTool },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearRegistry()
  })

  function createTestComponent(options?: Partial<Parameters<typeof useWebMcpTool>[0]>) {
    return defineComponent({
      setup() {
        useWebMcpTool({
          name: 'test_tool',
          description: 'A test tool',
          page: 'TestPage',
          execute: async () => ({ content: [{ type: 'text' as const, text: 'ok' }] }),
          ...options,
        })
        return () => h('div')
      },
    })
  }

  it('calls registerTool on mount with correct descriptor', () => {
    mount(createTestComponent())
    expect(mockRegisterTool).toHaveBeenCalledOnce()
    const call = mockRegisterTool.mock.calls[0][0]
    expect(call.name).toBe('test_tool')
    expect(call.description).toBe('A test tool')
    expect(call.inputSchema).toEqual({ type: 'object', properties: {} })
    expect(typeof call.execute).toBe('function')
  })

  it('registers tool in manifest on mount', () => {
    mount(createTestComponent())
    expect(isRegistered('test_tool')).toBe(true)
    const manifest = getManifest()
    expect(manifest).toHaveLength(1)
    expect(manifest[0].name).toBe('test_tool')
    expect(manifest[0].page).toBe('TestPage')
  })

  it('calls unregister and deregisters from manifest on unmount', () => {
    const wrapper = mount(createTestComponent())
    expect(isRegistered('test_tool')).toBe(true)
    wrapper.unmount()
    expect(mockUnregister).toHaveBeenCalledOnce()
    expect(isRegistered('test_tool')).toBe(false)
  })

  it('re-registers when deps change', async () => {
    const dep = ref(0)
    const TestComp = defineComponent({
      setup() {
        useWebMcpTool({
          name: 'dep_tool',
          description: 'Tool with deps',
          page: 'TestPage',
          execute: async () => ({ content: [{ type: 'text' as const, text: String(dep.value) }] }),
          deps: [dep],
        })
        return () => h('div')
      },
    })

    mount(TestComp)
    expect(mockRegisterTool).toHaveBeenCalledTimes(1)

    // Trigger dep change
    dep.value = 1
    await nextTick()

    // Should have deregistered old and registered new
    expect(mockUnregister).toHaveBeenCalledOnce()
    expect(mockRegisterTool).toHaveBeenCalledTimes(2)
  })

  it('no-ops silently when navigator.modelContext is absent', () => {
    vi.stubGlobal('navigator', {})
    // Should not throw
    const wrapper = mount(createTestComponent())
    expect(mockRegisterTool).not.toHaveBeenCalled()
    expect(isRegistered('test_tool')).toBe(false)
    wrapper.unmount()
  })

  it('warns on duplicate tool name', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // Pre-register a tool with the same name in the manifest
    registerInManifest('test_tool', 'Pre-existing', 'OtherPage')

    mount(createTestComponent())
    expect(warnSpy).toHaveBeenCalledOnce()
    expect(warnSpy.mock.calls[0][0]).toContain('Duplicate tool name "test_tool"')
    warnSpy.mockRestore()
  })

  it('uses unregisterTool fallback when registerTool returns void', () => {
    const mockUnregisterTool = vi.fn()
    mockRegisterTool.mockReturnValueOnce(undefined)
    vi.stubGlobal('navigator', {
      modelContext: {
        registerTool: mockRegisterTool,
        unregisterTool: mockUnregisterTool,
      },
    })

    const wrapper = mount(createTestComponent())
    expect(mockRegisterTool).toHaveBeenCalledOnce()

    wrapper.unmount()
    expect(mockUnregisterTool).toHaveBeenCalledWith('test_tool')
  })
})
