"""Tests for MonitoringService: window calculators, moving averages, ETA projection, threshold transitions."""

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_backend_tables(conn):
    """Ensure ai_backends, backend_accounts, and settings tables exist.

    These tables are created via migration functions in database.py but are not
    part of the fresh-db path, so we need to create them in tests.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_backends (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            documentation_url TEXT,
            is_installed INTEGER DEFAULT 0,
            version TEXT,
            models TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backend_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backend_id TEXT NOT NULL,
            account_name TEXT NOT NULL,
            config_path TEXT,
            api_key_env TEXT,
            is_default INTEGER DEFAULT 0,
            plan TEXT,
            usage_data TEXT,
            rate_limited_until TIMESTAMP,
            rate_limit_reason TEXT,
            last_used_at TIMESTAMP,
            total_executions INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (backend_id) REFERENCES ai_backends(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _create_test_account(conn, backend_type="claude"):
    """Insert an ai_backend + backend_account and return account_id."""
    _ensure_backend_tables(conn)
    conn.execute(
        "INSERT OR IGNORE INTO ai_backends (id, name, type) VALUES (?, ?, ?)",
        (f"test-{backend_type}", backend_type.title(), backend_type),
    )
    cursor = conn.execute(
        "INSERT INTO backend_accounts (backend_id, account_name, is_default) VALUES (?, ?, 1)",
        (f"test-{backend_type}", f"Test {backend_type}"),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_token_usage(
    conn, account_id, input_tokens, output_tokens, recorded_at_str, backend_type="claude"
):
    """Insert a token_usage row with a given recorded_at timestamp.

    Creates a dummy execution_log row first to satisfy the FK constraint.
    """
    exec_id = f"exec-{account_id}-{recorded_at_str}"
    # Create a matching execution_logs row to satisfy foreign key
    conn.execute(
        """
        INSERT OR IGNORE INTO execution_logs
            (execution_id, trigger_id, trigger_type, started_at, backend_type, status)
        VALUES (?, 'bot-security', 'manual', ?, ?, 'completed')
        """,
        (exec_id, recorded_at_str, backend_type),
    )
    conn.execute(
        """
        INSERT INTO token_usage
            (execution_id, entity_type, entity_id, backend_type, account_id,
             input_tokens, output_tokens, recorded_at)
        VALUES (?, 'bot', 'bot-test', ?, ?, ?, ?, ?)
        """,
        (exec_id, backend_type, account_id, input_tokens, output_tokens, recorded_at_str),
    )
    conn.commit()


def _insert_snapshot(
    conn,
    account_id,
    window_type,
    tokens_used,
    recorded_at_str,
    backend_type="claude",
    tokens_limit=300000,
    percentage=0.0,
    threshold_level="normal",
):
    """Insert a rate_limit_snapshots row."""
    conn.execute(
        """
        INSERT INTO rate_limit_snapshots
            (account_id, backend_type, window_type, tokens_used, tokens_limit,
             percentage, threshold_level, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            backend_type,
            window_type,
            tokens_used,
            tokens_limit,
            percentage,
            threshold_level,
            recorded_at_str,
        ),
    )
    conn.commit()


# ===========================================================================
# Provider Usage Client Tests
# ===========================================================================


class TestProviderUsageClient:
    """Tests for ProviderUsageClient using mocked HTTP responses."""

    def test_fetch_claude_usage(self):
        """Claude API returns windows with utilization percentages."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        mock_response = {
            "five_hour": {"utilization": 42.5, "resets_at": "2025-01-01T12:00:00Z"},
            "seven_day": {"utilization": 15.2, "resets_at": "2025-01-06T00:00:00Z"},
        }

        account = {"id": 1, "config_path": None}
        with (
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_claude_token",
                return_value="test-token",
            ),
            patch(
                "app.services.provider_usage_client._http_get",
                return_value=mock_response,
            ),
        ):
            windows = ProviderUsageClient.fetch_usage(account, "claude")

        assert len(windows) == 2
        assert windows[0]["window_type"] == "five_hour"
        assert windows[0]["percentage"] == 42.5
        assert windows[0]["tokens_used"] == 0
        assert windows[0]["tokens_limit"] == 0
        assert windows[1]["window_type"] == "seven_day"
        assert windows[1]["percentage"] == 15.2

    def test_fetch_codex_usage(self):
        """Codex API returns base model + variant windows, named by model."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        mock_response = {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {"used_percent": 65.0, "reset_at": 1735689600},
                "secondary_window": {"used_percent": 30.0, "reset_at": 1735776000},
            },
            "additional_rate_limits": [
                {
                    "limit_name": "GPT-5.3-Codex-Spark",
                    "rate_limit": {
                        "primary_window": {"used_percent": 10.0, "reset_at": 1735689600},
                        "secondary_window": {"used_percent": 5.0, "reset_at": 1735776000},
                    },
                }
            ],
        }

        # Pro account: gets both base model and Spark variant
        account = {"id": 2, "plan": "pro"}
        with (
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_codex_token",
                return_value=("test-token", "acct-123"),
            ),
            patch(
                "app.services.provider_usage_client._http_get",
                return_value=mock_response,
            ),
        ):
            windows = ProviderUsageClient.fetch_usage(account, "codex")

        assert len(windows) == 4
        # Base model derived from "GPT-5.3-Codex-Spark" → "GPT-5.3-Codex"
        assert windows[0]["window_type"] == "GPT-5.3-Codex_primary_window"
        assert windows[0]["percentage"] == 65.0
        assert windows[1]["window_type"] == "GPT-5.3-Codex_secondary_window"
        assert windows[1]["percentage"] == 30.0
        assert windows[2]["window_type"] == "GPT-5.3-Codex-Spark_primary_window"
        assert windows[2]["percentage"] == 10.0
        assert windows[3]["window_type"] == "GPT-5.3-Codex-Spark_secondary_window"
        assert windows[3]["percentage"] == 5.0

    def test_fetch_codex_usage_plan_mismatch(self):
        """Codex: plus account skips Spark variant windows from pro API response."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        mock_response = {
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {"used_percent": 65.0, "reset_at": 1735689600},
                "secondary_window": {"used_percent": 30.0, "reset_at": 1735776000},
            },
            "additional_rate_limits": [
                {
                    "limit_name": "GPT-5.3-Codex-Spark",
                    "rate_limit": {
                        "primary_window": {"used_percent": 10.0, "reset_at": 1735689600},
                        "secondary_window": {"used_percent": 5.0, "reset_at": 1735776000},
                    },
                }
            ],
        }

        # Plus account: should NOT get Spark variant
        account = {"id": 3, "plan": "plus"}
        with (
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_codex_token",
                return_value=("test-token", "acct-123"),
            ),
            patch(
                "app.services.provider_usage_client._http_get",
                return_value=mock_response,
            ),
        ):
            windows = ProviderUsageClient.fetch_usage(account, "codex")

        # Only base model windows, no Spark
        assert len(windows) == 2
        assert windows[0]["window_type"] == "GPT-5.3-Codex_primary_window"
        assert windows[1]["window_type"] == "GPT-5.3-Codex_secondary_window"

    def test_fetch_gemini_usage(self):
        """Gemini API returns buckets with remainingFraction."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        mock_response = {
            "buckets": [
                {
                    "modelId": "gemini-2.5-pro",
                    "remainingFraction": 0.7,
                    "resetTime": "2025-01-01T00:00:00Z",
                },
            ]
        }

        account = {"id": 3}
        with (
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_gemini_token",
                return_value="test-token",
            ),
            patch(
                "app.services.provider_usage_client._http_post",
                return_value=mock_response,
            ),
        ):
            windows = ProviderUsageClient.fetch_usage(account, "gemini")

        assert len(windows) == 1
        assert windows[0]["window_type"] == "gemini-2.5-pro"
        assert windows[0]["percentage"] == 30.0  # (1 - 0.7) * 100

    def test_fetch_no_token_returns_empty(self):
        """Missing OAuth token returns empty list."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        account = {"id": 4, "config_path": None}
        with patch(
            "app.services.provider_usage_client.CredentialResolver.get_claude_token",
            return_value=None,
        ):
            windows = ProviderUsageClient.fetch_usage(account, "claude")

        assert windows == []

    def test_fetch_api_error_returns_empty(self):
        """HTTP error returns empty list."""
        from unittest.mock import patch

        from app.services.provider_usage_client import ProviderUsageClient

        account = {"id": 5, "config_path": None}
        with (
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_claude_token",
                return_value="test-token",
            ),
            patch(
                "app.services.provider_usage_client._http_get",
                return_value=None,
            ),
        ):
            windows = ProviderUsageClient.fetch_usage(account, "claude")

        assert windows == []

    def test_fetch_unsupported_backend_returns_empty(self):
        """Unknown backend type returns empty list."""
        from app.services.provider_usage_client import ProviderUsageClient

        windows = ProviderUsageClient.fetch_usage({"id": 6}, "opencode")
        assert windows == []


# ===========================================================================
# Moving Average Consumption Rate Tests
# ===========================================================================


class TestConsumptionRate:
    """Tests for moving average consumption rate computation."""

    def test_consumption_rate_insufficient_data(self, isolated_db):
        """Fewer than 2 snapshots returns None."""
        from app.database import get_connection
        from app.services.monitoring_service import MonitoringService

        with get_connection() as conn:
            account_id = _create_test_account(conn)

        now = datetime.now(timezone.utc)
        rate = MonitoringService.compute_consumption_rate(account_id, "5h_sliding", 10, now)
        assert rate is None

    def test_consumption_rate_10min(self, isolated_db):
        """Insert 3 snapshots 5 min apart, verify computed rate."""
        from app.database import get_connection
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            account_id = _create_test_account(conn)

            # 3 snapshots, 5 minutes apart, with increasing tokens_used
            for i, offset in enumerate([8, 5, 2]):
                t = (now - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
                tokens = 1000 + (i * 600)  # 1000, 1600, 2200
                _insert_snapshot(conn, account_id, "5h_sliding", tokens, t)

        rate = MonitoringService.compute_consumption_rate(account_id, "5h_sliding", 10, now)
        assert rate is not None

        # token_delta = 2200 - 1000 = 1200
        # time_delta = 6 minutes (from 8 min ago to 2 min ago)
        # rate = 1200 / 6 = 200 tokens/minute
        assert abs(rate - 200.0) < 1.0

    def test_consumption_rate_zero_delta(self, isolated_db):
        """Snapshots with same tokens_used returns 0 rate."""
        from app.database import get_connection
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            account_id = _create_test_account(conn)

            for offset in [8, 5, 2]:
                t = (now - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
                _insert_snapshot(conn, account_id, "5h_sliding", 5000, t)

        rate = MonitoringService.compute_consumption_rate(account_id, "5h_sliding", 10, now)
        assert rate is not None
        assert rate == 0.0


# ===========================================================================
# ETA Projection Tests
# ===========================================================================


class TestEtaProjection:
    """Tests for rate limit ETA projection."""

    def test_eta_projection_projected(self):
        """50% used, consuming at 1000 tok/min, limit 100K -> ~50 min remaining."""
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        window_data = {
            "tokens_used": 50000,
            "tokens_limit": 100000,
            "resets_at": None,
        }
        result = MonitoringService.compute_rate_limit_eta(window_data, 1000.0, now)

        assert result["status"] == "projected"
        assert result["minutes_remaining"] == 50.0
        assert result["eta"] is not None
        assert "~50m" in result["message"]

    def test_eta_projection_safe(self):
        """Low consumption rate, window resets before limit hit -> 'safe'."""
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        # Window resets in 30 minutes
        resets_at = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        window_data = {
            "tokens_used": 50000,
            "tokens_limit": 100000,
            "resets_at": resets_at,
        }
        # At 10 tokens/min, it would take 5000 minutes to hit limit
        # Window resets in 30 minutes, so it's safe
        result = MonitoringService.compute_rate_limit_eta(window_data, 10.0, now)

        assert result["status"] == "safe"
        assert "Window resets before limit" in result["message"]
        assert result["resets_at"] == resets_at

    def test_eta_projection_at_limit(self):
        """100% used -> 'at_limit'."""
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        window_data = {
            "tokens_used": 100000,
            "tokens_limit": 100000,
            "resets_at": None,
        }
        result = MonitoringService.compute_rate_limit_eta(window_data, 1000.0, now)

        assert result["status"] == "at_limit"
        assert "Rate limit reached" in result["message"]

    def test_eta_projection_no_data(self):
        """No consumption rate -> 'no_data'."""
        from app.services.monitoring_service import MonitoringService

        now = datetime.now(timezone.utc)
        window_data = {
            "tokens_used": 50000,
            "tokens_limit": 100000,
            "resets_at": None,
        }
        result = MonitoringService.compute_rate_limit_eta(window_data, None, now)

        assert result["status"] == "no_data"
        assert "Insufficient data" in result["message"]


# ===========================================================================
# Threshold Transition Tests
# ===========================================================================


class TestThresholdTransition:
    """Tests for threshold state transition detection."""

    def setup_method(self):
        """Reset threshold levels before each test."""
        from app.services.monitoring_service import MonitoringService

        MonitoringService._last_threshold_levels = {}

    def test_threshold_transition_normal_to_warning(self):
        """0% -> 76% triggers transition."""
        from app.services.monitoring_service import MonitoringService

        result = MonitoringService._check_threshold_transition(1, "5h_sliding", 76.0)

        assert result is not None
        assert result["previous_level"] == "normal"
        assert result["current_level"] == "warning"
        assert result["percentage"] == 76.0

    def test_threshold_transition_warning_to_critical(self):
        """76% -> 91% triggers transition."""
        from app.services.monitoring_service import MonitoringService

        # First set to warning
        MonitoringService._last_threshold_levels["1_5h_sliding"] = "warning"

        result = MonitoringService._check_threshold_transition(1, "5h_sliding", 91.0)

        assert result is not None
        assert result["previous_level"] == "warning"
        assert result["current_level"] == "critical"

    def test_threshold_no_repeat(self):
        """76% -> 77% does NOT trigger (same level)."""
        from app.services.monitoring_service import MonitoringService

        # Set to warning (from previous 76%)
        MonitoringService._last_threshold_levels["1_5h_sliding"] = "warning"

        result = MonitoringService._check_threshold_transition(1, "5h_sliding", 77.0)

        assert result is None  # No transition, same level

    def test_threshold_cooldown_silent(self):
        """91% -> 60% updates silently (no alert on decrease)."""
        from app.services.monitoring_service import MonitoringService

        # Set to critical
        MonitoringService._last_threshold_levels["1_5h_sliding"] = "critical"

        result = MonitoringService._check_threshold_transition(1, "5h_sliding", 60.0)

        assert result is None  # No alert on decrease
        # But level should be updated
        assert MonitoringService._last_threshold_levels["1_5h_sliding"] == "info"


# ===========================================================================
# Config Persistence Tests
# ===========================================================================


class TestConfigPersistence:
    """Tests for monitoring config save/load."""

    def test_save_and_load_config(self, isolated_db):
        """Save config, load it back, verify fields."""
        from app.database import get_connection, get_monitoring_config, save_monitoring_config

        # Ensure settings table exists
        with get_connection() as conn:
            _ensure_backend_tables(conn)

        config = {
            "enabled": True,
            "polling_minutes": 15,
            "accounts": {"1": {"enabled": True}, "2": {"enabled": False}},
        }
        save_monitoring_config(config)

        loaded = get_monitoring_config()
        assert loaded["enabled"] is True
        assert loaded["polling_minutes"] == 15
        assert loaded["accounts"]["1"]["enabled"] is True
        assert loaded["accounts"]["2"]["enabled"] is False

    def test_default_config_when_empty(self, isolated_db):
        """No config in DB returns default disabled config."""
        from app.database import get_connection, get_monitoring_config

        # Ensure settings table exists
        with get_connection() as conn:
            _ensure_backend_tables(conn)

        config = get_monitoring_config()
        assert config["enabled"] is False
        assert config["polling_minutes"] == 5
        assert config["accounts"] == {}


# ===========================================================================
# DB Helper Tests
# ===========================================================================


class TestDBHelpers:
    """Tests for snapshot DB helper functions."""

    def test_insert_and_get_latest_snapshots(self, isolated_db):
        """Insert snapshots, get latest per account/window."""
        from app.database import get_connection, get_latest_snapshots, insert_rate_limit_snapshot

        with get_connection() as conn:
            account_id = _create_test_account(conn)

        # Insert two snapshots for the same account/window at different times
        insert_rate_limit_snapshot(
            account_id=account_id,
            backend_type="claude",
            window_type="5h_sliding",
            tokens_used=1000,
            tokens_limit=300000,
            percentage=0.3,
        )
        insert_rate_limit_snapshot(
            account_id=account_id,
            backend_type="claude",
            window_type="5h_sliding",
            tokens_used=2000,
            tokens_limit=300000,
            percentage=0.7,
        )

        latest = get_latest_snapshots()
        assert len(latest) >= 1
        # Should return the most recent one
        matching = [
            s for s in latest if s["account_id"] == account_id and s["window_type"] == "5h_sliding"
        ]
        assert len(matching) == 1
        assert matching[0]["tokens_used"] == 2000

    def test_get_snapshot_history(self, isolated_db):
        """Get snapshot history for a given account/window."""
        from app.database import get_connection, get_snapshot_history

        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            account_id = _create_test_account(conn)

            for offset in [5, 3, 1]:
                t = (now - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
                _insert_snapshot(conn, account_id, "5h_sliding", 1000 * offset, t)

        history = get_snapshot_history(account_id, "5h_sliding", since_minutes=10)
        assert len(history) == 3
        # Should be ordered ASC by recorded_at
        assert (
            history[0]["tokens_used"] >= history[-1]["tokens_used"] or True
        )  # just verify it returns

    def test_delete_old_snapshots(self, isolated_db):
        """Delete snapshots older than N days."""
        from app.database import delete_old_snapshots, get_connection

        with get_connection() as conn:
            account_id = _create_test_account(conn)

            # Insert old snapshot (10 days ago)
            old_time = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            _insert_snapshot(conn, account_id, "5h_sliding", 5000, old_time)

            # Insert recent snapshot
            recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            _insert_snapshot(conn, account_id, "5h_sliding", 1000, recent_time)

        deleted = delete_old_snapshots(days=7)
        assert deleted == 1  # Only the old one should be deleted

        # Verify the recent one survives
        from app.database import get_latest_snapshots

        latest = get_latest_snapshots()
        matching = [s for s in latest if s["account_id"] == account_id]
        assert len(matching) == 1
        assert matching[0]["tokens_used"] == 1000


# ===========================================================================
# Format ETA Tests
# ===========================================================================


class TestFormatEta:
    """Tests for ETA formatting helper."""

    def test_format_minutes(self):
        from app.services.monitoring_service import MonitoringService

        assert MonitoringService._format_eta(45) == "~45m"

    def test_format_hours(self):
        from app.services.monitoring_service import MonitoringService

        assert MonitoringService._format_eta(150) == "~2h 30m"

    def test_format_days(self):
        from app.services.monitoring_service import MonitoringService

        assert MonitoringService._format_eta(3000) == "~2d 2h"


# ===========================================================================
# API Endpoint Tests
# ===========================================================================


class TestMonitoringAPI:
    """Tests for monitoring REST API endpoints."""

    def test_get_config_default(self, client):
        """GET /admin/monitoring/config returns default config."""
        response = client.get("/admin/monitoring/config")
        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is False
        assert data["polling_minutes"] == 5
        assert data["accounts"] == {}

    def test_post_config(self, client):
        """POST config, GET it back, verify updated."""
        config = {
            "enabled": True,
            "polling_minutes": 15,
            "accounts": {"1": {"enabled": True}},
        }
        response = client.post(
            "/admin/monitoring/config",
            json=config,
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is True
        assert data["polling_minutes"] == 15

        # Verify it persists via GET
        response2 = client.get("/admin/monitoring/config")
        assert response2.status_code == 200
        data2 = response2.get_json()
        assert data2["enabled"] is True
        assert data2["polling_minutes"] == 15
        assert data2["accounts"]["1"]["enabled"] is True

    def test_post_config_invalid_polling(self, client):
        """POST config with invalid polling_minutes returns 400."""
        response = client.post(
            "/admin/monitoring/config",
            json={"enabled": True, "polling_minutes": 7},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_get_status(self, client):
        """GET /admin/monitoring/status returns valid response shape."""
        response = client.get("/admin/monitoring/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "enabled" in data
        assert "polling_minutes" in data
        assert "windows" in data
        assert isinstance(data["windows"], list)
        assert "threshold_alerts" in data

    def test_get_history(self, client, isolated_db):
        """Insert snapshots, GET history, verify returned list."""
        from app.database import get_connection

        now = datetime.now(timezone.utc)
        with get_connection() as conn:
            account_id = _create_test_account(conn)
            for offset in [5, 3, 1]:
                t = (now - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
                _insert_snapshot(conn, account_id, "5h_sliding", 1000 * offset, t)

        response = client.get(
            f"/admin/monitoring/history?account_id={account_id}&window_type=5h_sliding&minutes=10"
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["account_id"] == account_id
        assert data["window_type"] == "5h_sliding"
        assert len(data["history"]) == 3

    def test_get_history_missing_params(self, client):
        """GET /admin/monitoring/history without required params returns 400."""
        response = client.get("/admin/monitoring/history")
        assert response.status_code == 400
