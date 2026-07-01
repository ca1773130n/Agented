# 24-03 SUMMARY — wire sandbox + egress + enforce_sandbox

**Status:** DONE. `tests/test_enforce_sandbox_gate.py` (3) + `tests/test_sandbox_wiring.py` (2), green.

- `execution_service._apply_sandbox_and_enforce`: OS-sandbox-wrap at the stdbuf chokepoint, set the
  REAL `sandboxed` flag on `PolicyService.enforce_launch` (no longer hardcoded False), evaluate BEFORE
  Popen. enforce_sandbox DENY + sandboxed=False ⇒ PolicyDenied, Popen never reached (fail closed).
- Per-run `ThreadedEgressProxy` (opt-in via AGENTED_SANDBOX); `build_subprocess_env(..., proxy_url=)`
  merges proxy_env so HTTPS_PROXY/HTTP_PROXY match the sandbox setenv. Torn down in run_trigger finally.
- Defense-in-depth sweep: conversation_streaming (x2), cli_agent_runner, setup_execution,
  base_generation, replay all route cmd through `wrap_harness_command`. Sweep test asserts no bare
  harness Popen remains.

**CONTRACT NOTE:** wired against the ACTUAL merged Phase-23 API (`PolicyService.enforce_launch` +
`PolicyDenied` + `enforce_sandbox` builtin, sandboxed= param) — NOT the plan's hypothetical
`enforce_action`/`PolicyContext`/`eval_enforce_sandbox` contract, which never landed on disk.
Regressions: policy_harness_gates_23 / policy_enforcement / execution_service / cli_agent / streaming green.
