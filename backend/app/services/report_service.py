"""Report service for generating weekly team impact reports.

Queries execution_logs and pr_reviews tables directly to produce
team impact digests without over-engineering (no Jinja2, no PDF).
"""

import logging
from datetime import datetime, timedelta, timezone

from ..db.connection import get_connection

logger = logging.getLogger(__name__)


class ReportService:
    """Generates team impact reports from execution and PR review data."""

    TIME_SAVED_PER_PR_REVIEW_MINUTES = 15
    TIME_SAVED_PER_SECURITY_AUDIT_MINUTES = 30

    @classmethod
    def generate_weekly_report(cls, team_id: str = None) -> dict:
        """Generate a team impact report for the last 7 days.

        Args:
            team_id: Optional team filter (currently unused, reserved for future).

        Returns:
            Dict with prs_reviewed, issues_found, estimated_time_saved_minutes,
            top_bots, bots_needing_attention, period_start, period_end.
        """
        now = datetime.now(timezone.utc)
        period_end = now.strftime("%Y-%m-%d")
        period_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        with get_connection() as conn:
            # prs_reviewed: count of GitHub-triggered executions that completed
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM execution_logs
                WHERE trigger_type = 'github'
                  AND status = 'completed'
                  AND started_at >= datetime('now', '-7 days')
                """
            )
            prs_reviewed = cursor.fetchone()["cnt"]

            # issues_found: count of PR reviews with review_status = 'changes_requested'
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM pr_reviews
                WHERE review_status = 'changes_requested'
                  AND created_at >= datetime('now', '-7 days')
                """
            )
            issues_found = cursor.fetchone()["cnt"]

            # Count security audits (webhook-triggered completions)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM execution_logs
                WHERE trigger_type = 'webhook'
                  AND status = 'completed'
                  AND started_at >= datetime('now', '-7 days')
                """
            )
            security_audits = cursor.fetchone()["cnt"]

            # estimated_time_saved
            estimated_time_saved = (
                prs_reviewed * cls.TIME_SAVED_PER_PR_REVIEW_MINUTES
                + security_audits * cls.TIME_SAVED_PER_SECURITY_AUDIT_MINUTES
            )

            # top_bots: top 5 triggers by execution count in the period
            cursor = conn.execute(
                """
                SELECT e.trigger_id, t.name as trigger_name, COUNT(*) as execution_count
                FROM execution_logs e
                LEFT JOIN triggers t ON e.trigger_id = t.id
                WHERE e.started_at >= datetime('now', '-7 days')
                GROUP BY e.trigger_id
                ORDER BY execution_count DESC
                LIMIT 5
                """
            )
            top_bots = [
                {
                    "trigger_id": row["trigger_id"],
                    "trigger_name": row["trigger_name"],
                    "execution_count": row["execution_count"],
                }
                for row in cursor.fetchall()
            ]

            # bots_needing_attention: triggers with >50% failure rate or active health alerts
            cursor = conn.execute(
                """
                SELECT e.trigger_id, t.name as trigger_name,
                       COUNT(*) as total,
                       SUM(CASE WHEN e.status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM execution_logs e
                LEFT JOIN triggers t ON e.trigger_id = t.id
                WHERE e.started_at >= datetime('now', '-7 days')
                GROUP BY e.trigger_id
                HAVING total > 0 AND (CAST(failed AS FLOAT) / total) > 0.5
                """
            )
            bots_needing_attention = []
            seen_trigger_ids = set()
            for row in cursor.fetchall():
                failure_rate = round(row["failed"] / row["total"], 2) if row["total"] > 0 else 0
                bots_needing_attention.append(
                    {
                        "trigger_id": row["trigger_id"],
                        "trigger_name": row["trigger_name"],
                        "reason": f"High failure rate: {failure_rate:.0%}",
                        "failure_rate": failure_rate,
                        "active_alerts": 0,
                    }
                )
                seen_trigger_ids.add(row["trigger_id"])

            # Also add triggers with active (unacknowledged) health alerts
            cursor = conn.execute(
                """
                SELECT h.trigger_id, t.name as trigger_name, COUNT(*) as alert_count
                FROM health_alerts h
                LEFT JOIN triggers t ON h.trigger_id = t.id
                WHERE h.acknowledged = 0
                GROUP BY h.trigger_id
                """
            )
            for row in cursor.fetchall():
                if row["trigger_id"] not in seen_trigger_ids:
                    bots_needing_attention.append(
                        {
                            "trigger_id": row["trigger_id"],
                            "trigger_name": row["trigger_name"],
                            "reason": f"Active health alerts: {row['alert_count']}",
                            "failure_rate": None,
                            "active_alerts": row["alert_count"],
                        }
                    )

        return {
            "prs_reviewed": prs_reviewed,
            "issues_found": issues_found,
            "estimated_time_saved_minutes": estimated_time_saved,
            "top_bots": top_bots,
            "bots_needing_attention": bots_needing_attention,
            "period_start": period_start,
            "period_end": period_end,
        }
