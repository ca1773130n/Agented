#!/usr/bin/env node
/**
 * `ag mcp` — MCP stdio server for the Agented platform.
 *
 * Register with Claude Code:
 *   claude mcp add agented -- ag mcp
 * or in .mcp.json:
 *   { "mcpServers": { "agented": { "command": "ag", "args": ["mcp"] } } }
 *
 * Newline-delimited JSON-RPC 2.0 on stdin/stdout — the same framing `gd` uses,
 * hand-rolled, no SDK, no dependencies.
 *
 * STDOUT IS THE PROTOCOL. Nothing may print to it but a JSON-RPC response, or
 * the client's parser desyncs and the whole server looks broken. Every
 * diagnostic goes to stderr; `lib/output.ts` already enforces that split for the
 * CLI, and this file must not violate it.
 */

import { handleMessage, type JsonRpcMessage, type JsonRpcResponse } from '../lib/mcp.ts';

export function serve(): void {
  let buffer = '';
  process.stdin.setEncoding('utf-8');

  // Track in-flight work. `stdin.on('end')` fires as soon as the writer closes
  // the pipe, which for piped input is immediately after the last line — so
  // exiting there DROPPED every response still awaiting an HTTP round-trip.
  // Measured: piping four requests returned only the two that resolved
  // synchronously. A long-lived client keeps stdin open and would rarely show
  // this, which is exactly why it is worth handling rather than hoping.
  let pending = 0;
  let stdinEnded = false;
  const maybeExit = () => {
    if (stdinEnded && pending === 0) process.exit(0);
  };

  const write = (r: JsonRpcResponse) => process.stdout.write(JSON.stringify(r) + '\n');

  process.stdin.on('data', (chunk: string) => {
    buffer += chunk;
    let nl: number;
    while ((nl = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;

      let msg: JsonRpcMessage;
      try {
        msg = JSON.parse(line) as JsonRpcMessage;
      } catch {
        write({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
        continue;
      }

      // Never let one bad message kill the server: a rejected promise here would
      // take the process down mid-session and look like a crash to the client.
      pending++;
      handleMessage(msg)
        .then((res) => {
          if (res) write(res);
        })
        .catch((e: unknown) => {
          if (msg.id !== undefined && msg.id !== null) {
            write({
              jsonrpc: '2.0',
              id: msg.id,
              error: { code: -32603, message: e instanceof Error ? e.message : String(e) },
            });
          }
        })
        .finally(() => {
          pending--;
          maybeExit();
        });
    }
  });

  process.stdin.on('end', () => {
    stdinEnded = true;
    maybeExit();
  });
  process.stdin.resume();
}

// Run when invoked directly (`ag-mcp`), not when imported by `ag mcp`.
if (process.argv[1] && /ag-mcp(\.ts)?$/.test(process.argv[1])) serve();
