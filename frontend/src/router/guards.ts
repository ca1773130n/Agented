import type { Router } from 'vue-router';
import {
  teamApi,
  agentApi,
  projectApi,
  productApi,
  pluginApi,
  userSkillsApi,
  triggerApi,
  backendApi,
  auditApi,
  superAgentApi,
  workflowApi,
  mcpServerApi,
} from '../services/api';

/**
 * Map entity param names to lightweight existence check functions.
 * Each function calls the existing .get() API method which returns
 * the entity or throws on 404/error.
 */
const entityValidators: Record<string, (id: string) => Promise<boolean>> = {
  teamId: async (id) => {
    try { await teamApi.get(id); return true; } catch { return false; }
  },
  agentId: async (id) => {
    try { await agentApi.get(id); return true; } catch { return false; }
  },
  projectId: async (id) => {
    try { await projectApi.get(id); return true; } catch { return false; }
  },
  productId: async (id) => {
    try { await productApi.get(id); return true; } catch { return false; }
  },
  pluginId: async (id) => {
    try { await pluginApi.get(id); return true; } catch { return false; }
  },
  skillId: async (id) => {
    try { await userSkillsApi.get(Number(id)); return true; } catch { return false; }
  },
  triggerId: async (id) => {
    try { await triggerApi.get(id); return true; } catch { return false; }
  },
  backendId: async (id) => {
    try { await backendApi.get(id); return true; } catch { return false; }
  },
  auditId: async (id) => {
    try { await auditApi.getDetail(id); return true; } catch { return false; }
  },
  superAgentId: async (id) => {
    try { await superAgentApi.get(id); return true; } catch { return false; }
  },
  workflowId: async (id) => {
    try { await workflowApi.get(id); return true; } catch { return false; }
  },
  mcpServerId: async (id) => {
    try { await mcpServerApi.get(id); return true; } catch { return false; }
  },
};

/**
 * Cache recently validated entity IDs with a 5-minute TTL.
 * Key format: "paramName:entityId" -> timestamp of validation.
 */
const validatedCache = new Map<string, number>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function isCached(key: string): boolean {
  const ts = validatedCache.get(key);
  if (!ts) return false;
  if (Date.now() - ts > CACHE_TTL) {
    validatedCache.delete(key);
    return false;
  }
  return true;
}

/**
 * Clear the entity validation cache.
 * Call this when entities are deleted to force re-validation.
 */
export function clearEntityCache(): void {
  validatedCache.clear();
}

/**
 * Register global navigation guards on the router.
 *
 * The beforeEach guard:
 * 1. Sets document.title based on route meta
 * 2. Validates entity IDs for routes with meta.requiresEntity
 * 3. Redirects to not-found for invalid/missing entity IDs
 * 4. Fails open on network errors (allows navigation)
 */
export function registerGuards(router: Router): void {
  router.beforeEach(async (to) => {
    // Set page title
    const title = to.meta.title as string | undefined;
    if (title) {
      document.title = `Hive - ${title}`;
    } else {
      document.title = 'Hive';
    }

    // Prevent infinite redirect loop: never validate the not-found route itself
    if (to.name === 'not-found') {
      return;
    }

    // Entity validation
    const entityParam = to.meta.requiresEntity as string | undefined;
    if (!entityParam) {
      return;
    }

    const entityId = to.params[entityParam] as string | undefined;
    if (!entityId) {
      return { name: 'not-found' };
    }

    const cacheKey = `${entityParam}:${entityId}`;
    if (isCached(cacheKey)) {
      return;
    }

    const validator = entityValidators[entityParam];
    if (!validator) {
      return;
    }

    try {
      const exists = await validator(entityId);
      if (!exists) {
        return { name: 'not-found' };
      }
      validatedCache.set(cacheKey, Date.now());
    } catch {
      // Fail open on network errors -- let the component handle it
    }
  });
}
