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
  healthApi,
} from '../services/api';

/** Auth state — checked once per page load, reset on key generation */
let authChecked = false;
let needsSetup = false;

/**
 * Factory that creates an entity validator function from a fetch function.
 * The returned validator calls fetchFn(id) and returns true if it resolves,
 * false if it throws (404 or network error).
 */
function makeEntityValidator(fetchFn: (id: string) => Promise<unknown>): (id: string) => Promise<boolean> {
  return async (id: string) => {
    try {
      await fetchFn(id);
      return true;
    } catch (err) {
      console.warn(`[Router Guard] Entity validation failed for id="${id}":`, err);
      return false;
    }
  };
}

/**
 * Map entity param names to lightweight existence check functions.
 * Each function calls the existing .get() API method which returns
 * the entity or throws on 404/error.
 */
const entityValidators: Record<string, (id: string) => Promise<boolean>> = {
  teamId:       makeEntityValidator(teamApi.get.bind(teamApi)),
  agentId:      makeEntityValidator(agentApi.get.bind(agentApi)),
  projectId:    makeEntityValidator(projectApi.get.bind(projectApi)),
  productId:    makeEntityValidator(productApi.get.bind(productApi)),
  pluginId:     makeEntityValidator(pluginApi.get.bind(pluginApi)),
  skillId:      makeEntityValidator((id: string) => userSkillsApi.get(Number(id))),
  triggerId:    makeEntityValidator(triggerApi.get.bind(triggerApi)),
  backendId:    makeEntityValidator(backendApi.get.bind(backendApi)),
  auditId:      makeEntityValidator(auditApi.getDetail.bind(auditApi)),
  superAgentId: makeEntityValidator(superAgentApi.get.bind(superAgentApi)),
  workflowId:   makeEntityValidator(workflowApi.get.bind(workflowApi)),
  mcpServerId:  makeEntityValidator(mcpServerApi.get.bind(mcpServerApi)),
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

/** Reset auth guard state (call after key generation or login) */
export function resetAuthGuard(): void {
  authChecked = false;
  needsSetup = false;
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
      document.title = `Agented - ${title}`;
    } else {
      document.title = 'Agented';
    }

    // Auth guard: redirect to /welcome if not authenticated
    // Skip for the welcome page itself and not-found
    if (to.name !== 'welcome' && to.name !== 'not-found') {
      if (!authChecked) {
        try {
          const status = await healthApi.authStatus();
          needsSetup = !!status.needs_setup;
          authChecked = true;
        } catch {
          authChecked = true;
        }
      }
      if (needsSetup) {
        return { name: 'welcome' };
      }
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
    } catch (err) {
      // Fail open on network errors -- let the component handle it
      console.warn(`[Router Guard] Network error validating ${entityParam}="${entityId}", failing open:`, err);
    }
  });
}
