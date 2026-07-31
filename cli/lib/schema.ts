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

export interface Operation {
  method: string;
  path: string;
  summary: string;
  description: string;
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
  const paths = (doc as Record<string, unknown>).paths;
  if (!paths || typeof paths !== 'object') return ops;
  for (const [path, item] of Object.entries(paths as Record<string, unknown>)) {
    if (!item || typeof item !== 'object') continue;
    for (const [method, op] of Object.entries(item as Record<string, unknown>)) {
      if (!['get', 'post', 'put', 'patch', 'delete'].includes(method)) continue;
      const o = (op ?? {}) as Record<string, unknown>;
      ops.push({
        method: method.toUpperCase(),
        path,
        summary: typeof o.summary === 'string' ? o.summary : '',
        description: typeof o.description === 'string' ? o.description : '',
      });
    }
  }
  ops.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));
  return ops;
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
