"""Monitoring service for periodic rate limit window tracking with consumption rates and ETA projection."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service for periodic rate limit monitoring via APScheduler.

    Polls real provider APIs per backend account, records snapshots, detects threshold
    transitions, computes moving average consumption rates and ETA projections.
    """

    _job_id = "token_usage_monitoring"
    _cleanup_job_id = "snapshot_cleanup"
    _last_threshold_levels: dict = {}
    _recent_alerts: list = []
    _last_polled_at: Optional[str] = None

    # Threshold level ordering for comparison
    _LEVEL_ORDER = {"normal": 0, "info": 1, "warning": 2, "critical": 3}

    @classmethod
    def init(cls):
        """Initialize monitoring service. Called once at app startup.

        Auto-enables monitoring when backend accounts exist and registers
        a background APScheduler job.  Runs an immediate first poll so data
        is available before the frontend opens.
        """
        from ..database import (
            get_all_accounts_with_health,
            get_latest_snapshots,
            get_monitoring_config,
        )

        # Initialize threshold levels from latest snapshots (survives restarts)
        try:
            snapshots = get_latest_snapshots(max_age_minutes=44640)  # 31 days for init
            for snap in snapshots:
                key = f"{snap['account_id']}_{snap['window_type']}"
                cls._last_threshold_levels[key] = snap.get("threshold_level", "normal")
        except Exception as e:
            logger.warning(f"Could not initialize threshold levels from DB: {e}")

        # Load config and auto-enable if accounts exist
        try:
            config = get_monitoring_config()
            if not config.get("enabled"):
                # Auto-enable when backend accounts are configured
                try:
                    accounts = get_all_accounts_with_health()
                    if accounts:
                        config["enabled"] = True
                        config.setdefault("polling_minutes", 5)
                        from ..database import save_monitoring_config

                        save_monitoring_config(config)
                        logger.info(
                            "Monitoring auto-enabled: %d backend accounts found", len(accounts)
                        )
                except Exception:
                    pass

            if config.get("enabled"):
                polling_minutes = config.get("polling_minutes", 5)
                cls._register_job(polling_minutes)
                logger.info("Monitoring service: polling every %d min", polling_minutes)
                # Run immediate first poll in background so data is ready
                import threading

                threading.Thread(target=cls._poll_usage, daemon=True).start()
        except Exception as e:
            logger.warning(f"Could not load monitoring config: {e}")

        # Register daily cleanup job
        cls._register_cleanup_job()
        logger.info("Monitoring service initialized")

    @classmethod
    def reconfigure(cls, config: dict):
        """Reconfigure monitoring: save config and re-register/remove APScheduler job."""
        from ..database import save_monitoring_config

        save_monitoring_config(config)

        if config.get("enabled"):
            cls._register_job(config.get("polling_minutes", 5))
            logger.info(
                f"Monitoring reconfigured: polling every {config.get('polling_minutes', 5)} min"
            )
        else:
            cls._remove_job()
            logger.info("Monitoring disabled: job removed")

    @classmethod
    def _register_job(cls, interval_minutes: int):
        """Register or re-register the monitoring interval job."""
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            logger.warning("Scheduler not available, cannot register monitoring job")
            return

        existing = SchedulerService._scheduler.get_job(cls._job_id)
        if existing:
            SchedulerService._scheduler.remove_job(cls._job_id)

        SchedulerService._scheduler.add_job(
            func=cls._poll_usage,
            trigger="interval",
            minutes=interval_minutes,
            id=cls._job_id,
            replace_existing=True,
        )

    @classmethod
    def _remove_job(cls):
        """Remove the monitoring job if it exists."""
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            return

        existing = SchedulerService._scheduler.get_job(cls._job_id)
        if existing:
            SchedulerService._scheduler.remove_job(cls._job_id)

    @classmethod
    def _register_cleanup_job(cls):
        """Register daily snapshot cleanup job (4am UTC)."""
        from ..database import delete_old_snapshots
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            return

        SchedulerService._scheduler.add_job(
            func=delete_old_snapshots,
            trigger="cron",
            hour=4,
            minute=0,
            id=cls._cleanup_job_id,
            replace_existing=True,
            kwargs={"days": 31},
        )

    @classmethod
    def _poll_usage(cls):
        """Periodic polling job: call real provider APIs per enabled account, record snapshots."""
        from ..database import (
            get_all_accounts_with_health,
            get_monitoring_config,
            insert_rate_limit_snapshot,
        )
        from .provider_usage_client import ProviderUsageClient

        cls._recent_alerts = []
        now = datetime.now(timezone.utc)
        logger.info("Monitoring poll: starting at %s", now.isoformat())

        try:
            config = get_monitoring_config()
        except Exception as e:
            logger.error(f"Monitoring poll: failed to load config: {e}")
            return

        accounts_config = config.get("accounts", {})

        # Get all accounts with backend type info
        try:
            all_accounts = get_all_accounts_with_health()
        except Exception as e:
            logger.error(f"Monitoring poll: failed to load accounts: {e}")
            return

        if not all_accounts:
            return

        # When monitoring is globally enabled, poll ALL accounts unless explicitly disabled.
        # Auto-add any missing accounts to config so they appear next time.
        updated_config = False
        for acct in all_accounts:
            acct_key = str(acct["id"])
            if acct_key not in accounts_config:
                accounts_config[acct_key] = {"enabled": True}
                updated_config = True
        if updated_config:
            from ..database import save_monitoring_config

            config["accounts"] = accounts_config
            save_monitoring_config(config)

        account_map = {str(a["id"]): a for a in all_accounts}

        # Track fetched tokens to deduplicate accounts sharing the same credentials
        fetched_tokens: dict[str, list[dict]] = {}  # fingerprint -> windows

        for acct_id_str, acct_cfg in accounts_config.items():
            if not acct_cfg.get("enabled", False):
                continue

            account = account_map.get(acct_id_str)
            if not account:
                continue

            account_id = account["id"]
            backend_type = account.get("backend_type", "claude")

            # Deduplicate: if this token was already fetched, reuse results
            from .provider_usage_client import CredentialResolver

            fingerprint = CredentialResolver.get_token_fingerprint(account, backend_type)
            # Include plan in cache key so accounts with different plans
            # don't share cached results (e.g. plus vs pro have different models)
            plan = (account.get("plan") or "").lower()
            cache_key = f"{fingerprint}:{plan}" if fingerprint else None
            if cache_key and cache_key in fetched_tokens:
                windows = fetched_tokens[cache_key]
                logger.info(
                    f"Monitoring poll: account {account_id} shares credentials "
                    f"(fingerprint {fingerprint}), reusing cached data"
                )
            else:
                try:
                    windows = ProviderUsageClient.fetch_usage(account, backend_type)
                except Exception as e:
                    logger.error(
                        f"Monitoring poll: provider API failed for account {account_id}: {e}"
                    )
                    continue

                if cache_key:
                    fetched_tokens[cache_key] = windows

            if not windows:
                logger.debug(f"Monitoring poll: no windows returned for account {account_id}")
                continue

            for window_data in windows:
                # Determine threshold level
                pct = window_data.get("percentage", 0)
                level = cls._compute_threshold_level(pct)

                # Record snapshot
                try:
                    insert_rate_limit_snapshot(
                        account_id=account_id,
                        backend_type=backend_type,
                        window_type=window_data["window_type"],
                        tokens_used=window_data.get("tokens_used", 0),
                        tokens_limit=window_data.get("tokens_limit", 0),
                        percentage=pct,
                        threshold_level=level,
                        resets_at=window_data.get("resets_at"),
                    )
                except Exception as e:
                    logger.error(f"Monitoring poll: snapshot insert failed: {e}")
                    continue

                # Check threshold transition
                transition = cls._check_threshold_transition(
                    account_id, window_data["window_type"], pct
                )
                if transition:
                    cls._recent_alerts.append(transition)

        # Record last successful poll timestamp
        cls._last_polled_at = now.isoformat()

        # Scheduler evaluation (piggyback on monitoring poll)
        try:
            from .agent_scheduler_service import AgentSchedulerService

            AgentSchedulerService.evaluate_all_accounts(now)
        except Exception as e:
            logger.error(f"Scheduler evaluation failed: {e}")

    @classmethod
    def _compute_threshold_level(cls, percentage: float) -> str:
        """Compute threshold level from usage percentage."""
        if percentage >= 90:
            return "critical"
        elif percentage >= 75:
            return "warning"
        elif percentage >= 50:
            return "info"
        return "normal"

    @classmethod
    def _check_threshold_transition(
        cls, account_id: int, window_type: str, percentage: float
    ) -> Optional[dict]:
        """Check for threshold state transition. Returns transition info or None.

        Only fires on severity increase (normal->info->warning->critical).
        Silently updates on severity decrease (cooldown).
        """
        key = f"{account_id}_{window_type}"
        current_level = cls._compute_threshold_level(percentage)
        previous_level = cls._last_threshold_levels.get(key, "normal")

        if current_level == previous_level:
            return None

        current_severity = cls._LEVEL_ORDER.get(current_level, 0)
        previous_severity = cls._LEVEL_ORDER.get(previous_level, 0)

        # Always update the stored level
        cls._last_threshold_levels[key] = current_level

        if current_severity > previous_severity:
            # Severity increased - fire transition
            logger.info(
                f"Threshold transition: account {account_id} {window_type} "
                f"{previous_level} -> {current_level} ({percentage}%)"
            )
            return {
                "account_id": account_id,
                "window_type": window_type,
                "previous_level": previous_level,
                "current_level": current_level,
                "percentage": percentage,
            }

        # Severity decreased - silent update (cooldown)
        return None

    @classmethod
    def compute_consumption_rate(
        cls, account_id: int, window_type: str, window_minutes: int, now: datetime
    ) -> Optional[float]:
        """Compute moving average consumption rate over a time window.

        Returns rate in tokens/minute when tokens_limit > 0, or %/minute when
        in percentage-only mode (tokens_limit == 0). Returns None if < 2 snapshots.
        """
        from ..database import get_snapshot_history

        snapshots = get_snapshot_history(account_id, window_type, since_minutes=window_minutes)
        if len(snapshots) < 2:
            return None

        oldest = snapshots[0]
        newest = snapshots[-1]

        # Use percentage delta when in percentage-only mode (tokens_limit == 0)
        is_pct_only = newest.get("tokens_limit", 0) == 0
        if is_pct_only:
            delta = newest["percentage"] - oldest["percentage"]
        else:
            delta = newest["tokens_used"] - oldest["tokens_used"]

        try:
            oldest_time = datetime.fromisoformat(oldest["recorded_at"].replace("Z", "+00:00"))
            newest_time = datetime.fromisoformat(newest["recorded_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

        time_delta_minutes = (newest_time - oldest_time).total_seconds() / 60.0
        if time_delta_minutes <= 0:
            return 0.0

        return delta / time_delta_minutes

    @classmethod
    def get_consumption_rates(cls, account_id: int, window_type: str, now: datetime) -> dict:
        """Compute consumption rates using all available snapshot data.

        Returns dict with rate/hour values. Unit is '%/hr' when percentage-only mode,
        'tok/hr' otherwise. The `unit` field indicates which.
        """
        from ..database import get_snapshot_history

        # Use a large window (31 days) to capture all available data
        all_snapshots = get_snapshot_history(account_id, window_type, since_minutes=44640)
        is_pct_only = False
        if all_snapshots and all_snapshots[-1].get("tokens_limit", 0) == 0:
            is_pct_only = True

        result = {}
        for label, minutes in [
            ("24h", 1440),
            ("48h", 2880),
            ("72h", 4320),
            ("96h", 5760),
            ("120h", 7200),
        ]:
            # Filter snapshots to this window from the LATEST snapshot, not from now
            if len(all_snapshots) >= 2:
                try:
                    newest_time = datetime.fromisoformat(
                        all_snapshots[-1]["recorded_at"].replace("Z", "+00:00")
                    )
                    cutoff = newest_time - timedelta(minutes=minutes)
                    windowed = [
                        s
                        for s in all_snapshots
                        if datetime.fromisoformat(s["recorded_at"].replace("Z", "+00:00")) >= cutoff
                    ]
                    if len(windowed) >= 2:
                        oldest = windowed[0]
                        newest = windowed[-1]
                        if is_pct_only:
                            delta = newest["percentage"] - oldest["percentage"]
                        else:
                            delta = newest["tokens_used"] - oldest["tokens_used"]
                        oldest_t = datetime.fromisoformat(
                            oldest["recorded_at"].replace("Z", "+00:00")
                        )
                        newest_t = datetime.fromisoformat(
                            newest["recorded_at"].replace("Z", "+00:00")
                        )
                        time_delta_min = (newest_t - oldest_t).total_seconds() / 60.0
                        if time_delta_min > 0:
                            rate_per_min = delta / time_delta_min
                            result[label] = round(rate_per_min * 60, 1)
                            continue
                except (ValueError, TypeError):
                    pass
            result[label] = None

        result["unit"] = "%/hr" if is_pct_only else "tok/hr"
        return result

    @classmethod
    def compute_rate_limit_eta(
        cls, window_data: dict, consumption_rate_per_minute: Optional[float], now: datetime
    ) -> dict:
        """Compute estimated time until rate limit hit.

        Supports both token-based and percentage-only modes.
        Accounts for window reset times (returns 'safe' if window resets before limit).
        """
        tokens_limit = window_data.get("tokens_limit", 0)
        tokens_used = window_data.get("tokens_used", 0)
        percentage = window_data.get("percentage", 0)

        # Percentage-only mode (provider only returns utilization %)
        is_pct_only = tokens_limit == 0

        if is_pct_only:
            remaining = 100.0 - percentage
        else:
            remaining = tokens_limit - tokens_used

        if remaining <= 0:
            return {"status": "at_limit", "message": "Rate limit reached"}

        if consumption_rate_per_minute is None:
            return {"status": "no_data", "message": "Insufficient data"}
        if consumption_rate_per_minute <= 0:
            if percentage <= 0:
                return {"status": "safe", "message": "No activity"}
            return {"status": "safe", "message": "Usage declining"}

        minutes_until_limit = remaining / consumption_rate_per_minute
        eta_datetime = now + timedelta(minutes=minutes_until_limit)

        # Check if window resets before limit is hit
        resets_at_str = window_data.get("resets_at")
        if resets_at_str:
            try:
                resets_at = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
                if not resets_at.tzinfo:
                    resets_at = resets_at.replace(tzinfo=timezone.utc)
                if eta_datetime > resets_at:
                    return {
                        "status": "safe",
                        "message": "Window resets before limit",
                        "resets_at": resets_at_str,
                    }
            except (ValueError, TypeError):
                pass

        return {
            "status": "projected",
            "eta": eta_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "minutes_remaining": round(minutes_until_limit, 1),
            "message": cls._format_eta(minutes_until_limit),
        }

    @staticmethod
    def _format_eta(minutes: float) -> str:
        """Format ETA as human-readable string."""
        if minutes < 60:
            return f"~{int(minutes)}m"
        elif minutes < 1440:
            return f"~{int(minutes // 60)}h {int(minutes % 60)}m"
        else:
            return f"~{int(minutes // 1440)}d {int((minutes % 1440) // 60)}h"

    @classmethod
    def get_monitoring_status(cls) -> dict:
        """Return comprehensive monitoring status for the GET /admin/monitoring/status endpoint."""
        from ..database import (
            get_all_accounts_with_health,
            get_latest_snapshots,
            get_monitoring_config,
        )

        config = get_monitoring_config()
        now = datetime.now(timezone.utc)

        # Build account name/plan lookup and detect shared credentials
        try:
            all_accounts = get_all_accounts_with_health()
            account_names = {a["id"]: a.get("account_name", "") for a in all_accounts}
            account_plans = {a["id"]: a.get("plan", "") for a in all_accounts}
        except Exception as e:
            logger.warning("Account data fetch error: %s", e)
            all_accounts = []
            account_names = {}
            account_plans = {}

        # Detect shared credentials via token fingerprints
        shared_credential_groups: dict[int, list[int]] = {}  # account_id -> [peer_ids]
        try:
            from .provider_usage_client import CredentialResolver

            fingerprint_map: dict[str, list[int]] = {}
            for acct in all_accounts:
                fp = CredentialResolver.get_token_fingerprint(
                    acct, acct.get("backend_type", "claude")
                )
                if fp:
                    fingerprint_map.setdefault(fp, []).append(acct["id"])
            for _fp, ids in fingerprint_map.items():
                if len(ids) > 1:
                    for aid in ids:
                        shared_credential_groups[aid] = [x for x in ids if x != aid]
        except Exception as e:
            logger.debug("Credential fingerprint detection: %s", e)

        # Get latest snapshots (exclude data older than 3x polling interval)
        polling_min = config.get("polling_minutes", 5)
        max_age = max(polling_min * 3, 30)  # at least 30 min to avoid gaps
        snapshots = get_latest_snapshots(max_age_minutes=max_age)

        windows = []
        accounts_with_data: set[int] = set()
        for snap in snapshots:
            account_id = snap["account_id"]
            window_type = snap["window_type"]
            accounts_with_data.add(account_id)

            # Compute consumption rates
            rates = cls.get_consumption_rates(account_id, window_type, now)

            # Use best available rate for ETA projection (prefer longer windows for stability)
            rate_per_minute = None
            for rate_key in ("120h", "96h", "72h", "48h", "24h"):
                if rates.get(rate_key) is not None:
                    rate_per_minute = rates[rate_key] / 60.0  # convert per-hour to per-min
                    break

            # Compute ETA
            eta = cls.compute_rate_limit_eta(
                {
                    "tokens_used": snap["tokens_used"],
                    "tokens_limit": snap["tokens_limit"],
                    "percentage": snap["percentage"],
                    "resets_at": snap.get("resets_at"),
                },
                rate_per_minute,
                now,
            )

            window_entry = {
                "account_id": account_id,
                "account_name": account_names.get(account_id, ""),
                "plan": account_plans.get(account_id, ""),
                "backend_type": snap["backend_type"],
                "window_type": window_type,
                "tokens_used": snap["tokens_used"],
                "tokens_limit": snap["tokens_limit"],
                "percentage": snap["percentage"],
                "threshold_level": snap["threshold_level"],
                "resets_at": snap.get("resets_at"),
                "recorded_at": snap["recorded_at"],
                "consumption_rates": rates,
                "eta": eta,
            }
            if account_id in shared_credential_groups:
                peer_names = [
                    account_names.get(pid, str(pid)) for pid in shared_credential_groups[account_id]
                ]
                window_entry["shared_with"] = peer_names
            windows.append(window_entry)

        # Include enabled accounts that have no recent snapshot data so they
        # still appear as cards in the UI with a "no data / auth failed" indicator.
        monitoring_accounts = config.get("accounts", {})
        for acct in all_accounts:
            acct_id = acct["id"]
            acct_key = str(acct_id)
            acct_cfg = monitoring_accounts.get(acct_key, {})
            if acct_cfg.get("enabled", False) and acct_id not in accounts_with_data:
                windows.append(
                    {
                        "account_id": acct_id,
                        "account_name": account_names.get(acct_id, ""),
                        "plan": account_plans.get(acct_id, ""),
                        "backend_type": acct.get("backend_type", "claude"),
                        "window_type": "no_data",
                        "tokens_used": 0,
                        "tokens_limit": 0,
                        "percentage": 0,
                        "threshold_level": "normal",
                        "resets_at": None,
                        "recorded_at": None,
                        "consumption_rates": {},
                        "eta": {"status": "no_data", "message": "No monitoring data"},
                        "no_data": True,
                    }
                )

        return {
            "enabled": config.get("enabled", False),
            "polling_minutes": config.get("polling_minutes", 5),
            "windows": windows,
            "threshold_alerts": cls._recent_alerts.copy(),
            "last_polled_at": cls._last_polled_at,
        }
