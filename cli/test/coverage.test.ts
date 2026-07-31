/**
 * THE COVERAGE GUARANTEE.
 *
 * The requirement is "every single functionality on the entire Agented website
 * must be usable from the CLI". That is only meaningful if it is measured, and
 * only durable if it is enforced — otherwise it is true on the day it is written
 * and quietly false a week later.
 *
 * Definition used: the website's capability surface IS
 * `frontend/src/services/api/*.ts`. The Vue components cannot reach an endpoint
 * the client package does not call, so every endpoint in that package is a thing
 * you can do in the browser, and nothing else is.
 *
 * These tests fail when:
 *   - the frontend gains an endpoint the CLI has no command for, or
 *   - `cli/aliases.generated.ts` drifts from the client package (someone edited
 *     the frontend and did not re-run `just cli-gen`).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

import { GENERATED } from '../aliases.generated.ts';
import { ALIASES, allAliases } from '../aliases.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const API_DIR = join(HERE, '..', '..', 'frontend', 'src', 'services', 'api');
const GEN_SCRIPT = join(HERE, '..', 'scripts', 'gen-aliases.mjs');
const GEN_FILE = join(HERE, '..', 'aliases.generated.ts');

/**
 * Every distinct endpoint path the frontend calls, reduced to its SHAPE.
 *
 * This deliberately applies the same rule the generator does — an interpolation
 * is a path param only when it follows a `/`, otherwise the path ends there —
 * because the question being asked is "did the generator cover everything it
 * saw", and comparing under two different rules would produce phantom gaps.
 *
 * That shared rule is exactly why this test CANNOT be the correctness oracle: if
 * the rule itself is wrong, this test agrees with the bug. The independent
 * oracle is `backend/tests/test_cli_contract.py`, which checks every generated
 * path against the server's REAL route table — and which caught two classes of
 * wrong command that this test happily passed.
 */
function frontendEndpoints(): Set<string> {
  const paths = new Set<string>();
  const re = /apiFetch\s*(?:<[\s\S]*?>)?\s*\(\s*([`'"])([^`'"]+)\1/g;
  for (const file of readdirSync(API_DIR)) {
    if (!file.endsWith('.ts') || file.endsWith('.test.ts') || file === 'client.ts' || file === 'index.ts') continue;
    const text = readFileSync(join(API_DIR, file), 'utf8');
    let m: RegExpExecArray | null;
    re.lastIndex = 0;
    while ((m = re.exec(text))) {
      const raw = m[2];
      if (!raw.startsWith('/')) continue;
      let p = '';
      let i = 0;
      for (;;) {
        const at = raw.indexOf('${', i);
        if (at < 0) {
          p += raw.slice(i);
          break;
        }
        p += raw.slice(i, at);
        const close = raw.indexOf('}', at);
        const expr = close < 0 ? '' : raw.slice(at + 2, close);
        if (!p.endsWith('/') || close < 0 || /[`?:]/.test(expr)) break;
        p += ':p';
        i = close + 1;
      }
      p = p.split(/[\s'"`?]/)[0].replace(/\/+$/, '');
      if (p.startsWith('/')) paths.add(p);
    }
  }
  return paths;
}

/** The same normalisation applied to a CLI alias path, so the two are comparable. */
function normalise(path: string): string {
  return path.replace(/:[A-Za-z0-9_]+/g, ':p').replace(/\/+$/, '');
}

test('every endpoint the website calls has a CLI command', () => {
  const wanted = frontendEndpoints();
  const covered = new Set(allAliases().map((a) => normalise(a.path)));

  const missing = [...wanted].filter((p) => !covered.has(p)).sort();

  assert.deepEqual(
    missing,
    [],
    `${missing.length} website endpoint(s) have no CLI command.\n` +
      `Run \`just cli-gen\` and commit cli/aliases.generated.ts.\n` +
      missing.slice(0, 25).map((m) => '  ' + m).join('\n'),
  );
});

test('the generated table is in sync with the frontend (no stale commit)', () => {
  const before = readFileSync(GEN_FILE, 'utf8');
  execFileSync(process.execPath, [GEN_SCRIPT], { stdio: 'pipe' });
  const after = readFileSync(GEN_FILE, 'utf8');
  assert.equal(
    after,
    before,
    'cli/aliases.generated.ts is stale — the frontend API client changed. Run `just cli-gen` and commit the result.',
  );
});

test('coverage is substantial, so a broken extractor cannot pass vacuously', () => {
  // A regex that silently stops matching would make the test above trivially
  // green. Pin the floor: the website has hundreds of endpoints, not tens.
  assert.ok(frontendEndpoints().size > 300, `only found ${frontendEndpoints().size} frontend endpoints`);
  assert.ok(GENERATED.length > 300, `only generated ${GENERATED.length} commands`);
});

test('generated commands never shadow a curated one', () => {
  // Curated aliases exist to give an operation better ergonomics. If a generated
  // entry won, `ag product new "Name"` would silently lose its positional
  // handling and its bare-id output.
  for (const c of ALIASES) {
    const clash = GENERATED.find((g) => g.group === c.group && g.verb === c.verb);
    if (clash) {
      assert.equal(
        normalise(clash.path),
        normalise(c.path),
        `curated "${c.group} ${c.verb}" and its generated twin disagree on the path — ` +
          `the curated one wins at runtime, so the generated path is unreachable and probably wrong`,
      );
    }
  }
});

test('every generated command is well-formed', () => {
  for (const g of GENERATED) {
    assert.ok(g.path.startsWith('/'), `${g.group} ${g.verb}: path must be absolute, got ${g.path}`);
    assert.ok(!g.path.includes('${'), `${g.group} ${g.verb}: unresolved template in ${g.path}`);
    assert.match(g.method, /^(GET|POST|PUT|PATCH|DELETE)$/, `${g.group} ${g.verb}: bad method`);
    for (const p of g.params ?? []) {
      assert.ok(g.path.includes(':' + p), `${g.group} ${g.verb}: declares ${p} not present in ${g.path}`);
    }
  }
});

test('group+verb pairs are unique across the whole command set', () => {
  const seen = new Map<string, string>();
  for (const a of allAliases()) {
    const k = `${a.group} ${a.verb}`;
    // Curated wins by construction (it comes first); only flag a generated dup.
    if (seen.has(k) && seen.get(k) !== 'curated') {
      assert.fail(`duplicate command "${k}"`);
    }
    seen.set(k, ALIASES.includes(a) ? 'curated' : 'generated');
  }
});
