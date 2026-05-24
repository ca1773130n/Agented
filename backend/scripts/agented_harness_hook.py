#!/usr/bin/env python3
"""Agented harness-hook dispatcher (T2 hook injection).

Claude Code fires this as a PreToolUse / PostToolUse hook command. It reads
its rule set from a sidecar JSON file in the per-execution overlay dir, walks
the rules against the tool-call payload on stdin, and emits a Claude Code
hook response when a rule fires.

Sidecar lookup order:
    1. ``$AGENTED_HARNESS_HOOK_CONFIG`` (absolute path)
    2. ``$CLAUDE_CONFIG_DIR/_agented_harness_hooks.json``

Cross-fire state (for stateful H4 detectors) lives at
``$CLAUDE_CONFIG_DIR/_agented_harness_state.json``; we read it at the start
of each fire, update history + counters, and write it back at the end. The
file's lifespan is the overlay's, which is one execution.

Behaviour:
    - Exits 0 by default (allow the tool call to proceed).
    - On H2 ``block`` match: emits ``{"decision": "block", "reason": ...}``
      on stdout and exits 0 — Claude Code reads the JSON and refuses
      the tool call with the rule's message.
    - On H4 ``inject_hint`` match: writes the hint text to stderr so
      Claude Code surfaces it to the model on the next turn.
    - On H4 ``abort`` match: emits ``{"decision": "block", "reason": ...}``
      with the abort reason so Claude Code stops calling the tool.
    - Any internal error → exit 0 (pass-through). Our hook MUST NOT be
      able to wedge the user's bot.

H4 detectors supported today:
    - ``regex_count``  — stateless; matches against this fire's tool_response
    - ``repeat_action`` — stateful; counts identical (tool, args) in the
                          recent history window
    - ``stagnation``    — stateful; fires when the last K history entries
                          are identical
    - ``budget``        — stateful; fires when total fire_count >= threshold

H2 actions:
    - ``block``        — refuse with ``message`` as reason
    - ``canonicalize`` — refuse with an advisory message that names the
                         correct form. Claude Code's stdout hook protocol
                         doesn't expose a "modify-input" decision in
                         general, so the model retries with the corrected
                         form on the next turn. ``params.suggestion`` adds
                         the canonical form to the message.
    - ``rescue``       — refuse with an advisory naming the *correct tool*
                         to use. Common when the model emits a take_action(…)
                         in content rather than a real tool_use. ``params
                         .into_tool`` adds the target tool name.

Both ``canonicalize`` and ``rescue`` degrade to a useful block-with-hint
when the hook protocol can't truly modify the call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_EVENT_FOR_TRIGGER = {
    "pre_tool_use": "PreToolUse",
    "post_tool_use": "PostToolUse",
}


def _load_config() -> dict[str, Any]:
    """Locate and parse the harness-hook sidecar. ``{}`` on any failure."""
    candidates: list[Path] = []
    explicit = os.environ.get("AGENTED_HARNESS_HOOK_CONFIG")
    if explicit:
        candidates.append(Path(explicit))
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg_dir:
        candidates.append(Path(cfg_dir) / "_agented_harness_hooks.json")

    for p in candidates:
        try:
            if p.is_file():
                return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
    return {}


_HISTORY_CAP = 50  # rolling window of (tool, args) signatures


def _state_path() -> Optional[Path]:
    cfg_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if not cfg_dir:
        return None
    return Path(cfg_dir) / "_agented_harness_state.json"


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if p is None:
        return {"history": [], "fire_count": 0}
    try:
        if p.is_file():
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                data.setdefault("history", [])
                data.setdefault("fire_count", 0)
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"history": [], "fire_count": 0}


def _save_state(state: dict[str, Any]) -> None:
    p = _state_path()
    if p is None:
        return
    try:
        p.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        # Best-effort: state loss across one fire degrades stateful
        # detectors but doesn't break the hook.
        pass


def _detect_event(payload: dict[str, Any]) -> str:
    """Claude Code passes the event name as ``hook_event_name`` on newer
    versions. Older versions infer from presence of ``tool_response``."""
    name = payload.get("hook_event_name")
    if name:
        return str(name)
    return "PostToolUse" if "tool_response" in payload else "PreToolUse"


def _matches(match: dict[str, Any], tool_name: str,
             tool_input: dict[str, Any], content: str) -> bool:
    """All present fields in the H2/H4 match predicate must match."""
    expected_tool = match.get("tool")
    if expected_tool and expected_tool != tool_name:
        return False
    for arg, pattern in (match.get("arg_regex") or {}).items():
        val = str(tool_input.get(arg, ""))
        try:
            if not re.search(pattern, val):
                return False
        except re.error:
            return False
    content_re = match.get("content_regex")
    if content_re:
        try:
            if not re.search(content_re, content):
                return False
        except re.error:
            return False
    return True


def _detector_fires(
    detector: dict[str, Any],
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    content: str,
    state: dict[str, Any],
) -> bool:
    """Evaluate one H4 detector against the current fire + accumulated state."""
    kind = detector.get("kind")
    params = detector.get("params") or {}

    if kind == "regex_count":
        pattern = params.get("pattern")
        if not pattern:
            return False
        try:
            return bool(re.search(pattern, content))
        except re.error:
            return False

    history = state.get("history") or []

    if kind == "repeat_action":
        # Fires when the current (tool, args) ends a run of ``k`` *consecutive*
        # identical entries at the tail of the history. We deliberately do
        # NOT count occurrences across the whole window — the annotator's
        # post-hoc clustering does that; this detector exists to break a
        # live loop, where consecutive-tail is the right signal. Intervening
        # other tool calls reset the streak.
        k = int(params.get("k", 3))
        sig = [tool_name, json.dumps(tool_input, sort_keys=True, default=str)]
        streak = 0
        for h in reversed(history):
            if h == sig:
                streak += 1
            else:
                break
        return streak >= k

    if kind == "stagnation":
        k = int(params.get("k", 5))
        if len(history) < k:
            return False
        tail = [tuple(h) for h in history[-k:]]
        return len(set(tail)) == 1

    if kind == "budget":
        threshold = int(params.get("threshold", 50))
        return int(state.get("fire_count", 0)) >= threshold

    return False


def _emit_response(
    response_kind: str,
    text: str,
) -> Optional[int]:
    """Apply an H4 response. Returns an exit code to short-circuit, or
    ``None`` to keep processing further specs."""
    if response_kind == "inject_hint":
        if text:
            sys.stderr.write(text + "\n")
        return None
    if response_kind == "abort":
        sys.stdout.write(json.dumps({
            "decision": "block",
            "reason": text or "Aborted by harness rule.",
        }))
        return 0
    if response_kind == "suppress_dup":
        sys.stdout.write(json.dumps({
            "decision": "block",
            "reason": text or "Duplicate action suppressed.",
        }))
        return 0
    return None


def run(stdin_text: str) -> int:
    """Dispatcher entry point — split out for testability."""
    if not stdin_text:
        return 0
    try:
        payload = json.loads(stdin_text)
    except json.JSONDecodeError:
        return 0

    config = _load_config()
    hook_specs: list[dict[str, Any]] = config.get("hook_specs") or []
    if not hook_specs:
        return 0

    event = _detect_event(payload)
    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")
    content = "" if tool_response is None else (
        tool_response if isinstance(tool_response, str)
        else json.dumps(tool_response, default=str)
    )

    state = _load_state()
    # Record this fire BEFORE running detectors so the current call counts.
    sig = [tool_name, json.dumps(tool_input, sort_keys=True, default=str)]
    history = state.setdefault("history", [])
    history.append(sig)
    if len(history) > _HISTORY_CAP:
        del history[: len(history) - _HISTORY_CAP]
    state["fire_count"] = int(state.get("fire_count", 0)) + 1

    try:
        for spec in hook_specs:
            spec_body = spec.get("spec") or {}
            spec_event = _EVENT_FOR_TRIGGER.get(spec_body.get("trigger"))
            if spec_event != event:
                continue

            match = spec_body.get("match") or {}
            action = spec_body.get("action") or {}
            response = spec_body.get("response") or {}

            if spec.get("layer") == "h2":
                action_kind = action.get("kind")
                if action_kind not in ("block", "canonicalize", "rescue"):
                    continue
                if not _matches(match, tool_name, tool_input, content):
                    continue

                if action_kind == "block":
                    reason = (
                        spec_body.get("message") or "Refused by harness rule."
                    )
                elif action_kind == "canonicalize":
                    base = (
                        spec_body.get("message")
                        or "Action needs canonicalisation before it can run."
                    )
                    suggestion = (action.get("params") or {}).get("suggestion") or ""
                    reason = (
                        f"{base} Canonical form: {suggestion}" if suggestion else base
                    )
                else:  # rescue
                    base = (
                        spec_body.get("message")
                        or "This action must be submitted through a proper tool call."
                    )
                    into_tool = (action.get("params") or {}).get("into_tool") or ""
                    reason = (
                        f"{base} Use the {into_tool} tool."
                        if into_tool else base
                    )

                sys.stdout.write(json.dumps({
                    "decision": "block",
                    "reason": reason,
                }))
                return 0

            if spec.get("layer") == "h4":
                detector = spec_body.get("detector") or {}
                if not _detector_fires(
                    detector,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    content=content,
                    state=state,
                ):
                    continue
                response_kind = response.get("kind") or ""
                text = (response.get("params") or {}).get("text") or ""
                short_circuit = _emit_response(response_kind, text)
                if short_circuit is not None:
                    return short_circuit
    finally:
        _save_state(state)

    return 0


def main() -> int:
    try:
        return run(sys.stdin.read())
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
