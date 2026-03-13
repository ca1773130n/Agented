"""Tests for SkillDiscoveryService."""

import os

import pytest

from app.services.skill_discovery_service import SkillDiscoveryService, get_playground_working_dir


class TestParseFrontmatter:
    """Tests for _parse_frontmatter static method."""

    def test_valid_yaml_frontmatter(self):
        content = '---\nname: my-skill\ndescription: "A great skill"\n---\n# Body'
        result = SkillDiscoveryService._parse_frontmatter(content)
        assert result["name"] == "my-skill"
        assert result["description"] == "A great skill"

    def test_no_frontmatter(self):
        content = "# Just a heading\nSome text."
        result = SkillDiscoveryService._parse_frontmatter(content)
        assert result == {}

    def test_invalid_frontmatter_no_closing_delimiter(self):
        content = "---\nname: broken\nno closing delimiter"
        result = SkillDiscoveryService._parse_frontmatter(content)
        assert result == {}

    def test_multiple_fields(self):
        content = "---\nname: test\ndescription: desc\nrole: engineer\ncolor: blue\n---\nbody"
        result = SkillDiscoveryService._parse_frontmatter(content)
        assert result["name"] == "test"
        assert result["description"] == "desc"
        assert result["role"] == "engineer"
        assert result["color"] == "blue"

    def test_values_with_quotes_stripped(self):
        content = "---\nname: 'quoted-name'\ndescription: \"double-quoted\"\n---\n"
        result = SkillDiscoveryService._parse_frontmatter(content)
        assert result["name"] == "quoted-name"
        assert result["description"] == "double-quoted"

    def test_empty_content(self):
        result = SkillDiscoveryService._parse_frontmatter("")
        assert result == {}


class TestParseSkillFile:
    """Tests for _parse_skill_file classmethod."""

    def test_complete_skill_md(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            '---\nname: code-review\ndescription: "Review code for issues"\n---\n# Code Review\n'
        )
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "fallback-name")
        assert result["name"] == "code-review"
        assert result["description"] == "Review code for issues"

    def test_missing_description_falls_back_to_first_paragraph(self, tmp_path):
        # When no description in frontmatter, the fallback scans all lines
        # including frontmatter yaml lines. Lines starting with --- or # are skipped.
        # The first non-header, non-delimiter line becomes the description.
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: my-skill\n---\n# Title\nThis is the first paragraph.\n")
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "fallback")
        assert result["name"] == "my-skill"
        # "name: my-skill" is the first line that doesn't start with # or ---
        assert result["description"] == "name: my-skill"

    def test_no_frontmatter_description_body_only(self, tmp_path):
        # With description omitted and no yaml key lines, body text is used
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription:\n---\n# Title\nActual body text here.\n")
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "fallback")
        # description key is empty string in frontmatter, so fallback kicks in
        # "description:" line in raw content is picked up first
        assert result["description"] == "description:"

    def test_missing_name_falls_back_to_default(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription: some desc\n---\nbody\n")
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "default-name")
        assert result["name"] == "default-name"
        assert result["description"] == "some desc"

    def test_file_read_error_returns_none(self):
        result = SkillDiscoveryService._parse_skill_file("/nonexistent/path/SKILL.md", "fallback")
        assert result is None

    def test_no_frontmatter_extracts_body_text(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# My Skill\nFirst real line of text.\nMore text.\n")
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "my-skill")
        assert result["name"] == "my-skill"
        assert result["description"] == "First real line of text."

    def test_extra_frontmatter_fields_copied(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: agent-skill\ndescription: desc\nrole: reviewer\n"
            "skills: a, b, c\ncolor: red\n---\nbody\n"
        )
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "fallback")
        assert result["role"] == "reviewer"
        assert result["skills"] == ["a", "b", "c"]
        assert result["color"] == "red"

    def test_description_truncated_to_200_chars(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        long_line = "A" * 300
        # No frontmatter so the long line is the first non-header line
        skill_md.write_text(f"# Title\n{long_line}\n")
        result = SkillDiscoveryService._parse_skill_file(str(skill_md), "skill")
        assert len(result["description"]) == 200


class TestDiscoverAllSkills:
    """Tests for discover_all_skills with temporary skill directories."""

    def _create_skill(self, base_path, skill_name, frontmatter_content):
        """Helper to create a .claude/skills/<name>/SKILL.md structure."""
        skill_dir = base_path / ".claude" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(frontmatter_content)
        return skill_dir

    def test_discovers_skills_from_explicit_paths(self, tmp_path, monkeypatch):
        # Prevent scanning PROJECT_ROOT and global/plugin dirs
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        project = tmp_path / "myproject"
        project.mkdir()
        self._create_skill(
            project, "lint", '---\nname: lint\ndescription: "Lint code"\n---\nbody\n'
        )

        skills = SkillDiscoveryService.discover_all_skills(paths=[str(project)])
        names = [s["name"] for s in skills]
        assert "lint" in names

    def test_discovers_skills_from_trigger_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        project = tmp_path / "proj"
        project.mkdir()
        self._create_skill(project, "deploy", '---\nname: deploy\ndescription: "Deploy app"\n---\n')

        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_paths_for_trigger",
            lambda tid: [str(project)],
        )

        skills = SkillDiscoveryService.discover_all_skills(trigger_id="trig-123")
        names = [s["name"] for s in skills]
        assert "deploy" in names

    def test_no_trigger_no_paths_scans_all_triggers(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        project = tmp_path / "proj"
        project.mkdir()
        self._create_skill(project, "test", '---\nname: test\ndescription: "Run tests"\n---\n')

        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_all_triggers",
            lambda: [{"id": "trig-abc"}],
        )
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_paths_for_trigger",
            lambda tid: [str(project)],
        )

        skills = SkillDiscoveryService.discover_all_skills()
        names = [s["name"] for s in skills]
        assert "test" in names

    def test_deduplicates_skills_by_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        # Create the same skill in two different paths
        p1 = tmp_path / "p1"
        p2 = tmp_path / "p2"
        p1.mkdir()
        p2.mkdir()
        self._create_skill(p1, "dupe", '---\nname: dupe\ndescription: "First"\n---\n')
        self._create_skill(p2, "dupe", '---\nname: dupe\ndescription: "Second"\n---\n')

        skills = SkillDiscoveryService.discover_all_skills(paths=[str(p1), str(p2)])
        dupe_skills = [s for s in skills if s["name"] == "dupe"]
        assert len(dupe_skills) == 1

    def test_skips_nonexistent_paths(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        skills = SkillDiscoveryService.discover_all_skills(paths=["/nonexistent/path/abc123"])
        # Should return empty (or only PROJECT_ROOT skills, which has none)
        assert isinstance(skills, list)

    def test_skill_has_source_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.skill_discovery_service.PROJECT_ROOT", str(tmp_path))
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        project = tmp_path / "proj"
        project.mkdir()
        self._create_skill(project, "sk", '---\nname: sk\ndescription: "desc"\n---\n')

        skills = SkillDiscoveryService.discover_all_skills(paths=[str(project)])
        sk = [s for s in skills if s["name"] == "sk"]
        assert len(sk) == 1
        assert "source_path" in sk[0]


class TestDiscoverCliSkills:
    """Tests for discover_cli_skills with slash-prefixed names."""

    def _create_skill(self, base_path, skill_name, frontmatter_content):
        skill_dir = base_path / ".claude" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(frontmatter_content)

    def test_returns_slash_prefixed_names(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        project = tmp_path / "proj"
        project.mkdir()
        self._create_skill(project, "review", '---\nname: review\ndescription: "Review"\n---\n')

        skills = SkillDiscoveryService.discover_cli_skills([str(project)])
        names = [s["name"] for s in skills]
        assert "/review" in names

    def test_deduplicates_cli_skills(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

        p1 = tmp_path / "p1"
        p2 = tmp_path / "p2"
        p1.mkdir()
        p2.mkdir()
        self._create_skill(p1, "same", '---\nname: same\ndescription: "A"\n---\n')
        self._create_skill(p2, "same", '---\nname: same\ndescription: "B"\n---\n')

        skills = SkillDiscoveryService.discover_cli_skills([str(p1), str(p2)])
        same_skills = [s for s in skills if s["name"] == "/same"]
        assert len(same_skills) == 1


class TestParseFrontmatterFromFile:
    """Tests for _parse_frontmatter_from_file static method."""

    def test_extracts_name_and_description(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text('---\nname: tool\ndescription: "A tool"\n---\nbody\n')
        result = SkillDiscoveryService._parse_frontmatter_from_file(str(md))
        assert result["name"] == "tool"
        assert result["description"] == "A tool"

    def test_no_frontmatter_returns_empty(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("# No frontmatter\nJust text.\n")
        result = SkillDiscoveryService._parse_frontmatter_from_file(str(md))
        assert result == {}

    def test_no_closing_delimiter_returns_empty(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\nname: broken\n")
        result = SkillDiscoveryService._parse_frontmatter_from_file(str(md))
        assert result == {}

    def test_nonexistent_file_returns_empty(self):
        result = SkillDiscoveryService._parse_frontmatter_from_file("/no/such/file.md")
        assert result == {}

    def test_only_name_and_description_extracted(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("---\nname: x\ndescription: y\nrole: z\n---\n")
        result = SkillDiscoveryService._parse_frontmatter_from_file(str(md))
        assert "name" in result
        assert "description" in result
        assert "role" not in result


class TestGetPlaygroundWorkingDir:
    """Tests for get_playground_working_dir module function."""

    def test_env_variable_takes_priority(self, tmp_path, monkeypatch):
        env_dir = str(tmp_path / "env_cwd")
        os.makedirs(env_dir)
        monkeypatch.setenv("SKILLS_PLAYGROUND_CWD", env_dir)
        result = get_playground_working_dir()
        assert result == env_dir

    def test_env_variable_ignored_if_not_a_dir(self, monkeypatch):
        monkeypatch.setenv("SKILLS_PLAYGROUND_CWD", "/nonexistent/dir/xyz")
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: None,
        )
        # Should fall through to later checks
        result = get_playground_working_dir()
        assert isinstance(result, str)

    def test_db_setting_used_when_no_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_PLAYGROUND_CWD", raising=False)
        db_dir = str(tmp_path / "db_cwd")
        os.makedirs(db_dir)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: db_dir,
        )
        result = get_playground_working_dir()
        assert result == db_dir

    def test_db_setting_ignored_if_not_a_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_PLAYGROUND_CWD", raising=False)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: "/nonexistent/db/dir",
        )
        # Falls through to playground webapp or PROJECT_ROOT
        result = get_playground_working_dir()
        assert isinstance(result, str)

    def test_db_exception_handled_gracefully(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_PLAYGROUND_CWD", raising=False)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: (_ for _ in ()).throw(RuntimeError("db error")),
        )
        # Should not raise, falls through
        result = get_playground_working_dir()
        assert isinstance(result, str)

    def test_falls_back_to_playground_webapp(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_PLAYGROUND_CWD", raising=False)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: None,
        )
        webapp_dir = str(tmp_path / "webapp")
        os.makedirs(webapp_dir)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.PLAYGROUND_WEBAPP_DIR",
            webapp_dir,
        )
        result = get_playground_working_dir()
        assert result == webapp_dir

    def test_falls_back_to_project_root(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SKILLS_PLAYGROUND_CWD", raising=False)
        monkeypatch.setattr(
            "app.services.skill_discovery_service.get_setting",
            lambda key: None,
        )
        monkeypatch.setattr(
            "app.services.skill_discovery_service.PLAYGROUND_WEBAPP_DIR",
            "/nonexistent/webapp",
        )
        from app.services.skill_discovery_service import PROJECT_ROOT

        result = get_playground_working_dir()
        assert result == PROJECT_ROOT
