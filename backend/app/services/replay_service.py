"""Execution replay service for A/B testing and regression detection.

Replays a completed execution with identical inputs, creating a new execution
record and tracking the relationship in replay_comparisons. Output comparison
uses difflib to produce structured line-level diffs.
"""

import difflib
import logging
import shutil
import subprocess
import threading
from typing import Optional

from ..db.replay import create_replay_comparison
from ..services.execution_log_service import ExecutionLogService
from ..services.process_manager import ProcessManager

logger = logging.getLogger(__name__)


class ReplayService:
    """Service for replaying executions and comparing outputs."""

    @classmethod
    def replay_execution(cls, original_execution_id: str, notes: Optional[str] = None) -> dict:
        """Replay an execution with identical prompt/command from the original.

        Args:
            original_execution_id: The execution ID to replay.
            notes: Optional notes about this replay.

        Returns:
            Dict with comparison_id, original_execution_id, replay_execution_id.

        Raises:
            ValueError: If original execution not found or still running.
        """
        # Fetch original execution
        original = ExecutionLogService.get_execution(original_execution_id)
        if not original:
            raise ValueError(f"Execution not found: {original_execution_id}")

        status = original.get("status", "")
        if status == "running":
            raise ValueError(f"Cannot replay a running execution: {original_execution_id}")

        # Create new execution record with replay trigger type
        original_trigger_type = original.get("trigger_type", "unknown")
        replay_trigger_type = f"replay:{original_trigger_type}"

        replay_execution_id = ExecutionLogService.start_execution(
            trigger_id=original.get("trigger_id", "unknown"),
            trigger_type=replay_trigger_type,
            prompt=original.get("prompt", ""),
            backend_type=original.get("backend_type", "claude"),
            command=original.get("command", ""),
            trigger_config_snapshot=original.get("trigger_config_snapshot"),
        )

        # Persist comparison record BEFORE starting subprocess
        # (per 08-RESEARCH.md: relationship survives crashes)
        comparison_id = create_replay_comparison(
            original_execution_id=original_execution_id,
            replay_execution_id=replay_execution_id,
            notes=notes,
        )

        if not comparison_id:
            logger.error(
                "Failed to create replay comparison for %s -> %s",
                original_execution_id,
                replay_execution_id,
            )

        # Start subprocess execution in background thread
        cmd_str = original.get("command", "")
        if cmd_str:
            thread = threading.Thread(
                target=cls._run_replay_subprocess,
                args=(replay_execution_id, cmd_str, original.get("trigger_id", "")),
                daemon=True,
            )
            thread.start()
        else:
            # No command to replay -- mark as failed
            ExecutionLogService.finish_execution(
                execution_id=replay_execution_id,
                status="failed",
                error_message="Original execution has no command to replay",
            )

        return {
            "comparison_id": comparison_id,
            "original_execution_id": original_execution_id,
            "replay_execution_id": replay_execution_id,
        }

    @classmethod
    def _run_replay_subprocess(cls, execution_id: str, cmd_str: str, trigger_id: str) -> None:
        """Run the replay subprocess in background (mirrors run_trigger pattern)."""
        from app.config import PROJECT_ROOT

        try:
            cmd = cmd_str.split()

            # Wrap with stdbuf for line-buffered output if available
            if shutil.which("stdbuf"):
                cmd = ["stdbuf", "-oL", "-eL"] + cmd

            process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )

            ProcessManager.register(execution_id, process, trigger_id)

            # Stream stdout and stderr in threads
            stdout_thread = threading.Thread(
                target=cls._stream_pipe,
                args=(execution_id, "stdout", process.stdout),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=cls._stream_pipe,
                args=(execution_id, "stderr", process.stderr),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # Wait for process (30 minute timeout)
            try:
                exit_code = process.wait(timeout=1800)
            except subprocess.TimeoutExpired:
                import os
                import signal

                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except OSError:
                    pass
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status="timeout",
                    error_message="Replay timed out after 30 minutes",
                )
                ProcessManager.cleanup(execution_id)
                return

            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)

            # Determine status
            was_cancelled = ProcessManager.is_cancelled(execution_id)
            if was_cancelled:
                status = "cancelled"
            elif exit_code == 0:
                status = "success"
            else:
                status = "failed"

            ExecutionLogService.finish_execution(
                execution_id=execution_id,
                status=status,
                exit_code=exit_code,
            )
            ProcessManager.cleanup(execution_id)

        except Exception as e:
            logger.error("Replay subprocess error for %s: %s", execution_id, e)
            ExecutionLogService.finish_execution(
                execution_id=execution_id,
                status="failed",
                error_message=str(e),
            )
            ProcessManager.cleanup(execution_id)

    @classmethod
    def _stream_pipe(cls, execution_id: str, stream: str, pipe) -> None:
        """Read lines from a subprocess pipe and append to execution log."""
        try:
            for line in pipe:
                ExecutionLogService.append_log(execution_id, stream, line.rstrip("\n"))
        except Exception as e:
            logger.error("Error streaming %s for %s: %s", stream, execution_id, e)
        finally:
            pipe.close()

    @classmethod
    def compare_outputs(cls, execution_id_a: str, execution_id_b: str) -> dict:
        """Compare outputs of two executions using unified diff.

        Args:
            execution_id_a: First (original) execution ID.
            execution_id_b: Second (replay) execution ID.

        Returns:
            OutputDiff-shaped dict with diff_lines, line counts, and change_summary.

        Raises:
            ValueError: If either execution not found or still running.
        """
        exec_a = ExecutionLogService.get_execution(execution_id_a)
        exec_b = ExecutionLogService.get_execution(execution_id_b)

        if not exec_a:
            raise ValueError(f"Execution not found: {execution_id_a}")
        if not exec_b:
            raise ValueError(f"Execution not found: {execution_id_b}")

        if exec_a.get("status") == "running":
            raise ValueError(f"Execution still running: {execution_id_a}")
        if exec_b.get("status") == "running":
            raise ValueError(f"Execution still running: {execution_id_b}")

        # Get stdout logs
        stdout_a = (exec_a.get("stdout_log") or "").splitlines(keepends=True)
        stdout_b = (exec_b.get("stdout_log") or "").splitlines(keepends=True)

        # Generate unified diff
        diff = list(
            difflib.unified_diff(
                stdout_a,
                stdout_b,
                fromfile=f"execution/{execution_id_a}",
                tofile=f"execution/{execution_id_b}",
                lineterm="",
            )
        )

        # Parse diff into structured DiffLine objects
        diff_lines = []
        added = 0
        removed = 0
        unchanged = 0
        line_number = 0

        for line in diff:
            line_number += 1
            content = line.rstrip("\n")

            # Skip diff headers
            if content.startswith("---") or content.startswith("+++"):
                continue
            if content.startswith("@@"):
                diff_lines.append(
                    {"line_number": line_number, "type": "header", "content": content}
                )
                continue

            if content.startswith("+"):
                diff_lines.append(
                    {
                        "line_number": line_number,
                        "type": "added",
                        "content": content[1:],
                    }
                )
                added += 1
            elif content.startswith("-"):
                diff_lines.append(
                    {
                        "line_number": line_number,
                        "type": "removed",
                        "content": content[1:],
                    }
                )
                removed += 1
            else:
                diff_lines.append(
                    {
                        "line_number": line_number,
                        "type": "unchanged",
                        "content": content[1:] if content.startswith(" ") else content,
                    }
                )
                unchanged += 1

        return {
            "original_execution_id": execution_id_a,
            "replay_execution_id": execution_id_b,
            "diff_lines": diff_lines,
            "original_line_count": len(stdout_a),
            "replay_line_count": len(stdout_b),
            "change_summary": {
                "added": added,
                "removed": removed,
                "unchanged": unchanged,
            },
        }
