# Harness sandboxing & egress control

**Languages:** English (canonical) · [한국어](./sandboxing.ko.md)

Phase 24 confines every harness `subprocess.Popen` to an OS sandbox and routes its
outbound network through a deny-by-default egress proxy, gated by the Phase-23
`enforce_sandbox` policy. This runbook covers the model, how to operate it, its v1
ceiling, and the verification gates.

## 1. Sandbox model

The single builder `app/services/sandbox_wrap.py:build_sandbox_prefix(cmd,
workspace, *, net=False, proxy_url=None)` returns an argv **prefix** plus a
`sandboxed: bool` — it is prepended exactly like `stdbuf`, so the existing `Popen`
stays put (no second launcher).

- **Linux** → [`bwrap`](https://github.com/containers/bubblewrap) (bubblewrap): the
  workspace is `--bind` read-write, everything else `--ro-bind` read-only, with
  `--unshare-all --share-net` (isolated pid/ipc/uts namespaces but shared network so
  the child can reach the local proxy) and `--die-with-parent`.
- **macOS** → `sandbox-exec -p <SBPL>`: a seatbelt profile that is `(deny default)`,
  reads broadly, writes only inside the workspace (+ `TMPDIR` + `/dev`), and denies
  network except the egress proxy.

**Workspace-only writes.** Any write outside the workspace is refused ("Operation
not permitted"). A write inside the workspace succeeds — it is a boundary, not a
blanket block.

**Availability & degrade.** `sandbox_available()` = `shutil.which(tool)` **and** a
cached runtime probe (on Linux this catches `kernel.unprivileged_userns_clone=0`,
where `bwrap` is present but unusable). When no usable sandbox exists,
`build_sandbox_prefix` degrades **in place** to `(cmd, sandboxed=False)` and logs a
single warning — it never raises. The `enforce_sandbox` gate then decides
launch-vs-refuse (see §3).

**Feature flag.** Live wrapping at the harness launch sites is opt-in via
`AGENTED_SANDBOX` (default off). When off, `wrap_harness_command` is a no-op
pass-through, so normal operation is unchanged until an operator enables it. A
policy that mandates `enforce_sandbox` while the flag is off refuses every launch
(fail closed) — enable the flag to satisfy it.

## 2. Egress control

`app/services/egress_proxy.py` is a tiny stdlib-`asyncio` **deny-by-default**
forward proxy on an ephemeral loopback port. It filters on the cleartext `CONNECT`
host (the TLS SNI host is visible without any MITM) and on the plain-HTTP
`Host:`/absolute-form line:

- host in the per-run allowlist → `200 Connection Established` + a bidirectional
  byte pump;
- host **not** in the allowlist → `403 Forbidden` + a structured deny log
  `{session_id, host, port, action: "deny"}`.

**Per-run allowlist.** Set `AGENTED_EGRESS_ALLOWLIST` (comma-separated hosts) to
override. When unset, the conservative required set is `github.com`,
`api.github.com`, `api.anthropic.com`. An **empty** allowlist blocks everything —
the correct deny-by-default posture for autonomous / auto-implement runs.

**Env injection.** `proxy_env(handle)` yields `HTTPS_PROXY`/`HTTP_PROXY` = the proxy
url plus a **non-bypassing** `NO_PROXY` (`127.0.0.1,localhost` — never a `*`).
`execution_runner.build_subprocess_env(..., proxy_url=...)` merges these so the
child's HTTP(S) clients route through the proxy and match the sandbox's egress rule.

## 3. The `enforce_sandbox` gate (Phase 23)

At the launch boundary, `execution_service._apply_sandbox_and_enforce` wraps the
command, then calls `PolicyService.enforce_launch(..., sandboxed=<real flag>)`
**before** `Popen`. The `enforce_sandbox` builtin **denies** when a policy requires
a sandbox and the launch is not sandboxed:

- sandbox degraded / disabled ⇒ `sandboxed=False` ⇒ **`PolicyDenied` raised, the
  process never starts** (fail closed);
- real sandbox engaged ⇒ `sandboxed=True` ⇒ launch proceeds.

Author the policy with `PolicyService.create_policy(scope=..., kind="enforce_sandbox",
effect="deny", params={"require_sandbox": True})`.

## 4. Optional cloud runners (E2B / Modal)

For the two highest-risk fully-autonomous consumers — competitive-intel
auto-implement (`competitor_strategy_service.start_autoimplement`) and life-harness
autonomy (`harness_autonomy.process_project_autonomy`) —
`cloud_sandbox_runner.select_runner(risk, config)` picks an offboard sandbox:

- default → `LocalRunner` (the local OS sandbox above);
- `E2BRunner` when `E2B_API_KEY` is set AND the run is highest-risk;
- `ModalRunner` when `MODAL_TOKEN_ID` + `MODAL_TOKEN_SECRET` are set AND highest-risk.

**Graceful skip.** Absent credentials degrade to `LocalRunner` with a logged skip —
never a crash. The `e2b`/`modal` SDKs are imported **lazily** inside the adapters, so
a cloud-less install never hits `ImportError`. They are pinned as optional extras:
`pip install '.[cloud-sandbox]'`.

## 5. Ceiling & upgrade path

**v1 egress is env + proxy BEST-EFFORT.** `bwrap` keeps `--share-net` (host network
namespace) and only injects `HTTPS_PROXY`/`HTTP_PROXY`; a hostile child could unset
those or dial a raw IP. The escape tests prove the configured boundary holds for a
**cooperating** client — not that a hostile process cannot bypass env vars.

- **Airtight no-bypass egress** → an unprivileged network namespace (`--unshare-net`
  with the proxy bound inside it) + `nftables` forcing all egress to the proxy port.
  Deferred to a later wave.
- **URL-path / body filtering** → a `mitmproxy` addon (cert injected into the sandbox
  CA bundle). Deferred; the homegrown CONNECT proxy is the deliberate v1 choice
  (no TLS interception, no cert store, no extra dependency).

Do **not** claim airtight enforcement — document the ceiling honestly.

## 6. House-gate runbook

Before shipping a change that touches this layer:

1. `just build` (vue-tsc type checking + vite build).
2. `cd backend && uv run pytest` under a ~12-minute watchdog. The full serial suite
   has a known hang at ~40–48%; on hang, kill it and run a comprehensive targeted
   set — the sandbox suites plus execution/streaming/harness regressions:
   ```bash
   uv run pytest tests/test_sandbox_wrap.py tests/test_egress_proxy.py \
     tests/test_cloud_sandbox_runner.py tests/test_sandbox_escape.py \
     tests/test_enforce_sandbox_gate.py tests/test_sandbox_wiring.py \
     tests/test_policy_harness_gates_23.py tests/test_execution_service.py -q
   ```
   Disclose the substitution in the PR; never present a targeted run as the full suite.
3. `cd frontend && npm run test:run` — gate is **no NEW failures** (baseline carries
   7 known pre-existing failures).

`test_sandbox_escape.py` is `@skipif(not sandbox_available())`: it runs on a host
with a usable `bwrap`/`sandbox-exec` (proving the FS + egress boundaries hold) and
skips cleanly where neither exists.
