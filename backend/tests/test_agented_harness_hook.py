"""Tests for the harness-hook dispatcher script (T2 hook injection)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_dispatcher():
    """Load ``scripts/agented_harness_hook.py`` as a module (no ``__main__``
    side effects fire because we only run ``module.run(...)``)."""
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "agented_harness_hook.py"
    )
    spec = importlib.util.spec_from_file_location("agented_harness_hook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


dispatcher = _load_dispatcher()


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    """Stand up a fake CLAUDE_CONFIG_DIR with a sidecar config the dispatcher
    will pick up via the env var."""
    cfg_dir = tmp_path / "overlay"
    cfg_dir.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg_dir))
    monkeypatch.delenv("AGENTED_HARNESS_HOOK_CONFIG", raising=False)

    def _write(specs: list[dict]):
        (cfg_dir / "_agented_harness_hooks.json").write_text(
            json.dumps({"execution_id": "exec-test", "hook_specs": specs})
        )

    return _write


def test_h2_block_emits_decision_payload(sidecar, capsys):
    sidecar([{
        "layer": "h2",
        "name": "no-rm-rf",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "Bash", "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"},
            "message": "Refused: destructive command.",
        },
    }])

    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /tmp/foo"},
    })
    exit_code = dispatcher.run(payload)

    captured = capsys.readouterr()
    assert exit_code == 0
    response = json.loads(captured.out)
    assert response["decision"] == "block"
    assert "Refused" in response["reason"]


def test_h2_canonicalize_blocks_with_canonical_form_hint(sidecar, capsys):
    sidecar([{
        "layer": "h2", "name": "quote-cols",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "execute_sql",
                      "arg_regex": {"query": "FROM\\s+\\w+\\s+\\w+"}},
            "action": {"kind": "canonicalize",
                       "params": {"suggestion": "FROM \"table name\""}},
            "message": "Unquoted spaced table name.",
        },
    }])
    dispatcher.run(json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "execute_sql",
        "tool_input": {"query": "SELECT * FROM customer orders"},
    }))
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["decision"] == "block"
    assert "Unquoted spaced table name." in body["reason"]
    assert 'FROM "table name"' in body["reason"]


def test_h2_rescue_blocks_with_into_tool_hint(sidecar, capsys):
    """When the model wrote ``take_action({…})`` in content instead of using
    the real tool, rescue tells it which tool to use next."""
    sidecar([{
        "layer": "h2", "name": "rescue-take-action",
        "spec": {
            "trigger": "pre_tool_use",
            # The model called a generic intent-tool when it should have
            # used submit_answer.
            "match": {"tool": "generic_action"},
            "action": {"kind": "rescue",
                       "params": {"into_tool": "submit_answer"}},
        },
    }])
    dispatcher.run(json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "generic_action",
        "tool_input": {"data": "x"},
    }))
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["decision"] == "block"
    assert "submit_answer" in body["reason"]


def test_h2_block_no_match_passes_through(sidecar, capsys):
    sidecar([{
        "layer": "h2",
        "name": "no-rm-rf",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "Bash", "arg_regex": {"command": "rm\\s+-rf"}},
            "action": {"kind": "block"},
            "message": "blocked",
        },
    }])

    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls /tmp"},
    })
    exit_code = dispatcher.run(payload)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == ""  # no block emitted


def test_h2_wrong_tool_does_not_fire(sidecar, capsys):
    sidecar([{
        "layer": "h2",
        "name": "no-bash-rm",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "Bash", "arg_regex": {"command": ".*"}},
            "action": {"kind": "block"},
            "message": "x",
        },
    }])

    payload = json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"path": "/etc/passwd"},
    })
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_h2_ignored_on_post_tool_use_event(sidecar, capsys):
    """An H2 spec with trigger=pre_tool_use must not fire on PostToolUse."""
    sidecar([{
        "layer": "h2",
        "name": "x",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "Bash"},
            "action": {"kind": "block"},
            "message": "no",
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": "ok",
    })
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_h4_inject_hint_writes_to_stderr_on_post_match(sidecar, capsys):
    sidecar([{
        "layer": "h4",
        "name": "retry-on-perm-denied",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "regex_count",
                         "params": {"pattern": "permission denied"}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "Try with sudo."}},
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat /etc/shadow"},
        "tool_response": "cat: /etc/shadow: permission denied",
    })
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert captured.out == ""  # no block on stdout
    assert "Try with sudo." in captured.err


def test_h4_repeat_action_fires_after_k_identical_calls(sidecar, capsys):
    """The state file accumulates history across fires; ``repeat_action``
    fires on the K-th identical (tool, args)."""
    sidecar([{
        "layer": "h4",
        "name": "stop-repeats",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "repeat_action",
                         "params": {"k": 3, "window": 5}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "Try differently."}},
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "tool_response": "ok",
    })

    # First two fires: no hint (count < k).
    dispatcher.run(payload)
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert captured.err == ""

    # Third identical fire: hint emitted.
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert "Try differently." in captured.err


def test_h4_repeat_action_resets_with_different_call(sidecar, capsys):
    """Non-matching tool calls within the window count toward the rolling
    history but break the identical-streak."""
    sidecar([{
        "layer": "h4",
        "name": "stop-repeats",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "repeat_action",
                         "params": {"k": 3, "window": 5}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "Try differently."}},
        },
    }])
    same = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "ls"},
        "tool_response": "ok",
    })
    other = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "pwd"},
        "tool_response": "ok",
    })
    # 2x same, then 1x different, then 1x same — only 2 'same' in window-of-3.
    dispatcher.run(same)
    dispatcher.run(same)
    dispatcher.run(other)
    dispatcher.run(same)
    captured = capsys.readouterr()
    assert "Try differently." not in captured.err


def test_h4_stagnation_fires_when_last_k_are_identical(sidecar, capsys):
    sidecar([{
        "layer": "h4",
        "name": "halt-stagnation",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "stagnation", "params": {"k": 3}},
            "response": {"kind": "inject_hint",
                         "params": {"text": "You're stuck."}},
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Read", "tool_input": {"path": "/x"},
        "tool_response": "1",
    })
    dispatcher.run(payload)
    dispatcher.run(payload)
    capsys.readouterr()
    dispatcher.run(payload)
    captured = capsys.readouterr()
    assert "You're stuck." in captured.err


def test_h4_budget_fires_when_fire_count_threshold_reached(sidecar, capsys):
    sidecar([{
        "layer": "h4",
        "name": "budget-cap",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "budget", "params": {"threshold": 3}},
            "response": {"kind": "abort",
                         "params": {"text": "Budget exceeded."}},
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "ls"},
        "tool_response": "ok",
    })
    dispatcher.run(payload)
    dispatcher.run(payload)
    capsys.readouterr()
    dispatcher.run(payload)  # third fire crosses threshold
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["decision"] == "block"
    assert "Budget exceeded." in body["reason"]


def test_h4_state_file_is_persisted_under_claude_config_dir(sidecar, tmp_path):
    """State persistence is what makes the stateful detectors possible —
    verify the dispatcher actually writes the sidecar."""
    sidecar([{
        "layer": "h4", "name": "x",
        "spec": {
            "trigger": "post_tool_use",
            "detector": {"kind": "regex_count", "params": {"pattern": "ok"}},
            "response": {"kind": "inject_hint", "params": {"text": "hi"}},
        },
    }])
    payload = json.dumps({
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_input": {"command": "ls"},
        "tool_response": "ok",
    })
    dispatcher.run(payload)

    state_path = Path(__import__("os").environ["CLAUDE_CONFIG_DIR"]) / \
        "_agented_harness_state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text())
    assert state["fire_count"] == 1
    assert state["history"] and state["history"][-1][0] == "Bash"


def test_no_sidecar_is_a_passthrough(monkeypatch, capsys):
    """Empty env / no sidecar must not crash the dispatcher."""
    monkeypatch.delenv("AGENTED_HARNESS_HOOK_CONFIG", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    exit_code = dispatcher.run(json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }))
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_malformed_payload_is_a_passthrough(sidecar, capsys):
    sidecar([{
        "layer": "h2",
        "name": "x",
        "spec": {"trigger": "pre_tool_use",
                 "match": {"tool": "Bash"},
                 "action": {"kind": "block"}, "message": "x"},
    }])
    exit_code = dispatcher.run("not-json {")
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_invalid_regex_in_rule_is_skipped(sidecar, capsys):
    """A malformed regex in a user-authored / evolved layer must not break
    the dispatcher — that rule simply doesn't fire."""
    sidecar([{
        "layer": "h2",
        "name": "broken-regex",
        "spec": {
            "trigger": "pre_tool_use",
            "match": {"tool": "Bash", "arg_regex": {"command": "[unclosed"}},
            "action": {"kind": "block"},
            "message": "blocked",
        },
    }])
    dispatcher.run(json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }))
    captured = capsys.readouterr()
    assert captured.out == ""
