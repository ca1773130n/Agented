from pathlib import Path

from app.services.harness_evolution_eval import _static_checks
from app.services.forge_materialization_service import MaterializationResult, WrittenFile


def test_static_checks_pass_for_valid_files(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "deploy.md").write_text(
        '---\nname: "deploy"\n---\n\nbody\n'
    )
    (tmp_path / ".claude").joinpath("settings.json").write_text('{"hooks": {}}')
    result = MaterializationResult(
        written=[
            WrittenFile(".claude/commands/deploy.md", "command", "c1"),
            WrittenFile(".claude/settings.json", "hook", "settings"),
        ]
    )
    checks = _static_checks(tmp_path, result)
    assert all(c.passed for c in checks), [c.detail for c in checks if not c.passed]


def test_static_checks_flag_bad_json(tmp_path):
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{ not json")
    result = MaterializationResult(
        written=[WrittenFile(".claude/settings.json", "hook", "settings")]
    )
    checks = _static_checks(tmp_path, result)
    assert any(not c.passed for c in checks)


def test_static_checks_flag_unclosed_frontmatter(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "bad.md").write_text("no frontmatter here\nbody")
    result = MaterializationResult(
        written=[WrittenFile(".claude/commands/bad.md", "command", "c2")]
    )
    checks = _static_checks(tmp_path, result)
    assert any(not c.passed for c in checks)


def test_static_check_missing_file_is_failed(tmp_path):
    result = MaterializationResult(written=[WrittenFile(".claude/commands/gone.md", "command", "c9")])
    checks = _static_checks(tmp_path, result)
    assert checks and all(not c.passed for c in checks)


def test_frontmatter_body_dividers_do_not_false_pass(tmp_path):
    # A file with NO opening frontmatter but body --- dividers must FAIL.
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "hr.md").write_text("intro\n\n---\n\nsection\n\n---\n\nend\n")
    result = MaterializationResult(written=[WrittenFile(".claude/commands/hr.md", "command", "c8")])
    checks = _static_checks(tmp_path, result)
    assert any(not c.passed for c in checks)


def test_whitespace_only_hook_is_failed(tmp_path):
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "blank.sh").write_text("   \n  \n")
    result = MaterializationResult(written=[WrittenFile(".claude/hooks/blank.sh", "hook", "h1")])
    checks = _static_checks(tmp_path, result)
    assert any(not c.passed for c in checks)


def test_valid_closed_frontmatter_passes(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "ok.md").write_text('---\nname: "ok"\n---\n\nbody with --- divider\n')
    result = MaterializationResult(written=[WrittenFile(".claude/commands/ok.md", "command", "c7")])
    checks = _static_checks(tmp_path, result)
    assert all(c.passed for c in checks)
