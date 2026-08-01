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
  /**
   * Resolve each positional by NAME before filling the path, so
   * `ag mem compile GetResearchDone` works and nobody has to know `proj-xe3qj4`.
   * Index-aligned with `params`; a null entry means "pass through untouched".
   */
  resolve?: (('project' | 'product' | 'super-agent' | 'agent') | null)[];
  /**
   * This endpoint returns a job_id. `--wait` polls it and makes the JOB's
   * outcome the command's exit code — dispatching successfully is not the same
   * as the operation succeeding.
   */
  job?: boolean;
  /** Body keys taken from named flags: flag -> body key. */
  bodyFlags?: Record<string, string>;
  /**
   * Body fields sent when the caller supplies nothing — overridden by `-f` and by
   * any `bodyFlags` value. For a verb whose NAME is the intent (`mem enable`),
   * where the handler reads that intent from the body and rejects an empty one.
   */
  bodyDefaults?: Record<string, unknown>;
  /** Query keys taken from named flags: flag -> query key. */
  queryFlags?: Record<string, string>;
  /**
   * Resolve a FLAG's value by name, the way `resolve` does for positionals:
   * flag -> what kind of thing it names.
   *
   * Without this, `resolve` covered only positionals, so
   * `ag mem distill Apoc --project GetResearchDone` sent
   * `?project_id=GetResearchDone` and the endpoint 404'd — the one command where
   * the project arrives as a flag rather than a path segment. A name works in
   * one argument position and not the other is exactly the inconsistency this
   * CLI exists to remove.
   */
  resolveFlags?: Record<string, 'project' | 'product' | 'super-agent' | 'agent'>;
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
  // ---- product ------------------------------------------------------------
  { group: 'product', verb: 'ls', method: 'GET', path: '/admin/products',
    render: 'table', columns: ['id', 'name', 'status'],
    queryFlags: { limit: 'limit', offset: 'offset' }, help: 'List products' },
  { group: 'product', verb: 'show', method: 'GET', path: '/admin/products/:product',
    params: ['product'], resolve: ['product'], render: 'kv', help: 'Show one product (by name or id)' },
  { group: 'product', verb: 'new', method: 'POST', path: '/admin/products',
    bodyFlags: { desc: 'description', status: 'status' }, render: 'id', idPath: ['product', 'id'],
    help: 'ag product new "Agented Core" --desc "…"' },

  // ---- project ------------------------------------------------------------
  { group: 'project', verb: 'ls', method: 'GET', path: '/admin/projects',
    render: 'table', columns: ['id', 'name', 'status', 'clone_status', 'local_path'],
    queryFlags: { limit: 'limit', offset: 'offset' }, help: 'List projects' },
  { group: 'project', verb: 'show', method: 'GET', path: '/admin/projects/:project',
    params: ['project'], resolve: ['project'], render: 'kv', help: 'Show one project (by name or id)' },
  { group: 'project', verb: 'new', method: 'POST', path: '/admin/projects',
    bodyFlags: { repo: 'github_repo', product: 'product_id', desc: 'description', path: 'local_path', team: 'owner_team_id' },
    render: 'id', idPath: ['project', 'id'],
    help: 'ag project new GRD --repo owner/GRD --product "Dev Tools"  (clones into the workspace root)' },
  { group: 'project', verb: 'clone-status', method: 'GET', path: '/admin/projects/:project/clone-status',
    params: ['project'], resolve: ['project'], render: 'kv', help: 'Clone progress for a project created with --repo' },
  { group: 'project', verb: 'sessions', method: 'GET', path: '/admin/projects/:project/sessions',
    params: ['project'], resolve: ['project'], render: 'table', help: 'Sessions recorded against a project' },

  // ---- agent --------------------------------------------------------------
  { group: 'agent', verb: 'ls', method: 'GET', path: '/admin/agents',
    render: 'table', columns: ['id', 'name', 'status'], help: 'List agents' },
  { group: 'agent', verb: 'show', method: 'GET', path: '/admin/agents/:agent',
    params: ['agent'], resolve: ['agent'], render: 'kv', help: 'Show one agent (by name or id)' },
  { group: 'agent', verb: 'run', method: 'POST', path: '/admin/agents/:agent/run',
    params: ['agent'], resolve: ['agent'], bodyFlags: { message: 'message' }, render: 'raw',
    help: 'ag agent run Apoc --message "…"' },

  // ---- sa (super-agents) --------------------------------------------------
  { group: 'sa', verb: 'ls', method: 'GET', path: '/admin/super-agents',
    render: 'table', columns: ['id', 'name', 'backend_type'], help: 'List super-agents' },
  { group: 'sa', verb: 'show', method: 'GET', path: '/admin/super-agents/:sa',
    params: ['sa'], resolve: ['super-agent'], render: 'kv', help: 'Show one super-agent (by name or id)' },
  { group: 'sa', verb: 'sessions', method: 'GET', path: '/admin/super-agents/:sa/sessions',
    params: ['sa'], resolve: ['super-agent'], render: 'table',
    columns: ['id', 'project_id', 'status', 'session_type'], help: 'List a super-agent’s sessions' },
  { group: 'sa', verb: 'start', method: 'POST', path: '/admin/super-agents/:sa/sessions',
    params: ['sa'], resolve: ['super-agent'], bodyFlags: { project: 'project_id', title: 'title', type: 'session_type' },
    render: 'id', idPath: ['session_id'],
    help: 'ag sa start Apoc --project GRD   (WITHOUT --project the session is invisible to the memory loop)' },
  { group: 'sa', verb: 'end', method: 'POST', path: '/admin/super-agents/:sa/sessions/:session/end',
    params: ['sa', 'session'], resolve: ['super-agent', null], render: 'raw',
    help: 'End a session — only completed sessions are exported to memory' },

  // ---- mem (Tesserae memory) ----------------------------------------------
  { group: 'mem', verb: 'ls', method: 'GET', path: '/admin/system/memory/tesserae/projects',
    render: 'table', columns: ['project_name', 'enabled', 'distill_enabled', 'session_count'],
    help: 'Per-project memory state' },
  { group: 'mem', verb: 'status', method: 'GET', path: '/admin/system/memory',
    render: 'raw', help: 'Memory-system status (Tesserae CLI, version, project count)' },
  { group: 'mem', verb: 'enable', method: 'POST', path: '/admin/system/memory/tesserae/projects/:project',
    params: ['project'], resolve: ['project'], bodyFlags: { enabled: 'enabled' },
    bodyDefaults: { enabled: true }, render: 'raw',
    help: 'ag mem enable GRD   (resolves the workspace root; --enabled false to turn off)' },
  { group: 'mem', verb: 'distill-toggle', method: 'POST', path: '/admin/system/memory/tesserae/projects/:project/distill',
    params: ['project'], resolve: ['project'], bodyFlags: { enabled: 'enabled' }, render: 'raw',
    help: 'ag mem distill-toggle GRD --enabled true   (authorises LLM spend for this project)' },
  { group: 'mem', verb: 'compile', method: 'POST', path: '/admin/system/memory/tesserae/projects/:project/compile',
    params: ['project'], resolve: ['project'], job: true,
    queryFlags: { 'retry-fallbacks': 'retry_fallbacks', provider: 'provider', model: 'model' },
    render: 'raw',
    help: 'ag mem compile GRD --wait [--provider codex --model X]   (LLM spend; minutes)' },
  { group: 'mem', verb: 'ingest', method: 'POST', path: '/admin/system/memory/tesserae/projects/:project/ingest',
    params: ['project'], resolve: ['project'], render: 'raw',
    help: 'ag mem ingest GRD   (synchronous — returns the result, not a job)' },
  { group: 'mem', verb: 'sessions-import', method: 'POST', path: '/admin/system/memory/tesserae/projects/:project/refresh',
    params: ['project'], resolve: ['project'], render: 'raw',
    help: 'ag mem sessions-import GRD   (re-export sessions into the graph; distill needs this)' },
  { group: 'mem', verb: 'distill', method: 'POST', path: '/admin/super-agents/:sa/memory/distill',
    params: ['sa'], resolve: ['super-agent'], queryFlags: { project: 'project_id' },
    resolveFlags: { project: 'project' }, render: 'raw',
    help: 'ag mem distill Apoc --project GRD   (rebuild L1 runbooks; UNPRICED and uncapped)' },
  { group: 'mem', verb: 'read', method: 'GET', path: '/admin/super-agents/:sa/memory',
    params: ['sa'], resolve: ['super-agent'], queryFlags: { project: 'project_id' },
    resolveFlags: { project: 'project' }, render: 'raw',
    help: 'ag mem read Apoc --project GRD   (that agent’s distilled runbook)' },
  { group: 'mem', verb: 'job', method: 'GET', path: '/admin/system/memory/tesserae/jobs/:job',
    params: ['job'], render: 'raw', help: 'Status of one async memory job' },

  // ---- grd ----------------------------------------------------------------
  { group: 'grd', verb: 'steering', method: 'GET', path: '/admin/system/grd/steering/projects',
    render: 'table', columns: ['project_name', 'configured', 'autonomous_mode', 'interactive_fallback'],
    help: 'GRD 0.5.0 research-steering settings per project' },
  { group: 'grd', verb: 'steer', method: 'POST', path: '/admin/system/grd/steering/projects/:project',
    params: ['project'], resolve: ['project'],
    bodyFlags: { autonomous: 'autonomous_mode', fallback: 'interactive_fallback' }, render: 'raw',
    help: 'ag grd steer GRD --autonomous false --fallback panel' },

  // ---- backend / auth -----------------------------------------------------
  { group: 'backend', verb: 'check', method: 'POST', path: '/admin/backends/:backend_id/check',
    params: ['backend_id'], render: 'raw', help: 'Probe whether a backend CLI is installed on disk' },
  { group: 'auth', verb: 'session-events', method: 'GET', path: '/admin/auth/session-events',
    queryFlags: { user: 'user_id', type: 'event_type', limit: 'limit', offset: 'offset' },
    render: 'raw', help: 'Recent auth session events (login/logout/revoke)' },
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

/**
 * Body-shape hint for an alias, falling back to its GENERATED twin.
 *
 * A curated alias shadows the generated one to gain ergonomics (named flags,
 * resolution, --wait). It must not LOSE what the generated entry knew: the body
 * keys extracted from the web client are the only shape hint for the handlers
 * the server leaves untyped, so curation would otherwise make `--help` and
 * `ag_describe` less useful for exactly the commands people use most.
 */
export function bodyKeysFor(alias: Alias): string[] | undefined {
  if (alias.bodyKeys?.length) return alias.bodyKeys;
  const shape = (p: string) => p.replace(/:[A-Za-z0-9_]+/g, '*');
  const twin = GENERATED.find((g) => g.method === alias.method && shape(g.path) === shape(alias.path));
  return twin?.bodyKeys?.length ? twin.bodyKeys : undefined;
}

export function verbsFor(group: string): Alias[] {
  const curated = ALIASES.filter((a) => a.group === group);
  const gen = GENERATED.filter((a) => a.group === group && !curated.some((c) => c.verb === a.verb));
  return [...curated, ...gen];
}
