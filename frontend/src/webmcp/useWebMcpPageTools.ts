/**
 * Factory composable for registering standardized WebMCP tools on list pages.
 *
 * Generates `get_list_state`, `get_modal_state`, `trigger_create`, and
 * `trigger_delete` tools from a concise descriptor, reducing per-view
 * boilerplate from ~30 lines to ~10 lines.
 *
 * Usage:
 *   useWebMcpPageTools({
 *     page: 'TeamsPage',
 *     domain: 'teams',
 *     stateGetter: () => ({ items: teams.value, ... }),
 *     modalGetter: () => ({ showCreateModal: showCreateModal.value, ... }),
 *     modalActions: {
 *       openCreate: () => { showCreateModal.value = true; },
 *       openDelete: (id) => { ... },
 *     },
 *     deps: [teams, searchQuery],
 *   });
 */

import { type Ref } from 'vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import type { ToolResponse } from './types';

export interface ListState {
  items: unknown[];
  itemCount: number;
  isLoading: boolean;
  error: string | null;
  searchQuery?: string;
  sortField?: string;
  sortOrder?: string;
  currentPage?: number;
  pageSize?: number;
  totalCount?: number;
  [key: string]: unknown;
}

export interface ModalState {
  showCreateModal: boolean;
  showDeleteConfirm: boolean;
  formValues?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ModalActions {
  openCreate: () => void;
  openDelete: (id: string) => void;
}

export interface WebMcpPageToolsOptions {
  /** Component/page name for manifest tracking. */
  page: string;
  /** Domain slug used in tool names (e.g., 'teams', 'agents'). */
  domain: string;
  /** Returns current list state snapshot. */
  stateGetter: () => ListState;
  /** Returns current modal/form state snapshot. */
  modalGetter?: () => ModalState;
  /** Callbacks to trigger modal open actions. */
  modalActions?: ModalActions;
  /** Reactive dependencies for stale-closure prevention. */
  deps?: Ref[];
}

function textResponse(data: unknown): ToolResponse {
  return {
    content: [{ type: 'text', text: JSON.stringify(data) }],
  };
}

/**
 * Registers standardized WebMCP tools for a list page:
 * - `hive_{domain}_get_list_state`  — Current list state
 * - `hive_{domain}_get_modal_state` — Modal/form state (if modalGetter provided)
 * - `hive_{domain}_trigger_create`  — Open create modal (if modalActions provided)
 * - `hive_{domain}_trigger_delete`  — Open delete confirm (if modalActions provided)
 */
export function useWebMcpPageTools(options: WebMcpPageToolsOptions): void {
  const { page, domain, stateGetter, modalGetter, modalActions, deps } = options;

  // 1. List state tool
  useWebMcpTool({
    name: `hive_${domain}_get_list_state`,
    description: `Returns the current list state of the ${page} including items, search, sort, and pagination`,
    page,
    execute: async () => textResponse(stateGetter()),
    deps,
  });

  // 2. Modal state tool
  if (modalGetter) {
    useWebMcpTool({
      name: `hive_${domain}_get_modal_state`,
      description: `Returns modal and form state for the ${page} (create/delete dialogs)`,
      page,
      execute: async () => textResponse(modalGetter()),
      deps,
    });
  }

  // 3. Trigger create action
  if (modalActions) {
    useWebMcpTool({
      name: `hive_${domain}_trigger_create`,
      description: `Opens the create modal on the ${page}`,
      page,
      execute: async () => {
        modalActions.openCreate();
        return textResponse({ success: true, action: 'create_modal_opened' });
      },
    });

    // 4. Trigger delete action
    useWebMcpTool({
      name: `hive_${domain}_trigger_delete`,
      description: `Opens the delete confirmation dialog for an entity on the ${page}`,
      page,
      inputSchema: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'The entity ID to delete' },
        },
        required: ['id'],
      },
      execute: async (args: Record<string, unknown>) => {
        const id = args.id as string;
        if (!id) {
          return { content: [{ type: 'text', text: JSON.stringify({ success: false, error: 'id is required' }) }], isError: true };
        }
        modalActions.openDelete(id);
        return textResponse({ success: true, action: 'delete_confirm_opened', id });
      },
    });
  }
}
