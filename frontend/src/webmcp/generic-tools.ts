/**
 * Five generic verification tools registered at app startup.
 *
 * These tools provide a baseline verification layer that works across
 * any Hive page. They are registered directly via navigator.modelContext
 * (NOT via the useWebMcpTool composable) because they live for the
 * entire app lifetime, not scoped to a single component.
 *
 * Tools:
 * 1. hive_get_page_info       - Current page title, URL, and active view name
 * 2. hive_check_console_errors - Captured JS console.error messages
 * 3. hive_navigate_to          - Navigate to a Hive view by path
 * 4. hive_get_health_status    - Backend /health/readiness check
 * 5. hive_list_registered_tools - Manifest of all registered WebMCP tools
 */

import type { ToolResponse } from './types';
import { registerInManifest, getManifest } from './tool-registry';

// --- Console error capture ---

/** Module-level buffer for captured console.error messages. */
const capturedErrors: string[] = [];

/** Original console.error for passthrough. */
let originalConsoleError: typeof console.error | null = null;

/** Exposed for testing: get current captured errors. */
export function getConsoleErrors(): string[] {
  return [...capturedErrors];
}

/** Exposed for testing: clear captured errors. */
export function clearConsoleErrors(): void {
  capturedErrors.length = 0;
}

/**
 * Installs the console.error interceptor.
 * Subsequent console.error calls are captured into the buffer
 * while still forwarding to the original console.error.
 */
function installConsoleErrorCapture(): void {
  if (originalConsoleError !== null) return; // Already installed
  originalConsoleError = console.error;
  console.error = (...args: unknown[]) => {
    capturedErrors.push(args.map(String).join(' '));
    originalConsoleError!(...args);
  };
}

// --- Tool response helper ---

function textResponse(data: unknown): ToolResponse {
  return {
    content: [{ type: 'text', text: JSON.stringify(data) }],
  };
}

// --- Generic tool definitions ---

function createPageInfoTool() {
  return {
    name: 'hive_get_page_info',
    description: 'Returns the current page title, URL, and active Hive view name',
    inputSchema: { type: 'object', properties: {} },
    execute: async (): Promise<ToolResponse> => {
      const title = document.title;
      const url = window.location.href;
      // Try data-view-name attribute first, then extract from URL path
      let view =
        document.querySelector('[data-view-name]')?.getAttribute('data-view-name') || '';
      if (!view) {
        // Fallback: extract view from pathname (e.g., /projects -> projects)
        const path = window.location.pathname;
        view = path === '/' ? 'dashboards' : path.replace(/^\//, '').split('/')[0];
      }
      return textResponse({ title, url, view });
    },
  };
}

function createConsoleErrorsTool() {
  return {
    name: 'hive_check_console_errors',
    description: 'Returns any JavaScript console errors captured on the current page',
    inputSchema: {
      type: 'object',
      properties: {
        clear: {
          type: 'boolean',
          description: 'Clear captured errors after returning them',
        },
      },
    },
    execute: async (args: Record<string, unknown>): Promise<ToolResponse> => {
      const errors = getConsoleErrors();
      const count = errors.length;
      if (args.clear) {
        clearConsoleErrors();
      }
      return textResponse({ errors, count });
    },
  };
}

function createNavigateToTool() {
  return {
    name: 'hive_navigate_to',
    description: 'Navigates to a Hive view by changing the URL path',
    inputSchema: {
      type: 'object',
      properties: {
        path: {
          type: 'string',
          description: 'URL path to navigate to (e.g., /projects, /agents)',
        },
      },
      required: ['path'],
    },
    execute: async (args: Record<string, unknown>): Promise<ToolResponse> => {
      const path = args.path as string;
      window.location.href = path;
      return textResponse({ success: true, new_url: window.location.href });
    },
  };
}

function createHealthStatusTool() {
  return {
    name: 'hive_get_health_status',
    description: 'Calls the /health/readiness endpoint and returns backend connection status',
    inputSchema: { type: 'object', properties: {} },
    execute: async (): Promise<ToolResponse> => {
      try {
        const response = await fetch('/health/readiness');
        const data = await response.json();
        return textResponse({
          status: response.status,
          backend_connected: data.status === 'ready' || response.ok,
          details: data,
        });
      } catch {
        return textResponse({
          status: 0,
          backend_connected: false,
          error: 'Connection refused',
        });
      }
    },
  };
}

function createListRegisteredToolsTool() {
  return {
    name: 'hive_list_registered_tools',
    description: 'Returns a manifest of all currently registered WebMCP tools on this page',
    inputSchema: { type: 'object', properties: {} },
    execute: async (): Promise<ToolResponse> => {
      const manifest = getManifest();
      return textResponse({ tools: manifest, count: manifest.length });
    },
  };
}

// --- Public API ---

/**
 * Registers all 5 generic verification tools with navigator.modelContext.
 *
 * Call once at app init (e.g., from App.vue setup or a dedicated init module).
 * Silently no-ops in non-Canary browsers or test environments where
 * navigator.modelContext is unavailable.
 */
export function registerGenericTools(): void {
  // Feature detection -- no-op if WebMCP unavailable
  if (typeof navigator === 'undefined' || !('modelContext' in navigator)) {
    return;
  }

  // Install console.error capture before registering the tool
  installConsoleErrorCapture();

  const mc = navigator.modelContext as {
    registerTool(tool: {
      name: string;
      description: string;
      inputSchema?: Record<string, unknown>;
      execute: (args: Record<string, unknown>) => Promise<ToolResponse>;
    }): unknown;
  };

  const tools = [
    createPageInfoTool(),
    createConsoleErrorsTool(),
    createNavigateToTool(),
    createHealthStatusTool(),
    createListRegisteredToolsTool(),
  ];

  for (const tool of tools) {
    mc.registerTool(tool);
    registerInManifest(tool.name, tool.description, 'generic');
  }
}
