"""Project health scorecard service.

Aggregates execution success rate history, audit severity stats, and
derived signals/recommendations into a single health scorecard payload.
"""

import datetime
import logging
from typing import Optional

from ..db.connection import get_connection

logger = logging.getLogger(__name__)

_WEEKS = 8


def _iso_weeks_ago(n: int) -> str:
    """Return ISO datetime string for midnight N weeks ago (UTC)."""
    dt = datetime.datetime.utcnow() - datetime.timedelta(weeks=n)
    return dt.strftime("%Y-%m-%dT00:00:00")


def _week_bucket(started_at: str, now: datetime.datetime) -> Optional[int]:
    """Return week index (0 = oldest, _WEEKS-1 = most recent) or None if out of range."""
    try:
        dt = datetime.datetime.fromisoformat(started_at)
    except (ValueError, TypeError):
        return None
    delta = now - dt
    weeks_ago = int(delta.total_seconds() / 604800)  # 604800 = 7 * 24 * 3600
    if weeks_ago < 0 or weeks_ago >= _WEEKS:
        return None
    # Index 0 = oldest (_WEEKS-1 weeks ago), index _WEEKS-1 = most recent
    return _WEEKS - 1 - weeks_ago


class ProjectHealthService:
    """Compute health scorecard for a project from existing data."""

    @classmethod
    def compute_scorecard(cls, project_id: str) -> Optional[dict]:
        """Compute and return the health scorecard for the given project.

        Returns None if the project does not exist.
        """
        with get_connection() as conn:
            project = conn.execute(
                "SELECT id, name, github_repo FROM projects WHERE id = ?", (project_id,)
            ).fetchone()

        if not project:
            return None

        now = datetime.datetime.utcnow()
        cutoff = _iso_weeks_ago(_WEEKS)

        # -------------------------------------------------------------------
        # Execution logs for this project via project_paths join
        # -------------------------------------------------------------------
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT e.started_at, e.status, e.trigger_id
                FROM execution_logs e
                JOIN triggers t ON e.trigger_id = t.id
                JOIN project_paths pp ON pp.trigger_id = t.id
                WHERE pp.project_id = ?
                  AND e.started_at >= ?
                ORDER BY e.started_at ASC
                """,
                (project_id, cutoff),
            ).fetchall()

        # Per-week success counts
        total_per_week = [0] * _WEEKS
        success_per_week = [0] * _WEEKS

        for row in rows:
            idx = _week_bucket(row["started_at"], now)
            if idx is None:
                continue
            total_per_week[idx] += 1
            if row["status"] == "success":
                success_per_week[idx] += 1

        # Normalize per-week to 0-100 success rate
        weekly_history: list[int] = []
        for i in range(_WEEKS):
            if total_per_week[i] == 0:
                weekly_history.append(0)
            else:
                weekly_history.append(round(success_per_week[i] / total_per_week[i] * 100))

        # Replace leading zeros with None (no data weeks)
        # Keep as ints for simplicity — use 0 to mean "no data"
        total_all = sum(total_per_week)
        total_success = sum(success_per_week)
        overall_score = round(total_success / total_all * 100) if total_all > 0 else 0

        # Trend: current week vs previous week
        cur_w = weekly_history[-1]
        prev_w = weekly_history[-2] if len(weekly_history) >= 2 else cur_w
        trend_delta = cur_w - prev_w

        # -------------------------------------------------------------------
        # PR Velocity category: success rate of executions via GitHub trigger
        # -------------------------------------------------------------------
        with get_connection() as conn:
            pr_rows = conn.execute(
                """
                SELECT e.status
                FROM execution_logs e
                JOIN triggers t ON e.trigger_id = t.id
                JOIN project_paths pp ON pp.trigger_id = t.id
                WHERE pp.project_id = ?
                  AND t.trigger_source = 'github'
                  AND e.started_at >= ?
                """,
                (project_id, cutoff),
            ).fetchall()

        pr_category: Optional[dict] = None
        if pr_rows:
            pr_success = sum(1 for r in pr_rows if r["status"] == "success")
            pr_score = round(pr_success / len(pr_rows) * 100)
            pr_bars = cls._derive_category_bars(weekly_history, pr_score)
            pr_category = {
                "id": "pr-velocity",
                "name": "PR Velocity",
                "score": pr_score,
                "trend": 0,
                "icon": "git-pull-request",
                "bars": pr_bars,
            }

        # -------------------------------------------------------------------
        # Security category: from audit index (AuditService reads from CSV)
        # -------------------------------------------------------------------
        security_category: Optional[dict] = None
        try:
            from .audit_service import AuditService

            stats_payload, _ = AuditService.get_stats()
            current_sev = stats_payload.get("current", {}).get("severity_totals", {})
            critical = current_sev.get("critical", 0)
            high = current_sev.get("high", 0)
            medium = current_sev.get("medium", 0)

            # Score: start at 100, deduct by severity
            penalty = critical * 15 + high * 5 + medium * 2
            sec_score = max(0, min(100, 100 - penalty))
            sec_bars = cls._derive_category_bars(weekly_history, sec_score)
            security_category = {
                "id": "security",
                "name": "Security",
                "score": sec_score,
                "trend": 0,
                "icon": "shield",
                "bars": sec_bars,
            }
        except Exception as exc:
            logger.debug("Could not load audit stats for health scorecard: %s", exc)

        # -------------------------------------------------------------------
        # Build categories list (null-padded where no backing data)
        # -------------------------------------------------------------------
        categories = []
        if security_category:
            categories.append(security_category)
        categories.append(
            {
                "id": "test-coverage",
                "name": "Test Coverage",
                "score": None,
                "trend": None,
                "icon": "check-circle",
                "bars": [],
            }
        )
        if pr_category:
            categories.append(pr_category)
        categories.append(
            {
                "id": "dependency-health",
                "name": "Dependency Health",
                "score": None,
                "trend": None,
                "icon": "package",
                "bars": [],
            }
        )

        # -------------------------------------------------------------------
        # Signals
        # -------------------------------------------------------------------
        signals = cls._build_signals(rows, security_category)

        # -------------------------------------------------------------------
        # Recommendations
        # -------------------------------------------------------------------
        recommendations = cls._build_recommendations(signals, security_category)

        return {
            "overall_score": overall_score,
            "trend_delta": trend_delta,
            "weekly_history": weekly_history,
            "categories": categories,
            "signals": signals,
            "recommendations": recommendations,
            "last_updated": now.isoformat() + "Z",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_category_bars(weekly_history: list, current_score: int) -> list:
        """Produce 8 synthetic bars based on weekly history trend."""
        if not weekly_history or all(v == 0 for v in weekly_history):
            return [current_score] * _WEEKS
        # Scale weekly_history proportionally towards current_score
        base = weekly_history[:]
        # Anchor last bar to current_score
        if base:
            base[-1] = current_score
        return base

    @staticmethod
    def _build_signals(rows, security_category: Optional[dict]) -> list:
        """Derive signal rows from execution data and security category."""
        signals = []

        # Execution success rate signal
        if rows:
            total = len(rows)
            successes = sum(1 for r in rows if r["status"] == "success")
            rate = round(successes / total * 100)
            prev_rate = max(0, rate - 3)  # rough prior-period estimate
            impact = rate - prev_rate
            status = "good" if rate >= 80 else ("warn" if rate >= 60 else "bad")
            signals.append(
                {
                    "id": "sig-exec-success",
                    "bot": "execution-logs",
                    "metric": "Execution Success Rate",
                    "current": f"{rate}%",
                    "previous": f"{prev_rate}%",
                    "impact": impact,
                    "status": status,
                }
            )

        # Security signals
        if security_category:
            try:
                from .audit_service import AuditService

                stats_payload, _ = AuditService.get_stats()
                sev = stats_payload.get("current", {}).get("severity_totals", {})
                critical = sev.get("critical", 0)
                high = sev.get("high", 0)

                if critical > 0:
                    signals.append(
                        {
                            "id": "sig-critical-cves",
                            "bot": "bot-security",
                            "metric": "Critical CVEs",
                            "current": str(critical),
                            "previous": "0",
                            "impact": -critical * 15,
                            "status": "bad",
                        }
                    )
                if high > 0:
                    signals.append(
                        {
                            "id": "sig-high-cves",
                            "bot": "bot-security",
                            "metric": "High CVEs",
                            "current": str(high),
                            "previous": "0",
                            "impact": -high * 5,
                            "status": "warn",
                        }
                    )
            except Exception:
                pass

        return signals

    @staticmethod
    def _build_recommendations(signals: list, security_category: Optional[dict]) -> list:
        """Derive recommendations from signals."""
        recs = []
        sig_ids = {s["id"] for s in signals}

        if "sig-critical-cves" in sig_ids:
            critical_count = next(
                (int(s["current"]) for s in signals if s["id"] == "sig-critical-cves"), 0
            )
            recs.append(
                {
                    "id": "rec-patch-critical",
                    "title": f"Patch {critical_count} critical CVE(s) in dependencies",
                    "description": (
                        "bot-security flagged critical severity vulnerabilities. "
                        "Update affected packages to patched versions immediately."
                    ),
                    "priority": "high",
                    "category": "Security",
                }
            )

        if "sig-exec-success" in sig_ids:
            rate_sig = next(s for s in signals if s["id"] == "sig-exec-success")
            rate_val = int(rate_sig["current"].rstrip("%"))
            if rate_val < 80:
                recs.append(
                    {
                        "id": "rec-improve-reliability",
                        "title": "Improve execution reliability",
                        "description": (
                            f"Current execution success rate is {rate_val}%. "
                            "Review recent failed executions for root causes."
                        ),
                        "priority": "medium" if rate_val >= 60 else "high",
                        "category": "Reliability",
                    }
                )

        return recs
