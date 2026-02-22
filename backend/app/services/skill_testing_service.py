"""Skill testing service — test execution and SSE streaming."""

import datetime
import json
import secrets
import string
import subprocess
import threading
from http import HTTPStatus
from queue import Empty, Queue
from typing import Dict, Generator, List, Tuple

from .skill_discovery_service import get_playground_working_dir


class SkillTestingService:
    """Service for skill test execution and SSE streaming."""

    # In-memory test state: {test_id: {'status': str, 'output': []}}
    _test_sessions: Dict[str, dict] = {}
    # SSE subscribers for tests: {test_id: [Queue]}
    _test_subscribers: Dict[str, List[Queue]] = {}
    # Active test subprocesses: {test_id: Popen}
    _test_processes: Dict[str, subprocess.Popen] = {}
    _lock = threading.Lock()

    @classmethod
    def test_skill(cls, skill_name: str, test_input: str = "") -> Tuple[dict, HTTPStatus]:
        """Start a skill test in the playground."""
        # Generate test ID
        test_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))

        with cls._lock:
            cls._test_sessions[test_id] = {
                "status": "running",
                "skill_name": skill_name,
                "output": [],
                "started_at": datetime.datetime.now().isoformat(),
            }
            cls._test_subscribers[test_id] = []

        # Run test in background
        thread = threading.Thread(
            target=cls._run_skill_test, args=(test_id, skill_name, test_input), daemon=True
        )
        thread.start()

        return {
            "test_id": test_id,
            "message": f"Testing skill '{skill_name}'",
            "status": "running",
        }, HTTPStatus.ACCEPTED

    @classmethod
    def _run_skill_test(cls, test_id: str, skill_name: str, test_input: str):
        """Run a skill test (background thread)."""
        try:
            # Build command - prepend skill command to prompt
            skill_cmd = f"/{skill_name}" if not skill_name.startswith("/") else skill_name
            full_prompt = f"{skill_cmd} {test_input}".strip()

            cmd = ["claude", "-p", full_prompt]

            # Broadcast start
            cls._broadcast_test(
                test_id, "start", {"skill_name": skill_name, "test_input": test_input}
            )

            # Use configurable playground directory
            working_dir = get_playground_working_dir()

            process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            with cls._lock:
                cls._test_processes[test_id] = process

            # Stream stdout
            for line in iter(process.stdout.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    with cls._lock:
                        if test_id in cls._test_sessions:
                            cls._test_sessions[test_id]["output"].append(content)
                    cls._broadcast_test(test_id, "output", {"content": content})

            # Stream stderr
            for line in iter(process.stderr.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    with cls._lock:
                        if test_id in cls._test_sessions:
                            cls._test_sessions[test_id]["output"].append(f"[stderr] {content}")
                    cls._broadcast_test(test_id, "error_output", {"content": content})

            process.wait()
            exit_code = process.returncode

            with cls._lock:
                if test_id in cls._test_sessions:
                    cls._test_sessions[test_id]["status"] = (
                        "completed" if exit_code == 0 else "failed"
                    )
                    cls._test_sessions[test_id]["exit_code"] = exit_code

            cls._broadcast_test(
                test_id,
                "complete",
                {"exit_code": exit_code, "status": "completed" if exit_code == 0 else "failed"},
            )

        except Exception as e:
            with cls._lock:
                if test_id in cls._test_sessions:
                    cls._test_sessions[test_id]["status"] = "error"
                    cls._test_sessions[test_id]["error"] = str(e)

            cls._broadcast_test(test_id, "error", {"error": str(e)})

        finally:
            # Remove process reference immediately
            with cls._lock:
                cls._test_processes.pop(test_id, None)

            # Cleanup subscribers after delay
            def cleanup():
                import time

                time.sleep(60)  # Keep session for 60 seconds after completion
                with cls._lock:
                    cls._test_sessions.pop(test_id, None)
                    if test_id in cls._test_subscribers:
                        for q in cls._test_subscribers[test_id]:
                            q.put(None)
                        cls._test_subscribers.pop(test_id, None)

            threading.Thread(target=cleanup, daemon=True).start()

    @classmethod
    def subscribe_test(cls, test_id: str) -> Generator[str, None, None]:
        """SSE generator for skill test streaming."""
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
                    {"status": status, "exit_code": cls._test_sessions[test_id].get("exit_code")},
                )
                return

            # Register subscriber
            if test_id not in cls._test_subscribers:
                cls._test_subscribers[test_id] = []
            cls._test_subscribers[test_id].append(queue)

        try:
            while True:
                try:
                    event = queue.get(timeout=30)
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
    def stop_test(cls, test_id: str) -> Tuple[dict, HTTPStatus]:
        """Stop a running test by killing the subprocess."""
        with cls._lock:
            process = cls._test_processes.get(test_id)
            session = cls._test_sessions.get(test_id)

        if not session:
            return {"error": "Test not found"}, HTTPStatus.NOT_FOUND

        if session.get("status") != "running":
            return {"error": "Test is not running"}, HTTPStatus.BAD_REQUEST

        if process:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

        with cls._lock:
            if test_id in cls._test_sessions:
                cls._test_sessions[test_id]["status"] = "stopped"

        cls._broadcast_test(test_id, "complete", {"exit_code": -9, "status": "stopped"})

        return {"message": "Test stopped"}, HTTPStatus.OK

    @classmethod
    def _broadcast_test(cls, test_id: str, event_type: str, data: dict):
        """Broadcast an event to test subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if test_id in cls._test_subscribers:
                for q in cls._test_subscribers[test_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
