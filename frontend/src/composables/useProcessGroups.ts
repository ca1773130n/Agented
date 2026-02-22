import { ref } from 'vue';

/**
 * Process group types supported in the chat UI.
 */
export type ProcessGroupType = 'tool_call' | 'reasoning' | 'code_execution';

/**
 * A single process group represents a tool call, reasoning block,
 * or code execution section in the chat stream.
 */
export interface ProcessGroup {
  id: string;
  type: ProcessGroupType;
  label: string;
  content: string;
  timestamp: string;
  isExpanded: boolean;
  autoCollapseMs: number;
}

/**
 * Tool call delta event from the state_delta SSE protocol.
 */
export interface ToolCallDelta {
  id: string;
  name?: string;
  arguments?: string;
  type?: ProcessGroupType;
}

/**
 * Composable for managing collapsible process group state.
 * Process groups represent tool calls, reasoning blocks, and code executions
 * that appear in the chat stream during agent interactions.
 */
export function useProcessGroups() {
  const groups = ref<Map<string, ProcessGroup>>(new Map());

  function addGroup(group: Omit<ProcessGroup, 'isExpanded'>) {
    const entry: ProcessGroup = {
      ...group,
      isExpanded: true,
    };
    groups.value.set(group.id, entry);
    // Trigger reactivity by reassigning the Map
    groups.value = new Map(groups.value);
  }

  function removeGroup(id: string) {
    groups.value.delete(id);
    groups.value = new Map(groups.value);
  }

  function toggleGroup(id: string) {
    const group = groups.value.get(id);
    if (group) {
      group.isExpanded = !group.isExpanded;
      groups.value = new Map(groups.value);
    }
  }

  function collapseGroup(id: string) {
    const group = groups.value.get(id);
    if (group) {
      group.isExpanded = false;
      groups.value = new Map(groups.value);
    }
  }

  function expandGroup(id: string) {
    const group = groups.value.get(id);
    if (group) {
      group.isExpanded = true;
      groups.value = new Map(groups.value);
    }
  }

  function updateGroupContent(id: string, content: string) {
    const group = groups.value.get(id);
    if (group) {
      group.content += content;
      groups.value = new Map(groups.value);
    }
  }

  function clearGroups() {
    groups.value = new Map();
  }

  function processToolCallDelta(delta: ToolCallDelta) {
    const existing = groups.value.get(delta.id);
    if (existing) {
      // Append argument fragments to existing group
      if (delta.arguments) {
        existing.content += delta.arguments;
        groups.value = new Map(groups.value);
      }
    } else {
      // Create new group for this tool call
      addGroup({
        id: delta.id,
        type: delta.type || 'tool_call',
        label: delta.name || 'Tool Call',
        content: delta.arguments || '',
        timestamp: new Date().toISOString(),
        autoCollapseMs: (delta.type || 'tool_call') === 'tool_call' ? 4000 : 2000,
      });
    }
  }

  return {
    groups,
    addGroup,
    removeGroup,
    toggleGroup,
    collapseGroup,
    expandGroup,
    updateGroupContent,
    clearGroups,
    processToolCallDelta,
  };
}
