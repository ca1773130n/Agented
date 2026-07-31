/**
 * Hand-rolled argv parser. No commander, no yargs — the CLI has zero runtime
 * dependencies so it can be a symlink to a .ts file that Node runs directly.
 *
 * Grammar:
 *   --flag              -> true
 *   --flag value        -> "value"   (unless the next token starts with '-')
 *   --flag=value        -> "value"
 *   --no-flag           -> false
 *   -f k=v (repeatable) -> collected into `fields`
 *   -q k=v (repeatable) -> collected into `query`
 *   --                  -> everything after is a raw positional
 */

export interface Args {
  positionals: string[];
  flags: Record<string, string | boolean>;
  /** Repeated `-f k=v` pairs — request body fields. */
  fields: Record<string, string>;
  /** Repeated `-q k=v` pairs — query-string params. */
  query: Record<string, string>;
}

const VALUE_FLAGS_TAKING_NEXT = new Set<string>();

export function parseArgs(argv: string[]): Args {
  const out: Args = { positionals: [], flags: {}, fields: {}, query: {} };
  let passthrough = false;

  for (let i = 0; i < argv.length; i++) {
    const tok = argv[i];

    if (passthrough) {
      out.positionals.push(tok);
      continue;
    }
    if (tok === '--') {
      passthrough = true;
      continue;
    }

    if (tok === '-f' || tok === '-q') {
      const pair = argv[++i];
      if (pair === undefined) throw new UsageError(`${tok} needs a key=value pair`);
      const eq = pair.indexOf('=');
      if (eq < 0) throw new UsageError(`${tok} expects key=value, got ${JSON.stringify(pair)}`);
      const target = tok === '-f' ? out.fields : out.query;
      target[pair.slice(0, eq)] = pair.slice(eq + 1);
      continue;
    }

    if (tok.startsWith('--')) {
      const body = tok.slice(2);
      const eq = body.indexOf('=');
      if (eq >= 0) {
        out.flags[body.slice(0, eq)] = body.slice(eq + 1);
        continue;
      }
      if (body.startsWith('no-')) {
        out.flags[body.slice(3)] = false;
        continue;
      }
      const next = argv[i + 1];
      // A bare `--flag` followed by something that is not another flag takes it as
      // a value. `--json` before a positional would misfire, so boolean flags are
      // consumed by name in `bool()` and never looked up via `str()`.
      if (next !== undefined && !next.startsWith('-')) {
        out.flags[body] = next;
        i++;
      } else {
        out.flags[body] = true;
      }
      continue;
    }

    out.positionals.push(tok);
  }

  return out;
}

/** Read a flag as a string; `undefined` when absent. A bare boolean flag reads as ''. */
export function str(a: Args, name: string): string | undefined {
  const v = a.flags[name];
  if (v === undefined) return undefined;
  if (typeof v === 'boolean') return v ? '' : undefined;
  return v;
}

/** Read a flag as a boolean. Present-but-valued counts as true (e.g. `--json=1`). */
export function bool(a: Args, name: string): boolean {
  const v = a.flags[name];
  if (v === undefined) return false;
  if (typeof v === 'boolean') return v;
  return v !== 'false' && v !== '0';
}

export function num(a: Args, name: string, dflt: number): number {
  const v = str(a, name);
  if (v === undefined || v === '') return dflt;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new UsageError(`--${name} expects a number, got ${JSON.stringify(v)}`);
  return n;
}

/** A usage mistake by the caller — exit 2, never a stack trace. */
export class UsageError extends Error {}

export { VALUE_FLAGS_TAKING_NEXT };
