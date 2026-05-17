"""Skill conversation service for interactive skill creation with SSE streaming."""

import datetime
import hashlib
import json
import logging
import os
import secrets
import shutil
import string
import tempfile
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

from app.models.common import error_response

from ..database import (
    add_user_skill,
    create_skill_conversation,
    delete_skill_conversation,
    get_skill_conversation,
    get_user_skill,
    list_active_skill_conversations,
    upsert_skill_conversation,
)
from .skill_discovery_service import get_playground_working_dir

# Stale conversation cleanup threshold (30 minutes)
STALE_CONVERSATION_THRESHOLD = 1800

# System prompt for skill creation conversation. v0.7.77 — teaches
# claude to emit the full multi-file package shape (Anthropic Skills
# spec) so the wizard can write a real package, not just SKILL.md.
SKILL_CREATION_SYSTEM_PROMPT = """You are an AI assistant helping to create a Claude Code **Skill package**. A skill package is a directory under ``.claude/skills/<skill-name>/`` containing:

* ``SKILL.md`` — the entry point. Starts with YAML frontmatter, followed by the body of instructions Claude reads when the skill is active.
* ``scripts/`` (optional) — executable helpers Claude invokes via Bash when the skill is active (Python scripts, shell scripts).
* ``references/`` (optional) — long-form reference docs Claude loads on demand. The SKILL.md body should mention these files by their relative path (``See references/api-cheatsheet.md``).
* ``assets/`` (optional) — static files (templates, fixtures, data samples).

Guide the user through defining:

1. **Skill name** — kebab-case (``code-review``, ``data-explorer``).
2. **Description** — one-sentence summary surfaced in the frontmatter (helps Claude decide when to load the skill).
3. **Allowed tools** (optional) — restricts which Claude Code tools the skill may invoke (``Bash``, ``Read``, ``Glob``, ``Grep``, ``Write``, ``Edit``). Omit for unrestricted.
4. **License + tags** (optional) — defaults to MIT, no tags.
5. **Body** — the operational instructions Claude follows. Should reference any helpers / references the package ships.
6. **Helper scripts** (optional) — executable code the skill needs. Always include a shebang line.
7. **Reference docs** (optional) — supporting material Claude loads on demand.

Ask clarifying questions and propose helpers / references when they'd make the skill more useful. Suggest specific filenames so the package feels coherent.

When you have gathered enough information, summarize the package and ask the user to confirm.

When the user confirms, output the final configuration in this exact format — a single JSON object between the markers, NO other text inside the markers:

---SKILL_CONFIG---
{
  "skill_name": "data-explorer",
  "frontmatter": {
    "description": "Explore tabular datasets and surface key stats.",
    "license": "MIT",
    "allowed_tools": ["Bash", "Read", "Glob"],
    "tags": ["data", "analytics"]
  },
  "body": "Markdown body of SKILL.md, no frontmatter delimiters.\\n\\nReference scripts/profile.py to summarize a dataset.",
  "files": [
    {
      "path": "scripts/profile.py",
      "content": "#!/usr/bin/env python3\\n\\\"\\\"\\\"Dataset profiler.\\\"\\\"\\\"\\nimport sys, csv\\n..."
    },
    {
      "path": "references/column-spec.md",
      "content": "# Column-spec syntax\\n..."
    }
  ]
}
---END_CONFIG---

Rules for the config:

* ``skill_name`` is required, kebab-case.
* ``frontmatter.description`` is required. Other frontmatter keys are optional.
* ``body`` is required.
* ``files`` is optional; each entry's ``path`` MUST start with ``scripts/``, ``references/``, or ``assets/`` and must not contain ``..``. Each file is capped at 256 KB; total package capped at 50 files. The wizard rejects packages that violate.

Start by asking the user what kind of skill they want to create."""


# v0.7.77 — skill-package validation knobs. Each file 256 KB max so
# the LLM can't pump a wall of generated code into one binding;
# total file count cap so a hallucinated package full of imaginary
# helpers can't flood the disk. Path prefix allowlist enforces the
# Anthropic Skills convention.
_FILE_BYTE_CAP = 256 * 1024
_MAX_FILES = 50
_ALLOWED_PATH_PREFIXES = ("scripts/", "references/", "assets/")
_ALLOWED_FRONTMATTER_KEYS = {"description", "license", "allowed_tools", "tags"}
_SKILL_NAME_RE = __import__("re").compile(r"^[a-z][a-z0-9-]{0,63}$")


class _SkillConfigError(Exception):
    """Raised by ``_build_package_preview`` when the config block is
    malformed or violates a cap. Carries an error code + HTTP status
    so the route can translate cleanly via ``error_response``.
    """

    def __init__(self, code: str, message: str, status: HTTPStatus):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class ConversationMessage:
    """A message in a skill creation conversation."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: str


class SkillConversationService:
    """Service for managing skill creation conversations with real-time SSE streaming."""

    # In-memory conversation state: {conv_id: {'messages': [ConversationMessage], 'processing': bool}}
    _conversations: Dict[str, dict] = {}
    # SSE subscribers: {conv_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    # Track conversation start times for cleanup
    _start_times: Dict[str, datetime.datetime] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def _generate_conv_id(cls) -> str:
        """Generate a unique conversation ID."""
        chars = string.ascii_lowercase + string.digits
        return "skill_" + "".join(secrets.choice(chars) for _ in range(16))

    @classmethod
    def start_conversation(
        cls, user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Start a new skill creation conversation.

        v0.7.78 (codex BLOCK 1+2) — captures caller's ``user_id``
        so subsequent conv-id operations can enforce ownership and
        ``/active`` can scope to the operator's own conversations.
        """
        conv_id = cls._generate_conv_id()

        # Initialize in-memory state
        initial_messages = [
            ConversationMessage(
                role="system",
                content=SKILL_CREATION_SYSTEM_PROMPT,
                timestamp=datetime.datetime.now().isoformat(),
            )
        ]

        # v0.7.76 — append the kickoff user message BEFORE
        # ``_process_with_claude`` runs. The prior implementation
        # passed the kickoff string as a parameter that was never
        # added to ``conv["messages"]``; the LLM call then saw
        # only the system prompt with no user message, and the
        # upstream rejected with "text content blocks must be
        # non-empty" (no user message → empty user content block
        # in the OpenAI-format translation).
        kickoff = ConversationMessage(
            role="user",
            content="Hello, I'd like to create a new skill.",
            timestamp=datetime.datetime.now().isoformat(),
        )
        initial_messages.append(kickoff)

        with cls._lock:
            cls._conversations[conv_id] = {
                "messages": initial_messages,
                "processing": False,
                # v0.7.78 (codex BLOCK 2) — ownership stamped on
                # the in-memory cache so the ownership check on
                # every conv-id endpoint doesn't need a DB read.
                "user_id": user_id,
                # v0.7.81 (issue #124 / WARN 3) — defer the
                # kickoff LLM call until the first SSE subscriber
                # connects so early frames aren't broadcast into
                # an empty subscriber set.
                "needs_kickoff": True,
            }
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # v0.7.78 — write through to DB so refresh / backend
        # restart can resume. The kickoff is included in
        # ``initial_messages`` so a resumed conversation (post-
        # crash, post-restart) already has the user turn needed
        # for the next LLM call (closes issue #124 / WARN 1 for
        # this service; skill was already persisting the kickoff
        # via this call). Failures are logged but don't block
        # the start: the operator can still chat in-process, just
        # without survival across restarts.
        try:
            create_skill_conversation(
                conv_id,
                [asdict(m) for m in initial_messages],
                user_id=user_id,
            )
        except Exception:
            logger.warning(
                "skill_conv: failed to persist new conversation %s",
                conv_id,
                exc_info=True,
            )

        return {
            "conversation_id": conv_id,
            "message": "Skill creation conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def _maybe_fire_kickoff(cls, conv_id: str) -> None:
        """v0.7.81 (issue #124 / WARN 2+3) — atomic check-and-clear
        of ``needs_kickoff``; on success, spawn the LLM call on a
        non-daemon thread (matches ``send_message``).
        """
        with cls._lock:
            conv = cls._conversations.get(conv_id)
            if not conv or not conv.get("needs_kickoff"):
                return
            conv["needs_kickoff"] = False
            kickoff_msg = next(
                (m for m in reversed(conv["messages"]) if m.role == "user"),
                None,
            )
        if kickoff_msg is None:
            logger.error(
                "skill_conv: needs_kickoff=True but no user message in %s",
                conv_id,
            )
            return
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, kickoff_msg.content),
        ).start()

    @classmethod
    def _ensure_loaded(cls, conv_id: str) -> bool:
        """v0.7.78 — make sure the conversation is in the in-memory
        cache before it's consumed. If the wizard refreshed (new
        browser process) or the backend restarted (lost the dict),
        rehydrate from the DB.

        Returns True iff the conversation is loaded after the call.
        Doesn't raise — caller checks the return value and emits
        the right error_response.

        v0.7.78 (codex WARN 1) — the cache check + DB read + cache
        write happen under ``_lock`` so two concurrent rehydrates
        don't both read the same DB snapshot and stomp each other
        on write. Per-conversation locking would scale better but
        the single global lock is fine for the wizard's QPS.
        """
        with cls._lock:
            if conv_id in cls._conversations:
                return True
        try:
            row = get_skill_conversation(conv_id)
        except Exception:
            logger.warning(
                "skill_conv: DB lookup failed for %s", conv_id, exc_info=True
            )
            return False
        if not row or row["status"] != "active":
            return False
        messages = [
            ConversationMessage(
                role=m["role"], content=m["content"], timestamp=m["timestamp"]
            )
            for m in row["messages"]
        ]
        with cls._lock:
            # Re-check inside the lock — another thread may have
            # rehydrated while we were reading the DB.
            if conv_id in cls._conversations:
                return True
            cls._conversations[conv_id] = {
                "messages": messages,
                "processing": False,
                "user_id": row.get("user_id"),
            }
            cls._subscribers.setdefault(conv_id, [])
            cls._start_times[conv_id] = datetime.datetime.now()
        logger.info(
            "skill_conv: rehydrated %s from DB (%d messages)",
            conv_id,
            len(messages),
        )
        return True

    @classmethod
    def _check_owner(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> Optional[Tuple[dict, HTTPStatus]]:
        """v0.7.78 (codex BLOCK 2) — verify the calling user owns
        the conversation. Returns ``None`` when authorized, or an
        ``error_response`` tuple when not.

        Allowed:
          * ``conv.user_id is None`` (legacy/dev conversations
            created before ownership was enforced) — anyone can
            access. This is intentional dev-mode compat; production
            should always provide a caller user.
          * ``conv.user_id == caller_user_id`` — owner match.
        Otherwise 404 (not 403, to avoid leaking the existence of
        another user's conv to a probing caller).
        """
        conv = cls._conversations.get(conv_id)
        if not conv:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        owner = conv.get("user_id")
        if owner is None:
            return None
        if caller_user_id == owner:
            return None
        return error_response(
            "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
        )

    @classmethod
    def _persist(
        cls,
        conv_id: str,
        *,
        status: Optional[str] = None,
    ) -> None:
        """Write the in-memory conversation through to the DB.

        Called after every mutation (send_message, finalize,
        abandon) so a refresh / restart sees the latest state.
        Failures are logged but never raised — DB outage shouldn't
        crash the chat hot path.
        """
        conv = cls._conversations.get(conv_id)
        if not conv:
            return
        try:
            upsert_skill_conversation(
                conv_id,
                [asdict(m) for m in conv["messages"]],
                status=status,
            )
        except Exception:
            logger.warning(
                "skill_conv: failed to persist conversation %s",
                conv_id,
                exc_info=True,
            )

    @classmethod
    def list_active(cls, user_id: Optional[str] = None) -> Tuple[dict, HTTPStatus]:
        """v0.7.78 — list the operator's recent active conversations
        so the wizard can resume when localStorage is empty (e.g.
        new browser, different machine) but the DB has a row.
        """
        try:
            convs = list_active_skill_conversations(user_id=user_id, limit=10)
        except Exception:
            logger.warning("skill_conv: DB list failed", exc_info=True)
            convs = []
        return {
            "active_conversations": [
                {
                    "id": c["id"],
                    "status": c["status"],
                    "updated_at": c["updated_at"],
                    "message_count": len(c.get("messages") or []),
                }
                for c in convs
            ],
        }, HTTPStatus.OK

    @classmethod
    def get_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages."""
        if not cls._ensure_loaded(conv_id):
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err

        conv = cls._conversations[conv_id]
        messages = [asdict(m) for m in conv["messages"] if m.role != "system"]

        return {
            "id": conv_id,
            "status": "active" if not conv.get("finalized") else "completed",
            "messages_parsed": messages,
        }, HTTPStatus.OK

    @classmethod
    def send_message(
        cls,
        conv_id: str,
        message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
        caller_user_id: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with Claude."""
        if not cls._ensure_loaded(conv_id):
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err

        # v0.7.78 (codex WARN 2) — serialize the processing-check
        # + user-msg append + processing-set under one lock so a
        # second concurrent send_message can't pass the check
        # AND append AND spawn a second LLM call before the first
        # has marked itself processing. Without this we get
        # interleaved [u1, u2, a1, a2] when the wire order was
        # [u1, send u2 → race]; with this the second call gets a
        # 409 CONFLICT and the operator retries.
        with cls._lock:
            conv = cls._conversations[conv_id]
            if conv.get("processing"):
                return error_response(
                    "CONFLICT", "Conversation is processing", HTTPStatus.CONFLICT
                )
            conv["processing"] = True
            user_msg = ConversationMessage(
                role="user",
                content=message,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(user_msg)

        # v0.7.78 (codex WARN D / 2nd pass) — between the lock
        # release above and ``Thread.start()`` below we hand off
        # to ``_process_with_claude`` to ultimately reset
        # ``processing`` in its ``finally``. If anything in the
        # interim raises (``_broadcast`` getting a bad queue,
        # ``Thread.start`` OS failure, etc.) we'd leave the conv
        # stuck at ``processing=True`` forever. Wrap and reset on
        # failure so the operator can retry.
        try:
            # v0.7.78 — write through after the user message; the
            # assistant reply is persisted again at the end of
            # ``_process_with_claude`` once the full response is in
            # the in-memory list.
            cls._persist(conv_id)

            # Broadcast to subscribers
            cls._broadcast(conv_id, "user_message", asdict(user_msg))

            # Process with Claude in background
            threading.Thread(
                target=cls._process_with_claude,
                args=(conv_id, message),
                kwargs={"backend": backend, "account_id": account_id, "model": model},
            ).start()
        except Exception:
            # Reset processing under the lock so a follow-up
            # ``send_message`` isn't permanently 409'd. The user
            # message is intentionally left in the history (and
            # persisted) — re-emitting it would feel surprising
            # and the operator can decide whether to retry.
            logger.error(
                "skill_conv: failed to start LLM thread for %s; "
                "resetting processing flag",
                conv_id,
                exc_info=True,
            )
            with cls._lock:
                if conv_id in cls._conversations:
                    cls._conversations[conv_id]["processing"] = False
            raise

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def can_subscribe(
        cls, conv_id: str, caller_user_id: Optional[str]
    ) -> bool:
        """v0.7.78 (codex WARN B / 2nd pass) — precheck used by the
        SSE route so an unauthorized subscriber gets a real HTTP
        404 instead of a 200 with an ``event: error`` body. Returns
        True iff ``subscribe`` would actually start streaming for
        this caller.
        """
        if not cls._ensure_loaded(conv_id):
            return False
        return cls._check_owner(conv_id, caller_user_id) is None

    @classmethod
    def subscribe(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        # v0.7.78 — rehydrate from DB before subscribing so a
        # refreshed wizard's SSE stream resumes for a conversation
        # the in-memory dict doesn't know about yet. The route is
        # expected to call ``can_subscribe`` first and 404 on
        # failure (codex WARN B / 2nd pass), but we keep the
        # defensive in-stream error branch in case ``subscribe``
        # is invoked directly.
        if not cls._ensure_loaded(conv_id):
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return
        # v0.7.78 (codex BLOCK 2) — gate SSE on ownership so a
        # probing caller can't tail another operator's
        # conversation. Same 404-not-403 disclosure rule as the
        # other endpoints.
        if cls._check_owner(conv_id, caller_user_id) is not None:
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

        # v0.7.81 (issue #124 / WARN 3) — fire the deferred
        # kickoff after the queue is registered so any broadcast
        # the thread produces lands in this subscriber's queue.
        # Atomically clears ``needs_kickoff`` so a concurrent
        # second-tab subscribe can't double-spawn.
        cls._maybe_fire_kickoff(conv_id)

        try:
            # Send existing messages
            conv = cls._conversations.get(conv_id)
            if conv:
                for msg in conv["messages"]:
                    if msg.role != "system":
                        yield f"event: message\ndata: {json.dumps(asdict(msg))}\n\n"

            # Stream new events
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break
                    yield event
                except Empty:
                    yield f"event: ping\ndata: {json.dumps({'time': datetime.datetime.now().isoformat()})}\n\n"
        finally:
            with cls._lock:
                if conv_id in cls._subscribers and queue in cls._subscribers[conv_id]:
                    cls._subscribers[conv_id].remove(queue)

    @classmethod
    def preview_finalize(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Return the rendered package tree without writing anything.

        Used by ``SkillCreatePreviewDrawer`` to show the operator
        what would land on disk. Same validation path as
        ``finalize_skill`` so a preview that succeeds will also
        commit. Warnings (non-fatal nudges like missing license)
        are surfaced for UI display.
        """
        if not cls._ensure_loaded(conv_id):
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err
        conv = cls._conversations[conv_id]
        try:
            preview = cls._build_package_preview(conv)
        except _SkillConfigError as exc:
            return error_response(exc.code, exc.message, exc.status)
        return preview, HTTPStatus.OK

    @classmethod
    def finalize_skill(
        cls,
        conv_id: str,
        expected_config_hash: Optional[str] = None,
        caller_user_id: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and write the skill package to
        disk + DB.

        Uses the same validation as ``preview_finalize`` so the
        preview drawer's "Create Skill" button is guaranteed to
        succeed if the preview rendered without an error.

        v0.7.77 (codex BLOCK 4) — accepts an optional
        ``expected_config_hash``. The drawer passes the hash from
        the preview it rendered; if claude has since emitted a
        newer config block, the re-extracted hash won't match and
        we return 409 so the operator re-previews instead of
        silently committing a config they never reviewed.

        v0.7.77 (codex BLOCK 6) — package writes are now whole-
        package atomic. We stage every file in a temp directory
        under ``/tmp``, and only after every file is staged
        successfully do we ``os.replace`` the whole tree into the
        destination. Partial failures leave nothing behind in the
        skill dir; the staging dir is cleaned up best-effort.
        """
        if not cls._ensure_loaded(conv_id):
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err
        conv = cls._conversations[conv_id]
        try:
            preview = cls._build_package_preview(conv)
        except _SkillConfigError as exc:
            return error_response(exc.code, exc.message, exc.status)

        if (
            expected_config_hash
            and expected_config_hash != preview["config_hash"]
        ):
            return error_response(
                "CONFIG_HASH_MISMATCH",
                "The skill config has changed since you opened the preview. "
                "Please close the drawer and preview again before creating.",
                HTTPStatus.CONFLICT,
            )

        skill_name = preview["skill_name"]
        skill_dir_rel = f".claude/skills/{skill_name}"
        skill_md_rel = preview["skill_md_path"]
        playground = get_playground_working_dir()
        abs_skill_dir = os.path.join(playground, skill_dir_rel)

        # v0.7.77 (codex BLOCK 6 + 2nd-pass + 3rd-pass fix) —
        # stage the whole package in a temp dir on the SAME
        # FILESYSTEM as the destination (so ``os.replace`` is
        # atomic and doesn't raise ``EXDEV`` across mounts), but
        # OUTSIDE the ``.claude/skills/`` tree so the discovery
        # scanners (``SkillDiscoveryService``,
        # ``HarnessLoaderService._import_skills``) can't pick up
        # a half-baked staging dir as a skill during the rename
        # window. The dot-prefix from the 2nd-pass fix wasn't
        # enough — those scanners don't filter dot-prefixed
        # entries. Staging in a sibling root dir under the
        # playground keeps both invariants.
        staging_parent = os.path.join(playground, ".agented-skill-staging")
        os.makedirs(staging_parent, exist_ok=True)
        # Ensure the final ``.claude/skills/`` parent exists too,
        # since we removed the implicit ``makedirs`` from the
        # staging_parent path.
        os.makedirs(os.path.dirname(abs_skill_dir), exist_ok=True)
        staging_dir = tempfile.mkdtemp(
            prefix=f"{skill_name}-",
            dir=staging_parent,
        )
        try:
            written: list[str] = []
            for entry in [
                {"path": skill_md_rel, "content": preview["skill_md_content"]},
                *preview["files"],
            ]:
                rel = entry["path"]
                # Validation already enforced safe paths; double-
                # check via realpath() containment at write time so
                # a bug in the validator can't silently land files
                # outside the staging dir.
                in_pkg = rel.split(f"/{skill_name}/", 1)[-1]
                if not in_pkg or in_pkg == rel:
                    raise _SkillConfigError(
                        "INVALID_PATH",
                        f"Path does not live under the skill dir: {rel}",
                        HTTPStatus.BAD_REQUEST,
                    )
                abs_target = os.path.join(staging_dir, in_pkg)
                resolved = os.path.realpath(abs_target)
                root_resolved = os.path.realpath(staging_dir)
                if not (
                    resolved == root_resolved
                    or resolved.startswith(root_resolved + os.sep)
                ):
                    raise _SkillConfigError(
                        "INVALID_PATH",
                        f"Path escapes skill dir: {rel}",
                        HTTPStatus.BAD_REQUEST,
                    )
                os.makedirs(os.path.dirname(abs_target), exist_ok=True)
                with open(abs_target, "w", encoding="utf-8") as f:
                    f.write(entry["content"])
                # Make scripts/*.py and scripts/*.sh executable so
                # claude can invoke them via Bash without an extra
                # chmod step in the body.
                if in_pkg.startswith("scripts/") and any(
                    in_pkg.endswith(ext) for ext in (".py", ".sh", ".bash", ".zsh")
                ):
                    os.chmod(abs_target, 0o755)
                written.append(rel)

            # All files staged successfully. Atomic rename of the
            # whole tree into the destination. If a previous
            # package exists at the same skill_name, refuse rather
            # than merging — overwriting silently would lose
            # unrelated files the operator put there.
            if os.path.exists(abs_skill_dir):
                raise _SkillConfigError(
                    "SKILL_EXISTS",
                    f"A skill package already exists at "
                    f".claude/skills/{skill_name}/. Pick a different name "
                    f"or delete the existing package first.",
                    HTTPStatus.CONFLICT,
                )
            os.makedirs(os.path.dirname(abs_skill_dir), exist_ok=True)
            os.replace(staging_dir, abs_skill_dir)
            staging_dir = None  # ownership transferred; don't cleanup
            logger.info(
                "Wrote skill package %s with %d file(s) to %s",
                skill_name,
                len(written),
                abs_skill_dir,
            )
        except _SkillConfigError as exc:
            return error_response(exc.code, exc.message, exc.status)
        except OSError as exc:
            logger.error(
                "Failed to write skill package to disk: %s", exc, exc_info=True
            )
            return error_response(
                "INTERNAL_SERVER_ERROR",
                f"Failed to write package to disk: {exc}",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            # Best-effort cleanup of the staging dir on any failure
            # path. ``None`` means the rename succeeded and the
            # tree is now at its destination.
            if staging_dir and os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)

        try:
            skill_id = add_user_skill(
                skill_name=skill_name,
                skill_path=skill_md_rel,
                description=preview["frontmatter"].get("description", ""),
                enabled=1,
                selected_for_harness=0,
                # v0.7.77 (codex NIT 5) — store paths + frontmatter
                # only. Previously embedded ``skill_md_content``
                # too, duplicating disk content in a SQLite row
                # that could grow to hundreds of KB. Consumers
                # read the file from disk via ``skill_path``.
                metadata=json.dumps(
                    {
                        "frontmatter": preview["frontmatter"],
                        "files": [f["path"] for f in preview["files"]],
                    }
                ),
            )
            if not skill_id:
                return error_response(
                    "INTERNAL_SERVER_ERROR",
                    "Failed to create skill row",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            conv["finalized"] = True
            # v0.7.78 — mark the DB row finalized so it's
            # excluded from the resume-on-load list, then drop
            # the in-memory entry. We keep the row (instead of
            # deleting) so the operator's history page can show
            # past conversations even after the skill was
            # created.
            cls._persist(conv_id, status="finalized")
            cls._cleanup_conversation(conv_id)
            skill = get_user_skill(skill_id)
            return {
                "message": "Skill package created successfully",
                "skill_id": skill_id,
                "skill": skill,
                "files_written": written,
            }, HTTPStatus.CREATED
        except Exception as exc:
            logger.error("Failed to create skill row: %s", exc, exc_info=True)
            return error_response(
                "INTERNAL_SERVER_ERROR",
                f"Failed to create skill: {exc}",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    @classmethod
    def abandon_conversation(
        cls, conv_id: str, caller_user_id: Optional[str] = None
    ) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating a skill."""
        # v0.7.78 — load from DB if needed (operator might be
        # abandoning a conv that was rehydrated for inspection or
        # came from a different browser tab).
        if not cls._ensure_loaded(conv_id):
            # Even if not in memory, try to mark abandoned in DB
            # so the resume list stops surfacing it. v0.7.78
            # (codex BLOCK 2) — also gate on ownership in the
            # cold path: read the DB row once and compare its
            # ``user_id`` to the caller before flipping status.
            try:
                row = get_skill_conversation(conv_id)
                if row:
                    owner = row.get("user_id")
                    if owner is not None and owner != caller_user_id:
                        return error_response(
                            "NOT_FOUND",
                            "Conversation not found",
                            HTTPStatus.NOT_FOUND,
                        )
                    upsert_skill_conversation(
                        conv_id,
                        row["messages"],
                        status="abandoned",
                    )
                    return {"message": "Conversation abandoned"}, HTTPStatus.OK
            except Exception:
                pass
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        owner_err = cls._check_owner(conv_id, caller_user_id)
        if owner_err is not None:
            return owner_err
        cls._persist(conv_id, status="abandoned")
        cls._cleanup_conversation(conv_id)
        return {"message": "Conversation abandoned"}, HTTPStatus.OK

    @classmethod
    def _broadcast(cls, conv_id: str, event_type: str, data: dict) -> None:
        """Broadcast an SSE event to all subscribers of a conversation."""
        if conv_id not in cls._subscribers:
            return

        event = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        with cls._lock:
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(event)

    @classmethod
    def _process_with_claude(
        cls,
        conv_id: str,
        user_message: str,
        backend: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
    ) -> None:
        """Process a message with Claude using real-time LLM streaming."""
        if conv_id not in cls._conversations:
            return

        conv = cls._conversations[conv_id]
        conv["processing"] = True

        cls._broadcast(
            conv_id, "response_start", {"timestamp": datetime.datetime.now().isoformat()}
        )

        try:
            from .conversation_streaming import stream_llm_response

            # Build messages from conversation history.
            #
            # v0.7.80 — defense in depth: drop empty-content
            # messages and bail if no user message remains, so
            # a future regression that re-introduces the v0.7.76
            # "missing kickoff" pattern (or a buggy resume path
            # that loses the user turn) can't trigger the
            # CLIProxyAPI "empty text content blocks" error.
            messages = []
            for msg in conv["messages"]:
                if msg.content and msg.content.strip():
                    messages.append({"role": msg.role, "content": msg.content})
            if not any(m["role"] == "user" for m in messages):
                logger.error(
                    "skipping LLM call for %s: no non-empty user message in history",
                    conv_id,
                )
                cls._broadcast(
                    conv_id,
                    "error",
                    {"error": "Cannot send to LLM: no user message in conversation."},
                )
                return

            # Stream response chunks in real-time
            full_response_parts = []
            for chunk in stream_llm_response(
                messages, model=model, account_email=account_id, backend=backend
            ):
                full_response_parts.append(chunk)
                cls._broadcast(conv_id, "response_chunk", {"content": chunk})

            response = "".join(full_response_parts).strip()
            if not response:
                response = "(No response generated)"

            assistant_msg = ConversationMessage(
                role="assistant",
                content=response,
                timestamp=datetime.datetime.now().isoformat(),
            )
            conv["messages"].append(assistant_msg)

            # v0.7.78 — persist after the assistant reply lands so
            # a refresh between turns can see the full
            # conversation, including the SKILL_CONFIG block if
            # claude just emitted one.
            cls._persist(conv_id)

            cls._broadcast(
                conv_id,
                "response_complete",
                {"content": response, "backend": backend or "claude"},
            )

        except Exception as e:
            logger.error(f"Error processing with Claude: {e}", exc_info=True)
            cls._broadcast(conv_id, "error", {"error": str(e)})
        finally:
            conv["processing"] = False

    @classmethod
    def _cleanup_conversation(cls, conv_id: str) -> None:
        """Clean up a conversation and its resources."""
        with cls._lock:
            # Signal subscribers to stop
            for queue in cls._subscribers.get(conv_id, []):
                queue.put(None)

            cls._conversations.pop(conv_id, None)
            cls._subscribers.pop(conv_id, None)
            cls._start_times.pop(conv_id, None)

    # -----------------------------------------------------------------
    # v0.7.77 — skill package preview/validate (shared by preview +
    # finalize). Raises ``_SkillConfigError`` for any problem so the
    # route gets a clean translation to ``error_response``.
    # -----------------------------------------------------------------
    @classmethod
    def _build_package_preview(cls, conv: dict) -> dict:
        config = cls._extract_skill_config(conv)
        config_hash = cls._hash_config(config)
        skill_name = (config.get("skill_name") or "").strip()
        if not _SKILL_NAME_RE.match(skill_name):
            raise _SkillConfigError(
                "INVALID_SKILL_NAME",
                "skill_name must be lowercase kebab-case, 1-64 chars",
                HTTPStatus.BAD_REQUEST,
            )

        frontmatter = cls._validate_frontmatter(
            config.get("frontmatter") or {}, fallback_description=config.get("description")
        )
        body = (config.get("body") or "").strip()
        if not body:
            # Back-compat shim for legacy schema (v0.7.75 emitted
            # ``triggers`` + ``instructions``). Compose a body from
            # those so a mid-flight conversation that hits the new
            # backend doesn't error.
            body = cls._legacy_body_from_config(config)
            if not body:
                raise _SkillConfigError(
                    "MISSING_BODY",
                    "body (SKILL.md content) is required",
                    HTTPStatus.BAD_REQUEST,
                )

        files = cls._validate_files(config.get("files") or [], skill_name)

        skill_md_content = cls._render_skill_md(
            skill_name=skill_name, frontmatter=frontmatter, body=body
        )
        skill_md_path = f".claude/skills/{skill_name}/SKILL.md"

        warnings: list[str] = []
        if "license" not in frontmatter:
            warnings.append(
                "license missing — defaulted to MIT in the rendered frontmatter"
            )
        if not files:
            warnings.append(
                "no helper scripts or references — package is SKILL.md-only"
            )

        return {
            "skill_name": skill_name,
            "skill_md_path": skill_md_path,
            "skill_md_content": skill_md_content,
            "frontmatter": frontmatter,
            "files": files,
            "warnings": warnings,
            # v0.7.77 (codex BLOCK 4) — content fingerprint of the
            # extracted config. Finalize accepts an optional
            # ``expected_config_hash`` arg; mismatch means the
            # operator's preview is stale (claude emitted a newer
            # config block since they opened the drawer).
            "config_hash": config_hash,
        }

    @staticmethod
    def _extract_skill_config(conv: dict) -> dict:
        """Pull the most recent valid SKILL_CONFIG JSON block from
        the conversation's assistant messages.

        v0.7.77 (codex NIT 3) — distinguishes "no markers ever
        seen" from "markers present but JSON malformed". The first
        is a "keep chatting" hint; the second means claude emitted
        a bad block and the operator needs to ask for a clean one.
        """
        saw_markers = False
        last_parse_error: Optional[str] = None
        for msg in reversed(conv["messages"]):
            if msg.role != "assistant" or "---SKILL_CONFIG---" not in msg.content:
                continue
            saw_markers = True
            try:
                start = msg.content.index("---SKILL_CONFIG---") + len("---SKILL_CONFIG---")
                end = msg.content.index("---END_CONFIG---")
            except ValueError:
                last_parse_error = "missing ---END_CONFIG--- marker"
                continue
            blob = msg.content[start:end].strip()
            try:
                return json.loads(blob)
            except json.JSONDecodeError as exc:
                last_parse_error = (
                    f"invalid JSON at line {exc.lineno}, col {exc.colno}: {exc.msg}"
                )
                continue
        if saw_markers:
            raise _SkillConfigError(
                "INVALID_CONFIG_JSON",
                f"Skill configuration block exists but is malformed: "
                f"{last_parse_error}. Ask the assistant to re-emit a clean "
                f"---SKILL_CONFIG--- block.",
                HTTPStatus.BAD_REQUEST,
            )
        raise _SkillConfigError(
            "NO_CONFIG_BLOCK",
            "No skill configuration block found in the conversation yet.",
            HTTPStatus.BAD_REQUEST,
        )

    @staticmethod
    def _hash_config(config: dict) -> str:
        """Stable SHA-256 hash of the config block.

        Used as a content fingerprint so finalize can confirm the
        operator is committing the same config they previewed. Any
        whitespace/key-order variation is normalized via
        ``sort_keys=True``.
        """
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_frontmatter(
        raw: dict, *, fallback_description: str | None = None
    ) -> dict:
        if not isinstance(raw, dict):
            raise _SkillConfigError(
                "INVALID_FRONTMATTER",
                "frontmatter must be an object",
                HTTPStatus.BAD_REQUEST,
            )
        unknown = set(raw.keys()) - _ALLOWED_FRONTMATTER_KEYS
        if unknown:
            raise _SkillConfigError(
                "UNKNOWN_FRONTMATTER_KEY",
                f"unknown frontmatter keys: {sorted(unknown)}. "
                f"Allowed: {sorted(_ALLOWED_FRONTMATTER_KEYS)}",
                HTTPStatus.BAD_REQUEST,
            )
        out: dict = {}
        desc = (raw.get("description") or fallback_description or "").strip()
        if not desc:
            raise _SkillConfigError(
                "MISSING_DESCRIPTION",
                "frontmatter.description is required",
                HTTPStatus.BAD_REQUEST,
            )
        out["description"] = desc
        if raw.get("license"):
            out["license"] = str(raw["license"]).strip()
        if raw.get("allowed_tools"):
            tools = raw["allowed_tools"]
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                raise _SkillConfigError(
                    "INVALID_ALLOWED_TOOLS",
                    "allowed_tools must be an array of strings",
                    HTTPStatus.BAD_REQUEST,
                )
            out["allowed_tools"] = [t.strip() for t in tools if t.strip()]
        if raw.get("tags"):
            tags = raw["tags"]
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                raise _SkillConfigError(
                    "INVALID_TAGS",
                    "tags must be an array of strings",
                    HTTPStatus.BAD_REQUEST,
                )
            out["tags"] = [t.strip() for t in tags if t.strip()]
        return out

    @staticmethod
    def _validate_files(raw: list, skill_name: str) -> list[dict]:
        if not isinstance(raw, list):
            raise _SkillConfigError(
                "INVALID_FILES", "files must be an array", HTTPStatus.BAD_REQUEST
            )
        if len(raw) > _MAX_FILES:
            raise _SkillConfigError(
                "TOO_MANY_FILES",
                f"package has {len(raw)} files; max is {_MAX_FILES}",
                HTTPStatus.BAD_REQUEST,
            )
        out: list[dict] = []
        seen_paths: set[str] = set()
        for idx, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise _SkillConfigError(
                    "INVALID_FILE_ENTRY",
                    f"files[{idx}] must be an object with path + content",
                    HTTPStatus.BAD_REQUEST,
                )
            rel = (entry.get("path") or "").strip()
            content = entry.get("content")
            if not rel or not isinstance(content, str):
                raise _SkillConfigError(
                    "INVALID_FILE_ENTRY",
                    f"files[{idx}] must have non-empty path + string content",
                    HTTPStatus.BAD_REQUEST,
                )
            if ".." in rel.split("/"):
                raise _SkillConfigError(
                    "PATH_TRAVERSAL",
                    f"files[{idx}].path contains '..': {rel}",
                    HTTPStatus.BAD_REQUEST,
                )
            if not any(rel.startswith(p) for p in _ALLOWED_PATH_PREFIXES):
                raise _SkillConfigError(
                    "INVALID_PATH_PREFIX",
                    f"files[{idx}].path must start with one of "
                    f"{list(_ALLOWED_PATH_PREFIXES)}: {rel}",
                    HTTPStatus.BAD_REQUEST,
                )
            byte_len = len(content.encode("utf-8"))
            if byte_len > _FILE_BYTE_CAP:
                raise _SkillConfigError(
                    "FILE_TOO_LARGE",
                    f"files[{idx}] ({rel}) is {byte_len} bytes; "
                    f"max per file is {_FILE_BYTE_CAP}",
                    HTTPStatus.BAD_REQUEST,
                )
            full_path = f".claude/skills/{skill_name}/{rel}"
            if full_path in seen_paths:
                raise _SkillConfigError(
                    "DUPLICATE_FILE_PATH",
                    f"files[{idx}].path duplicates an earlier entry: {rel}",
                    HTTPStatus.BAD_REQUEST,
                )
            seen_paths.add(full_path)
            out.append(
                {
                    "path": full_path,
                    "content": content,
                    "size_bytes": byte_len,
                }
            )
        return out

    @staticmethod
    def _render_skill_md(*, skill_name: str, frontmatter: dict, body: str) -> str:
        """Render YAML frontmatter + body. Default license=MIT when
        the operator (via claude) didn't supply one.

        Uses PyYAML's safe dumper with a stable key order matching
        Anthropic's reference docs so diff'ed packages have
        predictable text. The ``allowed_tools`` field is rendered
        as ``allowed-tools`` on disk (Anthropic uses kebab-case in
        YAML but the JSON config uses snake_case to avoid
        ambiguity).
        """
        import yaml as _yaml

        fm_disk: dict = {"name": skill_name}
        fm_disk["description"] = frontmatter["description"]
        fm_disk["license"] = frontmatter.get("license", "MIT")
        if frontmatter.get("allowed_tools"):
            fm_disk["allowed-tools"] = frontmatter["allowed_tools"]
        if frontmatter.get("tags"):
            fm_disk["tags"] = frontmatter["tags"]
        yaml_block = _yaml.safe_dump(
            fm_disk, sort_keys=False, default_flow_style=False
        ).strip()
        return f"---\n{yaml_block}\n---\n\n{body.rstrip()}\n"

    @staticmethod
    def _legacy_body_from_config(config: dict) -> str:
        """Render a body from the v0.7.75 schema (description +
        triggers + instructions + examples). Used as a transition
        shim for in-flight conversations that span the upgrade.
        """
        description = (config.get("description") or "").strip()
        instructions = (config.get("instructions") or "").strip()
        triggers = config.get("triggers") or []
        examples = config.get("examples") or []
        if not instructions and not description:
            return ""
        parts = []
        if description:
            parts.append(description)
        if triggers:
            parts.append("## Triggers\n\nUse this skill when:")
            parts.extend(f"- {t}" for t in triggers)
        if instructions:
            parts.append(f"## Instructions\n\n{instructions}")
        if examples:
            parts.append("## Examples")
            parts.extend(f"- {e}" for e in examples)
        return "\n\n".join(parts)
