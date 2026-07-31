/**
 * MCP server over the SAME command registry the CLI uses.
 *
 * The point of this file is that there is no second implementation. A human runs
 * `ag project ls`; an agent calls the `ag_call` tool with `{group:"project",
 * verb:"ls"}`; both land in `lib/transport.request()` through the same alias
 * table, the same auth rules, the same service routing. Nothing can drift,
 * because there is nothing to keep in sync.
 *
 * FIVE TOOLS, NOT 754. Exposing one MCP tool per command would put ~754 tool
 * definitions into the model's context on every request — more tokens than most
 * conversations, before any work happens. Instead the surface is: discover
 * (`ag_groups`, `ag_find`), understand (`ag_describe`), act (`ag_call`), and one
 * escape hatch (`ag_request`) so an endpoint that has no alias is still
 * reachable. That is the whole platform in five definitions.
 */

import { request, buildRequest, exitCodeForStatus, errorMessage, type Service } from './transport.ts';
import { resolveProfile } from './config.ts';
import { loadSchema, searchOps, matchOp } from './schema.ts';
import { allAliases, findAlias, groups, verbsFor } from '../aliases.ts';

export interface JsonRpcMessage {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: Record<string, unknown>;
}

export interface JsonRpcResponse {
  jsonrpc: '2.0';
  id: string | number | null;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

const PROTOCOL_VERSION = '2024-11-05';

export const TOOLS = [
  {
    name: 'ag_groups',
    description:
      'List every Agented command group and how many verbs each has. Start here: the platform has 754 commands across 108 groups, all derived from the web UI’s own API client, so anything the website can do appears here.',
    inputSchema: {
      type: 'object',
      properties: {
        group: { type: 'string', description: 'Optional: list the verbs of one group instead of all groups.' },
      },
    },
  },
  {
    name: 'ag_find',
    description:
      'Search all API endpoints by keyword against the LIVE OpenAPI schema of the running server. Use when you know what you want to do but not which command. Terms are ANDed across method, path and summary.',
    inputSchema: {
      type: 'object',
      properties: {
        terms: { type: 'array', items: { type: 'string' }, description: 'Keywords, e.g. ["super-agent","memory"].' },
        limit: { type: 'number', description: 'Max results (default 40).' },
      },
      required: ['terms'],
    },
  },
  {
    name: 'ag_describe',
    description:
      'Explain one command: its HTTP method and path, positional arguments, query params, and REQUEST BODY SHAPE. Call this before ag_call on any write. Most of the backend’s handlers take an untyped body that the server’s schema does not describe, so the body keys here come from the web client — they are the only reliable shape hint.',
    inputSchema: {
      type: 'object',
      properties: {
        group: { type: 'string' },
        verb: { type: 'string' },
      },
      required: ['group', 'verb'],
    },
  },
  {
    name: 'ag_call',
    description:
      'Run an Agented command. Same registry the `ag` CLI uses, so behaviour matches the terminal exactly. Use ag_describe first to learn the body keys. Set dry_run to inspect the request without sending it.',
    inputSchema: {
      type: 'object',
      properties: {
        group: { type: 'string' },
        verb: { type: 'string' },
        args: {
          type: 'array',
          items: { type: 'string' },
          description: 'Positional path arguments, in the order ag_describe lists them.',
        },
        body: { type: 'object', description: 'Request body fields.' },
        query: { type: 'object', description: 'Query-string params.' },
        dry_run: { type: 'boolean', description: 'Build the request and return it without sending.' },
      },
      required: ['group', 'verb'],
    },
  },
  {
    name: 'ag_request',
    description:
      'Escape hatch: call ANY endpoint by method and path, including ones with no alias. Prefer ag_call when a command exists. Paths starting /api/v1/ are routed to the ai-accounts sidecar automatically.',
    inputSchema: {
      type: 'object',
      properties: {
        method: { type: 'string', description: 'GET | POST | PUT | PATCH | DELETE' },
        path: { type: 'string', description: 'Absolute path, e.g. /admin/products' },
        body: { type: 'object' },
        query: { type: 'object' },
        service: { type: 'string', description: 'backend | sidecar — override the automatic routing.' },
        dry_run: { type: 'boolean' },
      },
      required: ['method', 'path'],
    },
  },
];

function ok(id: JsonRpcMessage['id'], result: unknown): JsonRpcResponse {
  return { jsonrpc: '2.0', id: id ?? null, result };
}

function text(value: unknown): unknown {
  const s = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return { content: [{ type: 'text', text: s }] };
}

/** A tool error is reported IN the result with isError, not as a JSON-RPC error —
 *  the model needs to read it and adapt, not have the call fail opaquely. */
function toolError(message: string): unknown {
  return { content: [{ type: 'text', text: message }], isError: true };
}

function fillPath(template: string, args: string[]): string {
  let i = 0;
  return template.replace(/:([A-Za-z0-9_]+)/g, (_m, name: string) => {
    const v = args[i++];
    if (v === undefined) throw new Error(`missing positional argument <${name}> for path ${template}`);
    return encodeURIComponent(v);
  });
}

export async function handleMessage(msg: JsonRpcMessage): Promise<JsonRpcResponse | null> {
  const { method, id } = msg;

  // JSON-RPC: a message with NO id is a notification and must never be answered.
  // Replying (even `{id: null}`) desyncs a client's id matching. This applies to
  // every method, not just the `notifications/*` names — `{"method":"ping"}` with
  // no id was being answered with `{"id":null,...}`.
  const isNotification = id === undefined || id === null;
  if (isNotification && method !== 'initialize') return null;

  if (method === 'initialize') {
    return ok(id, {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: { tools: {} },
      serverInfo: { name: 'ag', version: '0.1.0' },
    });
  }
  // Notifications carry no id and expect no response.
  if (method === 'notifications/initialized' || method === 'initialized') return null;
  if (method === 'ping') return ok(id, {});
  if (method === 'tools/list') return ok(id, { tools: TOOLS });

  if (method === 'tools/call') {
    const params = (msg.params ?? {}) as { name?: string; arguments?: Record<string, unknown> };
    const args = params.arguments ?? {};
    try {
      return ok(id, await callTool(String(params.name ?? ''), args));
    } catch (e) {
      return ok(id, toolError(`ag: ${e instanceof Error ? e.message : String(e)}`));
    }
  }

  if (id === undefined || id === null) return null;
  return { jsonrpc: '2.0', id, error: { code: -32601, message: `method not found: ${method}` } };
}

async function callTool(name: string, a: Record<string, unknown>): Promise<unknown> {
  const profile = resolveProfile({});

  if (name === 'ag_groups') {
    const g = typeof a.group === 'string' ? a.group : undefined;
    if (g) {
      const verbs = verbsFor(g);
      if (!verbs.length) return toolError(`no such group "${g}". Call ag_groups with no argument to list them.`);
      return text(verbs.map((v) => ({ verb: v.verb, method: v.method, path: v.path, help: v.help })));
    }
    return text(groups().map((name) => ({ group: name, verbs: verbsFor(name).length })));
  }

  if (name === 'ag_find') {
    const terms = Array.isArray(a.terms) ? (a.terms as unknown[]).map(String) : [];
    const limit = typeof a.limit === 'number' ? a.limit : 40;
    const ops = await loadSchema(profile);
    const hits = searchOps(ops, terms).slice(0, limit);
    if (!hits.length) return text(`no endpoint matches ${terms.join(' ')} (${ops.length} indexed)`);
    return text(hits.map((o) => ({ method: o.method, path: o.path, summary: o.summary })));
  }

  if (name === 'ag_describe') {
    const alias = findAlias(String(a.group ?? ''), String(a.verb ?? ''));
    if (!alias) return toolError(`no command "${a.group} ${a.verb}". Use ag_groups or ag_find.`);
    let op;
    try {
      op = matchOp(await loadSchema(profile), alias.method, alias.path);
    } catch {
      /* server may be down — the alias itself is still describable */
    }
    return text({
      command: `${alias.group} ${alias.verb}`,
      method: alias.method,
      path: alias.path,
      arguments: alias.params ?? [],
      query: (op?.params ?? []).filter((p) => p.type.startsWith('query:')).map((p) => p.name),
      body_typed: op?.body?.length ? op.body : undefined,
      // The server does not type most bodies; these come from the web client.
      body_keys_from_web_ui: alias.bodyKeys?.length ? alias.bodyKeys : undefined,
      body_shape_unknown: !op?.body?.length && !alias.bodyKeys?.length && op?.bodyUntyped === true,
      help: alias.help,
    });
  }

  if (name === 'ag_call') {
    const alias = findAlias(String(a.group ?? ''), String(a.verb ?? ''));
    if (!alias) return toolError(`no command "${a.group} ${a.verb}". Use ag_groups or ag_find.`);
    const positional = Array.isArray(a.args) ? (a.args as unknown[]).map(String) : [];
    const path = fillPath(alias.path, positional);
    return await send({
      method: alias.method,
      path,
      body: (a.body as Record<string, unknown>) ?? undefined,
      query: (a.query as Record<string, string>) ?? undefined,
      dryRun: a.dry_run === true,
      profile,
    });
  }

  if (name === 'ag_request') {
    const path = String(a.path ?? '');
    if (!path.startsWith('/')) return toolError(`path must start with "/", got ${JSON.stringify(path)}`);
    return await send({
      method: String(a.method ?? 'GET').toUpperCase(),
      path,
      body: (a.body as Record<string, unknown>) ?? undefined,
      query: (a.query as Record<string, string>) ?? undefined,
      service: typeof a.service === 'string' ? (a.service as Service) : undefined,
      dryRun: a.dry_run === true,
      profile,
    });
  }

  return toolError(`unknown tool "${name}"`);
}

async function send(o: {
  method: string;
  path: string;
  body?: Record<string, unknown>;
  query?: Record<string, string>;
  service?: Service;
  dryRun: boolean;
  profile: ReturnType<typeof resolveProfile>;
}): Promise<unknown> {
  const opts = {
    method: o.method,
    path: o.path,
    body: o.body && Object.keys(o.body).length ? o.body : undefined,
    query: o.query,
    profile: o.profile,
    service: o.service,
  };
  if (o.dryRun) {
    const built = buildRequest(opts);
    const headers = { ...built.headers };
    if (headers['X-API-Key']) headers['X-API-Key'] = '<redacted>';
    return text({ dry_run: true, ...built, headers });
  }
  const res = await request(opts);
  const code = exitCodeForStatus(res.status);
  if (code !== 0) {
    return toolError(
      `HTTP ${res.status} ${res.method} ${res.url}\n${errorMessage(res.body)}` +
        (res.requestId ? `\nrequest-id: ${res.requestId}` : ''),
    );
  }
  return text(res.body);
}
