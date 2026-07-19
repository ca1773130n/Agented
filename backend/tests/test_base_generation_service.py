"""Regression: the generation SSE stream must not leak the claude subprocess.

An abandoned generator (SSE client disconnect → GeneratorExit at a `yield`) must
tear down the process group instead of leaking the child + reader threads + pipes.
"""

import io

from app.services import base_generation_service as bgs
from app.services import conversation_streaming as cs
from app.services import sandbox_wrap


class _FakeProc:
    pid = 999_999

    def __init__(self):
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class _Svc(bgs.BaseGenerationService):
    @classmethod
    def _gather_context(cls):
        return {}

    @classmethod
    def _summarize_context(cls, context):
        return ""

    @classmethod
    def _build_prompt(cls, description, context):
        return "prompt"

    @classmethod
    def _parse_json(cls, text):
        return {}

    @classmethod
    def _validate(cls, config):
        return config, []

    @classmethod
    def _extract_progress(cls, text, reported):
        return []

    @classmethod
    def _pump_claude_stream(cls, process, sse):
        # Simulate an in-progress stream that never completes on its own.
        yield sse("output", {"content": "partial"})
        yield sse("output", {"content": "more"})
        return "unreached"


def test_generate_streaming_terminates_process_on_client_disconnect(monkeypatch):
    terminated = []
    monkeypatch.setattr(cs, "_terminate_proc_group", lambda p: terminated.append(p))
    monkeypatch.setattr(
        sandbox_wrap, "apply_sandbox_and_enforce", lambda cmd, root, **kw: (cmd, False)
    )
    fake = _FakeProc()
    monkeypatch.setattr(bgs.subprocess, "Popen", lambda *a, **k: fake)

    gen = _Svc.generate_streaming("make a thing")
    # Drive through the pre-launch phase events into the streaming section.
    for ev in gen:
        if "partial" in ev:
            break
    # Client disconnects mid-stream.
    gen.close()

    assert terminated == [fake], "process group must be terminated on an abandoned generator"
