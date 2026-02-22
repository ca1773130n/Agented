/**
 * Unit tests for the page-specific WebMCP tool registration pattern.
 *
 * These tests validate that useWebMcpTool() correctly registers/deregisters
 * tools in the manifest when components mount/unmount, and that execute
 * handlers return valid ToolResponse shapes.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { defineComponent, h, nextTick } from 'vue';
import { mount } from '@vue/test-utils';
import { useWebMcpTool } from '../../composables/useWebMcpTool';
import {
  getManifest,
  deregisterFromManifest,
} from '../tool-registry';

// Mock navigator.modelContext so useWebMcpTool does not no-op
const mockUnregister = vi.fn();
const mockRegisterTool = vi.fn(() => ({ unregister: mockUnregister }));
const mockUnregisterTool = vi.fn();

beforeEach(() => {
  // Clean up manifest between tests
  for (const entry of getManifest()) {
    deregisterFromManifest(entry.name);
  }
  mockRegisterTool.mockClear();
  mockUnregister.mockClear();
  mockUnregisterTool.mockClear();

  // Set up navigator.modelContext mock
  Object.defineProperty(navigator, 'modelContext', {
    value: {
      registerTool: mockRegisterTool,
      unregisterTool: mockUnregisterTool,
    },
    writable: true,
    configurable: true,
  });
});

/** Factory: creates a test component that registers a page-specific tool. */
function createPageComponent(
  toolName: string,
  page: string,
  executeFn?: () => Promise<{ content: { type: 'text'; text: string }[] }>
) {
  return defineComponent({
    setup() {
      useWebMcpTool({
        name: toolName,
        description: `Test tool: ${toolName}`,
        page,
        execute:
          executeFn ??
          (async () => ({
            content: [{ type: 'text' as const, text: JSON.stringify({ loaded: true }) }],
          })),
      });
      return () => h('div', { 'data-testid': 'page-component' });
    },
  });
}

describe('Page-specific WebMCP tool registration', () => {
  it('registers tool in manifest on mount', async () => {
    const TestPage = createPageComponent('test_page_tool', 'TestPage');
    const wrapper = mount(TestPage);
    await nextTick();

    const manifest = getManifest();
    expect(manifest).toHaveLength(1);
    expect(manifest[0]).toEqual({
      name: 'test_page_tool',
      description: 'Test tool: test_page_tool',
      page: 'TestPage',
    });

    wrapper.unmount();
  });

  it('execute returns valid ToolResponse with JSON-parseable text', async () => {
    const TestPage = createPageComponent('test_execute_tool', 'TestPage');
    const wrapper = mount(TestPage);
    await nextTick();

    // The tool descriptor passed to registerTool
    const calls = mockRegisterTool.mock.calls as any[][];
    const registerCall = calls[0][0];
    expect(registerCall).toBeDefined();
    expect(registerCall.name).toBe('test_execute_tool');

    const result = await registerCall.execute({});
    expect(result).toHaveProperty('content');
    expect(Array.isArray(result.content)).toBe(true);
    expect(result.content.length).toBeGreaterThan(0);
    expect(result.content[0].type).toBe('text');

    // Verify the text is valid JSON
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed).toEqual({ loaded: true });

    wrapper.unmount();
  });

  it('deregisters tool from manifest on unmount', async () => {
    const TestPage = createPageComponent('test_unmount_tool', 'TestPage');
    const wrapper = mount(TestPage);
    await nextTick();

    expect(getManifest()).toHaveLength(1);

    wrapper.unmount();
    await nextTick();

    expect(getManifest()).toHaveLength(0);
  });

  it('supports multiple tools from different components', async () => {
    const PageA = createPageComponent('tool_page_a', 'PageA');
    const PageB = createPageComponent('tool_page_b', 'PageB');

    const wrapperA = mount(PageA);
    const wrapperB = mount(PageB);
    await nextTick();

    const manifest = getManifest();
    expect(manifest).toHaveLength(2);

    const names = manifest.map((e) => e.name).sort();
    expect(names).toEqual(['tool_page_a', 'tool_page_b']);

    wrapperA.unmount();
    wrapperB.unmount();
  });

  it('re-registers correctly after unmount and remount (no duplicates)', async () => {
    const TestPage = createPageComponent('test_remount_tool', 'TestPage');

    // Mount first time
    const wrapper1 = mount(TestPage);
    await nextTick();
    expect(getManifest()).toHaveLength(1);

    // Unmount
    wrapper1.unmount();
    await nextTick();
    expect(getManifest()).toHaveLength(0);

    // Mount again
    const wrapper2 = mount(TestPage);
    await nextTick();
    expect(getManifest()).toHaveLength(1);
    expect(getManifest()[0].name).toBe('test_remount_tool');

    wrapper2.unmount();
  });

  it('tool execute reads DOM state at call time (not stale setup-time)', async () => {
    // Create a component whose execute handler reads a DOM data attribute
    const DomReadingComponent = defineComponent({
      setup() {
        useWebMcpTool({
          name: 'test_dom_reader',
          description: 'Reads DOM at call time',
          page: 'TestPage',
          execute: async () => {
            const testAttr = document.body.getAttribute('data-test-marker');
            return {
              content: [
                {
                  type: 'text' as const,
                  text: JSON.stringify({ marker: testAttr }),
                },
              ],
            };
          },
        });
        return () => h('div');
      },
    });

    const wrapper = mount(DomReadingComponent);
    await nextTick();

    // Initially no marker on body
    const calls = mockRegisterTool.mock.calls as any[][];
    const registerCall = calls[0][0];
    let result = await registerCall.execute({});
    let parsed = JSON.parse(result.content[0].text);
    expect(parsed.marker).toBeNull();

    // Add marker to DOM after mount
    document.body.setAttribute('data-test-marker', 'updated-value');

    // Execute again -- should see the updated DOM
    result = await registerCall.execute({});
    parsed = JSON.parse(result.content[0].text);
    expect(parsed.marker).toBe('updated-value');

    // Clean up
    document.body.removeAttribute('data-test-marker');
    wrapper.unmount();
  });
});
