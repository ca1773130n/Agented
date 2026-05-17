"""Skill conversation service for interactive skill creation with SSE streaming."""

import datetime
import json
import logging
import os
import secrets
import string
import threading
from dataclasses import asdict, dataclass
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Tuple

logger = logging.getLogger(__name__)

from app.models.common import error_response

from ..database import (
    add_user_skill,
    get_user_skill,
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
    def start_conversation(cls) -> Tuple[dict, HTTPStatus]:
        """Start a new skill creation conversation."""
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
            cls._conversations[conv_id] = {"messages": initial_messages, "processing": False}
            cls._subscribers[conv_id] = []
            cls._start_times[conv_id] = datetime.datetime.now()

        # v0.7.76 — spawn the LLM call in a background thread so
        # the HTTP request returns immediately; the response
        # streams back over SSE just like ``send_message``. The
        # prior synchronous call blocked the request for the full
        # LLM round-trip, making the wizard hang on /skills/new.
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, kickoff.content),
            daemon=True,
        ).start()

        return {
            "conversation_id": conv_id,
            "message": "Skill creation conversation started",
        }, HTTPStatus.CREATED

    @classmethod
    def get_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Get conversation details and messages."""
        if conv_id not in cls._conversations:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

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
    ) -> Tuple[dict, HTTPStatus]:
        """Send a user message and process with Claude."""
        if conv_id not in cls._conversations:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

        conv = cls._conversations[conv_id]
        if conv.get("processing"):
            return error_response("CONFLICT", "Conversation is processing", HTTPStatus.CONFLICT)

        # Add user message
        user_msg = ConversationMessage(
            role="user",
            content=message,
            timestamp=datetime.datetime.now().isoformat(),
        )
        conv["messages"].append(user_msg)

        # Broadcast to subscribers
        cls._broadcast(conv_id, "user_message", asdict(user_msg))

        # Process with Claude in background
        threading.Thread(
            target=cls._process_with_claude,
            args=(conv_id, message),
            kwargs={"backend": backend, "account_id": account_id, "model": model},
        ).start()

        return {"message_id": conv_id, "status": "processing"}, HTTPStatus.OK

    @classmethod
    def subscribe(cls, conv_id: str) -> Generator[str, None, None]:
        """Subscribe to SSE events for a conversation."""
        if conv_id not in cls._conversations:
            yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found'})}\n\n"
            return

        queue: Queue = Queue()
        with cls._lock:
            if conv_id in cls._subscribers:
                cls._subscribers[conv_id].append(queue)

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
    def preview_finalize(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Return the rendered package tree without writing anything.

        Used by ``SkillCreatePreviewDrawer`` to show the operator
        what would land on disk. Same validation path as
        ``finalize_skill`` so a preview that succeeds will also
        commit. Warnings (non-fatal nudges like missing license)
        are surfaced for UI display.
        """
        if conv_id not in cls._conversations:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        conv = cls._conversations[conv_id]
        try:
            preview = cls._build_package_preview(conv)
        except _SkillConfigError as exc:
            return error_response(exc.code, exc.message, exc.status)
        return preview, HTTPStatus.OK

    @classmethod
    def finalize_skill(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Finalize the conversation and write the skill package to
        disk + DB.

        Uses the same validation as ``preview_finalize`` so the
        preview drawer's "Create Skill" button is guaranteed to
        succeed if the preview rendered without an error. Atomic
        per-file: writes each file to ``<path>.tmp`` then renames,
        so a partial failure doesn't leave a half-written package
        (best-effort — cross-file atomicity requires a transaction
        the filesystem doesn't give us).
        """
        if conv_id not in cls._conversations:
            return error_response(
                "NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND
            )
        conv = cls._conversations[conv_id]
        try:
            preview = cls._build_package_preview(conv)
        except _SkillConfigError as exc:
            return error_response(exc.code, exc.message, exc.status)

        skill_name = preview["skill_name"]
        skill_dir_rel = f".claude/skills/{skill_name}"
        skill_md_rel = preview["skill_md_path"]
        try:
            playground = get_playground_working_dir()
            abs_skill_dir = os.path.join(playground, skill_dir_rel)
            os.makedirs(abs_skill_dir, exist_ok=True)
            written: list[str] = []
            for entry in [
                {"path": skill_md_rel, "content": preview["skill_md_content"]},
                *preview["files"],
            ]:
                rel = entry["path"]
                # Validation already enforced safe paths; double-
                # check via resolve() + relative_to() at write time
                # so a bug in the validator can't silently land
                # files outside the skill dir.
                abs_target = os.path.join(playground, rel)
                resolved = os.path.realpath(abs_target)
                root = os.path.realpath(
                    os.path.join(playground, ".claude", "skills", skill_name)
                )
                if not resolved.startswith(root + os.sep) and resolved != root:
                    raise _SkillConfigError(
                        "INVALID_PATH",
                        f"Path escapes skill dir: {rel}",
                        HTTPStatus.BAD_REQUEST,
                    )
                os.makedirs(os.path.dirname(abs_target), exist_ok=True)
                tmp_path = f"{abs_target}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write(entry["content"])
                # Make scripts/*.py and scripts/*.sh executable so
                # claude can invoke them via Bash without an extra
                # chmod step in the body. ``rel`` here is the full
                # ``.claude/skills/<name>/scripts/foo.py`` path; we
                # check the in-package portion (after the skill
                # dir prefix) to detect the scripts subdir.
                in_pkg = rel.split(f"/{skill_name}/", 1)[-1]
                if in_pkg.startswith("scripts/") and any(
                    in_pkg.endswith(ext) for ext in (".py", ".sh", ".bash", ".zsh")
                ):
                    os.chmod(tmp_path, 0o755)
                os.replace(tmp_path, abs_target)
                written.append(rel)
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

        try:
            skill_id = add_user_skill(
                skill_name=skill_name,
                skill_path=skill_md_rel,
                description=preview["frontmatter"].get("description", ""),
                enabled=1,
                selected_for_harness=0,
                metadata=json.dumps(
                    {
                        "frontmatter": preview["frontmatter"],
                        "files": [f["path"] for f in preview["files"]],
                        "skill_md_content": preview["skill_md_content"],
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
    def abandon_conversation(cls, conv_id: str) -> Tuple[dict, HTTPStatus]:
        """Abandon a conversation without creating a skill."""
        if conv_id not in cls._conversations:
            return error_response("NOT_FOUND", "Conversation not found", HTTPStatus.NOT_FOUND)

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

            # Build messages from conversation history
            messages = []
            for msg in conv["messages"]:
                messages.append({"role": msg.role, "content": msg.content})

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
        }

    @staticmethod
    def _extract_skill_config(conv: dict) -> dict:
        """Pull the most recent valid SKILL_CONFIG JSON block from
        the conversation's assistant messages.
        """
        for msg in reversed(conv["messages"]):
            if msg.role != "assistant" or "---SKILL_CONFIG---" not in msg.content:
                continue
            try:
                start = msg.content.index("---SKILL_CONFIG---") + len("---SKILL_CONFIG---")
                end = msg.content.index("---END_CONFIG---")
            except ValueError:
                continue
            blob = msg.content[start:end].strip()
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                continue
        raise _SkillConfigError(
            "NO_CONFIG_BLOCK",
            "No skill configuration block found in the conversation yet.",
            HTTPStatus.BAD_REQUEST,
        )

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
