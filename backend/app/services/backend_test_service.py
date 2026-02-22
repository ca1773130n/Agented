"""One-shot prompt test service with SSE streaming for backend testing."""

import json
import logging
import os
import secrets
import string
import subprocess
import threading
from datetime import datetime
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BackendTestService:
    """Ephemeral one-shot prompt test service.

    Runs CLI commands against configured backends and streams output via SSE.
    No database records are created -- all state is in-memory with a 2-minute TTL.
    """

    _test_sessions: Dict[str, dict] = {}
    _test_subscribers: Dict[str, List[Queue]] = {}
    _lock = threading.Lock()

    @classmethod
    def test_prompt(
        cls,
        backend_type: str,
        prompt: str,
        account_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[dict, HTTPStatus]:
        """Start a one-shot prompt test against a backend CLI.

        Returns a test_id that can be used to subscribe to SSE output.
        """
        test_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))

        with cls._lock:
            cls._test_sessions[test_id] = {
                "status": "running",
                "prompt": prompt,
                "backend_type": backend_type,
                "output": [],
                "started_at": datetime.now().isoformat(),
            }
            cls._test_subscribers[test_id] = []

        thread = threading.Thread(
            target=cls._run_test,
            args=(test_id, backend_type, prompt, account_id, model),
            daemon=True,
        )
        thread.start()

        return {"test_id": test_id, "status": "running"}, HTTPStatus.ACCEPTED

    @classmethod
    def _run_test(
        cls,
        test_id: str,
        backend_type: str,
        prompt: str,
        account_id: Optional[str],
        model: Optional[str],
    ):
        """Run a one-shot prompt test (background thread).

        For Claude backend: uses CLIProxyAPI via LiteLLM for real-time streaming.
        For other backends: falls back to CLI subprocess.
        """
        try:
            cls._broadcast_test(
                test_id,
                "start",
                {"backend_type": backend_type, "prompt": prompt},
            )

            # Claude / Codex / Gemini: stream via CLIProxyAPI
            if backend_type in ("claude", "codex", "gemini"):
                cls._run_test_via_proxy(test_id, prompt, model, account_id, backend_type)
                return

            # Other backends: CLI subprocess
            cls._run_test_via_cli(test_id, backend_type, prompt, account_id, model)

        except Exception as e:
            with cls._lock:
                if test_id in cls._test_sessions:
                    cls._test_sessions[test_id]["status"] = "error"
                    cls._test_sessions[test_id]["error"] = str(e)

            cls._broadcast_test(test_id, "error", {"error": str(e)})

        finally:
            # 2-minute TTL cleanup
            def cleanup():
                import time

                time.sleep(120)
                with cls._lock:
                    cls._test_sessions.pop(test_id, None)
                    if test_id in cls._test_subscribers:
                        for q in cls._test_subscribers[test_id]:
                            q.put(None)
                        cls._test_subscribers.pop(test_id, None)

            threading.Thread(target=cleanup, daemon=True).start()

    @classmethod
    def _run_test_via_proxy(
        cls,
        test_id: str,
        prompt: str,
        model: Optional[str],
        account_id: Optional[str] = None,
        backend: str = "claude",
    ):
        """Stream test via CLIProxyAPI for real-time token streaming."""
        from .conversation_streaming import stream_llm_response

        messages = [{"role": "user", "content": prompt}]

        for chunk in stream_llm_response(
            messages, model=model, account_email=account_id, backend=backend
        ):
            if chunk:
                with cls._lock:
                    if test_id in cls._test_sessions:
                        cls._test_sessions[test_id]["output"].append(chunk)
                cls._broadcast_test(test_id, "output", {"content": chunk})

        cls._mark_test_complete(test_id)

    @classmethod
    def _mark_test_complete(cls, test_id: str):
        """Mark a test session as completed and broadcast."""
        with cls._lock:
            if test_id in cls._test_sessions:
                cls._test_sessions[test_id]["status"] = "completed"
                cls._test_sessions[test_id]["exit_code"] = 0
        cls._broadcast_test(test_id, "complete", {"exit_code": 0, "status": "completed"})

    @classmethod
    def _run_test_via_cli(
        cls,
        test_id: str,
        backend_type: str,
        prompt: str,
        account_id: Optional[str],
        model: Optional[str],
    ):
        """Run a test via CLI subprocess (fallback for non-proxy backends)."""
        cmd_map = {
            "opencode": ["opencode", "run", "--prompt", prompt],
        }

        cmd = cmd_map.get(backend_type)
        if not cmd:
            cls._broadcast_test(
                test_id, "error", {"error": f"Unsupported backend type: {backend_type}"}
            )
            return

        # Use playground working directory
        from .skills_service import get_playground_working_dir

        working_dir = get_playground_working_dir()

        process = subprocess.Popen(
            cmd,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        def _read_stdout():
            for line in iter(process.stdout.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    with cls._lock:
                        if test_id in cls._test_sessions:
                            cls._test_sessions[test_id]["output"].append(content)
                    cls._broadcast_test(test_id, "output", {"content": content})

        def _read_stderr():
            for line in iter(process.stderr.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    with cls._lock:
                        if test_id in cls._test_sessions:
                            cls._test_sessions[test_id]["output"].append(f"[stderr] {content}")
                    cls._broadcast_test(test_id, "error_output", {"content": content})

        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        stdout_thread.join()
        stderr_thread.join()

        process.wait()
        exit_code = process.returncode

        with cls._lock:
            if test_id in cls._test_sessions:
                cls._test_sessions[test_id]["status"] = "completed" if exit_code == 0 else "failed"
                cls._test_sessions[test_id]["exit_code"] = exit_code

        cls._broadcast_test(
            test_id,
            "complete",
            {
                "exit_code": exit_code,
                "status": "completed" if exit_code == 0 else "failed",
            },
        )

    @classmethod
    def subscribe_test(cls, test_id: str) -> Generator[str, None, None]:
        """SSE generator for backend test streaming."""
        queue: Queue = Queue()

        with cls._lock:
            if test_id not in cls._test_sessions:
                yield cls._format_sse("error", {"error": "Test not found"})
                return

            # Send existing output
            for line in cls._test_sessions[test_id]["output"]:
                yield cls._format_sse("output", {"content": line})

            # Check if already complete
            status = cls._test_sessions[test_id]["status"]
            if status in ("completed", "failed", "error"):
                yield cls._format_sse(
                    "complete",
                    {
                        "status": status,
                        "exit_code": cls._test_sessions[test_id].get("exit_code"),
                    },
                )
                return

            # Register subscriber
            if test_id not in cls._test_subscribers:
                cls._test_subscribers[test_id] = []
            cls._test_subscribers[test_id].append(queue)

        try:
            while True:
                try:
                    event = queue.get(timeout=120)
                    if event is None:
                        break
                    yield event
                except Empty:
                    yield ": keepalive\n\n"
        finally:
            with cls._lock:
                if test_id in cls._test_subscribers:
                    try:
                        cls._test_subscribers[test_id].remove(queue)
                    except ValueError:
                        pass

    @classmethod
    def _broadcast_test(cls, test_id: str, event_type: str, data: dict):
        """Broadcast an SSE event to all subscribers of a test session."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if test_id in cls._test_subscribers:
                for q in cls._test_subscribers[test_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message string."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
