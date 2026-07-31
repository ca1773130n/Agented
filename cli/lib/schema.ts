/**
 * OpenAPI index — how `ag` knows about all 834 handlers without hard-coding them.
 *
 * The schema is fetched from the RUNNING SERVER rather than committed, so it can
 * never skew from the deployment you are actually talking to. `/schema` is
 * auth-exempt (`_AUTH_BYPASS_PREFIXES` in middleware.py), so this works before a
 * key exists — which is what makes `ag find` usable on a fresh install.
 *
 * Cached under ~/.cache/ag/ keyed by host, because a 834-operation document is
 * not something to re-download per invocation.
 *
 * NOTE on why there are no generated subcommands: most mutating handlers take an
 * untyped `data: dict` body, so OpenAPI carries no property schema for them.
 * Generating a subcommand per operation would yield hundreds of commands whose
 * only option is `--data '<opaque json>'` — strictly worse than `ag api`, with
 * hundreds more names to learn. The schema is used for DISCOVERY (`ag find`),
 * not for command generation.
 */

import { homedir } from 'node:os';
import { join } from 'node:path';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { request } from './transport.ts';
import type { Resolved } from './config.ts';

export interface Field {
  name: string;
  type: string;
  required: boolean;
  description?: string;
}

export interface Operation {
  method: string;
  path: string;
  summary: string;
  description: string;
  /** Request-body properties, when the handler takes a TYPED body. */
  body: Field[];
  /** True when the handler declares a body but OpenAPI carries no property
   *  schema for it — i.e. an untyped `data: dict`. The description is then the
   *  only hint, which is why it is indexed and shown. */
  bodyUntyped: boolean;
  /** Query + path parameters. */
  params: Field[];
}

const CACHE_DIR = join(homedir(), '.cache', 'ag');
const MAX_AGE_MS = 6 * 60 * 60 * 1000;

function cachePath(host: string): string {
  return join(CACHE_DIR, `schema-${createHash('sha256').update(host).digest('hex').slice(0, 12)}.json`);
}

export async function loadSchema(profile: Resolved, opts: { refresh?: boolean } = {}): Promise<Operation[]> {
  const file = cachePath(profile.backend);
  if (!opts.refresh) {
    try {
      const raw = JSON.parse(readFileSync(file, 'utf8')) as { at: number; ops: Operation[] };
      if (Date.now() - raw.at < MAX_AGE_MS && Array.isArray(raw.ops) && raw.ops.length) return raw.ops;
    } catch {
      /* cold cache */
    }
  }
  const res = await request({ method: 'GET', path: '/schema/openapi.json', profile });
  if (res.status >= 400) {
    throw new Error(`could not fetch the OpenAPI schema (HTTP ${res.status}) from ${res.url}`);
  }
  const ops = indexSchema(res.body);
  try {
    mkdirSync(CACHE_DIR, { recursive: true });
    writeFileSync(file, JSON.stringify({ at: Date.now(), ops }));
  } catch {
    /* cache is an optimisation, never a hard failure */
  }
  return ops;
}

/**
 * Flatten an OpenAPI document into a searchable operation list.
 *
 * `description` is kept deliberately. Litestar populates it from the handler
 * docstring, and for the many handlers with an untyped body that docstring is
 * the ONLY machine-readable hint of what the body should contain — dropping it
 * would leave a caller (human or agent) to guess and get a 400.
 */
export function indexSchema(doc: unknown): Operation[] {
  const ops: Operation[] = [];
  if (!doc || typeof doc !== 'object') return ops;
  const root = doc as Record<string, unknown>;
  const paths = root.paths;
  if (!paths || typeof paths !== 'object') return ops;

  for (const [path, item] of Object.entries(paths as Record<string, unknown>)) {
    if (!item || typeof item !== 'object') continue;
    for (const [method, op] of Object.entries(item as Record<string, unknown>)) {
      if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue;
      const o = (op ?? {}) as Record<string, unknown>;
      const { body, bodyUntyped } = requestFields(o, root);
      ops.push({
        method: method.toUpperCase(),
        path,
        summary: typeof o.summary === 'string' ? o.summary : '',
        description: typeof o.description === 'string' ? o.description : '',
        body,
        bodyUntyped,
        params: paramFields(o, root),
      });
    }
  }
  ops.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
  return ops;
}

/** Follow a local `$ref` (`#/components/schemas/Foo`). */
function deref(node: unknown, root: Record<string, unknown>, seen = new Set<string>()): Record<string, unknown> {
  let cur = (node ?? {}) as Record<string, unknown>;
  let ref = typeof cur.$ref === 'string' ? cur.$ref : null;
  while (ref && !seen.has(ref)) {
    seen.add(ref);
    const parts = ref.replace(/^#\//, '').split('/');
    let target: unknown = root;
    for (const p of parts) {
      if (!target || typeof target !== 'object') return {};
      target = (target as Record<string, unknown>)[p];
    }
    cur = (target ?? {}) as Record<string, unknown>;
    ref = typeof cur.$ref === 'string' ? cur.$ref : null;
  }
  return cur;
}

function typeName(schema: Record<string, unknown>): string {
  if (Array.isArray(schema.oneOf) || Array.isArray(schema.anyOf)) {
    const alts = ((schema.oneOf ?? schema.anyOf) as unknown[])
      .map((s) => (s && typeof s === 'object' ? String((s as Record<string, unknown>).type ?? '?') : '?'))
      .filter((t) => t !== 'null');
    return [...new Set(alts)].join('|') || 'any';
  }
  const t = schema.type;
  if (t === 'array') {
    const items = (schema.items ?? {}) as Record<string, unknown>;
    return `${items.type ?? 'any'}[]`;
  }
  return typeof t === 'string' ? t : 'any';
}

function requestFields(op: Record<string, unknown>, root: Record<string, unknown>): { body: Field[]; bodyUntyped: boolean } {
  const rb = deref(op.requestBody, root);
  const content = (rb.content ?? {}) as Record<string, unknown>;
  const json = (content['application/json'] ?? {}) as Record<string, unknown>;
  if (!Object.keys(rb).length || !Object.keys(json).length) return { body: [], bodyUntyped: false };

  const schema = deref(json.schema, root);
  const props = (schema.properties ?? {}) as Record<string, unknown>;
  const required = new Set((Array.isArray(schema.required) ? schema.required : []) as string[]);

  if (!Object.keys(props).length) {
    // A body is declared but has no properties — the untyped `data: dict` case.
    return { body: [], bodyUntyped: true };
  }
  const body = Object.entries(props).map(([name, raw]) => {
    const s = deref(raw, root);
    return {
      name,
      type: typeName(s),
      required: required.has(name),
      description: typeof s.description === 'string' ? s.description : undefined,
    };
  });
  return { body, bodyUntyped: false };
}

function paramFields(op: Record<string, unknown>, root: Record<string, unknown>): Field[] {
  const list = Array.isArray(op.parameters) ? op.parameters : [];
  return list
    .map((raw) => deref(raw, root))
    .filter((p) => p.in === 'query' || p.in === 'path')
    .map((p) => ({
      name: String(p.name ?? ''),
      type: `${p.in}:${typeName(deref(p.schema, root))}`,
      required: p.required === true,
      description: typeof p.description === 'string' ? p.description : undefined,
    }))
    .filter((p) => p.name);
}

/**
 * Find the operation backing a CLI path template.
 *
 * The CLI writes `:id` (shell-friendly, no quoting) and OpenAPI writes
 * `{id:str}`, so compare structurally: same segment count, and each segment
 * either matches literally or is a placeholder on both sides.
 */
export function matchOp(ops: Operation[], method: string, cliPath: string): Operation | undefined {
  const want = cliPath.split('/');
  const M = method.toUpperCase();
  return ops.find((o) => {
    if (o.method !== M) return false;
    const got = o.path.split('/');
    if (got.length !== want.length) return false;
    return got.every((seg, i) => {
      const w = want[i];
      const segIsParam = seg.startsWith('{');
      const wIsParam = w.startsWith(':');
      return segIsParam && wIsParam ? true : seg === w;
    });
  });
}

/** All terms must match (AND), case-insensitive, across method+path+summary+description. */
export function searchOps(ops: Operation[], terms: string[]): Operation[] {
  if (!terms.length) return ops;
  const needles = terms.map((t) => t.toLowerCase());
  return ops.filter((o) => {
    const hay = `${o.method} ${o.path} ${o.summary} ${o.description}`.toLowerCase();
    return needles.every((n) => hay.includes(n));
  });
}
