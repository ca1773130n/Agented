"""Tests for ``ContextCompilerService``.

Covers: project binding resolution across the six kinds, session
overrides (opt-out + addition), per-prompt attachment rendering,
and the "skip silently" behavior for stale references.
"""

from __future__ import annotations

import pytest

from app.db import (
    add_project_forge_binding,
    create_command as db_create_command,
    create_hook as db_create_hook,
    create_project,
    create_rule as db_create_rule,
)
from app.services.context_compiler_service import (
    ATTACHMENT_BYTE_CAP,
    ContextBundle,
    ContextCompilerService,
)


@pytest.fixture
def project(isolated_db):
    del isolated_db
    return create_project(name="compiler-test", description="fixture")


def test_empty_project_returns_empty_bundle(project):
    bundle = ContextCompilerService.compile(project)
    assert isinstance(bundle, ContextBundle)
    assert bundle.is_empty()
    assert bundle.system_prompt_text == ""
    assert bundle.prompt_prepend == ""
    assert bundle.overlay_files == {}


def test_rule_binding_emits_system_prompt(project):
    rule_id = db_create_rule(
        name="no-emoji",
        description="Never use emoji in user-facing output.",
        rule_type="validation",
        project_id=project,
    )
    add_project_forge_binding(project, "rule", str(rule_id))

    bundle = ContextCompilerService.compile(project)
    assert "no-emoji" in bundle.system_prompt_text
    assert "Never use emoji" in bundle.system_prompt_text
    assert len(bundle.resolved_bindings) == 1
    assert bundle.resolved_bindings[0]["kind"] == "rule"


def test_command_binding_writes_overlay_file(project):
    cmd_id = db_create_command(
        name="deploy",
        description="ship it",
        content="echo deploying",
        project_id=project,
    )
    add_project_forge_binding(project, "command", str(cmd_id))

    bundle = ContextCompilerService.compile(project)
    assert "commands/deploy.md" in bundle.overlay_files
    assert bundle.overlay_files["commands/deploy.md"] == "echo deploying"


def test_hook_binding_lands_in_sidecar(project):
    hook_id = db_create_hook(
        name="guard",
        event="PreToolUse",
        content="set -e\necho guarding",
        project_id=project,
    )
    add_project_forge_binding(project, "hook", str(hook_id))

    bundle = ContextCompilerService.compile(project)
    assert "_agented_hooks.json" in bundle.overlay_files
    # Sidecar JSON contains the hook entry — the claude renderer
    # is what materializes it into the overlay's settings.json.
    assert "guarding" in bundle.overlay_files["_agented_hooks.json"]


def test_skill_binding_adds_pointer_to_prompt(project):
    add_project_forge_binding(project, "skill", "code-search")
    bundle = ContextCompilerService.compile(project)
    assert "code-search" in bundle.system_prompt_text
    assert "Skill available" in bundle.system_prompt_text


def test_subagent_binding_included_in_bundle(project):
    """A bound sub-agent surfaces in the compiled ContextBundle (name + body)
    via the get_subagent resolution path, and is mirrored into the overlay's
    agents/ dir for claude's native discovery."""
    from app.db.subagents import create_subagent

    sa = create_subagent(
        name="code-reviewer",
        description="Reviews code",
        content="You review code for bugs.",
        project_id=project,
    )
    add_project_forge_binding(project, "subagent", sa["id"])

    bundle = ContextCompilerService.compile(project)
    assert len(bundle.subagents) == 1
    assert bundle.subagents[0]["name"] == "code-reviewer"
    assert bundle.subagents[0]["body"] == "You review code for bugs."
    # claude native-discovery overlay file
    assert "agents/code-reviewer.md" in bundle.overlay_files
    assert bundle.overlay_files["agents/code-reviewer.md"] == "You review code for bugs."
    assert any(
        rb["kind"] == "subagent" and rb["asset_id"] == sa["id"]
        for rb in bundle.resolved_bindings
    )
    assert not bundle.is_empty()


def test_stale_subagent_binding_skipped(project):
    add_project_forge_binding(project, "subagent", "subag-doesnotexist")
    bundle = ContextCompilerService.compile(project)
    assert bundle.subagents == []
    assert len(bundle.skipped_bindings) == 1
    assert bundle.skipped_bindings[0]["reason"] == "not found"


def test_stale_binding_skipped_not_raised(project):
    # Bind to a rule id that doesn't exist — compile must succeed
    # and surface the skip in diagnostics so the operator can fix
    # the binding without the session breaking.
    add_project_forge_binding(project, "rule", "99999")
    bundle = ContextCompilerService.compile(project)
    assert bundle.system_prompt_text == ""
    assert len(bundle.skipped_bindings) == 1
    assert bundle.skipped_bindings[0]["reason"] == "not found"


def test_session_override_disables_binding(project):
    rule_id = db_create_rule(
        name="opt-out",
        description="should be disabled",
        rule_type="validation",
        project_id=project,
    )
    binding = add_project_forge_binding(project, "rule", str(rule_id))

    bundle = ContextCompilerService.compile(
        project,
        session_overrides={"disabled_binding_ids": [binding["id"]]},
    )
    assert bundle.system_prompt_text == ""


def test_session_override_adds_session_only_skill(project):
    bundle = ContextCompilerService.compile(
        project,
        session_overrides={
            "additions": [{"kind": "skill", "asset_id": "session-only-skill"}],
        },
    )
    assert "session-only-skill" in bundle.system_prompt_text


def test_attachment_file_embeds_repo_relative_path(project, tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("hello from notes", encoding="utf-8")

    bundle = ContextCompilerService.compile(
        project,
        attachments=[{"kind": "file", "path": "notes.md"}],
        project_root=str(tmp_path),
    )
    assert "=== Operator Context ===" in bundle.prompt_prepend
    assert "hello from notes" in bundle.prompt_prepend
    assert "### file: notes.md" in bundle.prompt_prepend


def test_attachment_file_outside_root_is_rejected(project, tmp_path):
    # Path escape attempts are silently dropped, not raised — the
    # operator's session shouldn't error on a typo'd path.
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("forbidden", encoding="utf-8")

    bundle = ContextCompilerService.compile(
        project,
        attachments=[{"kind": "file", "path": "../outside.txt"}],
        project_root=str(tmp_path),
    )
    assert "forbidden" not in bundle.prompt_prepend


def test_attachment_file_truncated_above_cap(project, tmp_path):
    big = tmp_path / "big.log"
    payload = "X" * (ATTACHMENT_BYTE_CAP + 1000)
    big.write_text(payload, encoding="utf-8")

    bundle = ContextCompilerService.compile(
        project,
        attachments=[{"kind": "file", "path": "big.log"}],
        project_root=str(tmp_path),
    )
    assert "[truncated]" in bundle.prompt_prepend
    # And the embedded chunk is exactly the cap — not the full file.
    assert bundle.prompt_prepend.count("X") <= ATTACHMENT_BYTE_CAP + 10


def test_attachment_snippet_and_url_combine(project, monkeypatch):
    # Stub the URL fetcher so the test doesn't hit the network.
    from app.services import url_summarizer as us

    monkeypatch.setattr(
        us,
        "fetch_and_summarize",
        lambda url: us.UrlSummary(url=url, title="Spec", text="Spec body"),
    )
    bundle = ContextCompilerService.compile(
        project,
        attachments=[
            {"kind": "snippet", "label": "error", "text": "TraceError: x"},
            {"kind": "url", "url": "https://example.com/spec"},
        ],
    )
    assert "TraceError" in bundle.prompt_prepend
    assert "https://example.com/spec" in bundle.prompt_prepend
    assert "Spec body" in bundle.prompt_prepend


def test_attachment_url_inline_summary_wins(project, monkeypatch):
    # When the operator supplies their own summary, we skip the
    # fetch entirely. Verify by making the fetcher raise — it
    # shouldn't be called.
    from app.services import url_summarizer as us

    def _should_not_be_called(url):
        raise AssertionError("fetcher should not be called when summary supplied")

    monkeypatch.setattr(us, "fetch_and_summarize", _should_not_be_called)
    bundle = ContextCompilerService.compile(
        project,
        attachments=[
            {"kind": "url", "url": "https://x/y", "summary": "op note"},
        ],
    )
    assert "op note" in bundle.prompt_prepend


def test_attachment_url_fetch_failure_still_renders(project, monkeypatch):
    from app.services import url_summarizer as us

    monkeypatch.setattr(
        us,
        "fetch_and_summarize",
        lambda url: us.UrlSummary(url=url, title="", text="", error="HTTP 404"),
    )
    bundle = ContextCompilerService.compile(
        project,
        attachments=[{"kind": "url", "url": "https://example.com/missing"}],
    )
    assert "https://example.com/missing" in bundle.prompt_prepend
    assert "[fetch failed: HTTP 404]" in bundle.prompt_prepend


def test_to_dict_roundtrips(project):
    add_project_forge_binding(project, "skill", "round-trip-skill")
    bundle = ContextCompilerService.compile(project)
    restored = ContextBundle.from_dict(bundle.to_dict())
    assert restored.system_prompt_text == bundle.system_prompt_text
    assert restored.overlay_files == bundle.overlay_files
    assert restored.mcp_servers == bundle.mcp_servers


def test_preview_dict_lists_overlay_keys(project):
    cmd_id = db_create_command(
        name="deploy",
        description="ship",
        content="echo go",
        project_id=project,
    )
    add_project_forge_binding(project, "command", str(cmd_id))

    preview = ContextCompilerService.compile(project).to_preview_dict()
    assert "commands/deploy.md" in preview["overlay_files"]
    assert preview["mcp_servers"] == []
    assert len(preview["resolved_bindings"]) == 1
