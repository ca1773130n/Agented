/**
 * WebMCP tool type helpers and response shapes.
 *
 * These types provide a simplified, Hive-specific subset of the WebMCP
 * type system for use in verification tool definitions. They align with
 * the W3C WebMCP spec and @mcp-b/global polyfill types.
 */

/** The content item shape returned by tool execute handlers (text-only per CONTEXT.md decision). */
export interface ToolContent {
  type: 'text';
  text: string;
}

/** The full response shape from tool execute handlers (matches W3C WebMCP spec). */
export interface ToolResponse {
  content: ToolContent[];
  isError?: boolean;
}

/** The handle returned by navigator.modelContext.registerTool(). */
export interface WebMcpToolRegistration {
  unregister: () => void;
}

/** The tool definition shape passed to registerTool. */
export interface WebMcpToolDescriptor {
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
  execute: (args: Record<string, unknown>) => Promise<ToolResponse>;
}

/** Shape for the tool registry manifest entries. */
export interface ManifestEntry {
  name: string;
  description: string;
  page: string;
}
