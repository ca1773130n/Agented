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


class AnalyticsService:
    """Service for analytics data aggregation. Uses @classmethod pattern."""

    @classmethod
    def _default_start_date(cls, start_date: Optional[str]) -> Optional[str]:
        """Default start_date to 30 days ago if not provided."""
        if start_date:
            return start_date
        return (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    @classmethod
    def get_cost_summary(
        cls,
        entity_type: Optional[str] = None,
        group_by: str = "day",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Get cost analytics summary with total cost computed from results.

        Defaults start_date to 30 days ago if not provided.
        """
        effective_start = cls._default_start_date(start_date)
        data = get_cost_analytics(
            entity_type=entity_type,
            group_by=group_by,
            start_date=effective_start,
            end_date=end_date,
        )
        total_cost = sum(row.get("total_cost_usd", 0) for row in data)
        periods = set(row.get("period") for row in data)
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
        """Get execution analytics summary with total executions computed.

        Defaults start_date to 30 days ago if not provided.
        """
        effective_start = cls._default_start_date(start_date)
        data = get_execution_analytics(
            group_by=group_by,
            start_date=effective_start,
            end_date=end_date,
            trigger_id=trigger_id,
            team_id=team_id,
        )
        total_executions = sum(row.get("total_executions", 0) for row in data)
        periods = set(row.get("period") for row in data)
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
        """Get effectiveness summary + over_time breakdown.

        Default trigger_id = None (all triggers with PR reviews).
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
