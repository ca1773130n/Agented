# Wireup Report

**Milestone:** v0.5.0
**Iteration:** 1
**Generated:** 2026-03-23T15:39:41.239Z

## Summary

| Metric | Count |
|--------|-------|
| Features Tested | 32 |
| Scenarios Run | 32 |
| Scenarios Passed | 15 |
| Scenarios Failed | 17 |
| Scenarios Skipped | 0 |
| Issues Found | 8 |
| Fixes Applied | 8 |
| Fixes Verified | 0 |
| Fixes Failed | 8 |
| Remaining Unwired | 17 |

## Issues Found

| # | Type | Source | Target | Confidence | Fix Status |
|---|------|--------|--------|------------|------------|
| 1 | missing-export | frontend/e2e/fixtures/mock-data.ts | frontend/e2e/fixtures/mock-data.ts | high | skipped |
| 2 | missing-export | frontend/e2e/fixtures/tour.ts | frontend/e2e/fixtures/tour.ts | high | skipped |
| 3 | missing-export | frontend/src/test/fixtures/audits.ts | frontend/src/test/fixtures/audits.ts | high | skipped |
| 4 | missing-export | frontend/src/test/fixtures/triggers.ts | frontend/src/test/fixtures/triggers.ts | high | skipped |
| 5 | missing-export | frontend/src/webmcp/generic-tools.ts | frontend/src/webmcp/generic-tools.ts | high | skipped |
| 6 | missing-export | frontend/src/webmcp/test-harness/random-runner.ts | frontend/src/webmcp/test-harness/random-runner.ts | high | skipped |
| 7 | missing-export | frontend/src/webmcp/test-harness/state-verifier.ts | frontend/src/webmcp/test-harness/state-verifier.ts | high | skipped |
| 8 | missing-export | frontend/src/webmcp/test-harness/tool-weights.ts | frontend/src/webmcp/test-harness/tool-weights.ts | high | skipped |

## Fixes Applied

_No fixes attempted._

## Requires Manual Review

_All detected issues are high-confidence and were auto-fixed._

## Remaining Unwired Features

- MOCK_HOOKS
- MOCK_COMMANDS
- MOCK_RULES
- MOCK_AGENTS
- MOCK_SKILLS
- MOCK_DASHBOARD_SUMMARY
- TourPage
- mockFinding
- mockFindings
- mockAuditRecord
- mockExecutionStatus
- mockTriggerWithGitHub
- mockTriggerWithWebhook
- getConsoleErrors
- DEFAULT_CONFIG
- parseToolResponse
- DEFAULT_WEIGHTS

## Iteration History

| Iteration | Date | Scenarios | Passed | Failed | Skipped | Issues | Fixes | Verified |
|-----------|------|-----------|--------|--------|---------|--------|-------|----------|
| 1 | 2026-03-23 | 32 | 15 | 17 | 0 | 8 | 8 | 0 |
