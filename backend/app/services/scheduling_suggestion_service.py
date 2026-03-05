"""Scheduling suggestion service for optimal trigger timing.

Analyzes historical execution data to recommend the best hours and days
for trigger scheduling based on success rate and execution duration.
"""

import logging
from typing import List, Optional

from ..db.analytics import get_execution_time_patterns
from ..models.analytics import SchedulingSuggestion, SchedulingSuggestionsResponse

logger = logging.getLogger(__name__)

# Day name mapping (strftime %w: 0=Sunday, 6=Saturday)
_DAY_NAMES = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
}


class SchedulingSuggestionService:
    """Analyzes execution patterns to suggest optimal scheduling times."""

    MIN_EXECUTIONS_FOR_SUGGESTION = 10

    @classmethod
    def get_day_name(cls, day_number: str) -> str:
        """Map strftime %w day number (0-6) to day name."""
        return _DAY_NAMES.get(str(day_number), f"Day {day_number}")

    @classmethod
    def get_suggestions(
        cls, trigger_id: Optional[str] = None, days: int = 90
    ) -> SchedulingSuggestionsResponse:
        """Get scheduling suggestions based on historical execution patterns.

        Analyzes hour-of-day and day-of-week patterns. Ranks by success_rate DESC,
        avg_duration_ms ASC. Returns top 3 hours and top 2 days.

        Returns empty suggestions with message if insufficient data (<10 executions).
        """
        hour_patterns, day_patterns = get_execution_time_patterns(trigger_id=trigger_id, days=days)

        # Calculate total executions analyzed
        total_executions = sum(row["total"] for row in hour_patterns)

        if total_executions < cls.MIN_EXECUTIONS_FOR_SUGGESTION:
            return SchedulingSuggestionsResponse(
                suggestions=[],
                total_executions_analyzed=total_executions,
                analysis_period_days=days,
                message=(
                    f"Not enough execution history for suggestions "
                    f"(need at least {cls.MIN_EXECUTIONS_FOR_SUGGESTION})"
                ),
            )

        suggestions: List[SchedulingSuggestion] = []

        # Rank hours by success_rate DESC, avg_duration_ms ASC
        hour_ranked = cls._rank_patterns(hour_patterns)
        for pattern in hour_ranked[:3]:
            hour_val = pattern["key"]
            success_rate = pattern["success_rate"]
            avg_dur = pattern["avg_duration_ms"]
            dur_str = f"{avg_dur / 60000:.1f} min" if avg_dur else "N/A"
            suggestions.append(
                SchedulingSuggestion(
                    type="hour",
                    value=f"{int(hour_val):02d}:00",
                    success_rate=success_rate,
                    avg_duration_ms=avg_dur,
                    execution_count=pattern["total"],
                    rationale=(
                        f"Highest success rate ({success_rate:.0f}%) "
                        f"with average execution ({dur_str})"
                    ),
                )
            )

        # Rank days by success_rate DESC, avg_duration_ms ASC
        day_ranked = cls._rank_patterns(day_patterns)
        for pattern in day_ranked[:2]:
            day_val = pattern["key"]
            success_rate = pattern["success_rate"]
            avg_dur = pattern["avg_duration_ms"]
            dur_str = f"{avg_dur / 60000:.1f} min" if avg_dur else "N/A"
            day_name = cls.get_day_name(day_val)
            suggestions.append(
                SchedulingSuggestion(
                    type="day",
                    value=day_name,
                    success_rate=success_rate,
                    avg_duration_ms=avg_dur,
                    execution_count=pattern["total"],
                    rationale=(
                        f"Highest success rate ({success_rate:.0f}%) "
                        f"with average execution ({dur_str})"
                    ),
                )
            )

        return SchedulingSuggestionsResponse(
            suggestions=suggestions,
            total_executions_analyzed=total_executions,
            analysis_period_days=days,
        )

    @classmethod
    def _rank_patterns(cls, patterns: List[dict]) -> List[dict]:
        """Rank patterns by success_rate DESC, avg_duration_ms ASC.

        Returns list of dicts with key, success_rate, avg_duration_ms, total.
        """
        ranked = []
        for row in patterns:
            total = row["total"]
            success = row["success"] or 0
            success_rate = (success / total * 100) if total > 0 else 0.0
            avg_dur = row["avg_duration_ms"]
            # Use the first key that's not 'total', 'success', or 'avg_duration_ms'
            key = row.get("hour") or row.get("day_of_week") or "unknown"
            ranked.append(
                {
                    "key": key,
                    "success_rate": round(success_rate, 1),
                    "avg_duration_ms": round(avg_dur, 1) if avg_dur else None,
                    "total": total,
                }
            )

        # Sort: success_rate DESC, then avg_duration_ms ASC (None last)
        ranked.sort(
            key=lambda x: (
                -x["success_rate"],
                x["avg_duration_ms"] if x["avg_duration_ms"] is not None else float("inf"),
            )
        )
        return ranked
