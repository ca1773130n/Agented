/**
 * The curated verb table — the ONLY file here that can go stale.
 *
 * Everything else in this CLI is endpoint-agnostic: `ag api` reaches all 834
 * handlers and `ag find` discovers them from the live schema. These aliases
 * exist purely so the operations people actually run every day are short.
 *
 * Every `path` below was read out of the live router
 * (`create_app().routes`), not guessed. `backend/tests/test_cli_contract.py`
 * asserts each one still resolves, so a route rename fails the backend test
 * suite instead of failing in someone's terminal.
 *
 * Deliberately capped: if a verb is not something you'd run weekly, it belongs
 * behind `ag api`, not here.
 */

export interface Alias {
  /** `ag <group> <verb>` */
  group: string;
  verb: string;
  method: string;
  /** `:name` segments are filled from positionals, in order. */
  path: string;
  /** Names for the positional path params, in order — used for usage errors. */
  params?: string[];
  /** Body keys taken from named flags: flag -> body key. */
  bodyFlags?: Record<string, string>;
  /** Query keys taken from named flags: flag -> query key. */
  queryFlags?: Record<string, string>;
  /** How to render a successful response on a TTY. */
  render?: 'table' | 'kv' | 'id' | 'raw';
  /** Columns for `render: table`. */
  columns?: string[];
  /** For `render: id` — which field of the response is the bare id. */
  idPath?: string[];
  /** Body keys the WEBSITE sends to this endpoint — the only shape hint for
   *  the 251 handlers whose OpenAPI body is untyped. */
  bodyKeys?: string[];
  /** This endpoint is Server-Sent Events. */
  stream?: boolean;
  help: string;
}

export const ALIASES: Alias[] = [
  // ---- products -----------------------------------------------------------
  {
    group: 'product',
    verb: 'ls',
    method: 'GET',
    path: '/admin/products',
    render: 'table',
    columns: ['id', 'name', 'status'],
    queryFlags: { limit: 'limit', offset: 'offset' },
    help: 'List products',
  },
  {
    group: 'product',
    verb: 'new',
    method: 'POST',
    path: '/admin/products',
    bodyFlags: { desc: 'description', status: 'status' },
    render: 'id',
    idPath: ['product', 'id'],
    help: 'Create a product:  ag product new "Name" --desc "..."',
  },
  {
    group: 'product',
    verb: 'get',
    method: 'GET',
    path: '/admin/products/:product_id',
    params: ['product_id'],
    render: 'kv',
    help: 'Show one product',
  },

  // ---- projects -----------------------------------------------------------
  {
    group: 'project',
    verb: 'ls',
    method: 'GET',
    path: '/admin/projects',
    render: 'table',
    columns: ['id', 'name', 'status', 'local_path'],
    queryFlags: { product: 'product_id', limit: 'limit' },
    help: 'List projects',
  },
  {
    group: 'project',
    verb: 'new',
    method: 'POST',
    path: '/admin/projects',
    bodyFlags: {
      repo: 'github_repo',
      product: 'product_id',
      desc: 'description',
      path: 'local_path',
      team: 'owner_team_id',
    },
    render: 'id',
    idPath: ['project', 'id'],
    help: 'Create a project (clones --repo into the workspace root):  ag project new Foo --repo owner/Foo --product prod-x',
  },
  {
    group: 'project',
    verb: 'get',
    method: 'GET',
    path: '/admin/projects/:project_id',
    params: ['project_id'],
    render: 'kv',
    help: 'Show one project',
  },
  {
    group: 'project',
    verb: 'clone-status',
    method: 'GET',
    path: '/admin/projects/:project_id/clone-status',
    params: ['project_id'],
    render: 'kv',
    help: 'Clone progress for a project created with --repo',
  },
  {
    group: 'project',
    verb: 'sessions',
    method: 'GET',
    path: '/admin/projects/:project_id/sessions',
    params: ['project_id'],
    render: 'table',
    help: 'Sessions recorded against a project',
  },

  // ---- super-agents -------------------------------------------------------
  {
    group: 'sa',
    verb: 'ls',
    method: 'GET',
    path: '/admin/super-agents',
    render: 'table',
    columns: ['id', 'name', 'backend_type'],
    help: 'List super-agents',
  },
  {
    group: 'sa',
    verb: 'get',
    method: 'GET',
    path: '/admin/super-agents/:super_agent_id',
    params: ['super_agent_id'],
    render: 'kv',
    help: 'Show one super-agent',
  },
  {
    group: 'sa',
    verb: 'sessions',
    method: 'GET',
    path: '/admin/super-agents/:super_agent_id/sessions',
    params: ['super_agent_id'],
    render: 'table',
    columns: ['id', 'project_id', 'status', 'session_type'],
    help: 'List a super-agent’s sessions',
  },
  {
    group: 'sa',
    verb: 'session-new',
    method: 'POST',
    path: '/admin/super-agents/:super_agent_id/sessions',
    params: ['super_agent_id'],
    bodyFlags: { project: 'project_id', title: 'title', type: 'session_type' },
    render: 'id',
    idPath: ['session_id'],
    help: 'Start a session. PASS --project: without it the session has no project_id and is invisible to the memory loop.',
  },
  {
    group: 'sa',
    verb: 'memory',
    method: 'GET',
    path: '/admin/super-agents/:super_agent_id/memory',
    params: ['super_agent_id'],
    queryFlags: { project: 'project_id' },
    render: 'raw',
    help: 'Read a super-agent’s distilled L1 runbook',
  },
  {
    group: 'sa',
    verb: 'distill',
    method: 'POST',
    path: '/admin/super-agents/:super_agent_id/memory/distill',
    params: ['super_agent_id'],
    queryFlags: { project: 'project_id' },
    render: 'raw',
    help: 'Rebuild L1 runbooks for a project’s super-agents (spends LLM calls)',
  },

  // ---- memory / tesserae --------------------------------------------------
  {
    group: 'mem',
    verb: 'status',
    method: 'GET',
    path: '/admin/system/memory',
    render: 'raw',
    help: 'Memory-system status (Tesserae CLI, version, project count)',
  },
  {
    group: 'mem',
    verb: 'config',
    method: 'GET',
    path: '/admin/system/memory/config',
    render: 'raw',
    help: 'Memory config, including consolidation daemon state',
  },
  {
    group: 'mem',
    verb: 'projects',
    method: 'GET',
    path: '/admin/system/memory/tesserae/projects',
    render: 'table',
    columns: ['project_id', 'project_name', 'enabled', 'distill_enabled'],
    help: 'Per-project Tesserae state (incl. last_auto_distill)',
  },

  // ---- GRD steering (added by this repo’s own settings work) -----------
  {
    group: 'grd',
    verb: 'steering',
    method: 'GET',
    path: '/admin/system/grd/steering/projects',
    render: 'table',
    columns: ['project_id', 'project_name', 'configured', 'autonomous_mode', 'interactive_fallback'],
    help: 'GRD 0.5.0 research-steering settings per project',
  },
];

import { GENERATED } from './aliases.generated.ts';

/**
 * Every command the CLI knows: the curated ones first, then everything derived
 * from the website's own API client.
 *
 * Order matters — a hand-written alias SHADOWS a generated one with the same
 * group+verb, so an operation can be given better ergonomics (positional args,
 * a nicer table, an `id` result) without losing the guarantee that the generated
 * layer covers the whole surface.
 */
export function allAliases(): Alias[] {
  return [...ALIASES, ...GENERATED];
}

export function findAlias(group: string, verb: string): Alias | undefined {
  return ALIASES.find((a) => a.group === group && a.verb === verb)
    ?? GENERATED.find((a) => a.group === group && a.verb === verb);
}

export function groups(): string[] {
  return [...new Set(allAliases().map((a) => a.group))].sort();
}

/** Curated groups only — what `ag help` shows before the long tail. */
export function curatedGroups(): string[] {
  return [...new Set(ALIASES.map((a) => a.group))];
}

export function verbsFor(group: string): Alias[] {
  const curated = ALIASES.filter((a) => a.group === group);
  const gen = GENERATED.filter((a) => a.group === group && !curated.some((c) => c.verb === a.verb));
  return [...curated, ...gen];
}
