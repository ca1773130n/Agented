/**
 * Vue 3 composable wrapping navigator.modelContext.registerTool()
 * with lifecycle hooks.
 *
 * Registers a WebMCP tool on mount, deregisters on unmount, and optionally
 * re-registers when reactive dependencies change (stale closure prevention).
 *
 * Feature detection ensures this composable no-ops gracefully when
 * navigator.modelContext is absent (non-Canary browsers).
 *
 * Usage:
 *   useWebMcpTool({
 *     name: 'agented_kanban_get_plan_cards',
 *     description: 'Returns all plan cards on the kanban board',
 *     page: 'ProjectManagement',
 *     execute: async () => ({ content: [{ type: 'text', text: '...' }] }),
 *   });
 */

import { onMounted, onUnmounted, watch, type Ref } from 'vue';
import type { ToolResponse, WebMcpToolRegistration } from '../webmcp/types';
import {
  registerInManifest,
  deregisterFromManifest,
  isRegistered,
} from '../webmcp/tool-registry';

export interface WebMcpToolOptions {
  name: string;
  description: string;
  /** Page/view identifier for manifest tracking (e.g., 'ProjectManagement', 'SchedulingDashboard'). */
  page: string;
  inputSchema?: Record<string, unknown>;
  execute: (args: Record<string, unknown>) => Promise<ToolResponse>;
  /** Optional reactive dependencies. Tool re-registers when these change (stale closure prevention). */
  deps?: Ref[];
}

/**
 * Registers a WebMCP tool with navigator.modelContext on mount and
 * deregisters on unmount. No-ops if WebMCP is unavailable.
 *
 * Returns void -- the composable owns the lifecycle; callers do not
 * manage registrations.
 */
export function useWebMcpTool(options: WebMcpToolOptions): void {
  // Feature detection -- no-op if WebMCP unavailable
  if (typeof navigator === 'undefined' || !('modelContext' in navigator)) {
    return;
  }

  let registration: WebMcpToolRegistration | null = null;

  function register() {
    // Deregister previous if exists
    if (registration) {
      registration.unregister();
      deregisterFromManifest(options.name);
    }

    // Collision detection during development
    if (isRegistered(options.name)) {
      console.warn(
        `[WebMCP] Duplicate tool name "${options.name}" detected. ` +
          'Another component may have registered a tool with the same name.'
      );
    }

    // Register with navigator.modelContext
    // The @mcp-b/global polyfill's registerTool returns a RegistrationHandle
    // but the strict @mcp-b/webmcp-types declares void. We cast to handle both.
    const handle = (navigator.modelContext as {
      registerTool(tool: {
        name: string;
        description: string;
        inputSchema?: Record<string, unknown>;
        execute: (args: Record<string, unknown>) => Promise<ToolResponse>;
      }): WebMcpToolRegistration | void;
    }).registerTool({
      name: options.name,
      description: options.description,
      inputSchema: options.inputSchema ?? { type: 'object', properties: {} },
      execute: options.execute,
    });

    // Store registration handle if returned (polyfill returns it, native may not)
    if (handle && typeof handle === 'object' && 'unregister' in handle) {
      registration = handle as WebMcpToolRegistration;
    } else {
      // Fallback: use unregisterTool by name if no handle returned
      registration = {
        unregister: () => {
          if ('modelContext' in navigator) {
            (navigator.modelContext as { unregisterTool(name: string): void }).unregisterTool(
              options.name
            );
          }
        },
      };
    }

    // Track in manifest for discoverability
    registerInManifest(options.name, options.description, options.page);
  }

  function cleanup() {
    if (registration) {
      registration.unregister();
      registration = null;
    }
    deregisterFromManifest(options.name);
  }

  onMounted(() => {
    register();
  });

  onUnmounted(() => {
    cleanup();
  });

  // Re-register when reactive dependencies change (stale closure prevention)
  if (options.deps && options.deps.length > 0) {
    watch(options.deps, () => {
      register();
    });
  }
}
