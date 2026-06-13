# Wireup Report

**Milestone:** v0.8.0
**Iteration:** 2
**Generated:** 2026-06-13T05:27:30.314Z

## Summary

| Metric | Count |
|--------|-------|
| Features Tested | 53 |
| Scenarios Run | 53 |
| Scenarios Passed | 42 |
| Scenarios Failed | 11 |
| Scenarios Skipped | 0 |
| Issues Found | 5 |
| Fixes Applied | 5 |
| Fixes Verified | 0 |
| Fixes Failed | 5 |
| Remaining Unwired | 11 |

## Issues Found

| # | Type | Source | Target | Confidence | Fix Status |
|---|------|--------|--------|------------|------------|
| 1 | missing-export | frontend/e2e/fixtures/mock-data.ts | frontend/e2e/fixtures/mock-data.ts | high | skipped |
| 2 | missing-export | frontend/src/components/monitoring/monitoringHelpers.ts | frontend/src/components/monitoring/monitoringHelpers.ts | high | skipped |
| 3 | missing-export | frontend/src/services/api/backend-management.ts | frontend/src/services/api/backend-management.ts | high | skipped |
| 4 | missing-export | frontend/src/test/fixtures/audits.ts | frontend/src/test/fixtures/audits.ts | high | skipped |
| 5 | missing-export | frontend/src/test/fixtures/triggers.ts | frontend/src/test/fixtures/triggers.ts | high | skipped |

## Fixes Applied

_No fixes attempted._

## Requires Manual Review

_All detected issues are high-confidence and were auto-fixed._

## Remaining Unwired Features

- MOCK_COMMANDS
- MOCK_RULES
- MOCK_AGENTS
- MOCK_SKILLS
- MOCK_DASHBOARD_SUMMARY
- geminiModelOrder
- sortWindows
- getAiAccountsClient
- mockAuditRecord
- mockTriggerWithGitHub
- mockTriggerWithWebhook

## Iteration History

| Iteration | Date | Scenarios | Passed | Failed | Skipped | Issues | Fixes | Verified |
|-----------|------|-----------|--------|--------|---------|--------|-------|----------|
| 1 | 2026-03-23 | 32 | 15 | 17 | 0 | 8 | 8 | 0 |
| 2 | 2026-06-13 | 53 | 42 | 11 | 0 | 5 | 5 | 0 |
