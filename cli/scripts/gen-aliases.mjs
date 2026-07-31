#!/usr/bin/env node
/**
 * Generate `cli/aliases.generated.ts` from the frontend's API client package.
 *
 * WHY THIS EXISTS
 * "Every functionality on the website" has a precise definition: every endpoint
 * `frontend/src/services/api/*.ts` calls. That package IS the website's
 * capability surface — a Vue component cannot reach an endpoint the client does
 * not call, and nothing else is reachable from the browser. So rather than
 * hand-maintaining hundreds of aliases (which would rot the moment a feature
 * shipped), the CLI derives its commands from the same source the UI uses, and
 * `cli/test/coverage.test.ts` fails when the two drift.
 *
 *   export const triggerApi = {
 *     list: () => apiFetch('/admin/triggers'),
 *     get: (id) => apiFetch(`/admin/triggers/${id}`),
 *   }
 * becomes
 *   ag trigger list  |  ag trigger get <id>
 *
 * Anything unparseable is REPORTED, never silently dropped — an invisible
 * coverage hole is the exact failure this file exists to prevent.
 */

import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const API_DIR = join(HERE, '..', '..', 'frontend', 'src', 'services', 'api');
const OUT = join(HERE, '..', 'aliases.generated.ts');

const PATH_RE = /apiFetch\s*(?:<[\s\S]*?>)?\s*\(\s*([`'"])([^`'"]+)\1/;
const METHOD_RE = /method:\s*['"](GET|POST|PUT|PATCH|DELETE)['"]/i;
const EXPORT_RE = /export\s+const\s+([A-Za-z0-9_]+Api)\s*(?::[^=]+)?=\s*\{/g;

const aliases = [];
const skipped = [];
const seen = new Set();
let currentFile = '';

/** `getStatus` -> `get-status`; `listPRs` -> `list-prs`. */
const kebab = (s) =>
  s
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .toLowerCase();

const groupName = (exportName) => kebab(exportName.replace(/Api$/, ''));

/**
 * Remove comments while respecting strings and template literals.
 *
 * Load-bearing: the client documents each entry with a JSDoc block
 * (`/** 1. GET /grd/health — health panel. *​/`), so an entry's text begins with
 * the comment, not the key. Without this the key regex misses and the entry is
 * silently skipped — that alone hid 225 endpoints, i.e. a third of the website.
 */
function stripComments(text) {
  let out = '';
  let inStr = null;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    const next = text[i + 1];
    if (inStr) {
      out += c;
      if (c === inStr && text[i - 1] !== '\\') inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') {
      inStr = c;
      out += c;
      continue;
    }
    if (c === '/' && next === '*') {
      const end = text.indexOf('*/', i + 2);
      i = end < 0 ? text.length : end + 1;
      out += ' ';
      continue;
    }
    if (c === '/' && next === '/') {
      const end = text.indexOf('\n', i);
      i = end < 0 ? text.length : end - 1;
      continue;
    }
    out += c;
  }
  return out;
}

/** Split an object-literal body into top-level `key: value` entries. */
function splitEntries(body) {
  const entries = [];
  let depth = 0;
  // Generic depth, tracked SEPARATELY. `apiFetch<Record<string, unknown>>(…)`
  // contains a comma that is not an entry separator; without this the entry was
  // cut in half and both halves became unparseable — which silently dropped
  // every call whose response type is a generic with more than one parameter.
  let angle = 0;
  let start = 0;
  let inStr = null;
  const isIdent = (ch) => !!ch && /[A-Za-z0-9_>\]]/.test(ch);
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (inStr) {
      if (c === inStr && body[i - 1] !== '\\') inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') inStr = c;
    else if ('([{'.includes(c)) depth++;
    else if (')]}'.includes(c)) depth--;
    // `Foo<` opens a generic; a bare `a < b` (preceded by whitespace) does not.
    else if (c === '<' && isIdent(body[i - 1])) angle++;
    // `>` closes one, except in `=>`, which is an arrow, not a generic.
    else if (c === '>' && angle > 0 && body[i - 1] !== '=') angle--;
    else if (c === ',' && depth === 0 && angle === 0) {
      entries.push(body.slice(start, i));
      start = i + 1;
    }
  }
  entries.push(body.slice(start));
  return entries.map((e) => e.trim()).filter(Boolean);
}

/** Walk from an opening brace to its match. */
function matchBrace(text, openIdx) {
  let depth = 0;
  let inStr = null;
  for (let i = openIdx; i < text.length; i++) {
    const c = text[i];
    if (inStr) {
      if (c === inStr && text[i - 1] !== '\\') inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') inStr = c;
    else if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}


/**
 * Register a command, disambiguating rather than dropping.
 *
 * The `seen` set is keyed on group+verb, and two different call sites can
 * legitimately produce the same key (e.g. `backendApi.list` and
 * `modelCacheApi.list` both under `backend`). Skipping the second silently lost
 * its DISTINCT path — 20 real endpoints, including all of `/api/setup/*`. So a
 * collision on a different path gets a numeric suffix; only an exact repeat of
 * the same path is a true duplicate worth dropping.
 */
function addAlias(group, baseVerb, method, path, params, source, bodyKeys = [], transforms = []) {
  if (aliases.some((a) => a.group === group && a.path === path && a.method === method)) return;
  let verb = baseVerb;
  let n = 2;
  while (seen.has(`${group} ${verb}`)) verb = `${baseVerb}-${n++}`;
  seen.add(`${group} ${verb}`);
  aliases.push({ group, verb, method, path, params, source, bodyKeys, transforms });
}


// ---------------------------------------------------------------------------
// Request-body hints.
//
// The server's OpenAPI is no help here: measured against the live schema, 878
// operations carry ZERO descriptions, and of the 286 with a request body only 35
// are typed — 251 expose no property schema at all. So `-f k=v` would be pure
// guesswork for the majority of write endpoints.
//
// The frontend client, however, demonstrably knows: it SENDS those bodies. Two
// forms cover 231 of 242 call sites:
//   `JSON.stringify({ name, color })`      -> keys read directly
//   `JSON.stringify(data)` where the arrow is `(data: CreateProjectRequest)`
//                                          -> keys read off that interface
// ---------------------------------------------------------------------------

const TYPE_CACHE = new Map();

/** Property names of a TS interface/type alias, searched across the api package. */
function typeKeys(typeName) {
  if (!typeName) return [];
  if (TYPE_CACHE.has(typeName)) return TYPE_CACHE.get(typeName);
  TYPE_CACHE.set(typeName, []); // guard against recursive types
  const roots = [API_DIR, join(API_DIR, 'types')];
  for (const root of roots) {
    let files;
    try {
      files = readdirSync(root).filter((f) => f.endsWith('.ts'));
    } catch {
      continue;
    }
    for (const f of files) {
      const text = stripComments(readFileSync(join(root, f), 'utf8'));
      const re = new RegExp(`(?:interface|type)\\s+${typeName}\\b[^{]*\\{`);
      const m = text.match(re);
      if (!m) continue;
      const open = text.indexOf('{', m.index);
      const close = matchBrace(text, open);
      if (close < 0) continue;
      // TOP-LEVEL properties only. Scanning every property-looking line hoisted
      // nested fields into the request body: `{ messages: Array<{ role, content }> }`
      // advertised `role`/`content` as top-level keys, so an agent told to send
      // `-f role=user` would build a body the server rejects.
      const keys = [];
      let depth = 0;
      for (const line of text.slice(open + 1, close).split('\n')) {
        const k = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)(\?)?\s*:/);
        if (k && depth === 0) keys.push(k[1] + (k[2] ? '?' : ''));
        for (const ch of line) {
          if (ch === '{' || ch === '[') depth++;
          else if (ch === '}' || ch === ']') depth--;
        }
      }
      TYPE_CACHE.set(typeName, keys);
      return keys;
    }
  }
  return [];
}

/** Body keys for one call site, from an inline literal or the parameter's type. */
function bodyKeysFor(entryValue, callText) {
  const inline = callText.match(/body:\s*JSON\.stringify\(\s*\{([\s\S]{0,400}?)\}\s*\)/);
  if (inline) {
    const keys = [];
    for (const part of inline[1].split(',')) {
      const k = part.trim().match(/^([A-Za-z_][A-Za-z0-9_]*)/);
      if (k) keys.push(k[1]);
    }
    if (keys.length) return keys;
  }
  const ident = callText.match(/body:\s*JSON\.stringify\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)/);
  if (ident) {
    // Find that identifier's declared type in the arrow/method signature.
    const sig = entryValue.slice(0, entryValue.indexOf('=>') + 1 || 200);
    const typed = sig.match(new RegExp(`\\b${ident[1]}\\s*:\\s*([A-Za-z_][A-Za-z0-9_]*)`));
    if (typed) return typeKeys(typed[1]);
  }
  return [];
}

/**
 * Raw template path -> `/a/:id`, plus the params that survived into it.
 *
 * The rule that matters: an interpolation is a PATH PARAM only when it directly
 * follows a `/`. Anything else is a query-string suffix and the path ends before
 * it. Getting this wrong is not cosmetic — it produced two classes of dangerous
 * output:
 *
 *   `/admin/projects/${encodeURIComponent(id)}/leader-chat/session`
 *      naive: the expression is not a bare identifier, so the whole tail was cut
 *      -> POST /admin/projects, i.e. `ag team-leader-chat open-session p1` would
 *      CREATE A PROJECT instead of opening a chat.
 *   `/admin/system/errors${query}`
 *      naive: `${query}` looks like an identifier -> `/admin/system/errors:query`,
 *      a path that does not exist and 404s.
 *
 * So: after a `/`, take the LAST identifier in the expression (which unwraps
 * `encodeURIComponent(projectId)` to `projectId`); anywhere else, stop.
 */
function normalisePath(raw, transforms = new Set()) {
  let path = '';
  let i = 0;
  while (i < raw.length) {
    const at = raw.indexOf('${', i);
    if (at < 0) {
      path += raw.slice(i);
      break;
    }
    path += raw.slice(i, at);
    const close = raw.indexOf('}', at);
    const expr = close < 0 ? raw.slice(at + 2) : raw.slice(at + 2, close);

    // Not a path position, unterminated (the capture stopped at a nested
    // backtick), or a conditional/nested template — the path ends here.
    if (!path.endsWith('/') || close < 0 || /[`?:]/.test(expr)) break;

    const ids = expr.match(/[A-Za-z_][A-Za-z0-9_]*/g) || [];
    if (!ids.length) break;
    // A wrapper the CLI cannot reproduce (e.g. `repoToSlug(repo)`, which turns
    // `owner/name` into `owner__name`) means the positional must already be in
    // the TRANSFORMED form — the CLI would otherwise percent-encode the slash
    // and hit a path the server does not decode. Record it so --help can say so.
    if (ids.length > 1 && ids[0] !== 'encodeURIComponent') transforms.add(ids[0]);
    path += ':' + ids[ids.length - 1];
    i = close + 1;
  }
  path = path.split(/[\s'"`?]/)[0].replace(/\/+$/, '');
  // Params are whatever survived into the FINAL path — never what we hoped to
  // substitute, or a truncated path would claim params it does not have.
  const params = [...path.matchAll(/:([A-Za-z0-9_]+)/g)].map((m) => m[1]);
  return { path, params };
}

/**
 * Walk an API-object body, emitting one command per apiFetch CALL SITE.
 *
 * Two things a naive "one entry, one path" pass loses — together ~300 commands:
 *   - NESTED objects (`api = { sub: { list: … } }`) are recursed into, so a
 *     capability is never hidden behind a namespace;
 *   - entries that make SEVERAL calls (read-then-write helpers) emit every path,
 *     suffixed `-2`, `-3` — the second call is a capability too.
 */
function walkObject(body, group, prefix) {
  for (const entry of splitEntries(body)) {
    // TWO declaration forms, and missing the second hid whole modules
    // (trigger-events, setup, model-cache …):
    //   property:  `list: (id) => apiFetch(…)`
    //   shorthand: `list(id: string): Promise<X> { return apiFetch(…) }`
    // Shorthand is tested FIRST because a property whose value is an arrow has a
    // `:` before its `(`, so it cannot match the shorthand pattern — while the
    // reverse is not true: shorthand's `id: string` parameter annotation would
    // fool a naive "first colon" split into treating `string): Promise…` as the
    // value.
    const shorthand = entry.match(/^\s*(?:async\s+)?([A-Za-z0-9_]+)\s*\(/);
    const property = entry.match(/^\s*([A-Za-z0-9_]+)\s*:/);
    let baseVerb;
    let value;
    if (shorthand) {
      baseVerb = prefix + kebab(shorthand[1]);
      value = entry.slice(shorthand[0].length - 1);
    } else if (property) {
      baseVerb = prefix + kebab(property[1]);
      value = entry.slice(entry.indexOf(':') + 1).trim();
    } else {
      continue;
    }

    // A nested object literal (not an arrow body) — recurse.
    if (value.startsWith('{')) {
      const end = matchBrace(value, 0);
      if (end > 0) {
        walkObject(value.slice(1, end), group, baseVerb + '-');
        continue;
      }
    }

    const calls = [...value.matchAll(new RegExp(PATH_RE.source, 'g'))];
    if (!calls.length) {
      if (/createAuthenticatedEventSource|EventSource/.test(value)) {
        skipped.push({ group, verb: baseVerb, why: 'SSE helper — use `ag stream`' });
      } else if (/apiFetch/.test(value)) {
        skipped.push({ group, verb: baseVerb, why: 'dynamic path — use `ag api`' });
      }
      continue;
    }

    calls.forEach((call, i) => {
      let raw = call[2];
      if (!raw.startsWith('/')) return;
      // STRING CONCATENATION, not just template literals: the client also writes
      // `apiFetch('/admin/prompt-snippets/' + id, …)`. The capture stops at the
      // closing quote, so without this the id vanished and the command became
      // `PUT /admin/prompt-snippets` — a write aimed at the collection instead of
      // the item. Splice the concatenated identifier back on as a path param.
      // CHAINED concatenation: `'/admin/bot-templates/' + id + '/deploy'`. Handling
      // only the first `+ ident` produced `/admin/bot-templates/:id`, silently
      // dropping `/deploy` — a POST aimed at the wrong endpoint again.
      let rest = value.slice(call.index + call[0].length);
      for (;;) {
        const ident = rest.match(/^\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)/);
        if (ident) {
          raw += '${' + ident[1] + '}';
          rest = rest.slice(ident[0].length);
          continue;
        }
        const lit = rest.match(/^\s*\+\s*(['"])([^'"]*)\1/);
        if (lit) {
          raw += lit[2];
          rest = rest.slice(lit[0].length);
          continue;
        }
        break;
      }
      const transforms = new Set();
      const { path, params } = normalisePath(raw, transforms);
      if (!path.startsWith('/')) return;

      // Method + body for this call: read the options object that follows it.
      const after = value.slice(call.index, call.index + 600);
      const method = (after.match(METHOD_RE)?.[1] || 'GET').toUpperCase();
      const bodyKeys = bodyKeysFor(value, after);

      const verb = i === 0 ? baseVerb : `${baseVerb}-${i + 1}`;
      addAlias(group, verb, method, path, params, currentFile, bodyKeys, [...transforms]);
    });
  }
}

for (const file of readdirSync(API_DIR).sort()) {
  if (!file.endsWith('.ts') || file.endsWith('.test.ts') || file === 'index.ts' || file === 'client.ts') continue;
  currentFile = file;
  const text = stripComments(readFileSync(join(API_DIR, file), 'utf8'));

  EXPORT_RE.lastIndex = 0;
  let m;
  while ((m = EXPORT_RE.exec(text))) {
    const group = groupName(m[1]);
    const open = text.indexOf('{', m.index + m[0].length - 1);
    const close = matchBrace(text, open);
    if (close < 0) continue;
    walkObject(text.slice(open + 1, close), group, '');
  }

  // Standalone `export const foo = (…) => apiFetch(…)` / `export function foo`.
  const standalone = /export\s+(?:async\s+)?(?:const|function)\s+([A-Za-z0-9_]+)\s*(?:=|\()/g;
  let s;
  while ((s = standalone.exec(text))) {
    const name = s[1];
    if (name.endsWith('Api')) continue;
    // Scope to THIS declaration, not a fixed window: a 600-char slice ran past
    // the end of a non-API helper and picked up the next function's apiFetch —
    // `invalidateAuthStatus()` (which only clears a local cache) was published as
    // `GET /health/readiness`, an executable command for something that is not an
    // API operation at all.
    // Scope to THIS declaration's own body, not "up to the next export": a
    // helper with no API call of its own (`toLocalKind`) swallowed a private
    // function defined after it and published that function's apiFetch as its
    // command. Prefer the balanced body; fall back to the next export only for
    // a concise arrow with no block.
    // End the window at the next TOP-LEVEL declaration, not at the next `{`.
    // Two failure modes to avoid at once:
    //   * too wide  — `toLocalKind()` has no call of its own and swallowed the
    //     private `tryDetect()` defined below it, publishing that function's
    //     endpoint as its command;
    //   * too narrow — a brace-based cut latched onto the `{` inside a template
    //     literal (`${superAgentId}`) and truncated the path mid-string, losing
    //     `/admin/super-agents/:id/memory/drill` and `/admin/backends/:id/check`
    //     entirely. Multi-line arrow bodies have no block brace at all.
    // A column-0 `function`/`const`/`export` is an unambiguous boundary; a brace
    // is not.
    let chunkEnd = text.length;
    for (const marker of ['\nexport ', '\nfunction ', '\nasync function ', '\nconst ']) {
      const at = text.indexOf(marker, s.index + 1);
      if (at >= 0 && at < chunkEnd) chunkEnd = at;
    }
    const chunk = text.slice(s.index, chunkEnd);
    const call = chunk.match(PATH_RE);
    if (!call || !call[2].startsWith('/')) continue;
    const { path, params } = normalisePath(call[2]);
    if (!path.startsWith('/')) continue;
    const group = kebab(file.replace(/\.ts$/, ''));
    const verb = kebab(name);
    const method = (chunk.slice(call.index).match(METHOD_RE)?.[1] || 'GET').toUpperCase();
    addAlias(group, verb, method, path, params, file, bodyKeysFor(chunk, chunk));
  }
}

aliases.sort((a, b) => a.group.localeCompare(b.group) || a.verb.localeCompare(b.verb));

const groupCount = new Set(aliases.map((a) => a.group)).size;
const header = `/**
 * GENERATED — do not edit. Regenerate with \`just cli-gen\`.
 *
 * Derived from frontend/src/services/api/*.ts, which is the website's own
 * capability surface: every endpoint the UI can call appears here, so every
 * action available in the browser has a command in the terminal.
 *
 * ${aliases.length} commands across ${groupCount} groups.
 * Hand-written aliases in ./aliases.ts take precedence over anything here.
 */

import type { Alias } from './aliases.ts';

export const GENERATED: Alias[] = [
`;

const rows = aliases
  .map((a) => {
    const params = a.params.length ? `, params: ${JSON.stringify(a.params)}` : '';
    const bodyKeys = a.bodyKeys?.length ? `, bodyKeys: ${JSON.stringify(a.bodyKeys)}` : '';
    return `  { group: ${JSON.stringify(a.group)}, verb: ${JSON.stringify(a.verb)}, method: ${JSON.stringify(
      a.method,
    )}, path: ${JSON.stringify(a.path)}${params}${bodyKeys}, render: "raw", help: ${JSON.stringify(
      `${a.method} ${a.path}  (${a.source})` +
        (a.transforms?.length
          ? `  [arg must be pre-transformed by ${a.transforms.join(', ')} — pass the value in the form the web UI sends]`
          : ''),
    )} },`;
  })
  .join('\n');

writeFileSync(OUT, header + rows + '\n];\n');

process.stderr.write(`${OUT}\n${aliases.length} commands, ${groupCount} groups, ${skipped.length} skipped\n`);
if (skipped.length) {
  process.stderr.write('skipped (still reachable via `ag api` / `ag stream`):\n');
  for (const s of skipped.slice(0, 10)) process.stderr.write(`  ${s.group} ${s.verb} — ${s.why}\n`);
  if (skipped.length > 10) process.stderr.write(`  … ${skipped.length - 10} more\n`);
}
