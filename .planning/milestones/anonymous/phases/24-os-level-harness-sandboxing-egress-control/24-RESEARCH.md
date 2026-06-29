# Phase 24: OS-level harness sandboxing + egress control — Research

**Researched:** 2026-06-30
**Domain:** OS sandboxing (bwrap/seatbelt), L7 egress control, cloud sandboxes (E2B/Modal), security
**Confidence:** HIGH (codebase contracts confirmed; primitives verified against current docs/wiki)

## Summary

Phase 24 wraps the central harness `subprocess.Popen` in an OS sandbox (bubblewrap on
Linux, `sandbox-exec`/SBPL on macOS) and forces all child egress through a tiny local
deny-by-default forward proxy injected via `HTTPS_PROXY`/`HTTP_PROXY`. The existing
`sandbox_eval.py` already establishes the pattern to generalize: scrubbed-env allowlist,
workspace-only filesystem boundary, process-group kill, graceful in-place degrade. The
new code is a single reusable **sandbox-command-prefix builder** (`sandbox_wrap.py`) that
returns an argv prefix (`["bwrap", ...]` / `["sandbox-exec", "-p", profile]`) prepended at
the one chokepoint in `execution_service.py` (right where `stdbuf` is already prepended,
L617-621, immediately before `subprocess.Popen` L767). Egress is enforced by a ~60-line
asyncio CONNECT-proxy (`egress_proxy.py`) plus blocking direct egress in the sandbox so the
proxy can't be bypassed. The Phase-23 `enforce_sandbox` verdict gates whether an
**unsandboxed** launch is admitted: the launch path sets `PolicyContext.sandbox_enabled`
from whether the wrapper actually engaged, then calls `enforce_action` pre-Popen; a DENY
raises `PolicyDeniedError` and the process never starts. Cloud runners (E2B/Modal) are an
opt-in execution target for the highest-risk autonomous consumers, behind absent-credential
graceful skip.

**Primary recommendation:** Build one `sandbox_wrap.build_sandbox_prefix(cmd, *, workspace, egress_allowlist, proxy_addr) -> (prefix_argv, sandboxed: bool)` + one stdlib asyncio `egress_proxy.py`; wrap at the single `execution_service` chokepoint; set `PolicyContext.sandbox_enabled` from the real result and call the Phase-23 `enforce_action` before Popen. Prefer the homegrown asyncio proxy over mitmproxy.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. Constraints carried from the task brief:
- **Ponytail/lazy bias:** stdlib + at most one small dep. Prefer a ~60-line asyncio
  allowlist CONNECT proxy over adding mitmproxy. Name the ceiling + upgrade path.
- Backend: Python 3.10+, Litestar, raw sqlite (no ORM), ruff line-length=100.
- macOS is dev (darwin), Linux is prod. BOTH paths must exist; degrade gracefully where a
  primitive is missing.
- Any cloud/LLM feature must degrade gracefully without credentials (E2B/Modal key absent →
  skip, not crash).

## Confirmed Integration Points (codebase, verified)

| Point | File:Line | Role in Phase 24 |
|-------|-----------|------------------|
| **Chokepoint to wrap** | `execution_service.py` build_command L466; `stdbuf` prepend L617-621; **`subprocess.Popen` L767** (`cwd=effective_cwd`, `start_new_session=True`, `env=proc_env`) | Prepend sandbox prefix exactly where `stdbuf` is prepended; this is THE lazy/DRY wrap site |
| Env builder | `execution_runner.py:build_subprocess_env` L380 (returns `{**os.environ, **overrides}`) | Inject `HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY` here (or in the prefix builder) |
| Pattern to generalize | `sandbox_eval.py`: `_scrubbed_env()` L53 (`_ENV_ALLOWLIST` PATH/HOME/LANG/…), `_neutralize_escaping_symlinks` L73, `_popen_run` L96 (own process group + SIGKILL), `IsolatedResult.sandboxed` flag | Reuse env-scrub allowlist + the `sandboxed: bool` reporting convention |
| Defense-in-depth Popen sites | `conversation_streaming.py` L834,L961; `cli_agent_runner_service.py` L92; `setup_execution_service.py` L70; `base_generation_service.py` L46; `replay_service.py` L111 | Route each through the shared prefix builder (sweep — see Pitfall 1) |
| Cloud consumers (REQ-33) | `competitor_strategy_service.py:start_autoimplement` L336 (→`goal_loop_runner.start_runner`); `harness_autonomy.py:autonomous_apply_eligible` L41 / `process_project_autonomy` L147 | Set runner-selection = cloud when configured + highest-risk |

## Phase-23 Policy Contract (from 23-0x-PLAN.md — this phase REQUIRES it)

> **Note:** Phase-23 artifacts are PLANNED, not yet on disk. Phase 24 depends on them. The contract below is the locked interface from the phase-23 plans.

- `app/models/policy.py`: `PolicyVerdict(ALLOW/DENY/ASK)`, `PolicyScope(server/team/session)`,
  `PolicyType(... enforce_sandbox ...)`, `PolicyDecision(verdict, reason, ...)`.
- `policy_service.py`: `PolicyContext` **dataclass** carrying `action: str` (e.g. `"sandbox"`/
  `"shell"`/process-launch), `tool_name: str|None`, **`sandbox_enabled: bool`**,
  `approved_ask_ids: set[str]`; `PolicyEvaluator.evaluate_action(ctx) -> PolicyDecision`
  (session→team→server, first DENY short-circuits).
- `policy_builtins.py:eval_enforce_sandbox`: **DENY when the action requires sandbox and
  `ctx.sandbox_enabled is False`; ALLOW when True.**
- `policy_enforcement.py:enforce_action(ctx, *, execution_id=None, broadcast=None)`:
  DENY ⇒ raise `PolicyDeniedError(reason, policy_id)` WITHOUT running the guarded action;
  ASK ⇒ create pending request + emit `POLICY_ASK_EVENT` + block; ALLOW ⇒ pass through.
  Phase-23 already inserts `enforce_action` at the pre-Popen boundary in `start_setup`.

**Phase-24 seam:** after computing `(prefix, sandboxed)` from the wrapper, set
`ctx.sandbox_enabled = sandboxed`, then call `enforce_action(ctx)` BEFORE Popen. If the OS
sandbox degraded (`sandboxed=False`) and an `enforce_sandbox` DENY policy applies, the
launch is refused — satisfying criterion 4.

## Paper-Backed / Authoritative Recommendations

### Rec 1: Bubblewrap (bwrap) on Linux
**Recommendation:** Wrap with `bwrap` building a tmpfs root: workspace `--bind` rw,
everything else `--ro-bind`, `--unshare-all` then drop net, with the proxy reachable.
**Argv prefix (concrete):**
```
bwrap \
  --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
  --ro-bind /etc/resolv.conf /etc/resolv.conf --ro-bind /etc/ssl /etc/ssl \
  --symlink usr/bin /bin   # (only if /bin is a symlink on the distro) \
  --proc /proc --dev /dev --tmpfs /tmp \
  --bind <WORKSPACE> <WORKSPACE> \
  --chdir <WORKSPACE> \
  --unshare-all --share-net          # keep net so the child can reach the LOCAL proxy \
  --die-with-parent \
  --setenv HTTPS_PROXY http://127.0.0.1:<PORT> --setenv HTTP_PROXY http://127.0.0.1:<PORT> \
  -- <CMD...>
```
**Egress note:** Full `--unshare-net` would cut the child off from the proxy too. Choices:
(a) keep `--share-net` and rely on the proxy + a firewall/`NO_PROXY` discipline (deny-by-default
at the proxy; the proxy is the only allowed destination), OR (b) `--unshare-net` + run the proxy
INSIDE the same net namespace bound to a unix socket / loopback. **Recommend (a)** for v1
(simpler, no root): the proxy is deny-by-default and the env forces all HTTP(S) clients through
it; document that a fully airtight version needs netns+nftables (upgrade path). For true
no-bypass, additionally run the child as a uid that an nftables rule confines to the proxy port
— defer to a later wave.
**Detection + degrade:** `shutil.which("bwrap")` AND a probe `bwrap --ro-bind / / true` (catches
kernels with unprivileged userns disabled — `kernel.unprivileged_userns_clone=0`). On failure:
log a warning, return `(cmd, sandboxed=False)`; the `enforce_sandbox` policy then decides
launch-vs-refuse. **Confidence:** HIGH (ArchWiki/man bwrap; pattern matches Chrome/flatpak/agent
sandboxes).

### Rec 2: macOS seatbelt via `sandbox-exec -p <SBPL>`
**Recommendation:** Generate an SBPL profile string; `["sandbox-exec", "-p", profile, *cmd]`.
**SBPL profile (concrete):**
```scheme
(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow sysctl-read)
(allow file-read*)                                  ; reads broadly; tighten later
(deny file-write*)
(allow file-write* (subpath "<WORKSPACE>"))
(allow file-write* (subpath "/private/var/folders"))  ; TMPDIR
(allow file-write* (subpath "/dev"))
(deny network*)
(allow network* (remote ip "localhost:<PORT>"))     ; only the local egress proxy
```
**Caveats (verified):** `sandbox-exec` is **deprecated but present** and actively used by
Chrome/OpenAI/Anthropic agent tooling. In SBPL **deny always wins over allow regardless of
order**. **Detection:** `shutil.which("sandbox-exec")` (always present on macOS) + a probe run.
Degrade like bwrap. **Confidence:** MEDIUM-HIGH (deprecated API; well-trodden in practice).

### Rec 3: L7 egress — homegrown asyncio CONNECT allowlist proxy (NOT mitmproxy)
**Recommendation:** A ~60-90 line stdlib `asyncio` forward proxy. Parse the first request
line; for HTTPS the client sends `CONNECT host:443 HTTP/1.1` (the host is in cleartext even
for TLS — no MITM/cert needed). Check `host` against the per-session allowlist:
- in allowlist → reply `HTTP/1.1 200 Connection Established\r\n\r\n`, then bidirectionally
  pump bytes (`asyncio.open_connection` + two `copy()` tasks).
- not in allowlist → reply `HTTP/1.1 403 Forbidden\r\n\r\n`, log `{session, host, action:"deny"}`,
  close.
For plain HTTP, parse the `Host:` header / absolute-form request line and apply the same check.
**Why homegrown over mitmproxy:** deny-by-default CONNECT filtering needs no TLS interception,
no cert store, no extra dep, and is trivially testable in CI. **Ceiling/upgrade path:** can't
filter by URL path or inspect TLS-encrypted bodies; for that, upgrade to mitmproxy addon (cert
injected into the sandbox CA bundle) — note it, don't build it now.
**No-bypass:** the sandbox sets `HTTPS_PROXY/HTTP_PROXY` (Rec 1/2) AND, for true enforcement,
blocks direct egress (netns+nftables, deferred). v1 relies on env + the proxy being the only
reachable destination. **Allowlist default:** for autonomous / auto-implement runs, deny-by-default
(empty allowlist + a small required set: github.com, api.anthropic.com, registry hosts as
configured). **Confidence:** HIGH (CONNECT host is cleartext; standard pattern).

### Rec 4: Cloud sandbox runners (E2B / Modal) — optional, credential-gated
**Recommendation:** A `cloud_sandbox_runner.py` with a thin `select_runner(risk, config)`:
local OS-sandbox by default; cloud when configured AND consumer is highest-risk
(competitive-intel auto-implement, life-harness autonomy). Absent credentials → log + fall
back to local (graceful skip), never crash.
**E2B (`pip install e2b`):**
```python
from e2b import Sandbox
sbx = Sandbox.create(timeout=300)          # api_key defaults to E2B_API_KEY env
res = sbx.commands.run('...'); print(res.stdout)
sbx.kill()
```
**Modal (`pip install modal`):**
```python
import modal
app = modal.App.lookup("agented-sandbox", create_if_missing=True)
sb = modal.Sandbox.create(app=app)         # auth via `modal token` / MODAL_TOKEN_*
p = sb.exec("bash", "-lc", "...", timeout=300); print(p.stdout.read())
sb.terminate()
```
**Auth env:** E2B → `E2B_API_KEY`; Modal → `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` (or
`modal token set`). Gate on these being present. **Confidence:** MEDIUM (SDK surfaces verified
vs current docs; pin versions at plan time).

## Standard Stack

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| bubblewrap (`bwrap`) | system pkg | Linux OS sandbox | unprivileged, standard (flatpak/Chrome) |
| `sandbox-exec` | macOS builtin | macOS OS sandbox | only no-extra-install option; used by agent tooling |
| Python `asyncio`+`ssl` (stdlib) | 3.10+ | egress CONNECT proxy | zero new deps, deny-by-default, CI-testable |
| `e2b` | latest (pin) | optional cloud sandbox | simplest sandbox API; `E2B_API_KEY` |
| `modal` | latest (pin) | optional cloud sandbox | `Sandbox.create`/`.exec`; GA Jan 2025 |

**Alternatives considered:** mitmproxy (L7 URL filtering — heavier, deferred upgrade);
netns+nftables (true no-bypass egress — needs root, deferred); App Sandbox entitlements
(needs signed app bundle — wrong tool for spawning CLIs).

**Install:** `bwrap` via distro pkg in prod image; `pip install e2b modal` as optional extras.

## Architecture Patterns

### Recommended module layout
```
backend/app/services/
├── sandbox_wrap.py      # NEW: build_sandbox_prefix(cmd, *, workspace, allowlist, proxy_addr)
│                        #      -> (prefix_argv, sandboxed: bool); bwrap+SBPL builders + detect
├── egress_proxy.py      # NEW: asyncio deny-by-default CONNECT/HTTP allowlist proxy + start/stop
├── cloud_sandbox_runner.py  # NEW: select_runner() + E2B/Modal adapters (graceful skip)
├── sandbox_eval.py      # REUSE _scrubbed_env / sandboxed-flag convention
└── execution_service.py # EDIT: prepend prefix at L617-621 site; set ctx.sandbox_enabled; enforce_action pre-Popen
```

### Pattern: prefix-builder, not a new launcher
Return an argv PREFIX + a `sandboxed: bool`; the existing Popen stays. Mirrors the `stdbuf`
prepend already in place — minimal, DRY, reversible.

### Anti-patterns
- **Don't** add a second Popen path / rewrite ExecutionService — prepend a prefix.
- **Don't** `--unshare-net` AND inject a loopback proxy without putting the proxy in the same
  netns — the child can't reach it. (See Rec 1 egress note.)
- **Don't** rely on env-only egress as "enforcement" without saying so — env can be unset by
  the child. Document v1 as best-effort; netns+nftables is the airtight upgrade.

## Don't Hand-Roll

| Problem | Don't build | Use | Why |
|---------|-------------|-----|-----|
| FS isolation | custom chroot/seccomp | bwrap / sandbox-exec | userns + mount setup is a footgun |
| env scrub | new allowlist | `sandbox_eval._scrubbed_env` | already correct + tested |
| process-group kill | manual | existing `_popen_run` pattern | already handles orphans |
| TLS MITM filtering | parse TLS | CONNECT host check (cleartext) | host visible without MITM; only build MITM if path-filtering is needed |

## Common Pitfalls

### Pitfall 1: Missing a Popen site (defense-in-depth)
Wrapping only `execution_service` leaves `conversation_streaming`/`cli_agent_runner`/`setup`/
`base_generation`/`replay` unsandboxed. **Avoid:** route every harness Popen through
`build_sandbox_prefix`. **Detect:** test grepping for `subprocess.Popen` in services asserts
each call site imports/uses the wrapper (matches the repo's "sweep the bug class" rule).

### Pitfall 2: Unprivileged userns disabled
`shutil.which("bwrap")` passes but `bwrap` fails at runtime when
`kernel.unprivileged_userns_clone=0`. **Avoid:** probe-run at detect; cache result. **Sign:**
"bwrap: setting up uid map: Permission denied".

### Pitfall 3: Proxy bypass
Child unsets `HTTPS_PROXY` or connects by IP. **Avoid v1:** document best-effort; **airtight:**
netns + nftables forcing all egress to the proxy port (deferred wave). Tests must NOT claim
airtight enforcement for the env-only path.

### Pitfall 4: macOS deny-wins
A broad `(deny network*)` overrides a later `(allow network* ...)` only if you forget that deny
always wins — structure as `(deny network*)` + a specific `(allow network* (remote ...))`, which
DOES work because the allow is more specific. Test both allow-host and deny-host on macOS.

## Experiment / Test Design

**Independent var:** sandbox availability (present/absent), egress host (allowlisted/denied),
policy verdict (ALLOW/DENY), runner (local/cloud).
**Dependent:** process launched? files written outside workspace? host reached? logged?

| Test | Tier | How |
|------|------|-----|
| prefix composition (bwrap) | L1 | assert argv contains `--bind <ws>`, `--unshare-all`, proxy setenv — no real bwrap needed |
| prefix composition (SBPL) | L1 | assert profile has `(deny network*)`, `(allow file-write* (subpath ws))` |
| degrade path | L1 | monkeypatch `which`→None ⇒ returns `(cmd, sandboxed=False)` + warning |
| egress allowlist pass | L2 | start proxy on ephemeral port; client `CONNECT allowed:443` ⇒ 200; tunnels to a local echo server |
| egress denied block | L2 | `CONNECT evil.test:443` ⇒ 403 + deny log |
| enforce_sandbox DENY | L2 | seed `enforce_sandbox` DENY + `sandboxed=False` ⇒ `enforce_action` raises `PolicyDeniedError`, Popen NOT called (sentinel) |
| runner selection | L1 | config without `E2B_API_KEY`/`MODAL_*` ⇒ `select_runner`→local; with creds+high-risk⇒cloud |
| cloud absent-cred skip | L1 | no creds ⇒ graceful local fallback, no exception |
| **escape attempt (crit 5)** | L3 (skip-if-unavailable) | inside a real wrapped harness on a host WITH bwrap/sandbox-exec: attempt `echo x > /etc/x` (write outside ws) AND `CONNECT non-allowlisted` ⇒ both blocked + logged; `@skipUnless(sandbox_available)` |

**CI reality:** bwrap/seatbelt may be absent → L1/L2 are deterministic (assert composed argv/env;
fake the proxy with a local server); L3 escape test marked skip-if-unavailable.

## Verification Strategy

| Item | Tier | Rationale |
|------|------|-----------|
| sandbox prefix argv/SBPL correct | L1 Sanity | pure string assertion |
| degrade returns `sandboxed=False`+warns | L1 | monkeypatch |
| egress allow-pass / deny-block | L2 Proxy | local proxy + echo server, no network |
| enforce_sandbox DENY refuses unsandboxed launch | L2 | integration with policy stub |
| real OS escape blocked (crit 5) | L3 Deferred | needs real bwrap/seatbelt; skip-if-unavailable |
| house gates | — | `just build`; backend pytest (watchdog); frontend no-new-failures |

## Production Considerations

- **Performance:** bwrap startup is sub-ms; SBPL compile is cheap. Proxy adds one localhost hop.
- **DNS:** keep `/etc/resolv.conf` ro-bound (bwrap) so name resolution works inside the sandbox.
- **Secrets:** vault secrets are injected via `build_subprocess_env`; the OS sandbox + deny-by-default
  egress reduces exfil surface, but env-only egress is best-effort (see Pitfall 3).
- **Cloud cost/latency:** E2B/Modal add seconds + $; reserve for highest-risk autonomous runs only.

## Recommended Decomposition into Plans/Waves (planner: lift directly)

- **24-01 sandbox_wrap.py** — `build_sandbox_prefix` with bwrap + SBPL builders, detection +
  probe, degrade-to-`sandboxed=False`. Tests: L1 argv/SBPL composition + degrade. (No policy dep.)
- **24-02 egress_proxy.py** — asyncio deny-by-default CONNECT/HTTP allowlist proxy + lifecycle;
  inject `HTTPS_PROXY/HTTP_PROXY/NO_PROXY` via `build_subprocess_env`/prefix. Tests: L2 allow/deny.
- **24-03 wire into execution_service + sweep** — prepend prefix at the `stdbuf` site; set
  `PolicyContext.sandbox_enabled`; call `enforce_action` pre-Popen; route the other 5 Popen sites
  through the builder. Tests: enforce_sandbox-DENY-refuses-unsandboxed (crit 4) + sweep test.
- **24-04 cloud_sandbox_runner.py** — `select_runner` + E2B/Modal adapters, credential-gated;
  wire as target for `competitor_strategy.start_autoimplement` + `harness_autonomy`. Tests:
  selection + absent-cred skip (crit 3).
- **24-05 escape verification + docs** — L3 skip-if-unavailable escape test (crit 5); operator
  docs (EN + `*.ko.md` per repo i18n rule); house gates.

> Dependency: 24-03/24-05 require Phase-23 policy artifacts on disk. If Phase 23 is unmerged at
> plan time, 24-03 must stub `PolicyContext`/`enforce_action` against the locked contract above.

## Open Questions

1. **Airtight egress (no env bypass) in v1?** Recommend v1 = env+proxy (best-effort, documented);
   netns+nftables airtight path as a later wave. Confirm acceptable for autonomous runs.
2. **bwrap in the prod image?** Needs adding to the deploy image + unprivileged-userns enabled.
   Flag for the deployment phase (26).
3. **Cloud runner workspace sync** — E2B/Modal need the worktree synced in/out; confirm the
   goal-loop worktree contract with `goal_loop_runner.start_runner` at plan time.

## Sources

### Primary (HIGH)
- Bubblewrap — ArchWiki Examples + `bwrap(1)` man (mankier/Debian): `--ro-bind`/`--bind`/`--tmpfs`/
  `--dev`/`--proc`/`--unshare-all`/`--die-with-parent`/`--setenv`.
- E2B Python SDK docs (`Sandbox.create`, `commands.run`, `E2B_API_KEY`, default timeout 300s).
- Modal Sandboxes docs (`App.lookup`, `Sandbox.create`, `.exec(timeout=)`; GA Jan 2025).
- Codebase: `sandbox_eval.py`, `execution_service.py` (L466/617/767), `execution_runner.py` L380,
  Phase-23 plans 23-01/02/03 (policy contract).

### Secondary (MEDIUM)
- macOS sandbox-exec / SBPL references (HackTricks, dnesting SBPL reference, 7402.org folder-write
  example; deprecated-but-present; deny-wins quirk).
- asyncio HTTPS/CONNECT proxy patterns (Duponchelle; pproxy/proxy2 as reference impls).

## Metadata

**Confidence breakdown:** stack HIGH; bwrap HIGH; SBPL MEDIUM-HIGH (deprecated); egress proxy
HIGH; cloud SDKs MEDIUM (pin at plan time); policy seam HIGH (contract locked).
**Research date:** 2026-06-30 · **Valid until:** ~30 days (pin E2B/Modal versions at plan).
