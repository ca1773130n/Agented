/**
 * Unit tests for `ag`. Run with `node --test cli/test/*.test.ts` — no server, no
 * network, no build step, no dependencies.
 *
 * These cover the parts where a bug is silent rather than loud: routing a path
 * to the wrong service, attaching credentials to the wrong request, or an SSE
 * parser that drops a frame.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseArgs, str, bool, num, UsageError } from '../lib/args.ts';
import { routeService, needsAuth, buildRequest, exitCodeForStatus, errorMessage } from '../lib/transport.ts';
import { SSEParser, parseFrame } from '../lib/stream.ts';
import { indexSchema, searchOps } from '../lib/schema.ts';
import { unwrapList } from '../lib/output.ts';
import { isLoopback } from '../lib/config.ts';
import { ALIASES, findAlias } from '../aliases.ts';

const PROFILE = {
  name: 'test',
  backend: 'http://127.0.0.1:20000',
  sidecar: 'http://127.0.0.1:20001',
  key: 'secret-key',
  allowRemote: false,
};

// ---- args -----------------------------------------------------------------

test('parses flags, values, negations and repeated -f/-q', () => {
  const a = parseArgs(['api', 'POST', '/x', '--json', '--host=http://h', '--no-color', '-f', 'a=1', '-f', 'b=2', '-q', 'p=3']);
  assert.deepEqual(a.positionals, ['api', 'POST', '/x']);
  assert.equal(bool(a, 'json'), true);
  assert.equal(str(a, 'host'), 'http://h');
  assert.equal(bool(a, 'color'), false);
  assert.deepEqual(a.fields, { a: '1', b: '2' });
  assert.deepEqual(a.query, { p: '3' });
});

test('a flag value may start with a dash', () => {
  // `ag product new "N" --desc "-5 degrees"` used to DROP the description (its
  // value starts with `-`) and merge it into the name — silent data corruption
  // with no error. A leading `-` does not make a token a flag.
  const a = parseArgs(['product', 'new', 'N', '--desc', '-5 degrees']);
  assert.equal(str(a, 'desc'), '-5 degrees');
  assert.deepEqual(a.positionals, ['product', 'new', 'N']);
});

test('negative numbers survive as flag values', () => {
  assert.equal(str(parseArgs(['--offset', '-1']), 'offset'), '-1');
});

test('a boolean flag never swallows the next token', () => {
  // `ag --json product ls` read "product" as the value of --json and dispatched
  // the wrong command.
  const a = parseArgs(['--json', 'product', 'ls']);
  assert.equal(bool(a, 'json'), true);
  assert.deepEqual(a.positionals, ['product', 'ls']);
});

test('a flag followed by another flag is boolean', () => {
  const a = parseArgs(['--dry-run', '--host', 'http://h']);
  assert.equal(bool(a, 'dry-run'), true);
  assert.equal(str(a, 'host'), 'http://h');
});

test('-- stops flag parsing', () => {
  const a = parseArgs(['api', 'GET', '/x', '--', '--not-a-flag']);
  assert.ok(a.positionals.includes('--not-a-flag'));
});

test('-f without = is a usage error, not a silent drop', () => {
  assert.throws(() => parseArgs(['-f', 'novalue']), UsageError);
});

test('num rejects non-numeric', () => {
  assert.throws(() => num(parseArgs(['--limit', 'abc']), 'limit', 1), UsageError);
});

// ---- service routing ------------------------------------------------------

test('/api/v1/* goes to the sidecar, everything else to the backend', () => {
  assert.equal(routeService('/api/v1/accounts'), 'sidecar');
  assert.equal(routeService('/admin/products'), 'backend');
  assert.equal(routeService('/api/projects'), 'backend'); // NOT /api/v1/
  assert.equal(routeService('/health'), 'backend');
});

test('--service overrides the prefix rule (the sidecar has its own /health)', () => {
  assert.equal(routeService('/health', 'sidecar'), 'sidecar');
  assert.equal(routeService('/api/v1/x', 'backend'), 'backend');
});

// ---- auth -----------------------------------------------------------------

test('only /admin and /api require auth; /health and /schema never do', () => {
  assert.equal(needsAuth('/admin/products'), true);
  assert.equal(needsAuth('/api/projects'), true);
  assert.equal(needsAuth('/health'), false);
  assert.equal(needsAuth('/health/verify-key'), false);
  assert.equal(needsAuth('/schema/openapi.json'), false);
  assert.equal(needsAuth('/api/oauth-callback'), false);
});

test('the key is attached only where auth is required', () => {
  const authed = buildRequest({ method: 'GET', path: '/admin/products', profile: PROFILE });
  assert.equal(authed.headers['X-API-Key'], 'secret-key');

  // This is the one that matters: `ag find` must work before a key exists, and
  // must not leak the key to an unauthenticated endpoint.
  const open = buildRequest({ method: 'GET', path: '/schema/openapi.json', profile: PROFILE });
  assert.equal(open.headers['X-API-Key'], undefined);
});

test('Content-Type is set only when there is a body', () => {
  assert.equal(buildRequest({ method: 'GET', path: '/admin/x', profile: PROFILE }).headers['Content-Type'], undefined);
  assert.equal(
    buildRequest({ method: 'POST', path: '/admin/x', body: {}, profile: PROFILE }).headers['Content-Type'],
    'application/json',
  );
});

test('query params are encoded onto the url', () => {
  const r = buildRequest({ method: 'GET', path: '/admin/projects', query: { product_id: 'p 1' }, profile: PROFILE });
  assert.match(r.url, /\?product_id=p\+1$/);
});

// ---- exit codes -----------------------------------------------------------

test('status maps to a stable exit code so callers can branch', () => {
  assert.equal(exitCodeForStatus(200), 0);
  assert.equal(exitCodeForStatus(401), 3);
  assert.equal(exitCodeForStatus(403), 3);
  assert.equal(exitCodeForStatus(404), 6);
  assert.equal(exitCodeForStatus(500), 7);
  assert.equal(exitCodeForStatus(422), 8);
});

test('error envelopes are unwrapped to a human message', () => {
  assert.equal(errorMessage({ error: { code: 'x', message: 'bad thing' } }), 'bad thing');
  assert.equal(errorMessage({ detail: 'missing field' }), 'missing field');
  assert.equal(errorMessage('plain text'), 'plain text');
});

// ---- SSE ------------------------------------------------------------------

test('parses a frame with event, data and id', () => {
  const f = parseFrame('event: delta\ndata: {"a":1}\nid: 7');
  assert.equal(f?.event, 'delta');
  assert.equal(f?.data, '{"a":1}');
  assert.equal(f?.id, '7');
});

test('multi-line data fields are joined, comments ignored', () => {
  const f = parseFrame(': heartbeat\ndata: one\ndata: two');
  assert.equal(f?.data, 'one\ntwo');
});

test('frames split across chunk boundaries are not lost', () => {
  const p = new SSEParser();
  assert.equal(p.push('data: a\n').length, 0, 'incomplete frame must not emit');
  const got = p.push('\ndata: b\n\n');
  assert.deepEqual(got.map((f) => f.data), ['a', 'b']);
});

test('handles CRLF framing', () => {
  const p = new SSEParser();
  const got = p.push('data: x\r\n\r\n');
  assert.deepEqual(got.map((f) => f.data), ['x']);
});

test('a trailing frame with no blank line is flushed, not dropped', () => {
  const p = new SSEParser();
  p.push('data: last');
  assert.deepEqual(p.flush().map((f) => f.data), ['last']);
});

// ---- schema ---------------------------------------------------------------

const DOC = {
  paths: {
    '/admin/products': {
      get: { summary: 'List products' },
      post: { summary: 'Create a product', description: 'body: name, description' },
    },
    '/health': { get: { summary: 'Health' } },
  },
};

test('indexes every method of every path', () => {
  const ops = indexSchema(DOC);
  assert.equal(ops.length, 3);
  assert.ok(ops.some((o) => o.method === 'POST' && o.path === '/admin/products'));
});

test('search ANDs its terms across path, summary and description', () => {
  const ops = indexSchema(DOC);
  assert.equal(searchOps(ops, ['product']).length, 2);
  assert.equal(searchOps(ops, ['product', 'create']).length, 1);
  // description is searchable — it is the only body hint for untyped handlers
  assert.equal(searchOps(ops, ['body:', 'name']).length, 1);
  assert.equal(searchOps(ops, ['nonexistent']).length, 0);
});

test('a malformed schema yields an empty index rather than throwing', () => {
  assert.deepEqual(indexSchema(null), []);
  assert.deepEqual(indexSchema({ paths: 'nope' }), []);
});

// ---- output ---------------------------------------------------------------

test('list envelopes unwrap to a bare array for jq', () => {
  assert.deepEqual(unwrapList({ products: [1, 2], total_count: 2 }), [1, 2]);
  assert.deepEqual(unwrapList([3]), [3]);
  // Ambiguous (two arrays) → leave it alone rather than guess wrong.
  assert.deepEqual(unwrapList({ a: [1], b: [2] }), { a: [1], b: [2] });
});

// ---- config guard ---------------------------------------------------------

test('loopback detection drives the production-safety guard', () => {
  assert.equal(isLoopback('http://127.0.0.1:20000'), true);
  assert.equal(isLoopback('http://localhost:3000'), true);
  assert.equal(isLoopback('https://api.example.com'), false);
  assert.equal(isLoopback('https://hypepaper.example'), false);
});

// ---- aliases --------------------------------------------------------------

test('alias paths are well-formed and unique per group+verb', () => {
  const seen = new Set<string>();
  for (const a of ALIASES) {
    assert.ok(a.path.startsWith('/'), `${a.group} ${a.verb}: path must be absolute`);
    assert.match(a.method, /^(GET|POST|PUT|PATCH|DELETE)$/);
    const k = `${a.group} ${a.verb}`;
    assert.ok(!seen.has(k), `duplicate alias ${k}`);
    seen.add(k);
  }
});

test('lookup finds a known alias and rejects an unknown one', () => {
  assert.ok(findAlias('product', 'ls'));
  assert.equal(findAlias('product', 'nope'), undefined);
});

test('every declared path param appears in the path template', () => {
  for (const a of ALIASES) {
    for (const p of a.params ?? []) {
      assert.ok(a.path.includes(`:${p}`), `${a.group} ${a.verb}: declares ${p} but the path lacks :${p}`);
    }
  }
});
