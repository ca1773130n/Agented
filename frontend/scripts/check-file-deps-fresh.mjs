#!/usr/bin/env node
/**
 * Pre-dev hook: invalidate Vite's bundled-deps cache when any `file:`-pinned
 * dependency's `dist/` is newer than the cache metadata.
 *
 * Vite pre-bundles `file:` deps once into `node_modules/.vite/deps/` and
 * holds them in memory across the dev server's lifetime. After we rebuild
 * `@ai-accounts/*` dist (e.g. via `just ai-accounts-dist-fresh`), the
 * cached bundle is stale. This script detects that case and clears
 * `.vite/deps/` so the next `vite` start re-bundles.
 *
 * Runs from `npm run dev` (via `predev`). Exit 0 always — never block dev
 * even if the heuristic fails.
 */
import { readFileSync, statSync, rmSync, existsSync, readdirSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");
const VITE_CACHE = join(ROOT, "node_modules", ".vite");
const PKG_JSON = join(ROOT, "package.json");

function readPkg() {
  try {
    return JSON.parse(readFileSync(PKG_JSON, "utf8"));
  } catch {
    return null;
  }
}

function newestMtime(dir) {
  if (!existsSync(dir)) return 0;
  let max = 0;
  const stack = [dir];
  while (stack.length) {
    const cur = stack.pop();
    let entries;
    try {
      entries = readdirSync(cur, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      const p = join(cur, e.name);
      try {
        const s = statSync(p);
        if (e.isDirectory()) stack.push(p);
        else if (s.mtimeMs > max) max = s.mtimeMs;
      } catch {
        /* ignore */
      }
    }
  }
  return max;
}

function viteCacheMtime() {
  if (!existsSync(VITE_CACHE)) return 0;
  // Use the metadata file as the cache bookkeeping signal; falls back to
  // the cache dir's own mtime if metadata isn't there yet.
  const meta = join(VITE_CACHE, "deps", "_metadata.json");
  if (existsSync(meta)) {
    try {
      return statSync(meta).mtimeMs;
    } catch {
      /* fall through */
    }
  }
  try {
    return statSync(VITE_CACHE).mtimeMs;
  } catch {
    return 0;
  }
}

function main() {
  const pkg = readPkg();
  if (!pkg) return;
  const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
  const fileDeps = Object.entries(deps).filter(([, v]) => typeof v === "string" && v.startsWith("file:"));
  if (fileDeps.length === 0) return;

  const cacheMtime = viteCacheMtime();
  if (cacheMtime === 0) return; // no cache yet — nothing to invalidate

  for (const [name, spec] of fileDeps) {
    const target = resolve(ROOT, spec.replace(/^file:/, ""), "dist");
    const distMtime = newestMtime(target);
    if (distMtime > cacheMtime) {
      console.log(
        `[predev] ${name} dist newer than .vite cache — clearing deps cache`,
      );
      try {
        rmSync(join(VITE_CACHE, "deps"), { recursive: true, force: true });
      } catch (e) {
        console.warn(`[predev] cache clear failed: ${e.message}`);
      }
      return; // one clear is enough
    }
  }
}

main();
