/**
 * Address things by NAME, not by generated id.
 *
 * `proj-xe3qj4` is a database detail. Nobody remembers it, and requiring it is
 * the difference between a CLI and a curl wrapper:
 *
 *   ag mem compile GetResearchDone      instead of   ag mem compile proj-xe3qj4
 *
 * An argument that already looks like an id (`proj-…`, `prod-…`, `sa-…`) is
 * passed straight through, so ids keep working and scripts do not break.
 */

import { request } from './transport.ts';
import type { Resolved } from './config.ts';

export type Kind = 'project' | 'product' | 'super-agent' | 'agent';

const SOURCES: Record<Kind, { path: string; prefix: string }> = {
  project: { path: '/admin/projects', prefix: 'proj-' },
  product: { path: '/admin/products', prefix: 'prod-' },
  'super-agent': { path: '/admin/super-agents', prefix: 'sa-' },
  agent: { path: '/admin/agents', prefix: 'agent-' },
};

/** One lookup per kind per process — these lists are small and this is a CLI. */
const cache = new Map<Kind, { id: string; name: string }[]>();

export class ResolveError extends Error {}

export async function resolveId(kind: Kind, value: string, profile: Resolved): Promise<string> {
  const src = SOURCES[kind];
  // Already an id — never spend a request on it.
  if (value.startsWith(src.prefix)) return value;

  let rows = cache.get(kind);
  if (!rows) {
    const res = await request({ method: 'GET', path: src.path, profile });
    if (res.status >= 400) {
      throw new ResolveError(`cannot list ${kind}s to resolve "${value}" (HTTP ${res.status})`);
    }
    rows = extract(res.body);
    cache.set(kind, rows);
  }

  const exact = rows.filter((r) => r.name === value);
  if (exact.length === 1) return exact[0].id;
  if (exact.length > 1) {
    throw new ResolveError(
      `"${value}" matches ${exact.length} ${kind}s — use an id:\n  ` +
        exact.map((r) => `${r.id}  ${r.name}`).join('\n  '),
    );
  }

  // Case-insensitive fallback, then a helpful "did you mean".
  const loose = rows.filter((r) => r.name.toLowerCase() === value.toLowerCase());
  if (loose.length === 1) return loose[0].id;

  const near = rows
    .filter((r) => r.name.toLowerCase().includes(value.toLowerCase()))
    .slice(0, 5);
  throw new ResolveError(
    `no ${kind} named "${value}".` +
      (near.length ? `\n  did you mean:\n  ` + near.map((r) => `${r.id}  ${r.name}`).join('\n  ') : ''),
  );
}

/** Pull {id,name} out of whatever envelope the list endpoint used. */
function extract(body: unknown): { id: string; name: string }[] {
  let list: unknown = body;
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const arrays = Object.values(body as Record<string, unknown>).filter(Array.isArray);
    if (arrays.length === 1) list = arrays[0];
  }
  if (!Array.isArray(list)) return [];
  return list
    .filter((r): r is Record<string, unknown> => !!r && typeof r === 'object')
    .map((r) => ({ id: String(r.id ?? ''), name: String(r.name ?? '') }))
    .filter((r) => r.id);
}
