"""Analytics service orchestrating DB queries with date range defaults."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..db.analytics import (
    get_cost_analytics,
    get_effectiveness_analytics,
    get_effectiveness_over_time,
    get_execution_analytics,
)

logger = logging.getLogger(__name__)


def _default_start_date(start_date: Optional[str], days_back: int = 30) -> Optional[str]:
    """Return start_date or default to N days ago if not provided."""
    if start_date:
        return start_date
    return (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")


class AnalyticsService:
    """Service for analytics aggregation with sensible defaults."""

    @classmethod
    def get_cost_summary(
        cls,
        entity_type: Optional[str] = None,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Get cost analytics with 30-day default window.

        Returns dict with data, period_count, total_cost.
        """
        effective_start = _default_start_date(start_date)
        data = get_cost_analytics(
            entity_type=entity_type,
            group_by=group_by,
            start_date=effective_start,
            end_date=end_date,
        )
        periods = set()
        total_cost = 0.0
        for row in data:
            periods.add(row["period"])
            total_cost += row["total_cost_usd"]

        return {
            "data": data,
            "period_count": len(periods),
            "total_cost": round(total_cost, 6),
        }

    @classmethod
    def get_execution_summary(
        cls,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trigger_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> dict:
        """Get execution analytics with 30-day default window.

        Returns dict with data, period_count, total_executions.
        """
        effective_start = _default_start_date(start_date)
        data = get_execution_analytics(
            group_by=group_by,
            start_date=effective_start,
            end_date=end_date,
            trigger_id=trigger_id,
            team_id=team_id,
        )
        periods = set()
        total_executions = 0
        for row in data:
            periods.add(row["period"])
            total_executions += row["total_executions"]

        return {
            "data": data,
            "period_count": len(periods),
            "total_executions": total_executions,
        }

    @classmethod
    def get_effectiveness(
        cls,
        trigger_id: Optional[str] = None,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Get effectiveness analytics (summary + over_time).

        Returns dict with total_reviews, accepted, ignored, pending,
        acceptance_rate, and over_time time-series.
        """
        summary = get_effectiveness_analytics(
            trigger_id=trigger_id,
            start_date=start_date,
            end_date=end_date,
        )
        over_time = get_effectiveness_over_time(
            trigger_id=trigger_id,
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
        )
        summary["over_time"] = over_time
        return summary
