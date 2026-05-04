"""v0.5.13: env-var validator tests."""
import pytest


_AGENTED_VARS = (
    "AGENTED_API_KEY",
    "AI_ACCOUNTS_API_KEY",
    "AI_ACCOUNTS_VAULT_KEY",
    "AGENTED_ENV",
    "LOG_LEVEL",
    "GUNICORN_BIND",
    "VITE_HOST",
    "VITE_ALLOWED_HOSTS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip all v0.5.13 env vars from each test's environment."""
    for name in _AGENTED_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(f"{name}_FILE", raising=False)


class TestValidate:
    def test_dev_posture_does_not_fail_on_missing(self):
        from scripts.check_env import validate
        ok, missing, warnings = validate()
        assert ok is True
        assert missing == []
        assert any("AGENTED_API_KEY" in w for w in warnings)

    def test_production_posture_fails_on_missing_required(self, monkeypatch):
        monkeypatch.setenv("AGENTED_ENV", "production")
        from scripts.check_env import validate
        ok, missing, warnings = validate()
        assert ok is False
        assert "AGENTED_API_KEY" in missing
        assert "AI_ACCOUNTS_API_KEY" in missing
        assert "AI_ACCOUNTS_VAULT_KEY" in missing

    def test_production_posture_passes_when_all_set(self, monkeypatch):
        monkeypatch.setenv("AGENTED_ENV", "production")
        monkeypatch.setenv("AGENTED_API_KEY", "k1")
        monkeypatch.setenv("AI_ACCOUNTS_API_KEY", "k2")
        monkeypatch.setenv("AI_ACCOUNTS_VAULT_KEY", "k3")
        from scripts.check_env import validate
        ok, missing, warnings = validate()
        assert ok is True
        assert missing == []


class TestFileRedirect:
    def test_FILE_suffix_loads_from_path(self, monkeypatch, tmp_path):
        secret_file = tmp_path / "key.txt"
        secret_file.write_text("real-secret-value\n")
        monkeypatch.setenv("AGENTED_ENV", "production")
        monkeypatch.setenv("AGENTED_API_KEY_FILE", str(secret_file))
        monkeypatch.setenv("AI_ACCOUNTS_API_KEY", "k2")
        monkeypatch.setenv("AI_ACCOUNTS_VAULT_KEY", "k3")
        from scripts.check_env import resolve, validate
        assert resolve("AGENTED_API_KEY") == "real-secret-value"
        ok, missing, _ = validate()
        assert ok is True

    def test_FILE_redirect_with_nonexistent_path_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("AGENTED_ENV", "production")
        monkeypatch.setenv("AGENTED_API_KEY_FILE", "/nonexistent/path")
        monkeypatch.setenv("AI_ACCOUNTS_API_KEY", "k2")
        monkeypatch.setenv("AI_ACCOUNTS_VAULT_KEY", "k3")
        from scripts.check_env import validate
        ok, missing, _ = validate()
        assert ok is False
        assert "AGENTED_API_KEY" in missing

    def test_literal_env_takes_precedence_over_FILE(self, monkeypatch, tmp_path):
        secret_file = tmp_path / "key.txt"
        secret_file.write_text("from-file")
        monkeypatch.setenv("AGENTED_API_KEY", "from-env")
        monkeypatch.setenv("AGENTED_API_KEY_FILE", str(secret_file))
        from scripts.check_env import resolve
        assert resolve("AGENTED_API_KEY") == "from-env"


class TestCLI:
    def test_main_exits_0_in_dev_with_warnings(self, capsys):
        from scripts.check_env import main
        rc = main([])
        assert rc == 0

    def test_main_exits_1_in_production_with_missing(self, capsys, monkeypatch):
        monkeypatch.setenv("AGENTED_ENV", "production")
        from scripts.check_env import main
        rc = main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "AGENTED_API_KEY" in captured.err
        assert "RUNBOOK" in captured.err
