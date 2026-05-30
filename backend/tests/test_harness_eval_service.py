from pathlib import Path
from unittest.mock import patch

from app.services.harness_evolution_eval import _static_checks
from app.services.forge_materialization_service import MaterializationResult, WrittenFile
from app.services import harness_evolution_eval as ev
from app.models.harness_evolution import ReplaySample


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


def _samples():
    return [ReplaySample(incident_kind="h2_invalid_tool_call", layer="h2",
                         evidence={"error": "missing arg"}, trajectory_excerpt="...")]


def test_judge_replay_parses_checkresult():
    fake = '{"name": "replay", "passed": true, "detail": "addressed", "confidence": 0.85}'
    with patch.object(ev, "_run_judge", lambda prompt, provider_kind: fake):
        checks = ev._replay_checks(_samples(), patched_summary="rule X added", provider_kind="anthropic")
    assert len(checks) == 1 and checks[0].passed is True and checks[0].confidence == 0.85


def test_judge_malformed_output_is_failed_low_confidence():
    with patch.object(ev, "_run_judge", lambda prompt, provider_kind: "garbage not json"):
        checks = ev._replay_checks(_samples(), patched_summary="x", provider_kind="anthropic")
    assert checks[0].passed is False and checks[0].confidence <= 0.3


def test_judge_subprocess_error_is_failed_check():
    def _boom(prompt, provider_kind):
        raise RuntimeError("cli missing")
    with patch.object(ev, "_run_judge", _boom):
        checks = ev._replay_checks(_samples(), patched_summary="x", provider_kind="anthropic")
    assert checks[0].passed is False


def test_evaluate_patch_combines_static_and_replay(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "d.md").write_text('---\nname: "d"\n---\nb\n')
    mat = MaterializationResult(written=[WrittenFile(".claude/commands/d.md", "command", "c1")])
    good = '{"name":"replay","passed":true,"detail":"ok","confidence":0.9}'
    with patch.object(ev, "materialize_round", lambda rid, ws: mat), \
         patch.object(ev, "_run_judge", lambda prompt, provider_kind: good):
        verdict = ev.evaluate_patch(round_id="r1", workspace_dir=tmp_path,
                                    samples=_samples(), patched_summary="x", provider_kind="anthropic")
    assert verdict.passed is True
    assert 0.0 <= verdict.score <= 1.0
    assert any(c.name.startswith("frontmatter") for c in verdict.per_check)


def test_evaluate_patch_static_fail_skips_replay(tmp_path):
    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{ bad json")
    mat = MaterializationResult(written=[WrittenFile(".claude/settings.json", "hook", "settings")])
    judge_called = {"n": 0}
    def _judge(prompt, provider_kind):
        judge_called["n"] += 1
        return '{"name":"r","passed":true,"confidence":0.9}'
    with patch.object(ev, "materialize_round", lambda rid, ws: mat), \
         patch.object(ev, "_run_judge", _judge):
        verdict = ev.evaluate_patch(round_id="r2", workspace_dir=tmp_path,
                                    samples=_samples(), patched_summary="x", provider_kind="anthropic")
    assert verdict.passed is False
    assert judge_called["n"] == 0   # static failure short-circuits replay


def test_failed_verdict_score_below_floor():
    """A failed verdict must report a score below the trust floor (consistency)."""
    from app.models.harness_evolution import CheckResult
    checks = [
        CheckResult(name="frontmatter:x", passed=False, detail="bad", confidence=1.0),
        CheckResult(name="replay:y", passed=True, detail="ok", confidence=0.95),
    ]
    v = ev._verdict(checks)
    assert v.passed is False
    assert v.score < 0.5


def test_passed_verdict_score_reflects_confidence():
    from app.models.harness_evolution import CheckResult
    checks = [CheckResult(name="frontmatter:x", passed=True, confidence=0.9),
              CheckResult(name="replay:y", passed=True, confidence=0.8)]
    v = ev._verdict(checks)
    assert v.passed is True
    assert v.score > 0.5
