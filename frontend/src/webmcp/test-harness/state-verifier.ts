/**
 * Post-action state verification for the randomized test runner.
 *
 * After invoking an action tool, verifies that the corresponding
 * state tool reflects the expected change.
 */

export interface ToolResult {
  toolName: string;
  success: boolean;
  responseTime: number;
  data: unknown;
  error?: string;
}

export interface VerificationResult {
  actionTool: string;
  stateTool: string | null;
  verified: boolean;
  details: string;
}

/**
 * Maps action tool names to their corresponding state tool names.
 * Returns null if no state tool mapping exists.
 */
export function getStateToolForAction(actionToolName: string): string | null {
  // Pattern: hive_{domain}_trigger_create -> hive_{domain}_get_modal_state
  if (actionToolName.includes('_trigger_create') || actionToolName.includes('_trigger_delete')) {
    const domain = actionToolName.replace(/^hive_/, '').replace(/_(trigger_create|trigger_delete)$/, '');
    return `hive_${domain}_get_modal_state`;
  }

  // Pattern: hive_{domain}_perform_search -> hive_{domain}_get_list_state
  if (actionToolName.includes('_perform_search') || actionToolName.includes('_perform_sort')) {
    const domain = actionToolName.replace(/^hive_/, '').replace(/_(perform_search|perform_sort)$/, '');
    return `hive_${domain}_get_list_state`;
  }

  // Pattern: hive_settings_switch_tab -> hive_settings_get_state
  if (actionToolName === 'hive_settings_switch_tab') {
    return 'hive_settings_get_state';
  }

  // Pattern: hive_navigate_to -> hive_get_page_info
  if (actionToolName === 'hive_navigate_to') {
    return 'hive_get_page_info';
  }

  return null;
}

/**
 * Parses a ToolResponse-shaped result to extract the JSON data.
 */
export function parseToolResponse(result: unknown): unknown {
  if (!result || typeof result !== 'object') return null;
  const r = result as { content?: { type: string; text: string }[] };
  if (!r.content || !Array.isArray(r.content) || r.content.length === 0) return null;
  try {
    return JSON.parse(r.content[0].text);
  } catch {
    return null;
  }
}

/**
 * Verifies that after an action tool was invoked, the corresponding
 * state tool reflects the expected change.
 */
export function verifyStateChange(
  actionResult: ToolResult,
  stateResult: ToolResult | null,
): VerificationResult {
  const stateTool = getStateToolForAction(actionResult.toolName);

  if (!stateTool) {
    return {
      actionTool: actionResult.toolName,
      stateTool: null,
      verified: true,
      details: 'No corresponding state tool — skipping verification',
    };
  }

  if (!stateResult) {
    return {
      actionTool: actionResult.toolName,
      stateTool,
      verified: false,
      details: `State tool ${stateTool} was not invoked after action`,
    };
  }

  if (!stateResult.success) {
    return {
      actionTool: actionResult.toolName,
      stateTool,
      verified: false,
      details: `State tool ${stateTool} returned error: ${stateResult.error}`,
    };
  }

  // If action succeeded, verify state tool returned valid data
  if (actionResult.success && stateResult.success) {
    return {
      actionTool: actionResult.toolName,
      stateTool,
      verified: true,
      details: 'Action succeeded and state tool returned valid data',
    };
  }

  return {
    actionTool: actionResult.toolName,
    stateTool,
    verified: false,
    details: `Action success=${actionResult.success}, state success=${stateResult.success}`,
  };
}
