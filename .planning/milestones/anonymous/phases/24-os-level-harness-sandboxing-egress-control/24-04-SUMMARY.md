# 24-04 SUMMARY — cloud_sandbox_runner.py

**Status:** DONE. `backend/app/services/cloud_sandbox_runner.py` + `tests/test_cloud_sandbox_runner.py` (9), green.

- `select_runner(*, risk, config)`: LocalRunner by default; E2BRunner when E2B_API_KEY + highest-risk;
  ModalRunner when MODAL_TOKEN_ID+MODAL_TOKEN_SECRET + highest-risk; low-risk always local.
- Absent creds ⇒ graceful fallback to LocalRunner + logged skip. e2b/modal imported LAZILY inside
  adapters — no ImportError when absent (verified: `python -c "import ...cloud_sandbox_runner"` OK).
- Wired into competitor_strategy.start_autoimplement + harness_autonomy.process_project_autonomy;
  local path reproduces today's goal-loop exactly (no regression).
- pyproject: e2b/modal pinned as optional `[cloud-sandbox]` extras, not runtime deps.

**Test tier:** L1 selection + absent-cred skip; live E2B/Modal round-trip is L3 (needs creds, out of CI).
