"""Shared streaming helper for LLM response generation.

Extracted from super_agent_chat.py to be reusable by both the Playground
chat endpoint and the Sketch execution service.
"""

import logging
import threading
import traceback
from typing import Callable, Optional

from ..db import harness_evidence
from .chat_state_service import ChatStateService
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


def _mark_account_rate_limited(candidate, rl_info) -> None:
    """Persist a rate limit for the candidate's account so the scheduler /
    next turn skips it. Uses the provider's parsed reset time when present,
    else a default cooldown. A candidate with no local account id (the
    default-vault fallback) can't be marked — nothing to do."""
    if candidate.account_id is None:
        return
    try:
        from .account_rotation_service import DEFAULT_COOLDOWN_SECONDS
        from .rate_limit_service import RateLimitService

        if rl_info.reset_at:
            RateLimitService.mark_blocked_until(
                candidate.account_id, rl_info.reset_at, rl_info.reason
            )
        else:
            RateLimitService.mark_rate_limited(candidate.account_id, DEFAULT_COOLDOWN_SECONDS)
        logger.info(
            "Marked account %s (%s) rate-limited until %s",
            candidate.account_id,
            candidate.display_name,
            rl_info.reset_at or f"+{1}h",
        )
    except Exception:
        logger.warning("Failed to mark account rate-limited", exc_info=True)


def _record_tool_use_evidence(session_id: str, super_agent_id, event) -> None:
    """Best-effort: persist a ToolUseEvent to the evidence ledger (Phase 2 P3).
    Never raises — a ledger write must not disrupt streaming."""
    try:
        harness_evidence.record_tool_use(
            session_id,
            super_agent_id=super_agent_id,
            tool_name=event.name,
            tool_input=event.input,
            tool_use_id=event.id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("evidence ledger write failed for %s: %s", session_id, e)


def _clean_model_label(raw: str, backend: Optional[str]) -> str:
    """Turn a raw model id into a compact pill label for the chat bubble.

    Drops a provider path prefix (``opencode/glm-4.7-free`` -> ``glm-4.7-free``)
    and a trailing date stamp (``claude-sonnet-4-20250514`` -> ``claude-sonnet-4``),
    then drops a leading provider token that just duplicates the backend already
    shown as the bubble's author (``claude-sonnet-4`` with backend ``claude`` ->
    ``sonnet-4``). Conservative on purpose — no aggressive title-casing that
    would mangle acronyms like GPT / GLM.
    """
    import re

    s = raw.split("/")[-1]
    s = re.sub(r"-\d{6,}$", "", s)
    if backend:
        head = s.split("-", 1)[0].lower()
        if head == backend.lower() and "-" in s:
            s = s.split("-", 1)[1]
    return s


def _resolve_finish_model(model: Optional[str], backend: Optional[str]) -> Optional[str]:
    """Resolve the model to show on a finish/persisted assistant turn.

    A requested ``model`` passes through (cleaned). When none was requested —
    the routed super-agent / default case — resolve the backend's default model
    (mirrors the cliproxy resolution in ``conversation_streaming``) so the
    bubble shows the concrete model that answered instead of a blank pill.
    Best-effort: never raises (runs on the streaming background thread).
    """
    raw = model
    if not raw:
        try:
            from .conversation_streaming import _get_default_model

            raw = _get_default_model(backend or "claude")
        except Exception:
            logger.debug("finish-model resolution failed", exc_info=True)
            raw = None
    if not raw:
        return None
    try:
        return _clean_model_label(raw, backend)
    except Exception:
        return raw


def run_streaming_response(
    session_id: str,
    super_agent_id: str,
    backend: str,
    account_id: Optional[str] = None,
    model: Optional[str] = None,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
    cwd: Optional[str] = None,
    chat_mode: Optional[str] = None,
    instance_id: Optional[str] = None,
    use_cli_agent: Optional[bool] = None,
    retry_attempts: int = 0,
    rag_enabled: bool = False,
    rag_project_id: Optional[str] = None,
) -> None:
    """Launch a background thread that streams an LLM response.

    ``retry_attempts`` carries the rate-limit retry count forward when the
    scheduler re-dispatches a queued turn, so the MAX_ATTEMPTS cap actually
    advances across "account frees → re-limited" cycles instead of resetting.

    Assembles system prompt, builds message history, calls stream_llm_response(),
    pushes content_delta chunks via ChatStateService (SSE), persists the
    assistant message, and updates backend last used.

    Args:
        session_id: The session to stream into.
        super_agent_id: The super agent generating the response.
        backend: LLM backend type (e.g., 'claude', 'litellm').
        account_id: Optional account for API key resolution (passed as account_email).
        model: Optional model override.
        on_complete: Called after successful completion (no args).
        on_error: Called on error with (error_message: str).
        cwd: Optional working directory for CLI subprocess (work mode).
        chat_mode: Optional chat mode ('management' or 'work').
        instance_id: Optional project SA instance ID for project context.
        use_cli_agent: When ``True``, route through the CLI agent runner
            (claude/codex/gemini subprocess with tool privileges) instead
            of CLIProxyAPI. When ``None`` (default), reads the global
            ``agent_yolo_mode`` setting — on by default. Pass ``False``
            to force CLIProxyAPI even when YOLO is globally on (the
            ai-accounts chat panel uses this to keep its pure-token
            flow).
    """
    _session_id = session_id
    _super_agent_id = super_agent_id

    # Register the session in ChatStateService synchronously, BEFORE the
    # streaming thread is spawned. The frontend opens its SSE immediately
    # after the POST that triggered us returns; if the session isn't
    # already registered, `ChatStateService.subscribe()` yields a
    # "Session not found" error event and closes the stream. The user
    # sees that as a "Connection lost" toast on the panel.
    #
    # `init_session` is idempotent — when the caller (project chat,
    # super-agent session create) already registered the session it's a
    # no-op. Doing this here covers every caller of `run_streaming_response`
    # in one place: sketches, playground chat, autofix, agent chats.
    ChatStateService.init_session(_session_id)

    def _stream_response():
        try:
            from .cli_agent_runner_service import (
                is_yolo_mode_enabled,
                resolve_account_config_dir,
                resolve_execution_driver,
                stream_via_cli_agent,
            )
            from .conversation_streaming import (
                ThinkingEvent,
                ToolUseEvent,
                stream_llm_response,
            )

            ChatStateService.push_status(_session_id, "streaming")

            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id,
                _session_id,
                chat_mode=chat_mode,
                instance_id=instance_id,
            )
            # Build LLM messages: system prompt first, then conversation log
            state = SuperAgentSessionService.get_session_state(_session_id)
            from .conversation_filters import drop_empty_content_messages

            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                llm_messages.extend(drop_empty_content_messages(state["conversation_log"]))

            # Derive the last user turn text from the assembled messages list.
            _last_user_content = ""
            for _msg in reversed(llm_messages):
                if _msg.get("role") == "user":
                    _last_user_content = _msg.get("content") or ""
                    break

            # --- Agentic-RAG hook (Task 3) -----------------------------------
            # Runs AFTER llm_messages is built, BEFORE the routing branch.
            # Fail-open: any exception → log + plain turn.
            _rag_chunks: list = []
            if rag_enabled and rag_project_id:
                try:
                    from .answer_pipeline_service import corpus_health as _corpus_health
                    from .answer_pipeline_service import gather_context as _gather_context

                    _health = _corpus_health(rag_project_id)
                    if not _health["healthy"]:
                        # Per-project corpus-health gate: a corpus too thin to
                        # help makes the RAG pipeline net-negative (answer-eval
                        # run 6), so skip it entirely — saves planner/fanout/
                        # sufficiency cost and avoids degrading the answer. The
                        # per-query injection gate is the finer backstop.
                        logger.info(
                            "RAG skipped for %s: thin corpus (%d < %d durable items)",
                            rag_project_id,
                            _health["total"],
                            _health["min_items"],
                        )
                        ChatStateService.push_delta(
                            _session_id,
                            "retrieval",
                            {"skipped": "thin_corpus", "corpus_items": _health["total"]},
                        )
                    else:
                        ChatStateService.push_delta(_session_id, "planning", {"status": "started"})
                        rag = _gather_context(
                            rag_project_id,
                            _last_user_content,
                            backend=backend,
                            account_email=account_id,
                        )
                        ChatStateService.push_delta(
                            _session_id,
                            "retrieval",
                            {
                                "chunks": len(rag["chunks"]),
                                "iterations": rag["iterations"],
                                "sufficient": rag["sufficient"],
                            },
                        )
                        if rag.get("context_message"):
                            # Insert BEFORE the final user message (which is
                            # already the last entry in llm_messages).
                            llm_messages.insert(-1, rag["context_message"])
                        _rag_chunks = rag["chunks"]
                except Exception:
                    logger.warning(
                        "answer pipeline failed — falling back to baseline", exc_info=True
                    )
                    _rag_chunks = []
            # -----------------------------------------------------------------

            def _finalize(accumulated: list, used_backend: str) -> None:
                full_response = "".join(accumulated)
                # Resolve the concrete model that answered (the request often
                # omits it for routed super-agent turns) so the bubble shows a
                # model pill, not just the backend name.
                finish_model = _resolve_finish_model(model, used_backend)
                if full_response:
                    SuperAgentSessionService.add_assistant_message(
                        _session_id, full_response, backend=used_backend, model=finish_model
                    )
                    if used_backend:
                        try:
                            from ..db.backends import update_backend_last_used

                            update_backend_last_used(used_backend)
                        except Exception:
                            logger.error("Failed to update backend last used", exc_info=True)
                ChatStateService.push_delta(
                    _session_id,
                    "finish",
                    {"content": full_response, "backend": used_backend, "model": finish_model},
                )
                ChatStateService.push_status(_session_id, "idle")
                if on_complete:
                    on_complete()

                # --- Post-finish: extract facts + push citations delta --------
                # Best-effort; arrives AFTER finish by design (extraction is an
                # LLM call — the visible turn must not wait). The frontend
                # attaches late citations to the LAST assistant message (Task 5).
                if _rag_chunks and full_response:
                    try:
                        from ..db import extracted_facts as _ef
                        from .answer_pipeline_service import _default_llm_call
                        from .answer_pipeline_service import (
                            extract_facts_from_answer as _extract_facts,
                        )

                        _llm_call = _default_llm_call(
                            backend=used_backend, account_email=account_id
                        )
                        facts = _extract_facts(full_response, _rag_chunks, llm_call=_llm_call)
                        if facts:
                            _ef.insert_facts(
                                _session_id,
                                super_agent_id=_super_agent_id,
                                project_id=rag_project_id,
                                facts=facts,
                            )
                        citations = [
                            {"kind": c.source, "value": c.provenance_key} for c in _rag_chunks
                        ]
                        ChatStateService.push_delta(
                            _session_id,
                            "citations",
                            {
                                "message_scope": "last_assistant",
                                "citations": citations,
                                "facts": facts,
                            },
                        )
                    except Exception:
                        logger.warning(
                            "post-finish fact extraction failed for session %s",
                            _session_id,
                            exc_info=True,
                        )
                # ---------------------------------------------------------------

            # The cliproxy conversational path is byte-identical to its
            # pre-19-05 form; it is extracted into this closure ONLY so the
            # grd-conversational fallthrough can share the exact same code
            # path (no duplicate-and-diverge). Do NOT edit its body — the
            # byte-identity is success-criterion-3 (cliproxy regression).
            def _run_cliproxy() -> None:
                # CLIProxy path — single attempt (it marks its own rate
                # limits in conversation_streaming; cross-account retry for
                # this path is a follow-up).
                stream_iter = stream_llm_response(
                    llm_messages,
                    model=model,
                    account_email=account_id,
                    backend=backend,
                    cwd=cwd,
                    chat_mode=chat_mode,
                )
                accumulated = []
                for chunk in stream_iter:
                    if isinstance(chunk, ToolUseEvent):
                        ChatStateService.push_delta(_session_id, "tool_use", chunk.to_dict())
                        _record_tool_use_evidence(_session_id, _super_agent_id, chunk)
                        continue
                    if chunk:
                        accumulated.append(chunk)
                        ChatStateService.push_delta(
                            _session_id, "content_delta", {"content": chunk}
                        )
                _finalize(accumulated, backend)

            # Routing decision lives in `resolve_execution_driver` so the
            # three streaming sites (this one, design conversations, project
            # chat) make the same choice. It returns one of
            # "cliproxy" | "cli_agent" | "grd". Best-effort project_id from
            # the session row feeds the precedence chain; the resolver
            # tolerates None and degrades grd→cli_agent when GRD/workspace
            # is unavailable, so a missing project_id never crashes the turn.
            _project_id = None
            try:
                if state:
                    _project_id = state.get("project_id")
            except Exception:
                _project_id = None
            driver = resolve_execution_driver(
                backend=backend,
                use_cli_agent=use_cli_agent,
                super_agent_id=_super_agent_id,
                project_id=_project_id,
                instance_id=instance_id,
            )

            if driver == "cliproxy":
                _run_cliproxy()
                return

            if driver == "grd":
                # GRD branch (REQ-11): classify the turn. Conversational
                # turns fall BACK through the SAME cliproxy block (shared, not
                # duplicated). Task turns dispatch the grd_chat handler and
                # bridge its PSM stream-json output onto chat SSE deltas.
                # Any failure degrades to the cliproxy/cli_agent path rather
                # than dropping the turn.
                try:
                    from .turn_classifier_service import classify_turn

                    classification = classify_turn(
                        _last_user_content, backend_kind=backend, model_override=model
                    )
                    if classification.get("shape") != "task":
                        _run_cliproxy()
                        return

                    from .execution_type_handler import get_handler
                    from .grd_chat_bridge import bridge_psm_to_chat
                    from .project_session_manager import ProjectSessionManager

                    handler = get_handler("grd_chat")
                    if handler is None:
                        logger.warning("grd_chat handler missing; degrading to cli_agent")
                    else:
                        # Subscribe to raw PSM events BEFORE starting the
                        # session — raw subscribers do not replay history, so
                        # registering first guarantees no early events are lost.
                        result = handler.start(
                            {
                                "project_id": _project_id,
                                "task": _last_user_content,
                                "intent": classification.get("intent"),
                                "grd_command": classification.get("grd_command"),
                                "super_agent_id": _super_agent_id,
                            }
                        )
                        grd_session_id = (result or {}).get("session_id")
                        if not grd_session_id:
                            logger.warning(
                                "grd_chat start returned no session_id (%s); "
                                "degrading to cli_agent",
                                result,
                            )
                        else:
                            raw_q = ProjectSessionManager.subscribe_raw(grd_session_id)

                            def _psm_events():
                                while True:
                                    event_type, data = raw_q.get()
                                    if event_type == "__end__":
                                        return
                                    payload = dict(data or {})
                                    payload.setdefault("type", event_type)
                                    yield payload

                            # Past this point the GRD session is RUNNING, so a
                            # failure must NOT degrade to cli_agent: that path
                            # would execute the same task a second time while
                            # the GRD session kept going, double-billing the
                            # user and interleaving two answers into one
                            # bubble. Surface the failure as an error delta and
                            # stop. Degrading is only safe *before* the spawn.
                            try:
                                bridge_psm_to_chat(
                                    _session_id,
                                    _psm_events(),
                                    ChatStateService,
                                    backend=backend,
                                    model=_resolve_finish_model(model, backend),
                                    grd_session_id=grd_session_id,
                                )
                            except Exception:
                                logger.warning(
                                    "GRD bridge failed for session %s after the GRD "
                                    "session had started; reporting an error rather "
                                    "than re-running the task",
                                    _session_id,
                                    exc_info=True,
                                )
                                ChatStateService.push_delta(
                                    _session_id,
                                    "error",
                                    {"error_message": "GRD session stream failed"},
                                )
                                ChatStateService.push_status(_session_id, "error")
                            finally:
                                ProjectSessionManager.unsubscribe_raw(grd_session_id, raw_q)
                            if on_complete:
                                on_complete()
                            return
                except Exception:
                    logger.warning(
                        "GRD task dispatch failed for session %s; falling through "
                        "to the legacy path",
                        _session_id,
                        exc_info=True,
                    )
                # Fall through to the cli_agent block below (degrade). Only
                # reachable BEFORE a GRD session spawned — see above.

            # ---- CLI-agent path with rate-limit rotation --------------------
            # When an account hits a provider rate limit (429 / weekly cap),
            # rotate to the next eligible account — same backend first, then
            # other backends — and retry the turn. A 429 fires with zero
            # output tokens, so we only rotate when nothing has streamed yet;
            # that guarantees a retry never duplicates assistant text.
            from .account_rotation_service import (
                RateLimitEvent,
                RotationCandidate,
                rotation_candidates,
                soonest_reset_message,
            )

            attempts = rotation_candidates(backend, exclude_account_ids=set())
            # Honor an explicit account pick by trying it first.
            requested_cfg = resolve_account_config_dir(account_id, backend)
            if requested_cfg:
                for i, cand in enumerate(attempts):
                    if cand.config_dir == requested_cfg:
                        attempts.insert(0, attempts.pop(i))
                        break
            if not attempts:
                # No eligible local accounts at all — fall back to the CLI's
                # default vault (preserves behavior when no accounts are
                # registered). A single attempt; no rotation possible.
                attempts = [
                    RotationCandidate(
                        account_id=None,
                        backend=(backend or "").lower(),
                        config_dir=requested_cfg,
                        display_name="default",
                    )
                ]

            attempted_ids: set = set()
            prev_name = None
            last_reason = None
            for idx, cand in enumerate(attempts):
                if cand.account_id is not None:
                    if cand.account_id in attempted_ids:
                        continue
                    attempted_ids.add(cand.account_id)

                if idx > 0:
                    logger.info(
                        "Chat rotation: %s rate-limited → trying %s (%s)",
                        prev_name,
                        cand.display_name,
                        cand.backend,
                    )
                    ChatStateService.push_delta(
                        _session_id,
                        "rotation",
                        {
                            "from": prev_name,
                            "to": cand.display_name,
                            "backend": cand.backend,
                            "reason": last_reason or "rate limit reached",
                        },
                    )
                prev_name = cand.display_name

                logger.info(
                    "Streaming via CLI agent runner (backend=%s, cwd=%s, config=%s, account=%s)",
                    cand.backend,
                    cwd,
                    cand.config_dir,
                    cand.display_name,
                )
                stream_iter = stream_via_cli_agent(
                    llm_messages,
                    backend=cand.backend,
                    cwd=cwd,
                    yolo=is_yolo_mode_enabled(),
                    model=model,
                    config_dir=cand.config_dir,
                )

                accumulated = []
                rl_info = None
                for chunk in stream_iter:
                    if isinstance(chunk, RateLimitEvent):
                        rl_info = chunk.info
                        break  # stop consuming this account; rotate
                    if isinstance(chunk, ThinkingEvent):
                        ChatStateService.push_delta(_session_id, "thinking", chunk.to_dict())
                        continue
                    if isinstance(chunk, ToolUseEvent):
                        ChatStateService.push_delta(_session_id, "tool_use", chunk.to_dict())
                        _record_tool_use_evidence(_session_id, _super_agent_id, chunk)
                        continue
                    if chunk:
                        accumulated.append(chunk)
                        ChatStateService.push_delta(
                            _session_id, "content_delta", {"content": chunk}
                        )

                if rl_info is not None and not accumulated:
                    # Rate-limited before any content → record + rotate.
                    last_reason = rl_info.reason
                    _mark_account_rate_limited(cand, rl_info)
                    continue

                # Success (or content already streamed before a late limit).
                _finalize(accumulated, cand.backend)
                return

            # Every eligible account is rate-limited.
            msg = soonest_reset_message(backend)

            def _surface_rate_limit_error() -> None:
                ChatStateService.push_delta(
                    _session_id, "error", {"error": msg, "kind": "rate_limited"}
                )
                ChatStateService.push_status(_session_id, "error")
                if on_error:
                    on_error(msg)

            # Park the turn for scheduler auto-retry ONLY when it's safe to:
            #  (a) it's a pure chat turn — no on_complete/on_error side effects.
            #      The queue persists routing args, not caller callbacks, so a
            #      redispatch can't re-run them; queuing a sketch/autofix/
            #      delegation turn would strand its status. Those surface an
            #      error so their on_error fires instead.
            #  (b) at least one registered account exists that could free up.
            #      With no accounts (the default-vault fallback, account_id=None)
            #      rotation_candidates() is always empty, so a queued row would
            #      never dispatch or expire — "queued" forever. Surface an error.
            had_real_account = any(c.account_id is not None for c in attempts)
            can_queue = on_complete is None and on_error is None and had_real_account
            if not can_queue:
                logger.warning(
                    "Chat: all accounts rate-limited for backend=%s — surfacing error "
                    "(pure_chat=%s, has_account=%s)",
                    backend,
                    on_complete is None and on_error is None,
                    had_real_account,
                )
                _surface_rate_limit_error()
                return

            # Persistent retry queue — the chat_retry_queue scheduler job
            # re-dispatches once a cooldown expires (survives restarts).
            try:
                from .chat_retry_service import ChatRetryService

                ChatRetryService.enqueue(
                    session_id=_session_id,
                    super_agent_id=_super_agent_id,
                    backend=backend,
                    account_id=account_id,
                    model=model,
                    cwd=cwd,
                    chat_mode=chat_mode,
                    instance_id=instance_id,
                    use_cli_agent=use_cli_agent,
                    reason=last_reason or msg,
                    attempts=retry_attempts,
                )
                logger.warning(
                    "Chat: all accounts rate-limited for backend=%s — turn queued", backend
                )
                ChatStateService.push_delta(
                    _session_id,
                    "queued",
                    {"message": msg, "reason": last_reason or msg},
                )
                # Stop the spinner; the queued notice tells the user it will
                # auto-resume. The scheduler re-dispatch re-enters streaming.
                ChatStateService.push_status(_session_id, "idle")
            except Exception:
                logger.warning("Failed to queue chat retry; surfacing error instead", exc_info=True)
                _surface_rate_limit_error()

        except Exception as e:
            error_msg = str(e)
            logger.exception("Streaming error for session %s", _session_id)
            from app.services.error_capture import capture_error

            capture_error(
                category="streaming_error",
                message=error_msg,
                stack_trace=traceback.format_exc(),
                context={"session_id": _session_id, "super_agent_id": _super_agent_id},
            )
            # v0.7.7: emit an activity event so the inspector timeline
            # surfaces model-streaming failures. Best-effort — must never
            # break the runtime.
            try:
                from app.services import super_agent_activity_service

                super_agent_activity_service.record(
                    super_agent_id=_super_agent_id,
                    session_id=_session_id,
                    event_type="error",
                    payload={
                        "source": "streaming_helper",
                        "backend": backend,
                        "model": model,
                    },
                    status="error",
                    error_message=error_msg,
                )
            except Exception:
                logger.warning(
                    "Failed to record super-agent streaming-error activity",
                    exc_info=True,
                )
            try:
                ChatStateService.push_delta(_session_id, "error", {"error": error_msg})
                ChatStateService.push_status(_session_id, "error")
            except Exception:
                logger.exception("Failed to propagate streaming error for session %s", _session_id)

            if on_error:
                on_error(error_msg)

    thread = threading.Thread(target=_stream_response, daemon=True)
    thread.start()
