"""Tests for the v0.7.77 multi-file skill package finalize path.

Covers ``SkillConversationService._build_package_preview`` (the
shared validator) + the end-to-end ``finalize_skill`` write to
disk: frontmatter rendering, file-path validation (prefix +
traversal + cap), atomic per-file write, legacy schema shim.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services import skill_conversation_service as svc
from app.services.skill_conversation_service import (
    ConversationMessage,
    SkillConversationService,
    _SkillConfigError,
)


def _conv_with(cfg: dict) -> dict:
    """Build a conversation dict whose last assistant message
    contains the given config as a SKILL_CONFIG block.
    """
    body = "---SKILL_CONFIG---\n" + json.dumps(cfg) + "\n---END_CONFIG---"
    return {
        "messages": [
            ConversationMessage(role="system", content="sys", timestamp="t"),
            ConversationMessage(role="user", content="hi", timestamp="t"),
            ConversationMessage(role="assistant", content=body, timestamp="t"),
        ],
    }


_GOOD = {
    "skill_name": "data-explorer",
    "frontmatter": {
        "description": "Explore tabular datasets.",
        "license": "MIT",
        "allowed_tools": ["Bash", "Read"],
        "tags": ["data"],
    },
    "body": "Body. See scripts/profile.py.",
    "files": [
        {"path": "scripts/profile.py", "content": "#!/usr/bin/env python3\nprint('hi')\n"},
        {"path": "references/spec.md", "content": "# Spec\n"},
    ],
}


# -----------------------------------------------------------------
# preview builder
# -----------------------------------------------------------------


def test_preview_renders_frontmatter_and_body():
    preview = SkillConversationService._build_package_preview(_conv_with(_GOOD))
    md = preview["skill_md_content"]
    assert md.startswith("---\n")
    assert "name: data-explorer" in md
    assert "description: Explore tabular datasets." in md
    assert "license: MIT" in md
    assert "allowed-tools:" in md  # kebab-case on disk
    assert "Body. See scripts/profile.py" in md


def test_preview_lists_each_file_with_size():
    preview = SkillConversationService._build_package_preview(_conv_with(_GOOD))
    paths = [f["path"] for f in preview["files"]]
    assert ".claude/skills/data-explorer/scripts/profile.py" in paths
    assert ".claude/skills/data-explorer/references/spec.md" in paths
    sizes = {f["path"]: f["size_bytes"] for f in preview["files"]}
    assert sizes[".claude/skills/data-explorer/scripts/profile.py"] > 0


def test_preview_defaults_license_to_mit_when_missing():
    cfg = {**_GOOD, "frontmatter": {**_GOOD["frontmatter"]}}
    del cfg["frontmatter"]["license"]
    preview = SkillConversationService._build_package_preview(_conv_with(cfg))
    assert "license: MIT" in preview["skill_md_content"]
    assert any("license missing" in w for w in preview["warnings"])


def test_preview_warns_when_no_helper_files():
    cfg = {**_GOOD, "files": []}
    preview = SkillConversationService._build_package_preview(_conv_with(cfg))
    assert any("SKILL.md-only" in w for w in preview["warnings"])


# -----------------------------------------------------------------
# validation rejections
# -----------------------------------------------------------------


def test_reject_invalid_skill_name():
    cfg = {**_GOOD, "skill_name": "Bad Name!"}
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "INVALID_SKILL_NAME"


def test_reject_missing_description():
    cfg = {**_GOOD, "frontmatter": {"license": "MIT"}}
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "MISSING_DESCRIPTION"


def test_reject_unknown_frontmatter_key():
    cfg = {**_GOOD, "frontmatter": {**_GOOD["frontmatter"], "bogus": True}}
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "UNKNOWN_FRONTMATTER_KEY"


def test_reject_path_traversal():
    cfg = {
        **_GOOD,
        "files": [{"path": "scripts/../../etc/passwd", "content": "x"}],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "PATH_TRAVERSAL"


def test_reject_invalid_path_prefix():
    cfg = {**_GOOD, "files": [{"path": "random.txt", "content": "x"}]}
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "INVALID_PATH_PREFIX"


def test_reject_file_too_large():
    cfg = {
        **_GOOD,
        "files": [{"path": "scripts/big.py", "content": "x" * (svc._FILE_BYTE_CAP + 1)}],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "FILE_TOO_LARGE"


def test_reject_too_many_files():
    cfg = {
        **_GOOD,
        "files": [
            {"path": f"scripts/h{i}.py", "content": "x"}
            for i in range(svc._MAX_FILES + 1)
        ],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "TOO_MANY_FILES"


def test_reject_duplicate_path():
    cfg = {
        **_GOOD,
        "files": [
            {"path": "scripts/a.py", "content": "x"},
            {"path": "scripts/a.py", "content": "y"},
        ],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(_conv_with(cfg))
    assert exc.value.code == "DUPLICATE_FILE_PATH"


def test_reject_no_config_block():
    conv = {
        "messages": [
            ConversationMessage(role="assistant", content="plain text", timestamp="t"),
        ],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(conv)
    assert exc.value.code == "NO_CONFIG_BLOCK"


# -----------------------------------------------------------------
# legacy schema shim
# -----------------------------------------------------------------


def test_legacy_schema_body_synthesized():
    """v0.7.75 schema (description + triggers + instructions +
    examples, no body / frontmatter) still finalizes because the
    builder synthesizes a body from the legacy fields. Operator
    must supply ``skill_name`` + ``description`` either way.
    """
    legacy = {
        "skill_name": "legacy-skill",
        "description": "An old-schema skill.",
        "triggers": ["do x", "fix y"],
        "instructions": "Run the steps in order.",
        "examples": ["example 1"],
        # NOTE: no ``body`` / ``frontmatter`` / ``files`` keys.
    }
    preview = SkillConversationService._build_package_preview(_conv_with(legacy))
    md = preview["skill_md_content"]
    assert "name: legacy-skill" in md
    assert "An old-schema skill." in md
    assert "## Triggers" in md
    assert "## Instructions" in md
    assert preview["files"] == []


# -----------------------------------------------------------------
# end-to-end finalize: writes to disk + DB
# -----------------------------------------------------------------


def test_finalize_writes_full_package_to_disk(
    isolated_db, tmp_path, monkeypatch
):
    """Finalize writes SKILL.md + each helper/reference file
    atomically to the playground working dir, and the
    user_skills row is created."""
    del isolated_db
    monkeypatch.setattr(svc, "get_playground_working_dir", lambda: str(tmp_path))
    # Seed a conversation in the service's in-memory store.
    conv_id = "skill_testtesttesttest"
    SkillConversationService._conversations[conv_id] = {
        "messages": [
            ConversationMessage(role="assistant",
                                content="---SKILL_CONFIG---\n" + json.dumps(_GOOD) + "\n---END_CONFIG---",
                                timestamp="t"),
        ],
    }
    SkillConversationService._subscribers[conv_id] = []
    try:
        result, status = SkillConversationService.finalize_skill(conv_id)
        assert status == 201
        assert result["skill_id"]
        skill_dir = tmp_path / ".claude" / "skills" / "data-explorer"
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "profile.py").exists()
        assert (skill_dir / "references" / "spec.md").exists()
        # Script is executable
        st = (skill_dir / "scripts" / "profile.py").stat()
        assert st.st_mode & 0o100
        # SKILL.md has the frontmatter we asked for
        md = (skill_dir / "SKILL.md").read_text()
        assert md.startswith("---\nname: data-explorer\n")
        assert "Body. See scripts/profile.py" in md
        # No leftover .tmp files
        assert not any(p.suffix == ".tmp" for p in skill_dir.rglob("*"))
    finally:
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)


def test_preview_returns_stable_config_hash():
    """v0.7.77 codex BLOCK 4 — the hash is a content fingerprint
    of the extracted SKILL_CONFIG JSON. Same input → same hash;
    different content → different hash.
    """
    p1 = SkillConversationService._build_package_preview(_conv_with(_GOOD))
    p2 = SkillConversationService._build_package_preview(_conv_with(_GOOD))
    assert p1["config_hash"] == p2["config_hash"]
    assert len(p1["config_hash"]) == 64  # sha256 hex

    mutated = {**_GOOD, "skill_name": "different-name"}
    p3 = SkillConversationService._build_package_preview(_conv_with(mutated))
    assert p3["config_hash"] != p1["config_hash"]


def test_finalize_rejects_stale_config_hash(
    isolated_db, tmp_path, monkeypatch
):
    """v0.7.77 codex BLOCK 4 — when the operator passes a hash
    that doesn't match the latest config in the conversation,
    finalize returns 409 instead of silently writing a config the
    operator never reviewed.
    """
    del isolated_db
    monkeypatch.setattr(svc, "get_playground_working_dir", lambda: str(tmp_path))
    conv_id = "skill_stalehashstaleha"
    SkillConversationService._conversations[conv_id] = {
        "messages": [
            ConversationMessage(role="assistant",
                                content="---SKILL_CONFIG---\n" + json.dumps(_GOOD) + "\n---END_CONFIG---",
                                timestamp="t"),
        ],
    }
    SkillConversationService._subscribers[conv_id] = []
    try:
        result, status = SkillConversationService.finalize_skill(
            conv_id, expected_config_hash="deadbeef" * 8
        )
        assert status == 409
        # error_response shape: {"code": ..., "message": ..., "error": <msg>}
        assert "changed since you opened the preview" in result["message"]
        assert result["code"] == "CONFIG_HASH_MISMATCH"
        # Nothing should have been written to disk.
        assert not (tmp_path / ".claude" / "skills" / "data-explorer").exists()
    finally:
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)


def test_finalize_refuses_to_overwrite_existing_skill(
    isolated_db, tmp_path, monkeypatch
):
    """v0.7.77 codex BLOCK 6 spinoff — if a skill of the same
    name already exists, finalize 409s rather than silently
    merging or overwriting. Operator must delete the existing
    package first."""
    del isolated_db
    monkeypatch.setattr(svc, "get_playground_working_dir", lambda: str(tmp_path))
    existing_dir = tmp_path / ".claude" / "skills" / "data-explorer"
    existing_dir.mkdir(parents=True)
    (existing_dir / "preserved.txt").write_text("operator put this here")

    conv_id = "skill_existskillexists"
    SkillConversationService._conversations[conv_id] = {
        "messages": [
            ConversationMessage(role="assistant",
                                content="---SKILL_CONFIG---\n" + json.dumps(_GOOD) + "\n---END_CONFIG---",
                                timestamp="t"),
        ],
    }
    SkillConversationService._subscribers[conv_id] = []
    try:
        result, status = SkillConversationService.finalize_skill(conv_id)
        assert status == 409
        assert "already exists" in result["message"]
        assert result["code"] == "SKILL_EXISTS"
        # Pre-existing files are untouched.
        assert (existing_dir / "preserved.txt").exists()
    finally:
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)


def test_extract_distinguishes_no_block_from_malformed_block():
    """v0.7.77 codex NIT 3 — different error codes for the two
    distinct operator-facing states: "no SKILL_CONFIG markers
    yet" (keep chatting) vs "markers present but JSON malformed"
    (ask the assistant to re-emit).
    """
    no_markers = {
        "messages": [ConversationMessage(role="assistant", content="just text", timestamp="t")],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(no_markers)
    assert exc.value.code == "NO_CONFIG_BLOCK"

    bad_json = {
        "messages": [
            ConversationMessage(
                role="assistant",
                content="---SKILL_CONFIG---\n{bad json,,}\n---END_CONFIG---",
                timestamp="t",
            )
        ],
    }
    with pytest.raises(_SkillConfigError) as exc:
        SkillConversationService._build_package_preview(bad_json)
    assert exc.value.code == "INVALID_CONFIG_JSON"
    assert "malformed" in exc.value.message.lower()


def test_finalize_metadata_omits_skill_md_content(
    isolated_db, tmp_path, monkeypatch
):
    """v0.7.77 codex NIT 5 — the user_skills metadata row stores
    paths + frontmatter only, not the full SKILL.md body
    (consumers read from disk). Avoids fat DB rows when SKILL.md
    is large.
    """
    del isolated_db
    monkeypatch.setattr(svc, "get_playground_working_dir", lambda: str(tmp_path))
    conv_id = "skill_metadataomitsmd"
    SkillConversationService._conversations[conv_id] = {
        "messages": [
            ConversationMessage(role="assistant",
                                content="---SKILL_CONFIG---\n" + json.dumps(_GOOD) + "\n---END_CONFIG---",
                                timestamp="t"),
        ],
    }
    SkillConversationService._subscribers[conv_id] = []
    try:
        result, status = SkillConversationService.finalize_skill(conv_id)
        assert status == 201
        skill = result["skill"]
        meta = json.loads(skill["metadata"]) if skill.get("metadata") else {}
        assert "skill_md_content" not in meta
        assert "frontmatter" in meta
        assert "files" in meta
    finally:
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)


def test_finalize_rejects_bad_config_without_partial_write(
    isolated_db, tmp_path, monkeypatch
):
    """A config that fails validation should not leave any files
    on disk — the validator runs before any write."""
    del isolated_db
    monkeypatch.setattr(svc, "get_playground_working_dir", lambda: str(tmp_path))
    bad_cfg = {**_GOOD, "files": [{"path": "random.txt", "content": "x"}]}
    conv_id = "skill_testbadbadbadbad"
    SkillConversationService._conversations[conv_id] = {
        "messages": [
            ConversationMessage(role="assistant",
                                content="---SKILL_CONFIG---\n" + json.dumps(bad_cfg) + "\n---END_CONFIG---",
                                timestamp="t"),
        ],
    }
    SkillConversationService._subscribers[conv_id] = []
    try:
        result, status = SkillConversationService.finalize_skill(conv_id)
        assert status == 400
        # No skill directory should have been created.
        assert not (tmp_path / ".claude" / "skills" / "data-explorer").exists()
    finally:
        SkillConversationService._conversations.pop(conv_id, None)
        SkillConversationService._subscribers.pop(conv_id, None)
