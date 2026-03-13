"""Cross-team insights aggregation queries.

Provides per-team execution counts, success rates, week-over-week changes,
and most active trigger for the cross-team insights dashboard.
Findings and repo-risk data are not yet stored in the DB — those fields
return empty lists with data_available: false.
"""

import logging
import sqlite3
from typing import List

from .connection import get_connection
from .teams import get_all_teams

logger = logging.getLogger(__name__)


def get_cross_team_insights() -> dict:
    """Return aggregated cross-team insights.

    Returns:
        dict with keys:
          - teams: list of per-team insight dicts
          - org_findings: [] (data_available: false — no findings DB yet)
          - top_risky_repos: [] (data_available: false — no findings DB yet)
    """
    teams = get_all_teams()
    team_insights = []

    with get_connection() as conn:
        for team in teams:
            team_id = team["id"]
            insight = _build_team_insight(conn, team)
            team_insights.append(insight)

    return {
        "teams": team_insights,
        "org_findings": [],
        "top_risky_repos": [],
        "data_available": False,
    }


def _build_team_insight(conn, team: dict) -> dict:
    """Build a single team's insight dict from the DB.

    Queries execution_logs joined through triggers (via team_id).
    """
    team_id = team["id"]

    # Total executions and success rate for all time
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_executions,
                COALESCE(
                    CAST(SUM(CASE WHEN el.status = 'success' THEN 1 ELSE 0 END) AS REAL)
                    / NULLIF(COUNT(*), 0) * 100,
                    0
                ) as success_rate
            FROM execution_logs el
            JOIN triggers t ON el.trigger_id = t.id
            WHERE t.team_id = ?
            """,
            (team_id,),
        ).fetchone()
        total_executions = row["total_executions"] if row else 0
        success_rate = round(row["success_rate"] or 0.0, 1) if row else 0.0
    except sqlite3.Error as e:
        logger.error("Error fetching execution stats for team %s: %s", team_id, e)
        total_executions = 0
        success_rate = 0.0

    # Week-over-week change: last 7 days vs prior 7 days
    try:
        wow_row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN date(el.started_at) >= date('now', '-7 days') THEN 1 ELSE 0 END)
                    as last_week,
                SUM(CASE WHEN date(el.started_at) >= date('now', '-14 days')
                          AND date(el.started_at) < date('now', '-7 days') THEN 1 ELSE 0 END)
                    as prior_week
            FROM execution_logs el
            JOIN triggers t ON el.trigger_id = t.id
            WHERE t.team_id = ?
              AND date(el.started_at) >= date('now', '-14 days')
            """,
            (team_id,),
        ).fetchone()
        last_week = wow_row["last_week"] or 0 if wow_row else 0
        prior_week = wow_row["prior_week"] or 0 if wow_row else 0
        if prior_week > 0:
            week_over_week_change = round(((last_week - prior_week) / prior_week) * 100)
        elif last_week > 0:
            week_over_week_change = 100
        else:
            week_over_week_change = 0
    except sqlite3.Error as e:
        logger.error("Error fetching WoW stats for team %s: %s", team_id, e)
        week_over_week_change = 0

    # Most active trigger name
    try:
        trig_row = conn.execute(
            """
            SELECT t.name, COUNT(*) as cnt
            FROM execution_logs el
            JOIN triggers t ON el.trigger_id = t.id
            WHERE t.team_id = ?
            GROUP BY el.trigger_id
            ORDER BY cnt DESC
            LIMIT 1
            """,
            (team_id,),
        ).fetchone()
        most_active_trigger_name = trig_row["name"] if trig_row else None
    except sqlite3.Error as e:
        logger.error("Error fetching most active trigger for team %s: %s", team_id, e)
        most_active_trigger_name = None

    return {
        "teamId": team_id,
        "teamName": team["name"],
        "totalExecutions": total_executions,
        "activeBots": team.get("member_count", 0),
        "findingsCount": 0,
        "criticalFindings": 0,
        "successRate": success_rate,
        "riskScore": 0,
        "topRisks": [],
        "mostActiveBotName": most_active_trigger_name or "",
        "weekOverWeekChange": week_over_week_change,
    }
