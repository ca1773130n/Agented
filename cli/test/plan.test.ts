/**
 * Drive the WHOLE alias table through `planCommand` — 784 commands, no server.
 *
 * The argument rules in `planCommand` (fill the path params, lift named flags
 * into query/body, refuse leftovers) are the same code for every alias, so a bug
 * in them is one bug in 784 places. Before planning was split out of `aliasCmd`
 * that code was unreachable without a live backend, and the table went
 * unexercised; this is the test that split bought.
 *
 * Failures are COLLECTED and asserted once at the end. A test that dies on alias
 * #3 says nothing about the other 781, which is exactly the information a
 * table-driven test exists to produce.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseArgs } from '../lib/args.ts';
import { buildRequest } from '../lib/transport.ts';
import { allAliases, findAlias, type Alias } from '../aliases.ts';
import { planCommand } from '../bin/ag.ts';

const PROFILE = {
  name: 'test',
  backend: 'http://127.0.0.1:20000',
  sidecar: 'http://127.0.0.1:20001',
  key: 'secret-key',
  allowRemote: false,
};

/**
 * Values `resolveId` returns without a request: it short-circuits on the id
 * prefix for its kind (`SOURCES` in lib/resolve.ts). If one of those prefixes
 * ever changes, these stop short-circuiting — and the fetch trap below reports
 * that as a network attempt instead of the run stalling on a dead port.
 */
const ID_FOR: Record<string, string> = {
  project: 'proj-aaaaaa',
  product: 'prod-aaaaaa',
  'super-agent': 'sa-aaaaaa',
  agent: 'agent-aaaaaa',
};

/** Index-aligned with the path params, the way `planCommand` reads `resolve`. */
function positionalFor(alias: Alias, segment: string, i: number): string {
  const kind = alias.resolve?.[i];
  return kind ? ID_FOR[kind] : segment.slice(1);
}

/**
 * The value a flag is given, and therefore the value expected back out of the
 * plan. The space is deliberate — it is what makes the "no unencoded space in
 * the url" assertion below mean something.
 */
function sampleFor(alias: Alias, flag: string, isQuery: boolean): string {
  const kind = isQuery ? alias.resolveFlags?.[flag] : undefined;
  return kind ? ID_FOR[kind] : `sample ${flag}`;
}

/**
 * A canonical invocation: `<group> <verb>`, exactly as many positionals as the
 * path template consumes, and one flag per declared query/body flag.
 *
 * Counting with the same regex `fillPath` uses matters: one positional short is
 * a "needs <param>" usage error and one too many is the "unexpected argument"
 * refusal, and either would abort planning before a single assertion ran.
 *
 * `--flag=value` rather than `--flag value` because `parseArgs` treats the
 * BOOLEAN_FLAGS set (`--all`, `--wait`, `--json`, …) as switches that never
 * consume the next token — a flag named after one of those would otherwise
 * strand its value in the positionals.
 */
function invocation(alias: Alias): string[] {
  const argv = [alias.group, alias.verb];
  const segments = alias.path.match(/:[a-zA-Z_]+/g) ?? [];
  segments.forEach((seg, i) => argv.push(positionalFor(alias, seg, i)));
  for (const flag of Object.keys(alias.queryFlags ?? {})) argv.push(`--${flag}=${sampleFor(alias, flag, true)}`);
  for (const flag of Object.keys(alias.bodyFlags ?? {})) argv.push(`--${flag}=${sampleFor(alias, flag, false)}`);
  return argv;
}

test('every alias plans into a well-formed request, with no network', async () => {
  const aliases = allAliases();
  // A table-driven test over an empty table passes while proving nothing.
  assert.ok(aliases.length > 700, `alias table looks truncated: ${aliases.length} entries`);

  const realFetch = globalThis.fetch;
  const attempted: string[] = [];
  globalThis.fetch = ((input: unknown) => {
    const url = String(input instanceof Request ? input.url : input);
    attempted.push(url);
    // Reject immediately. A plan that needs a lookup has to FAIL and be
    // reported; letting it reach a port nothing is listening on turns a finding
    // into a 30-second-per-alias stall.
    return Promise.reject(new Error(`network call attempted: ${url}`));
  }) as typeof fetch;

  const failures: string[] = [];
  try {
    for (const alias of aliases) {
      const at = `ag ${alias.group} ${alias.verb} (${alias.method} ${alias.path})`;
      const push = (msg: string) => failures.push(`${at}: ${msg}`);
      const argv = invocation(alias);
      const callsBefore = attempted.length;

      let plan;
      try {
        plan = await planCommand(parseArgs(argv), PROFILE, alias.group, alias);
      } catch (e) {
        const net = attempted.length > callsBefore ? ` (after calling ${attempted[callsBefore]})` : '';
        push(`planning threw${net}: ${(e as Error).message.split('\n')[0]} [argv: ${argv.join(' ')}]`);
        continue;
      }
      if (attempted.length > callsBefore) push(`planning called the network: ${attempted[callsBefore]}`);

      if (plan.method !== alias.method) push(`method is ${plan.method}, alias declares ${alias.method}`);
      if (!plan.path.startsWith('/')) push(`path is not absolute: ${plan.path}`);
      if (/:[A-Za-z_]/.test(plan.path)) push(`path keeps an unfilled param: ${plan.path}`);
      // `${…}` is the generator leaking a frontend template literal verbatim;
      // `{…}` is the OpenAPI param spelling, which `fillPath` does not fill and
      // which the `:` check above cannot see. Measured: 0 of 784 alias paths
      // contain a brace today, so neither can fire as a false positive.
      if (/\$?\{[^}]*\}/.test(plan.path)) push(`path keeps an unexpanded template: ${plan.path}`);

      for (const [flag, key] of Object.entries(alias.queryFlags ?? {})) {
        const want = sampleFor(alias, flag, true);
        if (plan.query[key] !== want) {
          push(`--${flag} should land in query as ${key}=${JSON.stringify(want)}, got ${JSON.stringify(plan.query[key])}`);
        }
      }
      for (const [flag, key] of Object.entries(alias.bodyFlags ?? {})) {
        const want = sampleFor(alias, flag, false);
        if (plan.body?.[key] !== want) {
          push(`--${flag} should land in body as ${key}=${JSON.stringify(want)}, got ${JSON.stringify(plan.body?.[key])}`);
        }
      }
      if (alias.method === 'GET' && plan.body !== undefined) {
        push(`GET carries a body: ${JSON.stringify(plan.body)}`);
      }

      let url: string;
      try {
        url = buildRequest({
          method: plan.method,
          path: plan.path,
          query: plan.query,
          body: plan.body,
          profile: PROFILE,
        }).url;
      } catch (e) {
        push(`buildRequest threw: ${(e as Error).message.split('\n')[0]}`);
        continue;
      }
      // An empty path segment (`//`) is a 404 on the backend, and a raw space is
      // an invalid request line — both are silent-at-build-time, loud-in-prod.
      if (url.slice(new URL(url).origin.length).includes('//')) push(`url has an empty path segment: ${url}`);
      if (url.includes(' ')) push(`url carries an unencoded space: ${url}`);
    }
  } finally {
    globalThis.fetch = realFetch;
  }

  assert.deepEqual(
    failures,
    [],
    `${failures.length} of ${aliases.length} aliases plan wrongly:\n  ${failures.join('\n  ')}`,
  );
});

/**
 * The sweep above plans all 784 aliases in ONE canonical shape: every flag as
 * `--flag=value`, never a leftover positional. These are the shapes it cannot
 * reach by construction, and every one of them was MEASURED wrong before the
 * fix that follows it. They share a failure mode the sweep is blind to: a
 * plausible request, exit 0, and the wrong bytes on the wire.
 */
test('the argument shapes the canonical sweep cannot reach', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = ((input: unknown) => {
    throw new Error(`network call attempted: ${String(input)}`);
  }) as typeof fetch;

  const plan = (argv: string[]) => {
    const alias = findAlias(argv[0], argv[1]);
    if (!alias) throw new Error(`no such alias: ag ${argv[0]} ${argv[1]}`);
    return planCommand(parseArgs(argv), PROFILE, argv[0], alias);
  };

  try {
    // A leftover positional means the entity's NAME only on a create-style
    // command — POST that consumes no path param. `product new` is one;
    // `agent run` addresses an agent that already exists, and used to lift
    // "oops" into {"name":"oops"} for a handler reading only data["message"],
    // so the agent ran on an EMPTY message and the CLI reported success.
    assert.equal((await plan(['product', 'new', 'Agented Core'])).body?.name, 'Agented Core');
    await assert.rejects(
      plan(['agent', 'run', ID_FOR.agent, 'oops']),
      /unexpected argument "oops"/,
      'a leftover positional on an entity-addressing command must be refused, not renamed',
    );

    // `coerce` turns "3" into 3 because `-f n=3` means a number. A name lifted
    // out of the positionals is a string however digit-like: this sent 123.
    assert.equal((await plan(['product', 'new', '123'])).body?.name, '123');

    // Both of the parser's boolean forms used to arrive at the body loop as the
    // two values it skipped (`--flag` -> '', `--no-flag` -> undefined), so the
    // POST went out with no body at all — and this handler reads intent from
    // the body, making the documented way to turn memory off a silent no-op.
    assert.equal((await plan(['mem', 'enable', ID_FOR.project, '--enabled'])).body?.enabled, true);
    assert.equal((await plan(['mem', 'enable', ID_FOR.project, '--no-enabled'])).body?.enabled, false);
    assert.equal((await plan(['mem', 'enable', ID_FOR.project, '--enabled=false'])).body?.enabled, false);

    // The same drop on the query side: a documented switch that sent nothing.
    assert.equal(
      (await plan(['mem', 'compile', ID_FOR.project, '--retry-fallbacks'])).query.retry_fallbacks,
      'true',
    );

    // A flag that names a thing has no name to resolve in a boolean, so it
    // refuses rather than look up a project called "true".
    await assert.rejects(
      plan(['mem', 'distill', ID_FOR['super-agent'], '--project']),
      /--project needs a project name or id/,
    );
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a verb whose NAME is the intent sends that intent with no flags', async () => {
  // `ag mem enable GRD` is the invocation the alias's own help documents, but the
  // handler reads intent from the body and rejects an empty one ("missing 'root'
  // or 'enabled'"), so the documented command 400'd. bodyDefaults fills it, and
  // must lose to anything the caller says explicitly.
  const alias = findAlias('mem', 'enable')!;
  const plan = async (...rest: string[]) =>
    (await planCommand(parseArgs(['mem', 'enable', 'proj-aaaaaa', ...rest]), PROFILE, 'mem', alias)).body;

  assert.deepEqual(await plan(), { enabled: true }, 'bare invocation must carry the intent');
  assert.deepEqual(await plan('--enabled', 'false'), { enabled: false }, 'explicit value wins');
  assert.deepEqual(await plan('--no-enabled'), { enabled: false }, 'negation wins');
  assert.deepEqual(await plan('-f', 'root=/x'), { enabled: true, root: '/x' }, '-f merges over the default');
});

test('bodyDefaults is deliberately rare — it is not a way to paper over a required field', async () => {
  // Every entry here changes what a bare command sends, so each one needs a
  // reason. Keep the list short and explicit rather than letting it accrete.
  const withDefaults = allAliases().filter((a) => a.bodyDefaults).map((a) => `${a.group} ${a.verb}`);
  assert.deepEqual(withDefaults, ['mem enable']);
});

test('a flag with no value is refused for a string flag, honoured for a boolean one', async () => {
  // The canonical sweep above always writes `--flag=value`, so it cannot reach
  // this: `parseArgs` gives a bare `--flag` the value `true`. For a declared
  // boolean that IS the value; for a string flag the user forgot the value, and
  // both silent answers corrupt the request — dropping it ignores what they
  // typed, forwarding it wrote {"description": true} into a string field.
  const plan = async (group: string, verb: string, ...rest: string[]) => {
    const alias = findAlias(group, verb)!;
    return planCommand(parseArgs([group, verb, ...rest]), PROFILE, group, alias);
  };
  const refuses = async (msg: string, ...argv: [string, string, ...string[]]) => {
    await assert.rejects(() => plan(...argv), (e: Error) => e.message.includes(msg), argv.join(' '));
  };

  await refuses('needs a value', 'product', 'new', 'Foo', '--desc');
  await refuses('needs a value', 'product', 'new', 'Foo', '--no-desc');
  await refuses('needs a value', 'mem', 'compile', 'proj-aaaaaa', '--provider');
  // An explicit empty cannot mean anything for a boolean, but still clears a string.
  await refuses('expects true or false', 'mem', 'enable', 'proj-aaaaaa', '--enabled=');
  assert.deepEqual((await plan('product', 'new', 'Foo', '--desc=')).body, { name: 'Foo' });

  // Declared booleans keep working — the bug this file exists to pin.
  assert.deepEqual((await plan('mem', 'enable', 'proj-aaaaaa', '--enabled')).body, { enabled: true });
  assert.deepEqual((await plan('mem', 'enable', 'proj-aaaaaa', '--no-enabled')).body, { enabled: false });
  assert.equal((await plan('mem', 'compile', 'proj-aaaaaa', '--retry-fallbacks')).query.retry_fallbacks, 'true');
});

test('every declared boolFlag is actually a flag that alias declares', async () => {
  // A typo here silently turns a boolean back into a string flag, restoring the
  // bug. Nothing else would catch it.
  for (const a of allAliases()) {
    for (const f of a.boolFlags ?? []) {
      const known = { ...(a.bodyFlags ?? {}), ...(a.queryFlags ?? {}) };
      assert.ok(f in known, `${a.group} ${a.verb}: boolFlags names "${f}", which is not a body or query flag`);
    }
  }
});

test('a path param containing a digit is filled whole, not truncated', async () => {
  // fillPath used /:([a-zA-Z_]+)/, which stops at the digit: `:id2` matched `:id`
  // and left a literal "2" in the URL — a wrong endpoint, silently. No alias has
  // such a param today (all 784 scanned), so this pins the grammar rather than a
  // live bug: the generator and coverage test already use [A-Za-z0-9_].
  const alias: Alias = {
    group: 'x', verb: 'y', method: 'GET', path: '/admin/a/:id2/b',
    params: ['id2'], help: 'test-only alias',
  };
  const plan = await planCommand(parseArgs(['x', 'y', 'val']), PROFILE, 'x', alias);
  assert.equal(plan.path, '/admin/a/val/b');
});
