#!/usr/bin/env node
/**
 * ag — drive the entire Agented platform from the terminal.
 *
 * Three layers, deliberately:
 *   1. `ag api <METHOD> <path>`  — the escape hatch. Reaches ALL 834 handlers on
 *      day one, so nothing is ever unreachable while the nice commands catch up.
 *   2. `ag find <terms…>`        — discovery from the LIVE OpenAPI schema, so it
 *      can never skew from the server you are talking to.
 *   3. `ag <group> <verb>`       — ~19 curated aliases for the daily operations.
 *
 * No build step: Node 24 strips the types and runs this file directly.
 */

import { parseArgs, str, bool, num, UsageError, type Args } from '../lib/args.ts';
import { resolveProfile, ConfigError, checkPerms, CONFIG_PATH } from '../lib/config.ts';
import {
  request,
  buildRequest,
  exitCodeForStatus,
  errorMessage,
  TransportError,
  type Service,
} from '../lib/transport.ts';
import { out, note, json, scalar, table, kv, unwrapList, isTTY } from '../lib/output.ts';
import { loadSchema, searchOps, matchOp, type Operation } from '../lib/schema.ts';
import { stream } from '../lib/stream.ts';
import { ALIASES, findAlias, groups, curatedGroups, verbsFor, allAliases, type Alias } from '../aliases.ts';

const VERSION = '0.1.0';

async function main(argv: string[]): Promise<number> {
  const a = parseArgs(argv);
  const cmd = a.positionals[0];

  // `--version` is checked BEFORE the usage fallback: it takes no command, so
  // the `!cmd` branch would otherwise swallow it and print help instead.
  if (bool(a, 'version') || cmd === 'version') {
    scalar(VERSION);
    return 0;
  }
  // Global usage only when there is NO command. With one, `--help` is handled
  // per-command (it needs the schema to explain that operation's body).
  if (!cmd || cmd === 'help') return usage(a);

  const warn = checkPerms();
  if (warn) note(`warning: ${warn}`);

  const profile = resolveProfile({
    profile: str(a, 'profile'),
    host: str(a, 'host'),
    key: str(a, 'key'),
  });

  switch (cmd) {
    case 'ping':
      return await ping(a, profile);
    case 'login':
      return await login(a, profile);
    case 'api':
      return await apiCmd(a, profile);
    case 'groups':
      return listGroups(a);
    case 'find':
    case 'routes':
      return await findCmd(a, profile);
    case 'stream':
      return await streamCmd(a, profile);
    case 'qa': {
      // Local only, and its exit code IS the result (3 = unverified, never a pass).
      const { qaCmd } = await import('../commands/qa.ts');
      return await qaCmd(a);
    }
    case 'mcp': {
      // Serve MCP on stdio. Never returns until stdin closes; stdout is the
      // protocol from here on, so nothing else may write to it.
      const { serve } = await import('./ag-mcp.ts');
      serve();
      return await new Promise<number>(() => {});
    }
    default:
      return await aliasCmd(a, profile, cmd);
  }
}

// ---------------------------------------------------------------------------

function usage(a: Args): number {
  const lines: string[] = [
    'ag — control the Agented platform from the terminal',
    '',
    'USAGE',
    '  ag <command> [args] [--json]',
    '',
    'CORE',
    '  ping                       reach both services and report auth state',
    '  login --key <k>            verify a key and store it (0600)',
    '  find <terms…>              search all endpoints from the live schema',
    '  api <METHOD> <path>        call ANY endpoint  (the escape hatch)',
    '  stream <path>              follow a Server-Sent Events endpoint',
    '  mcp                        serve MCP on stdio (claude mcp add agented -- ag mcp)',
    '  qa [--seed N] [--headed]   random-click QA over the local app (exit 3 = unverified)',
    '  qa replay <runId>          re-run a previous run exactly',
    '',
    'SHORTCUTS',
  ];
  for (const g of curatedGroups()) {
    const verbs = ALIASES.filter((x) => x.group === g).map((x) => x.verb);
    lines.push(`  ${g.padEnd(10)} ${verbs.join(', ')}`);
  }
  lines.push(
    '',
    `EVERYTHING ELSE — ${allAliases().length} commands across ${groups().length} groups,`,
    "derived from the website's own API client, so every UI action has a command:",
    '  ag groups                  list every command group',
    '  ag <group>                 list that group\'s verbs',
  );
  lines.push(
    '',
    'GLOBAL',
    '  --json            machine-readable output (stdout is data, stderr is narration)',
    '  --host URL        override the backend base URL',
    '  --profile NAME    use a named profile',
    '  --service backend|sidecar   force which service a path goes to',
    '  --dry-run         print the request that would be sent, and exit',
    '',
    `config: ${CONFIG_PATH}`,
    '',
    'EXAMPLES',
    '  ag ping',
    '  ag find super-agent session',
    '  ag product new "Agented Core" --desc "harness meta-layer"',
    '  ag project new GRD --repo neo/GetResearchDone --product prod-x',
    '  ag api GET /admin/system/memory/tesserae/projects --json | jq',
    "  ag api POST /admin/projects -f name=Foo -f github_repo=owner/Foo",
  );
  note(lines.join('\n'));
  return bool(a, 'help') || !a.positionals.length ? 0 : 2;
}

async function ping(a: Args, profile: ReturnType<typeof resolveProfile>): Promise<number> {
  const rows: Record<string, unknown>[] = [];
  let worst = 0;

  // The two services expose DIFFERENT health paths — verified against a running
  // pair, not assumed: the Litestar backend serves /health/readiness (there is no
  // bare /health, it 404s), while the ai-accounts sidecar serves /health.
  const HEALTH = { backend: '/health/readiness', sidecar: '/health' } as const;

  for (const svc of ['backend', 'sidecar'] as const) {
    const base = svc === 'backend' ? profile.backend : profile.sidecar;
    try {
      const res = await request({
        method: 'GET',
        path: HEALTH[svc],
        profile,
        service: svc,
        timeoutMs: 5000,
      });
      rows.push({ service: svc, url: base, status: res.status < 400 ? 'ok' : `HTTP ${res.status}` });
      if (res.status >= 400) worst = Math.max(worst, exitCodeForStatus(res.status));
    } catch (e) {
      rows.push({ service: svc, url: base, status: 'unreachable' });
      worst = Math.max(worst, e instanceof TransportError ? e.code : 4);
    }
  }

  // An authenticated probe: distinguishes "server up" from "key actually works".
  let auth = 'no key configured';
  if (profile.key) {
    try {
      const res = await request({ method: 'GET', path: '/admin/system/memory/config', profile, timeoutMs: 5000 });
      auth = res.status < 400 ? 'ok' : res.status === 401 || res.status === 403 ? 'key rejected' : `HTTP ${res.status}`;
      if (res.status === 401 || res.status === 403) worst = Math.max(worst, 3);
    } catch {
      auth = 'unreachable';
    }
  }
  rows.push({ service: 'auth', url: `profile=${profile.name}`, status: auth });

  if (bool(a, 'json')) json(rows);
  else table(rows, ['service', 'url', 'status']);
  return worst;
}

async function login(a: Args, profile: ReturnType<typeof resolveProfile>): Promise<number> {
  const key = str(a, 'key') ?? a.positionals[1];
  if (!key) throw new UsageError('ag login --key <api-key>');
  const res = await request({
    method: 'POST',
    path: '/health/verify-key',
    body: { api_key: key },
    profile: { ...profile, key },
  });
  const ok = res.status < 400 && (res.body as Record<string, unknown>)?.valid !== false;
  if (!ok) {
    note(`key rejected (HTTP ${res.status}): ${errorMessage(res.body)}`);
    return 3;
  }
  const { storeKey } = await import('../lib/config.ts');
  storeKey(profile.name, key);
  note(`key verified and stored in ${CONFIG_PATH} (profile "${profile.name}", mode 600)`);
  return 0;
}

function listGroups(a: Args): number {
  const gs = groups();
  if (bool(a, 'json')) {
    json(gs.map((g) => ({ group: g, verbs: verbsFor(g).map((v) => v.verb) })));
    return 0;
  }
  for (const g of gs) out(`${g.padEnd(26)} ${verbsFor(g).length}`);
  note(`\n${allAliases().length} commands across ${gs.length} groups — ag <group> to list verbs`);
  return 0;
}


/**
 * Explain ONE operation: what it does, and what body/params it takes.
 *
 * This is the answer to "`-f k=v` is guesswork". For a typed handler the schema
 * names every field; for the many handlers with an untyped `data: dict` body
 * OpenAPI carries no properties at all, so the DOCSTRING is the only hint there
 * is — which is exactly why it is printed rather than dropped.
 */
async function describe(
  profile: ReturnType<typeof resolveProfile>,
  method: string,
  path: string,
  title: string,
  alias?: Alias,
): Promise<number> {
  let op: Operation | undefined;
  try {
    op = matchOp(await loadSchema(profile), method, path);
  } catch (e) {
    note(`(schema unavailable: ${(e as Error).message})`);
  }
  note(title);
  note(`  ${method} ${path}`);
  // The alias's own help carries notes the schema cannot know — most importantly
  // that an argument must be pre-transformed (e.g. repoToSlug turns `owner/name`
  // into `owner__name`, and the server only decodes the latter). Printing it here
  // matters because --help is where someone looks for detail; without this the
  // warning appeared only in the terse group listing, which is backwards.
  if (alias?.help) {
    // Generated help begins with "METHOD /path", which was just printed — show
    // only what it adds, so the line is not duplicated.
    const extra = alias.help.replace(`${alias.method} ${alias.path}`, '').trim();
    if (extra) note(`  ${extra}`);
  }
  if (!op) {
    note('\n  No schema entry found — the server may be down, or this path is');
    note('  served by the sidecar (which publishes no OpenAPI).');
    return 0;
  }
  if (op.summary) note(`\n  ${op.summary}`);
  if (op.description && op.description !== op.summary) {
    note(op.description.split('\n').map((l) => '  ' + l).join('\n'));
  }

  const pathParams = op.params.filter((p) => p.type.startsWith('path:'));
  const queryParams = op.params.filter((p) => p.type.startsWith('query:'));

  if (pathParams.length) {
    note('\n  ARGUMENTS (positional, in order)');
    for (const p of pathParams) note(`    <${p.name}>`);
  }
  if (queryParams.length) {
    note('\n  QUERY  -q name=value');
    for (const p of queryParams) {
      note(`    ${p.name.padEnd(24)} ${p.type.replace('query:', '')}${p.required ? '  (required)' : ''}`);
    }
  }
  if (op.body.length) {
    note('\n  BODY  -f name=value');
    for (const f of op.body) {
      const desc = f.description ? `  — ${f.description.split('\n')[0]}` : '';
      note(`    ${f.name.padEnd(24)} ${f.type}${f.required ? '  (required)' : ''}${desc}`);
    }
  } else if (op.bodyUntyped || alias?.bodyKeys?.length) {
    note('\n  BODY  -f name=value');
    if (alias?.bodyKeys?.length) {
      // The server's OpenAPI has no property schema for this handler (251 of 286
      // bodies are untyped, and 0 operations carry a description). These keys are
      // what the WEBSITE actually sends to this endpoint, read off the frontend
      // client — the only real shape hint available. `?` marks optional.
      for (const k of alias.bodyKeys) note(`    ${k}`);
      note('\n    (from the frontend client — the server schema does not type this body)');
    } else {
      note('    shape not in the schema and the website does not call this endpoint,');
      note('    so there is no hint. `--dry-run` shows exactly what would be sent.');
    }
  }
  return 0;
}

async function findCmd(a: Args, profile: ReturnType<typeof resolveProfile>): Promise<number> {
  const ops = await loadSchema(profile, { refresh: bool(a, 'refresh') });
  const hits = searchOps(ops, a.positionals.slice(1));
  if (bool(a, 'json')) {
    json(hits);
    return hits.length ? 0 : 6;
  }
  if (!hits.length) {
    note(`no endpoint matches ${a.positionals.slice(1).join(' ')} (${ops.length} indexed)`);
    return 6;
  }
  const limit = num(a, 'limit', 40);
  for (const o of hits.slice(0, limit)) {
    out(`${o.method.padEnd(6)} ${o.path}${o.summary ? '   ' + o.summary : ''}`);
  }
  if (hits.length > limit) note(`… ${hits.length - limit} more (--limit ${hits.length} to see all)`);
  return 0;
}

async function apiCmd(a: Args, profile: ReturnType<typeof resolveProfile>): Promise<number> {
  const method = (a.positionals[1] ?? '').toUpperCase();
  const path = a.positionals[2];
  if (!method || !path) throw new UsageError('ag api <METHOD> <path> [-f k=v …] [-q k=v …]');
  if (!path.startsWith('/')) throw new UsageError(`path must start with "/", got ${JSON.stringify(path)}`);
  if (bool(a, 'help')) {
    const hint = allAliases().find(
      (x) => x.method === method && x.path.replace(/:[A-Za-z0-9_]+/g, '*') === path.replace(/:[A-Za-z0-9_]+|\{[^}]+\}/g, '*'),
    );
    return await describe(profile, method, path, `ag api ${method} ${path}`, hint);
  }

  const body = Object.keys(a.fields).length ? coerce(a.fields) : undefined;
  const opts = {
    method,
    path,
    query: a.query,
    body,
    profile,
    service: str(a, 'service') as Service | undefined,
    timeoutMs: num(a, 'timeout', 30_000),
  };

  if (bool(a, 'dry-run')) {
    const built = buildRequest(opts);
    json({ ...built, headers: redact(built.headers) });
    return 0;
  }
  return emit(a, await request(opts));
}

async function streamCmd(a: Args, profile: ReturnType<typeof resolveProfile>): Promise<number> {
  const path = a.positionals[1];
  if (!path) throw new UsageError('ag stream <path> [--limit N]');
  const r = await stream({
    method: (str(a, 'method') ?? 'GET').toUpperCase(),
    path,
    profile,
    service: str(a, 'service') as Service | undefined,
    limit: bool(a, 'limit') ? num(a, 'limit', 0) : undefined,
  });
  if (!r.frames) {
    note('stream closed without delivering a frame');
    return 8;
  }
  return 0;
}

async function aliasCmd(a: Args, profile: ReturnType<typeof resolveProfile>, group: string): Promise<number> {
  const verb = a.positionals[1];
  const alias = verb ? findAlias(group, verb) : undefined;
  if (!alias) {
    const known = verbsFor(group);
    if (!known.length) {
      note(`unknown command "${group}". Try: ag help, or ag find ${group}`);
      return 2;
    }
    note(`ag ${group} <verb>`);
    for (const k of known) note(`  ${k.verb.padEnd(14)} ${k.help}`);
    return 2;
  }

  if (bool(a, 'help')) {
    return await describe(profile, alias.method, alias.path, `ag ${alias.group} ${alias.verb}`, alias);
  }

  const { path, used } = fillPath(alias, a.positionals.slice(2));
  const body: Record<string, unknown> = { ...a.fields };
  if (alias.bodyFlags) {
    for (const [flag, key] of Object.entries(alias.bodyFlags)) {
      const v = str(a, flag);
      if (v !== undefined && v !== '') body[key] = v;
    }
  }
  // Positionals left over after the path params are the primary field — so
  // `ag product new "Agented Core"` puts the name in the body without a flag.
  // `params` on an alias documents PATH params only; a body field never appears
  // there (the unit test enforces that every declared param exists in the path).
  const extra = a.positionals.slice(2 + used);
  if (extra.length) {
    // ONLY for curated aliases that declare a body flag mapping. This shortcut
    // exists so `ag product new "Agented Core"` works without a flag — but it was
    // applying to all 700+ GENERATED commands too, where it invented a field the
    // endpoint never asked for: `ag agent run agent-7 oops` sent
    // {"name":"oops"} to an endpoint whose body is {message}. Silently adding a
    // bogus field is worse than refusing, so unknown extras are now an error.
    if (alias.method === 'POST' && alias.bodyFlags && body.name === undefined) {
      body.name = extra.join(' ');
    } else {
      throw new UsageError(
        `ag ${alias.group} ${alias.verb}: unexpected argument${extra.length > 1 ? 's' : ''} ` +
          `${extra.map((e) => JSON.stringify(e)).join(', ')}\n` +
          `  ${alias.method} ${alias.path}\n` +
          `  pass body fields with -f key=value (see: ag ${alias.group} ${alias.verb} --help)`,
      );
    }
  }
  const query: Record<string, string> = { ...a.query };
  if (alias.queryFlags) {
    for (const [flag, key] of Object.entries(alias.queryFlags)) {
      const v = str(a, flag);
      if (v !== undefined && v !== '') query[key] = v;
    }
  }

  const opts = {
    method: alias.method,
    path,
    query,
    body: alias.method === 'GET' || !Object.keys(body).length ? undefined : coerce(body),
    profile,
    timeoutMs: num(a, 'timeout', 30_000),
  };

  if (bool(a, 'dry-run')) {
    const built = buildRequest(opts);
    json({ ...built, headers: redact(built.headers) });
    return 0;
  }
  if (alias.stream) {
    const r = await stream(opts);
    return r.frames ? 0 : 8;
  }
  return emit(a, await request(opts), alias);
}

// ---------------------------------------------------------------------------

function fillPath(alias: Alias, positionals: string[]): { path: string; used: number } {
  let used = 0;
  const path = alias.path.replace(/:([a-zA-Z_]+)/g, (_m, name: string) => {
    const v = positionals[used++];
    if (v === undefined) throw new UsageError(`ag ${alias.group} ${alias.verb} needs <${name}>\n  ${alias.help}`);
    return encodeURIComponent(v);
  });
  return { path, used };
}

/** `-f n=3` / `-f ok=true` should not become the strings "3"/"true". */
function coerce(fields: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(fields)) {
    if (typeof v !== 'string') {
      out[k] = v;
      continue;
    }
    if (v === 'true') out[k] = true;
    else if (v === 'false') out[k] = false;
    else if (v === 'null') out[k] = null;
    else if (/^-?\d+(\.\d+)?$/.test(v)) out[k] = Number(v);
    else if ((v.startsWith('{') && v.endsWith('}')) || (v.startsWith('[') && v.endsWith(']'))) {
      try {
        out[k] = JSON.parse(v);
      } catch {
        out[k] = v;
      }
    } else out[k] = v;
  }
  return out;
}

function redact(h: Record<string, string>): Record<string, string> {
  const c = { ...h };
  if (c['X-API-Key']) c['X-API-Key'] = '<redacted>';
  return c;
}

function emit(a: Args, res: Awaited<ReturnType<typeof request>>, alias?: Alias): number {
  const code = exitCodeForStatus(res.status);
  if (code !== 0) {
    note(`HTTP ${res.status} ${res.method} ${res.url}`);
    note(errorMessage(res.body));
    if (res.requestId) note(`request-id: ${res.requestId}`);
    return code;
  }

  // `render: 'id'` emits the bare id even when piped — that is the entire point
  // of it. Falling through to JSON here broke `ID=$(ag product new X)`, i.e. the
  // one situation the bare id exists for. Only --json overrides it.
  if (alias?.render === 'id' && !bool(a, 'json')) {
    const id = dig(res.body, alias.idPath ?? []);
    if (typeof id === 'string' || typeof id === 'number') {
      scalar(id);
      return 0;
    }
  }
  if (bool(a, 'json') || !isTTY) {
    json(alias?.render === 'table' ? unwrapList(res.body) : res.body);
    return 0;
  }

  switch (alias?.render) {
    case 'table': {
      const rows = unwrapList(res.body);
      if (Array.isArray(rows)) table(rows as Record<string, unknown>[], alias.columns);
      else json(res.body);
      return 0;
    }
    case 'kv': {
      const b = res.body && typeof res.body === 'object' ? (res.body as Record<string, unknown>) : {};
      const inner = Object.keys(b).length === 1 && typeof Object.values(b)[0] === 'object' ? Object.values(b)[0] : b;
      kv(inner as Record<string, unknown>);
      return 0;
    }
    case 'id': {
      const id = dig(res.body, alias.idPath ?? []);
      if (typeof id === 'string' || typeof id === 'number') scalar(id);
      else json(res.body);
      return 0;
    }
    default:
      json(res.body);
      return 0;
  }
}

function dig(body: unknown, path: string[]): unknown {
  let cur: unknown = body;
  for (const k of path) {
    if (!cur || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  // Fall back to a top-level id if the declared path missed.
  if (cur === undefined && body && typeof body === 'object') {
    const o = body as Record<string, unknown>;
    for (const k of ['id', 'session_id', 'job_id']) if (typeof o[k] === 'string') return o[k];
  }
  return cur;
}

// ---------------------------------------------------------------------------

/**
 * Set `exitCode` and RETURN — never `process.exit()`.
 *
 * `process.exit()` terminates before Node flushes a pipe, so any payload past
 * the ~64 KB pipe buffer is silently truncated. That turned
 * `ag api GET /schema/openapi.json --json | jq` into a parse error on a
 * half-written document — and it fails ONLY when piped and only past 64 KB, so
 * it looks like a server problem rather than a CLI one. Letting the event loop
 * drain naturally is the fix.
 */
function fail(message: string, code: number): void {
  note(message);
  process.exitCode = code;
}

main(process.argv.slice(2))
  .then((code) => {
    process.exitCode = code;
  })
  .catch((e) => {
    if (e instanceof UsageError || e instanceof ConfigError) return fail(String(e.message), 2);
    if (e instanceof TransportError) return fail(String(e.message), e.code);
    return fail(`ag: ${e instanceof Error ? e.message : String(e)}`, 1);
  });
