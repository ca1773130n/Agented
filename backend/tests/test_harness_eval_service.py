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
