# Sketch → Federated-Tesserae Chat + Manual Routing

## Bottom line

Three changes, all reusing existing infra — no new systems:

1. **Wire latest Tesserae (v0.11.0).** Nothing in Agented pins a version; `tesserae`/`tesserae_mcp` resolve via `shutil.which()` at import. The live PATH shim is stale (serves a 0.9.0 venv) while the checkout/uv-tool is 0.11.0. Fix the shim and add an explicit install/verify step so "latest" is reproducible.
2. **Federated retrieval per turn.** Add one backend function `federated_ask_tesserae(question)` beside `ask_tesserae` that shells `tesserae ask --scope federated --scope-aliases <all> --json`, and inject its output into the sketch turn via the existing `streaming_helper` RAG hook (`llm_messages.insert(-1, context_message)`). No new pipeline.
3. **Manual routing.** Routing is auto today (one user message fires create→classify→route→execute). Remove the auto-route call in `submitSketch`, add a "Route this conversation" button in `SketchChatPage.vue` that calls the already-exported `routeSketch`, gated on `status==='classified'` + a message-count threshold.

---

## 1. Tesserae version + exact wiring change

- **Latest = v0.11.0** (`Tesserae/pyproject.toml:7`, git tag `v0.11.0`). Theme: **federation** (cross-project identity-merged graph + opt-out semantic cross-links).
- **How it's wired today:** `backend/app/services/tesserae_integration.py:48` `_TESSERAE_CMD = shutil.which("tesserae") or "tesserae"`; `:196` same for `tesserae_mcp`. No pin in `pyproject.toml`/`uv.lock`/`package.json`/`justfile`/`setup.sh`. The per-project MCP binding (`_ensure_tesserae_mcp_binding`, `:221`) is consumed by the spawned **harness** subprocess, not backend Python.
- **Live inconsistency:** PATH `tesserae` → shim → `Tesserae/.venv/bin/tesserae` reports `0.9.0`, but the checkout and `uv tool list` are `0.11.0` (broken symlinks). So backend code shells a stale binary.
- **Bump:** (a) reinstall the tool so PATH `tesserae`/`tesserae_mcp` are 0.11.0 (`uv tool install --force <Tesserae checkout>` or `uv tool upgrade tesserae`); (b) add a `scripts/setup.sh` / `justfile` line that installs+verifies `tesserae --version >= 0.11.0` so other machines are reproducible; (c) keep PATH resolution (no Python-dep pin needed — it's a CLI binary). **Re-verify 0.9.0 command names still work in 0.11.0** before relying: confirmed present — `ask`, `ask --scope federated|all-registered`, `--scope-aliases`, `--semantic/--no-semantic`, `--json`, `projects list/register`. (`context --multi-pool` is the older path used by `context_tesserae`; verify it still exists in 0.11.0 or migrate to `ask`/`compile_context`.)

---

## 2. Federated retrieval mechanism + injection point

**Cross-project query path (concrete):** Tesserae federation is **never an implicit global graph** — `--scope federated` *requires* an explicit alias list. So the backend must (a) enumerate aliases, then (b) federate over them:

```
1. tesserae projects list  (or `tesserae ask ... --scope all-registered` lists by_project keys)
2. tesserae ask "<sketch query>" \
       --scope federated \
       --scope-aliases <alias1> <alias2> ... \
       --json [--no-semantic]
   → {scope:'federated', question, projects, stats, body, citations, selected_node_ids}
```

`body` + `citations` is the cross-referenced, cited answer over the identity-merged graph (no LLM required — `synthesize` defaults false). Semantic cross-project `shares_concept_with` links are on by default (needs the `semantic`/model2vec extra; degrades with a warning if absent — pass `--no-semantic` for deterministic identity-merge-only).

**Backend function (new, beside `ask_tesserae`):** `federated_ask_tesserae(question, *, top_k=5, semantic=True) -> Optional[str]` in `tesserae_integration.py`. It omits `--project`, runs `projects list` once to get aliases, then the federated `ask --json`, returns `body` (degrade-to-None on any failure, same contract as `ask_tesserae`). This is the only genuinely new code; it mirrors `ask_tesserae` exactly.

**Where it injects into the chat turn:** reuse the **existing RAG hook** in `streaming_helper.py:208-262` — the `rag_enabled` path already calls `gather_context` and does `llm_messages.insert(-1, rag['context_message'])` immediately before the last user message. This runs **before** the cliproxy/cli_agent driver branch (`:376`), so it grounds **both** drivers. For sketches:
- `execute_sketch` (`sketch_execution_service.py:256-266`) currently omits `rag_enabled`. Add a `federated_tesserae=True` flag plumbed from the sketch route so this injection is **sketch-scoped** (don't touch the shared `assemble_system_prompt`, which all super-agent sessions use).
- Build the context block from `federated_ask_tesserae(query)` and insert it via the same `insert(-1, …)` convention. **Bypass the `_NON_SELF_JUSTIFYING` gate** (`answer_pipeline_service.py:489`) for this path — a free-text sketch with `project_id=NULL` has no other source to "open the gate", so federated Tesserae facts must be injectable on their own.

---

## 3. Routing today + manual button

**Reality:** routing is **fully automatic**. `submitSketch` (`useSketchChat.ts:148-154`, comment "Auto-route after classification") pushes "Routing..." and immediately awaits `routeSketch`. Backend `route_sketch` (`leaf_crud_g.py:163-215`) doesn't stop at choosing a target — at `:205` it calls `execute_sketch(...)`, so one `/route` call **both routes and launches the SA session**. There is no button today.

**Make it manual:**
- **Disable auto-route:** remove the `useSketchChat.ts:148-154` block (the "Routing..." push + `await routeSketch`). `submitSketch` then ends at status `classified`.
- **Add button:** `routeSketch` is already exported (`useSketchChat.ts:461`), so a new handler calls it directly. Add a "Route this conversation" button in `SketchChatPage.vue` right panel near the `SketchRouting` block (~line 287). Gate: `currentSketch.status==='classified'` **AND** `messages.length >= N` ("only after enough conversation").
- **Scope = frontend-only** if manual means "click → route+execute" (backend already couples them). Only split the backend (route-without-execute) if the user wants a "preview target, then execute" two-step.

**Design gap (flag to user):** `submitSketch` creates a **new sketch per message** (`:112-118`). "Route after enough conversation" implies multiple turns on **one** sketch. Either (a) rework `submitSketch` to create-once-then-append onto the current draft, or (b) treat each send as appending content to `currentSketch` and only `create` when none exists. This is the real structural work behind the button.

---

## Ranked implementation plan

| # | Step | Files | Effort |
|---|------|-------|--------|
| 1 | Reinstall Tesserae 0.11.0 onto PATH (fix stale shim); add install+`--version` verify to setup | `scripts/setup.sh`, `justfile`; (PATH/uv-tool, no repo code) | S |
| 2 | Re-verify 0.11.0 CLI surface vs `tesserae_integration.py` calls; migrate `context --multi-pool` if changed | `backend/app/services/tesserae_integration.py` | S |
| 3 | Add `federated_ask_tesserae()` (projects list → `ask --scope federated --json`), degrade-to-None | `tesserae_integration.py` | M |
| 4 | Plumb a sketch-scoped `federated_tesserae` flag into the RAG hook; bypass `_NON_SELF_JUSTIFYING`; insert context_message | `sketch_execution_service.py`, `streaming_helper.py`, `answer_pipeline_service.py` | M |
| 5 | Rework chat to accumulate one draft sketch across turns (create-once-then-append) | `useSketchChat.ts` (`submitSketch`) | M |
| 6 | Remove auto-route block; add "Route this conversation" button gated on classified + msg-count | `useSketchChat.ts:148-154`, `SketchChatPage.vue` (~287), i18n catalogs | S |
| 7 | Tests: federated fn (mock subprocess), injection-on for sketch path, button gating; verify `just build` + targeted pytest + `npm run test:run` | backend + frontend test files | M |

---

## Open decisions (for the user)

1. **Version pinning** — leave PATH-based and just fix the stale shim, or declare an explicit install step in setup so the version is reproducible across machines? (Rec: explicit install + `--version` gate in setup.)
2. **Federation alias set** — federate over **all** registered projects (enumerate via `projects list`), or a curated/per-user allowlist (auth/scoping)? `federated` requires explicit aliases — there's no "all" shortcut. (Rec: all-registered enumerated server-side for v1, revisit scoping later.)
3. **Semantic bridging** — keep semantic cross-project links on (needs model2vec extra installed where the backend runs) or `--no-semantic` for deterministic identity-merge-only? (Rec: `--no-semantic` for v1 unless the extra is confirmed installed.)
4. **Conversation-before-route UX + threshold** — accept the create-once-then-append rework, and what is N (min messages before the Route button enables)? And: manual = "click → route+execute" (frontend-only) or "preview target, then execute" (backend split)? (Rec: append-rework, N=2, frontend-only route+execute.)
