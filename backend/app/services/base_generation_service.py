"""Base service for AI-powered entity generation using Claude CLI."""

import json
import logging
import os
import subprocess
import threading
from abc import ABC, abstractmethod
from queue import Empty, Queue
from typing import Generator

logger = logging.getLogger(__name__)


class BaseGenerationService(ABC):
    """Abstract base for Claude CLI-powered generation services."""

    SUBPROCESS_TIMEOUT = 120  # seconds

    @classmethod
    def generate_streaming(cls, description: str) -> Generator[str, None, None]:
        """Generate entity config with real-time SSE streaming of Claude's output."""

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        # Phase 1: Gather context
        yield sse("phase", {"message": "Scanning resources..."})
        context = cls._gather_context()

        context_summary = cls._summarize_context(context)
        if context_summary:
            yield sse("phase", {"message": context_summary})

        # Phase 2: Build prompt
        yield sse("phase", {"message": "Constructing AI prompt..."})
        prompt = cls._build_prompt(description, context)

        # Phase 3: Run Claude CLI with streaming
        yield sse("phase", {"message": "Calling Claude CLI..."})

        try:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            )
            process = subprocess.Popen(
                [
                    "claude",
                    "-p",
                    prompt,
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--include-partial-messages",
                ],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            yield sse("error", {"error": "Claude CLI not found. Please install it first."})
            return

        # Read stdout and stderr concurrently via threads + queue
        line_queue: Queue = Queue()

        def read_stream(stream, stream_type):
            for line in iter(stream.readline, ""):
                if line:
                    line_queue.put((stream_type, line.rstrip("\n\r")))
            line_queue.put((stream_type, None))

        stdout_thread = threading.Thread(
            target=read_stream, args=(process.stdout, "stdout"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=read_stream, args=(process.stderr, "stderr"), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        result_text = ""
        reported = set()
        streams_done = 0

        while streams_done < 2:
            try:
                stream_type, content = line_queue.get(timeout=0.1)
            except Empty:
                continue

            if content is None:
                streams_done += 1
                continue

            if stream_type == "stderr":
                if content.strip():
                    yield sse("thinking", {"content": content})
                continue

            content = content.strip()
            if not content:
                continue

            try:
                msg = json.loads(content)
            except json.JSONDecodeError:
                yield sse("output", {"content": content})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "system":
                subtype = msg.get("subtype", "")
                if subtype == "init":
                    model = msg.get("model", "unknown")
                    tools = msg.get("tools", [])
                    tool_count = len(tools) if tools else 0
                    info = f"Connected to {model}"
                    if tool_count:
                        info += f" with {tool_count} tools"
                    yield sse("thinking", {"content": info})
                else:
                    yield sse("thinking", {"content": f"System: {subtype or 'ready'}"})

            elif msg_type == "stream_event":
                event = msg.get("event", {})
                event_type = event.get("type", "")

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            result_text += text
                            for progress_msg in cls._extract_progress(result_text, reported):
                                yield sse("output", {"content": progress_msg})

                    elif delta_type == "thinking_delta":
                        thinking = delta.get("thinking", "")
                        if thinking:
                            for line in thinking.split("\n"):
                                if line:
                                    yield sse("thinking", {"content": line})

                elif event_type == "message_start":
                    yield sse("thinking", {"content": "Claude is generating..."})

                elif event_type == "message_delta":
                    usage = event.get("usage", {})
                    if usage:
                        out = usage.get("output_tokens", 0)
                        if out:
                            yield sse("thinking", {"content": f"Output tokens: {out:,}"})

            elif msg_type == "assistant":
                if not result_text:
                    message = msg.get("message", {})
                    for block in message.get("content", []):
                        if block.get("type") == "text":
                            result_text = block.get("text", "")
                            break

            elif msg_type == "result":
                if not result_text:
                    result_text = msg.get("result", "")
                cost = msg.get("cost_usd")
                duration = msg.get("duration_ms")
                parts = []
                if duration:
                    parts.append(f"{duration / 1000:.1f}s")
                if cost:
                    parts.append(f"${cost:.4f}")
                if parts:
                    yield sse("thinking", {"content": f"Completed in {', '.join(parts)}"})

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        process.wait()

        if not result_text:
            yield sse("error", {"error": "Claude returned empty output. Please try again."})
            return

        # Phase 4: Parse and validate
        yield sse("phase", {"message": "Parsing AI response..."})

        try:
            config = cls._parse_json(result_text)
        except RuntimeError as e:
            yield sse("error", {"error": str(e)})
            return

        yield sse("phase", {"message": "Validating..."})
        config, warnings = cls._validate(config)

        yield sse("result", {"config": config, "warnings": warnings})

    @classmethod
    @abstractmethod
    def _gather_context(cls) -> dict:
        """Gather entity-specific context from the database."""
        ...

    @classmethod
    def _summarize_context(cls, context: dict) -> str:
        """Summarize gathered context for the log."""
        parts = []
        for key, items in context.items():
            if items:
                parts.append(f"{len(items)} {key}")
        return f"Found {', '.join(parts)}" if parts else "No existing resources"

    @classmethod
    @abstractmethod
    def _build_prompt(cls, description: str, context: dict) -> str:
        """Build the Claude prompt for generation."""
        ...

    @classmethod
    @abstractmethod
    def _extract_progress(cls, text: str, reported: set) -> list[str]:
        """Extract progress messages from growing JSON text."""
        ...

    @classmethod
    @abstractmethod
    def _validate(cls, config: dict) -> tuple:
        """Validate and annotate the generated config. Returns (config, warnings)."""
        ...

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse JSON from CLI output that may contain mixed text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
            raise RuntimeError(
                "Could not find a valid JSON object in the CLI output. Please try again."
            )

        json_str = text[first_brace : last_brace + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse generated JSON: {e}")
