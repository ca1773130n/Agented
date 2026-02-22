import { ref, reactive, computed } from 'vue';

export type ChatMode = 'single' | 'all' | 'compound';

export interface BackendResponse {
  backend: string;
  content: string;
  status: 'streaming' | 'complete' | 'error' | 'timeout';
  error?: string;
}

export interface SynthesisState {
  status: 'waiting' | 'streaming' | 'complete' | 'error';
  content: string;
  primaryBackend: string;
  backendsCollected: string[];
  error?: string;
}

export function useAllMode() {
  const chatMode = ref<ChatMode>('single');
  const backendResponses = reactive<Map<string, BackendResponse>>(new Map());
  const synthesisState = ref<SynthesisState | null>(null);
  const isAllModeActive = ref(false);
  // True once the POST response confirms the full list of backends.
  // Prevents premature deactivation when fast backends complete before
  // the POST response arrives (race condition).
  const backendListFinalized = ref(false);

  const activeBackends = computed(() => Array.from(backendResponses.keys()));

  const allBackendsComplete = computed(() => {
    if (backendResponses.size === 0) return false;
    return Array.from(backendResponses.values()).every(
      (r) => r.status !== 'streaming',
    );
  });

  function startAllMode(backends: string[]) {
    backendResponses.clear();
    synthesisState.value = null;
    isAllModeActive.value = true;
    backendListFinalized.value = false;
    for (const backend of backends) {
      backendResponses.set(backend, {
        backend,
        content: '',
        status: 'streaming',
      });
    }
  }

  /**
   * Called after the POST response confirms the full backend list.
   * Adds any missing backends and enables deactivation checks.
   */
  function finalizeBackendList(backends: string[]) {
    for (const backend of backends) {
      if (!backendResponses.has(backend)) {
        backendResponses.set(backend, {
          backend,
          content: '',
          status: 'streaming',
        });
      }
    }
    backendListFinalized.value = true;
    // All backends may have completed before the POST response arrived
    _checkDeactivation();
  }

  /**
   * Deactivate all-mode only when the backend list is finalized AND
   * every backend has finished. Compound mode deactivates via
   * synthesis_complete/error instead.
   */
  function _checkDeactivation() {
    if (chatMode.value === 'compound') return;
    if (backendListFinalized.value && allBackendsComplete.value) {
      isAllModeActive.value = false;
    }
  }

  function handleMultiBackendDelta(data: Record<string, unknown>): boolean {
    const type = data.type as string;
    const backend = data.backend as string;

    if (
      !backend &&
      type !== 'synthesis_start' &&
      type !== 'synthesis_delta' &&
      type !== 'synthesis_complete' &&
      type !== 'synthesis_error' &&
      type !== 'compound_error'
    ) {
      return false; // Not a multi-backend event
    }

    switch (type) {
      case 'content_delta': {
        if (backend) {
          // Auto-add backend if events arrive before startAllMode() (race condition)
          if (!backendResponses.has(backend)) {
            backendResponses.set(backend, {
              backend,
              content: '',
              status: 'streaming',
            });
          }
          const resp = backendResponses.get(backend)!;
          resp.content += (data.text as string) || '';
        }
        return true;
      }
      case 'backend_complete': {
        if (backend) {
          if (!backendResponses.has(backend)) {
            backendResponses.set(backend, {
              backend,
              content: '',
              status: 'complete',
            });
          } else {
            backendResponses.get(backend)!.status = 'complete';
          }
        }
        _checkDeactivation();
        return true;
      }
      case 'backend_timeout': {
        if (backend) {
          if (!backendResponses.has(backend)) {
            backendResponses.set(backend, {
              backend,
              content: '',
              status: 'timeout',
              error: 'Response timed out',
            });
          } else {
            const resp = backendResponses.get(backend)!;
            resp.status = 'timeout';
            resp.error = 'Response timed out';
          }
        }
        _checkDeactivation();
        return true;
      }
      case 'backend_error': {
        if (backend) {
          if (!backendResponses.has(backend)) {
            backendResponses.set(backend, {
              backend,
              content: '',
              status: 'error',
              error: (data.error as string) || 'Unknown error',
            });
          } else {
            const resp = backendResponses.get(backend)!;
            resp.status = 'error';
            resp.error = (data.error as string) || 'Unknown error';
          }
        }
        _checkDeactivation();
        return true;
      }
      case 'synthesis_start': {
        synthesisState.value = {
          status: 'streaming',
          content: '',
          primaryBackend: (data.primary_backend as string) || '',
          backendsCollected: (data.backends_collected as string[]) || [],
        };
        return true;
      }
      case 'synthesis_delta': {
        if (synthesisState.value) {
          synthesisState.value.content += (data.text as string) || '';
        }
        return true;
      }
      case 'synthesis_complete': {
        if (synthesisState.value) {
          synthesisState.value.status = 'complete';
        }
        isAllModeActive.value = false;
        return true;
      }
      case 'synthesis_error':
      case 'compound_error': {
        if (synthesisState.value) {
          synthesisState.value.status = 'error';
          synthesisState.value.error = (data.error as string) || 'Synthesis failed';
        }
        isAllModeActive.value = false;
        return true;
      }
      default:
        return false;
    }
  }

  function reset() {
    backendResponses.clear();
    synthesisState.value = null;
    isAllModeActive.value = false;
  }

  return {
    chatMode,
    backendResponses,
    synthesisState,
    isAllModeActive,
    activeBackends,
    allBackendsComplete,
    startAllMode,
    finalizeBackendList,
    handleMultiBackendDelta,
    reset,
  };
}
