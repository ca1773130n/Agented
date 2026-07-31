/**
 * Profile / host / credential resolution.
 *
 * Config lives at ~/.config/ag/config.json (JSON, not TOML — the whole point of
 * zero dependencies is that we already have a parser for JSON and would have to
 * hand-write one for TOML).
 *
 *   {
 *     "profile": "local",
 *     "profiles": {
 *       "local": {
 *         "backend": "http://127.0.0.1:20000",
 *         "sidecar": "http://127.0.0.1:20001",
 *         "key": "ag_live_…",
 *         "allow_remote": false
 *       }
 *     }
 *   }
 *
 * Precedence, highest first: explicit flag -> env -> config file -> default.
 */

import { homedir } from 'node:os';
import { join } from 'node:path';
import { readFileSync, writeFileSync, mkdirSync, chmodSync, statSync } from 'node:fs';

export interface Profile {
  backend: string;
  sidecar: string;
  key?: string;
  /** Guard: a non-loopback host is refused unless this is explicitly true. */
  allow_remote?: boolean;
}

export interface Config {
  profile: string;
  profiles: Record<string, Profile>;
}

export const CONFIG_DIR = join(homedir(), '.config', 'ag');
export const CONFIG_PATH = join(CONFIG_DIR, 'config.json');

const DEFAULT_PROFILE: Profile = {
  backend: 'http://127.0.0.1:20000',
  sidecar: 'http://127.0.0.1:20001',
  allow_remote: false,
};

export function loadConfig(): Config {
  try {
    const raw = JSON.parse(readFileSync(CONFIG_PATH, 'utf8')) as Partial<Config>;
    const profiles = raw.profiles ?? {};
    return {
      profile: raw.profile ?? 'local',
      profiles: Object.keys(profiles).length ? (profiles as Record<string, Profile>) : { local: { ...DEFAULT_PROFILE } },
    };
  } catch {
    return { profile: 'local', profiles: { local: { ...DEFAULT_PROFILE } } };
  }
}

export function saveConfig(cfg: Config): void {
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + '\n');
  // The file holds an API key. 0600 is not advisory.
  chmodSync(CONFIG_PATH, 0o600);
}

export interface Resolved {
  name: string;
  backend: string;
  sidecar: string;
  key?: string;
  allowRemote: boolean;
}

const LOOPBACK = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\]|0\.0\.0\.0)(:\d+)?$/i;

export function isLoopback(url: string): boolean {
  return LOOPBACK.test(url.replace(/\/+$/, ''));
}

/**
 * Resolve the active profile.
 *
 * `allow_remote` is a real guard, not decoration: this CLI exists on a machine
 * that also runs a commercial product on AWS, and a fat-fingered `--host` must
 * not be able to reach a production origin. Turning it on is a deliberate edit
 * to a 0600 file.
 */
export function resolveProfile(opts: {
  profile?: string;
  host?: string;
  key?: string;
}): Resolved {
  const cfg = loadConfig();
  const name = opts.profile ?? process.env.AG_PROFILE ?? cfg.profile ?? 'local';
  const p = cfg.profiles[name] ?? { ...DEFAULT_PROFILE };

  const backend = (opts.host ?? process.env.AG_HOST ?? p.backend ?? DEFAULT_PROFILE.backend).replace(/\/+$/, '');
  const sidecar = (process.env.AG_SIDECAR ?? p.sidecar ?? DEFAULT_PROFILE.sidecar).replace(/\/+$/, '');
  const key = opts.key ?? process.env.AG_KEY ?? p.key;
  const allowRemote = p.allow_remote === true || process.env.AG_ALLOW_REMOTE === '1';

  for (const [label, url] of [
    ['backend', backend],
    ['sidecar', sidecar],
  ] as const) {
    if (!isLoopback(url) && !allowRemote) {
      throw new ConfigError(
        `refusing to talk to a non-loopback ${label} (${url}).\n` +
          `This machine also runs production services. If you really mean it, set\n` +
          `  "allow_remote": true\n` +
          `in the "${name}" profile of ${CONFIG_PATH}, or export AG_ALLOW_REMOTE=1.`,
      );
    }
  }

  return { name, backend, sidecar, key, allowRemote };
}

export function storeKey(profileName: string, key: string): void {
  const cfg = loadConfig();
  cfg.profiles[profileName] = { ...(cfg.profiles[profileName] ?? DEFAULT_PROFILE), key };
  cfg.profile = profileName;
  saveConfig(cfg);
}

/** Warn (once, on stderr) if the config file is group/world readable. */
export function checkPerms(): string | null {
  try {
    const mode = statSync(CONFIG_PATH).mode & 0o777;
    if (mode & 0o077) return `${CONFIG_PATH} is mode ${mode.toString(8)}; it holds an API key. chmod 600 it.`;
  } catch {
    /* no config yet */
  }
  return null;
}

export class ConfigError extends Error {}
