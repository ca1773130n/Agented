# v0.5.6 State

Status: **COMPLETE** — ready for tag/release.

## Shipped — 7 upstream PRs against ca1773130n/ai-accounts

All seven open against `main`. Each adds Agented's b2ee00d~1
features additively to the existing upstream component without
breaking the public API. Pre-existing failures in upstream
`AiChatPanel.test.ts` (process groups) and `LoginStream.test.ts`
(network test) remained at 4 throughout — no regressions
introduced.

| # | PR | Component | Type | Tests added |
|---|----|----------|------|-------------|
| 1 | [ai-accounts#7](https://github.com/ca1773130n/ai-accounts/pull/7) | ChatBubble | upgrade | 8 |
| 2 | [ai-accounts#8](https://github.com/ca1773130n/ai-accounts/pull/8) | ProcessGroup | upgrade | 12 |
| 3 | [ai-accounts#9](https://github.com/ca1773130n/ai-accounts/pull/9) | MessageActions | upgrade | 8 |
| 4 | [ai-accounts#10](https://github.com/ca1773130n/ai-accounts/pull/10) | CompoundSynthesis | upgrade | 7 |
| 5 | [ai-accounts#11](https://github.com/ca1773130n/ai-accounts/pull/11) | AllModeResponses | upgrade | 9 |
| 6 | [ai-accounts#12](https://github.com/ca1773130n/ai-accounts/pull/12) | ChatModeSelector | new | 6 |
| 7 | [ai-accounts#13](https://github.com/ca1773130n/ai-accounts/pull/13) | AiChatSelector | new | 13 |

Total: 7 PRs, 63 new tests upstream.

### Per-PR additive features (highlights)

**ChatBubble (#7):** `avatarPaths?` SVG icon override, `assistantName?`
header label, `skipTransition?` mass-render opt-out, default 350ms
fade-in animation.

**ProcessGroup (#8):** `autoCollapseMs?` hover-cancellable timer,
`iconBadges?` per-type SVG icons, robust invalid-timestamp
formatting, watcher re-arms timer on re-expand.

**MessageActions (#9):** `iconButtons?` for clipboard/check/X/copy-all/
export SVGs, `MessageLike.timestamp?` fallback, dynamic `title`
per copy-state, `@click.stop`, hidden-textarea fallback path,
empty-array guards on copy-all/export, Windows-safe filenames.

**CompoundSynthesis (#10):** `sparkleIcon?` ✨ header, `loadingPlaceholders?`
pulsing "Generating synthesis..." / "Waiting for backend responses..."
for empty streaming/waiting cards.

**AllModeResponses (#11):** `summaryHeader?` global "N/total responded"
toggle, `waitingPlaceholder?` italicized fallback for empty
streaming bodies. Internal `bodyHidden`→`bodyShown` rename.

**ChatModeSelector (#12, new):** Single/All/Compound segmented
selector with `mode: ChatMode` v-model, `role="radiogroup"` ARIA
semantics, per-mode tooltips. Net-new standalone component.

**AiChatSelector (#13, new):** Backend / Account / Model / optional
ChatMode horizontal strip. Loads backends via
`useAiAccounts().client.listBackends()` directly (replaces
Agented's `listGroupedBackends` wrapper). Lazy `listModels(id)`
per kind. Picking a specific kind in all/compound mode forces
single mode.

## Deferred to v0.5.7 (or later)

**PR-8: AiChatPanel orchestrator extraction.** The Agented restored
panel is 830 lines mixing presentational composition (extractable)
with Agented-specific orchestration (entity-aware behavior, route
awareness, `Sketch`/`Agent` type references). The extraction
boundary is opinionated; pushing a PR before deciding the cut would
generate review churn. Deferred to v0.5.7+ pending design pass on
where to draw the line.

## Verification

This milestone has zero Agented source changes. Verification is the
state of the upstream PRs:

| Gate | Result |
|------|--------|
| 7 PRs open against ai-accounts:main | ✓ |
| Each PR includes additive props/features + tests | ✓ |
| Existing upstream tests not regressed | ✓ (4 pre-existing failures unchanged) |
| Upstream package CI | (will run on each PR) |

## Next steps

- **Wait for v0.5.6 PR review/merge.** Each upstream PR can be
  merged independently as the maintainer reviews. Maintainer is the
  same user who owns Agented, so review velocity is self-determined.
- **v0.5.7+ Path Y per-call-site migration.** Once the upstream PRs
  release as ai-accounts 0.3.10 (or later), Agented's 11 chat-bearing
  pages can migrate to consume the upgraded upstream directly. Each
  page's migration deletes Agented's local copy of the corresponding
  component as the upstream version reaches feature parity. Once all
  components are deleted, the local restored copies (and the type
  shims at `useAllMode.ts` / `useProcessGroups.ts`) become deletable.
- **PR-8 design pass.** AiChatPanel orchestrator extraction needs a
  separate design exercise to decide which parts move upstream.
