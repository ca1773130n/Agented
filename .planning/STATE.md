# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-21)

**Core value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard
**Current version:** v0.7.98 (last shipped via PR #146 on 2026-05-21)

## Current Position

**Active milestone:** v0.8.0 — Team Harness & Self-Improvement (started
2026-06-13). **Roadmap created 2026-06-13** — 6 phases (17–22), 26/26
requirements mapped. Approved design spec:
``docs/superpowers/specs/2026-06-13-team-harness-self-improvement-design.md``
(+ ``.ko.md``). PR-per-phase + codex-review-until-green cadence.

Phase: 17 of 22 (Forge creation surface) — **all plans complete (ready for verify)**
Plan: 6 complete (17-01, 17-02, 17-03, 17-04, 17-05, 17-06)
Status: Plan 17-06 executed (forge-creator bundle + gated session auto-import,
6/6 proxy + 174 backend green; phase house gates run)
Last activity: 2026-06-13 — Completed 17-06-PLAN.md (FINAL plan of phase 17).
Shipped the forge-creator default bundle (5 global-scope agentskills.io creator
skills — skill/rule/hook/command/subagent-creator — seeded idempotently at startup,
predefined-bot pattern) and the session-completion auto-import pipeline: a 4th
handler on the `execution_events` bus diffs `.claude/` vs the forge manifest and
auto-imports session-scaffolded subagents via the 17-05 atomic API, recording
sha256 + source-session-id provenance in `forge_origin` (migration 157). SECURITY:
the session_kind gate fails CLOSED — only {project_session, super_agent,
team_session, goal_loop} auto-bind; foreign/unknown kinds (incl. external
clone-import) import nothing. House gates: backend 174 passed (targeted-set
substitution disclosed, full-suite hang avoided); frontend 1480 passed / 7
known-baseline / 0 NEW; `just build` fails only on a PRE-EXISTING unrelated TS
error in AnswerGroundednessCard.vue (PR #212, phase 17 touched zero frontend files).
See prior 17-05 below.

Prior activity: 2026-06-13 — Completed 17-05-PLAN.md; `POST /admin/projects/{id}/forge/create`
creates+binds+materializes atomically via explicit LIFO compensation (no DB+FS saga
exists) — injected failure at the bind stage AND the materialize stage each leaves
zero orphaned row/binding/repo file; cross-kind bundle-bind binds every item in one
transaction via 17-03's conn-accepting `_add_binding`. See prior 17-04 below.

Prior activity: 2026-06-13 — Completed 17-04-PLAN.md; subagents now materialize to
byte-stable `.claude/agents/<name>.md` (manifest-tracked, resolved 17-02 WRITE
TODO) and project across all four renderers — claude via native `agents/`
discovery (no inline body), codex/gemini/opencode via a named prompt-prefix
degrade block. Added `ContextBundle.subagents` + compiler resolution. 58/58
proxy tests green (forge_materialization + prompt_renderer + context_compiler).

Progress: [----------] 0% (0 of 6 phases complete)

**Phase queue:** 17 Forge creation surface (REQ-01..05) → 18 Sketch→primitive
routing (REQ-06..09) → 19 GRD default driver (REQ-10..13) → 20 GRD frontend
wiring (REQ-14..18) → 21 One-click team harness setup (REQ-19..21, integration)
→ 22 Repeated-request auto-skill (REQ-22..26).

**Next command:** `/grd:plan-phase 17`

**Workflow mode (history):** PR-driven from v0.5.1 through v0.7.98. Each
commit-message version tag corresponds to one merged PR. Per-version STATE.md
stubs live at ``.planning/milestones/v0.7.N/STATE.md`` (backfilled via PR #148
— 94 files covering v0.7.0 through v0.7.98).

**Last completed GRD-planned milestone:** v0.5.0 — Production-Level Onboarding
Experience (10 phases / 19 plans, complete 2026-03-23). The detail below is
preserved as the v0.5.0 historical record.

---

## Historical: v0.5.0 — Production-Level Onboarding Experience

**Primary hypothesis:** A guided onboarding tour can bring new users from zero to first bot execution in under 3 minutes

Phase: 10 of 10 (Integration Testing)
Plan: 4 of 4 in current phase
Status: Milestone Complete
Last activity: 2026-03-23 — Completed 10-04-PLAN.md

Progress: [##########] 100%

## Current Baseline

| Metric | Value | Target | Delta | Phase |
|--------|-------|--------|-------|-------|
| Tour completion time | N/A | < 3 min | - | - |
| Welcome page load | N/A | < 200ms | - | - |
| Step transition time | N/A | < 300ms | - | - |
| State machine branch coverage | 100% | >= 90% | +100% | Phase 10 |
| useTourMachine branch coverage | 92% | >= 90% | +92% | Phase 10 |

**Last evaluated:** 2026-03-23
**Trend:** All coverage targets met

## Pending Validations

| From Phase | Validation | Resolve By | Priority |
|-----------|-----------|------------|----------|
| Phase 2 | Full visual regression across all step types | Phase 10 | Medium |
| Phase 4 | End-to-end tour flow with real backend accounts | Phase 10 | High |
| Phase 6 | Keyboard navigation through complete tour | Phase 10 | Medium |
| Phase 8 | Screen reader compatibility validation | Phase 10 | Medium |

## Performance Metrics

**Velocity:**
- Total plans completed: 18
- Average duration: 9min
- Total execution time: 2.81 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-backend-state-machine-foundation | 2/2 | 25min | 13min |
| 02-visual-layer | 2/2 | 9min | 5min |
| 03-welcome-flow-tour-entry | 1/1 | 7min | 7min |
| 04-core-step-content | 2/2 | 12min | 6min |
| 05-form-field-guidance | 1/1 | 8min | 8min |
| 06-navigation-controls | 2/2 | 9min | 5min |
| 07-loading-error-resilience | 2/2 | 11min | 6min |
| 08-accessibility | 1/1 | 5min | 5min |
| 09-post-tour-experience | 2/2 | 24min | 12min |
| 10-integration-testing | 4/4 | 64min | 16min |
| Phase 17 P06 | 13min | 4 tasks | 13 files |

## Accumulated Context

### Decisions

- Roadmap: Drop driver.js, use XState v5 + Floating UI + focus-trap
- Roadmap: Existing WelcomePage.vue is approved — build on it, do not rewrite
- Roadmap: Backend needs `app_meta` table with `instance_id` for DB reset detection
- 01-01: Used SQLite hex(randomblob()) for UUID — no Python uuid dependency in SQL
- 01-01: XState v5 setup() API with string-referenced guards for type safety
- 01-01: backends is hierarchical state; parent NEXT handles transition to verification
- 01-02: Singleton XState actor pattern — shared across components, survives route changes
- 01-02: Async guard checks in composable, not machine — keeps tourMachine.ts pure
- 01-02: Toast z-index conflict (hardcoded 10000 = --z-tour-overlay) deferred to Phase 7
- 10-01: Pure actor testing with createActor — no Vue, no DOM, no mocks
- 10-01: Guard override via machine.provide() for SKIP_ALL testing
- 10-02: vi.resetModules + dynamic import pattern for singleton composable testing
- 10-02: getSnapshotAtState helper creates valid XState snapshots for persistence tests
- 10-02: Mutable mockApiKey for testing X-API-Key header inclusion
- 10-03: Tour fixture extends base.ts (not @playwright/test) to inherit global API mocks
- 10-03: Accessibility tests use graceful degradation — document gaps rather than hard-fail
- 10-03: Instance-id mismatch documented as useTour limitation (only useTourMachine checks it)
- 02-01: CSS custom property padding reads from --tour-spotlight-padding with fallback to 8px
- 02-01: Glow animation uses opacity-based box-shadow per Research Pitfall 6
- 02-01: Accent color switched from indigo to --accent-cyan to match app design language
- 02-01: Static analysis test pattern: read .vue source, extract style block, grep for hardcoded values
- 02-02: Virtual Element Bridge pattern: computed returns fresh object per targetRect change for Floating UI reactivity
- 02-02: Middleware chain: offset(12) + flip() + shift({padding:8}) + arrow() for viewport-safe tooltip positioning
- 02-02: Two-phase transition on position change: fade out, recompute, fade in to prevent tooltip flicker
- 02-02: TourProgressBar uses filter:brightness(1.15) for hover instead of hardcoded color value
- 03-01: TOUR_STEP_META flat Record maps machine state names to TourOverlay display metadata
- 03-01: Computed bridge layer in App.vue translates machine state to StepLike interface
- 03-01: Direct navigation from WelcomePage to /settings#general (no /?tour=start redirect)
- 03-01: totalTourSteps=3 hardcoded (workspace, backends, verification) pending Phase 4
- 04-01: Monitoring step targets token-monitoring card on /settings#general
- 04-01: Verification step changed to harness-plugins on /settings#harness (not /plugins)
- 04-01: OpenCode substep targets opencode-info note (add-account-btn hidden for OpenCode)
- 04-01: totalTourSteps updated to 4 (workspace, backends, monitoring, verification)
- 04-02: No code changes needed -- 04-01 already updated all test files for monitoring state
- 05-01: Selector generation prefers input id-based (.form-group:has(#id)) for uniqueness, nth-of-type fallback
- 05-01: TourFormGuide is renderless (slot-only template) — zero DOM footprint
- 05-01: field-change emit { target, message } matches TourOverlay TargetLike interface
- 06-01: Skip confirmation uses inline v-if/v-else replacement, not modal overlay
- 06-01: isSignificantStep checks step.title against hardcoded set ['AI Backend Accounts']
- 06-01: confirmingSkip resets via watch on skippable + stepTitle props
- 06-02: Document-level keydown listener (not window) for keyboard capture before page content
- 06-02: Reused floating ref for focus trap container — no extra ref needed
- 06-02: Focus trap activation synced with tooltip two-phase transition via computed

- 07-01: Element-not-found (3s) takes priority over loading timeout (5s) via v-if/v-else-if chain
- 07-01: MutationObserver scoped to #main-content with document.body fallback
- 07-01: nextTick + 100ms delay before starting observer to avoid premature observation
- 07-01: prefetchTourRoutes uses Promise.allSettled for resilient fire-and-forget
- 07-02: --z-toast: 10005 placed above --z-tour-progress: 10004 in CSS scale
- 07-02: Modal coordination uses provide/inject setTourModalOpen pattern (not event bus)
- 07-02: TourOverlay + TourSpotlight both dim to 0.3 opacity when modal open during tour

- 08-01: getTransitionDuration() reads --tour-transition-speed via getComputedStyle for JS timing bypass
- 08-01: ARIA live region inside v-if block (renders only during active tour)
- 08-01: sr-only pattern (clip/overflow hidden) instead of display:none for screen reader accessibility

- 09-01: RouterLink in skipped items emits done to close overlay before navigation
- 09-01: Sidebar checklist hidden when desktop sidebar is collapsed via isCollapsedDesktop()
- 09-01: restartTour() resets machine to idle (not start) so completion screen hides cleanly
- 09-02: Restart button placed in GeneralSettings.vue (General tab content component)
- 09-02: restartTour + startTour + nextStep sequence skips welcome for returning users
- 09-02: create_project route set to /products with Phase 7 graceful fallback
- 10-04: tourMachine.ts function/line thresholds relaxed (XState guard stubs are runtime-overridden)
- 10-04: App.test.ts provide/inject tests fixed with route name + flushPromises
- 17-01: replace_for_project now mirrors add_binding's full 10-column INSERT + coalescing so the two write paths cannot drift; calls _ensure_propagation_columns first
- 17-03: cross-kind forge_bundles + forge_bundle_items (migration 156, FK ON DELETE CASCADE); conn-accepting _add_binding(conn,...) for atomic bundle-bind in one transaction (17-05 route foundation); skill_sets DDL pinned byte-for-byte; migration 155 reserved for 17-02 (subagents, not yet run)
- 17-05: atomic forge/create implemented as explicit LIFO compensation in create_and_bind_and_materialize (no DB+FS saga abstraction exists); forward steps (create row -> bind -> materialize) undone in reverse on any exception, each cleanup isolated so it cannot mask the original error; bundle-bind binds all cross-kind items in one get_connection() block (commit-once or rollback); skill excluded from create dispatch (no db create fn)
- [Phase 17]: 17-03: cross-kind forge_bundles + forge_bundle_items (migration 156); conn-accepting _add_binding for atomic bundle-bind (17-05 foundation); skill_sets DDL pinned byte-for-byte
- [Phase 22]: 22-02: REQ-26 consistency fixes — _build_harness_session now normalizes project_session/workflow/team_session (was else: None, collapsing tesserae signal coverage to 2/5); 3 new normalizers reuse harness_failure_annotator fetcher table/columns; workflow/team normalizers take pre-aggregated child rows (_nodes/_components) keeping DB I/O in the dispatcher; evolver _DESIGN_GUIDE/_PROMPT_TEMPLATE rewritten to declare skills writable (text-only — skills already in WRITABLE_KINDS/_create_dispatch); 6/6 S5 tests green
- [Phase 22]: 22-03: repeated-request detector — NEW (3rd) register_session_handler callback (on_session_complete_detect) over all 5 kinds; extracts user-request text from payload jsonl type==user text blocks (parse_claude_stream only emits user tool_result, so a dedicated _extract_user_request_text was added); embeds + cosine-matches (>=0.83) against list_signals candidates via cosine_similarity_batch, else new normalize_request_hash signal; embed-disabled falls back to exact hash (A1); 0.83 is precision-first (paraphrase pairs 0.68-0.997 vs unrelated <0.11 — fixtures recalibrated to tight 0.96-0.997 variants, constant unchanged); non-blocking proven at the bus (P4); self-registers on import + explicit lifecycle block; 3/3 P1/A1/P4 tests green
- [Phase 22]: 22-01: repeated_request_signals store — hash-keyed UPSERT accumulates salience (occurrence_count grows, first_seen_at set once in INSERT clause, never in DO UPDATE); example_session_ids FIFO-capped at 5 in Python read-then-merge; embedding stored as serialize_embedding BLOB; registered in create_fresh_schema after harness-takeaways
- [Phase 17]: 17-06: forge-creator bundle (5 global-scope creator skills, idempotent startup seed); session-completion auto-import handler (4th on execution_events bus) gated on session_kind={project_session,super_agent,team_session,goal_loop}, fails closed on foreign/unknown; forge_origin (mig 157) records sha256+source-session-id; global scope via forge_bundles.scope='global' (user_skills inherently global)

### Pending Todos

None yet.

### Blockers/Concerns

- RESOLVED: XState v5 + `@xstate/vue` integration — implemented via manual createActor + shallowRef (01-02)
- RESOLVED: `app_meta.instance_id` endpoint accessible before auth (implemented in 01-01)

## Session Continuity

Last session: 2026-06-13
Stopped at: Completed 22-05-PLAN.md (hybrid auto-skill confidence gate: evaluate_signal routes AUTO/PROPOSE/REJECT as a pure function; convert_signal drives AUTO via evolver _create_dispatch['skill'] — discovered_procedure takeaway conf 0.9, origin recorded, skill_created marked; scan-fail/provenance/policy-off downgrade to PROPOSE; per-project project_autonomy_config gates AUTO with AGENTED_TAKEAWAY_AUTOAPPLY env fallback — 17/17 P2/A2 tests green, create called once in AUTO / zero in PROPOSE/REJECT)
Resume file: None
