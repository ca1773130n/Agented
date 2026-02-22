/**
 * Random tool invocation engine for the WebMCP test harness.
 *
 * Discovers registered tools, selects them using weighted randomization,
 * generates valid random inputs, and tracks invocation results.
 */

import { selectWeightedTool, type ToolWeight } from './tool-weights';
import {
  getStateToolForAction,
  verifyStateChange,
  type ToolResult,
  type VerificationResult,
} from './state-verifier';

export interface RunnerConfig {
  /** Maximum number of tool invocations per run. Default: 100. */
  maxIterations: number;
  /** Delay between invocations in ms. Default: 100. */
  delayMs: number;
  /** Allow destructive actions (trigger_delete). Default: false. */
  allowDestructive: boolean;
  /** Abort after N consecutive errors. Default: 3. */
  maxConsecutiveErrors: number;
  /** Custom weight overrides. */
  weights?: ToolWeight[];
}

export interface RunReport {
  totalInvocations: number;
  successes: number;
  failures: number;
  verifications: VerificationResult[];
  errors: { tool: string; error: string; iteration: number }[];
  abortedEarly: boolean;
  durationMs: number;
  toolCoverage: Map<string, number>;
}

export const DEFAULT_CONFIG: RunnerConfig = {
  maxIterations: 100,
  delayMs: 100,
  allowDestructive: false,
  maxConsecutiveErrors: 3,
};

/**
 * Generates random inputs for a tool based on its inputSchema.
 * Produces minimal valid values to exercise the tool.
 */
export function generateRandomInputs(inputSchema?: Record<string, unknown>): Record<string, unknown> {
  if (!inputSchema) return {};

  const properties = inputSchema.properties as Record<string, { type: string; description?: string }> | undefined;
  if (!properties) return {};

  const args: Record<string, unknown> = {};
  const required = (inputSchema.required as string[]) ?? [];

  for (const [key, schema] of Object.entries(properties)) {
    // Only fill required fields (optional fields left out for simplicity)
    if (!required.includes(key)) continue;

    switch (schema.type) {
      case 'string':
        if (key === 'path') {
          args[key] = '/dashboards';
        } else if (key === 'id') {
          args[key] = 'test-id-001';
        } else if (key === 'query') {
          args[key] = 'test';
        } else if (key === 'tab') {
          args[key] = 'general';
        } else if (key === 'field') {
          args[key] = 'name';
        } else if (key === 'order') {
          args[key] = Math.random() > 0.5 ? 'asc' : 'desc';
        } else {
          args[key] = 'random-test-value';
        }
        break;
      case 'number':
        args[key] = Math.floor(Math.random() * 100);
        break;
      case 'boolean':
        args[key] = Math.random() > 0.5;
        break;
      default:
        args[key] = null;
    }
  }

  return args;
}

/**
 * Invokes a single tool by name using navigator.modelContext tools.
 *
 * In a real browser environment, this would call the tool's execute
 * handler directly. In tests, the tool registry provides the manifest
 * and execute functions are accessed via the mock.
 */
export async function invokeTool(
  toolName: string,
  args: Record<string, unknown>,
  toolMap: Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>,
): Promise<ToolResult> {
  const start = performance.now();
  const tool = toolMap.get(toolName);

  if (!tool) {
    return {
      toolName,
      success: false,
      responseTime: performance.now() - start,
      data: null,
      error: `Tool "${toolName}" not found in registry`,
    };
  }

  try {
    const result = await tool.execute(args);
    return {
      toolName,
      success: true,
      responseTime: performance.now() - start,
      data: result,
    };
  } catch (err) {
    return {
      toolName,
      success: false,
      responseTime: performance.now() - start,
      data: null,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Runs the randomized test harness.
 *
 * 1. Discovers all tools from the provided tool map
 * 2. Weighted-randomly selects a tool
 * 3. Generates random inputs from its schema
 * 4. Invokes the tool
 * 5. After action tools, invokes the corresponding state tool for verification
 * 6. Repeats for maxIterations or until abort threshold
 */
export async function runRandomWalk(
  toolMap: Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>,
  config: Partial<RunnerConfig> = {},
): Promise<RunReport> {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const start = performance.now();

  const report: RunReport = {
    totalInvocations: 0,
    successes: 0,
    failures: 0,
    verifications: [],
    errors: [],
    abortedEarly: false,
    durationMs: 0,
    toolCoverage: new Map(),
  };

  const toolNames = Array.from(toolMap.keys());
  let consecutiveErrors = 0;

  for (let i = 0; i < cfg.maxIterations; i++) {
    // Select a tool
    const selected = selectWeightedTool(toolNames, {
      allowDestructive: cfg.allowDestructive,
      weights: cfg.weights,
    });

    if (!selected) {
      report.abortedEarly = true;
      break;
    }

    // Generate inputs
    const tool = toolMap.get(selected)!;
    const args = generateRandomInputs(tool.inputSchema);

    // Invoke
    const result = await invokeTool(selected, args, toolMap);
    report.totalInvocations++;
    report.toolCoverage.set(selected, (report.toolCoverage.get(selected) ?? 0) + 1);

    if (result.success) {
      report.successes++;
      consecutiveErrors = 0;
    } else {
      report.failures++;
      consecutiveErrors++;
      report.errors.push({ tool: selected, error: result.error ?? 'unknown', iteration: i });
    }

    // Abort on too many consecutive errors
    if (consecutiveErrors >= cfg.maxConsecutiveErrors) {
      report.abortedEarly = true;
      break;
    }

    // After action tools, verify state change
    const stateTool = getStateToolForAction(selected);
    if (stateTool && toolMap.has(stateTool)) {
      const stateResult = await invokeTool(stateTool, {}, toolMap);
      report.totalInvocations++;
      report.toolCoverage.set(stateTool, (report.toolCoverage.get(stateTool) ?? 0) + 1);
      if (stateResult.success) report.successes++;
      else report.failures++;

      const verification = verifyStateChange(result, stateResult);
      report.verifications.push(verification);
    }

    // Delay between invocations
    if (cfg.delayMs > 0 && i < cfg.maxIterations - 1) {
      await sleep(cfg.delayMs);
    }
  }

  report.durationMs = performance.now() - start;
  return report;
}
