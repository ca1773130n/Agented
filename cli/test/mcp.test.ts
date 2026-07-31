/**
 * MCP protocol tests. No server, no network — these cover the framing and the
 * tool contract, which is where an MCP server breaks in ways that look like a
 * client bug.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { handleMessage, TOOLS } from '../lib/mcp.ts';

test('initialize returns a protocol version and server info', async () => {
  const r = await handleMessage({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} });
  assert.ok(r);
  const result = r!.result as Record<string, any>;
  assert.equal(result.protocolVersion, '2024-11-05');
  assert.equal(result.serverInfo.name, 'ag');
  assert.ok(result.capabilities.tools, 'must advertise the tools capability');
});

test('notifications get NO response', async () => {
  // A response to a notification desyncs the client's id matching.
  assert.equal(await handleMessage({ jsonrpc: '2.0', method: 'notifications/initialized' }), null);
  assert.equal(await handleMessage({ jsonrpc: '2.0', method: 'initialized' }), null);
});

test('tools/list exposes a SMALL fixed surface, not one tool per command', async () => {
  const r = await handleMessage({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
  const tools = (r!.result as any).tools as { name: string }[];
  assert.deepEqual(tools.map((t) => t.name), ['ag_groups', 'ag_find', 'ag_describe', 'ag_call', 'ag_request']);
  // The whole point: 754 tool definitions would cost more context than most
  // conversations before any work happened.
  assert.ok(tools.length < 10, 'the tool surface must stay tiny');
});

test('every tool declares a usable schema', () => {
  for (const t of TOOLS) {
    assert.ok(t.description.length > 40, `${t.name}: description too thin to guide a model`);
    assert.equal(t.inputSchema.type, 'object');
    for (const req of (t.inputSchema as any).required ?? []) {
      assert.ok((t.inputSchema as any).properties[req], `${t.name}: required "${req}" is not a declared property`);
    }
  }
});

test('an unknown method is a JSON-RPC error, but only when it has an id', async () => {
  const r = await handleMessage({ jsonrpc: '2.0', id: 9, method: 'nope/nope' });
  assert.equal(r!.error?.code, -32601);
  assert.equal(await handleMessage({ jsonrpc: '2.0', method: 'nope/nope' }), null);
});

test('ag_groups lists groups, and drills into one', async () => {
  const all = await handleMessage({
    jsonrpc: '2.0', id: 3, method: 'tools/call',
    params: { name: 'ag_groups', arguments: {} },
  });
  const rows = JSON.parse((all!.result as any).content[0].text);
  assert.ok(rows.length > 50, `expected many groups, got ${rows.length}`);

  const one = await handleMessage({
    jsonrpc: '2.0', id: 4, method: 'tools/call',
    params: { name: 'ag_groups', arguments: { group: 'product' } },
  });
  const verbs = JSON.parse((one!.result as any).content[0].text);
  assert.ok(verbs.some((v: any) => v.verb === 'ls'));
});

test('a tool failure is an isError RESULT, not a JSON-RPC error', async () => {
  // The model has to be able to read the message and correct itself; a
  // transport-level error would just look like the server broke.
  const r = await handleMessage({
    jsonrpc: '2.0', id: 5, method: 'tools/call',
    params: { name: 'ag_call', arguments: { group: 'nope', verb: 'nope' } },
  });
  assert.equal(r!.error, undefined);
  assert.equal((r!.result as any).isError, true);
  assert.match((r!.result as any).content[0].text, /no command/);
});

test('a missing positional names the argument it wants', async () => {
  const r = await handleMessage({
    jsonrpc: '2.0', id: 6, method: 'tools/call',
    params: { name: 'ag_call', arguments: { group: 'sa', verb: 'show' } },
  });
  assert.equal((r!.result as any).isError, true);
  assert.match((r!.result as any).content[0].text, /\bsa\b/);
});

test('ag_call dry_run builds the request and redacts the key', async () => {
  const r = await handleMessage({
    jsonrpc: '2.0', id: 7, method: 'tools/call',
    params: {
      name: 'ag_call',
      arguments: { group: 'product', verb: 'new', body: { name: 'X' }, dry_run: true },
    },
  });
  const built = JSON.parse((r!.result as any).content[0].text);
  assert.equal(built.dry_run, true);
  assert.equal(built.method, 'POST');
  assert.match(built.url, /\/admin\/products$/);
  assert.deepEqual(built.body, { name: 'X' });
  if (built.headers['X-API-Key']) assert.equal(built.headers['X-API-Key'], '<redacted>');
});

test('ag_request refuses a path that is not absolute', async () => {
  const r = await handleMessage({
    jsonrpc: '2.0', id: 8, method: 'tools/call',
    params: { name: 'ag_request', arguments: { method: 'GET', path: 'admin/products' } },
  });
  assert.equal((r!.result as any).isError, true);
});

test('ag_request routes /api/v1 to the sidecar', async () => {
  const r = await handleMessage({
    jsonrpc: '2.0', id: 10, method: 'tools/call',
    params: { name: 'ag_request', arguments: { method: 'GET', path: '/api/v1/accounts', dry_run: true } },
  });
  const built = JSON.parse((r!.result as any).content[0].text);
  assert.equal(built.service, 'sidecar');
  assert.match(built.url, /:20001\//);
});

test('ag_describe surfaces the body shape the web UI sends', async () => {
  // The server types almost no bodies, so this is the only shape hint an agent
  // gets — if it stops appearing, ag_call becomes guesswork again.
  const r = await handleMessage({
    jsonrpc: '2.0', id: 11, method: 'tools/call',
    params: { name: 'ag_describe', arguments: { group: 'agent', verb: 'run' } },
  });
  const d = JSON.parse((r!.result as any).content[0].text);
  assert.equal(d.method, 'POST');
  assert.deepEqual(d.body_keys_from_web_ui, ['message']);
});
