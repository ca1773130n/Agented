"""Product owner service -- meeting protocol, health aggregation, dashboard data."""

import json
import logging
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.db.messages import add_agent_message
from app.db.products import get_product, get_product_detail
from app.db.rotations import (
    get_decisions_by_product,
    get_milestones_by_product,
    get_projects_for_milestone,
)

logger = logging.getLogger(__name__)


class ProductOwnerService:
    """Encapsulates product owner business logic: meetings, health, dashboard."""

    @staticmethod
    def compute_health(product_id: str) -> dict:
        """Compute product health from project statuses.

        Green = all active, red = any archived or more than half not active,
        yellow = otherwise, neutral = no projects.
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) as count FROM projects WHERE product_id = ? GROUP BY status",
                (product_id,),
            )
            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}

        total = sum(status_counts.values())
        if total == 0:
            return {
                "health": "neutral",
                "reason": "No projects",
                "project_count": 0,
                "active_count": 0,
            }

        active = status_counts.get("active", 0)
        if active == total:
            return {
                "health": "green",
                "reason": "All projects active",
                "project_count": total,
                "active_count": active,
            }
        elif status_counts.get("archived", 0) > 0 or (total - active) > total // 2:
            return {
                "health": "red",
                "reason": f"{total - active} of {total} projects not active",
                "project_count": total,
                "active_count": active,
            }
        else:
            return {
                "health": "yellow",
                "reason": f"{active}/{total} projects active",
                "project_count": total,
                "active_count": active,
            }

    @staticmethod
    def trigger_standup_meeting(product_id: str) -> dict:
        """Trigger a standup meeting between product owner and project leaders.

        The owner_agent_id must be a super_agents.id (not agents.id) because
        agent_messages.from_agent_id has FOREIGN KEY to super_agents(id) and
        PRAGMA foreign_keys = ON is enforced.

        Returns dict with meeting_id, message_ids, participants.
        """
        product = get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        owner_agent_id = product.get("owner_agent_id")
        if not owner_agent_id:
            raise ValueError("No owner agent assigned to this product")

        # Get leader super_agents for projects under this product.
        # Query team_members with tier='leader' for teams assigned to product's projects,
        # then get their super_agent_id (which references super_agents table).
        leader_ids = set()
        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT tm.super_agent_id
                FROM team_members tm
                JOIN project_teams pt ON tm.team_id = pt.team_id
                JOIN projects p ON pt.project_id = p.id
                WHERE p.product_id = ?
                  AND tm.tier = 'leader'
                  AND tm.super_agent_id IS NOT NULL
            """,
                (product_id,),
            )
            for row in cursor.fetchall():
                leader_ids.add(row["super_agent_id"])

        now = datetime.now(timezone.utc).isoformat()
        agenda = {
            "type": "standup",
            "product_id": product_id,
            "items": ["status_update", "blockers", "priorities"],
            "triggered_at": now,
        }

        message_ids = []
        for leader_id in leader_ids:
            msg_id = add_agent_message(
                from_agent_id=owner_agent_id,
                to_agent_id=leader_id,
                message_type="request",
                subject="standup",
                content=json.dumps(agenda),
                priority="normal",
            )
            if msg_id:
                message_ids.append(msg_id)

        meeting_id = f"meeting-{product_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        return {
            "meeting_id": meeting_id,
            "message_ids": message_ids,
            "participants": len(message_ids),
        }

    @staticmethod
    def get_meeting_history(product_id: str, limit: int = 20) -> list:
        """Get standup meeting history for a product.

        Queries agent_messages where subject='standup' and from_agent_id is the
        product's owner_agent_id.
        """
        product = get_product(product_id)
        if not product:
            return []

        owner_agent_id = product.get("owner_agent_id")
        if not owner_agent_id:
            return []

        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM agent_messages
                WHERE from_agent_id = ? AND subject = 'standup'
                ORDER BY created_at DESC
                LIMIT ?
            """,
                (owner_agent_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_token_spend(product_id: str, days: int = 30) -> list:
        """Get token spend aggregated by day for a product's projects.

        Queries token_usage joined through projects to products, grouped by day.
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT DATE(tu.recorded_at) as day,
                       SUM(tu.input_tokens) as input_tokens,
                       SUM(tu.output_tokens) as output_tokens,
                       SUM(tu.total_cost_usd) as total_cost
                FROM token_usage tu
                JOIN projects p ON tu.entity_id = p.id AND tu.entity_type = 'project'
                WHERE p.product_id = ?
                  AND tu.recorded_at >= date('now', ?)
                GROUP BY day
                ORDER BY day DESC
            """,
                (product_id, f"-{days} days"),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_dashboard_data(product_id: str) -> dict:
        """Aggregate all dashboard data for a product in one call.

        Returns product detail, decisions, milestones with linked projects,
        health, recent activity, and token spend.
        """
        product = get_product_detail(product_id)
        if not product:
            return {}

        decisions = get_decisions_by_product(product_id)

        milestones = get_milestones_by_product(product_id)
        for ms in milestones:
            ms["projects"] = get_projects_for_milestone(ms["id"])

        health = ProductOwnerService.compute_health(product_id)

        # Recent activity: agent_messages involving the product's owner agent
        activity = []
        owner_agent_id = product.get("owner_agent_id")
        if owner_agent_id:
            with get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM agent_messages
                    WHERE from_agent_id = ? OR to_agent_id = ?
                    ORDER BY created_at DESC
                    LIMIT 20
                """,
                    (owner_agent_id, owner_agent_id),
                )
                activity = [dict(row) for row in cursor.fetchall()]

        token_spend = ProductOwnerService.get_token_spend(product_id)

        return {
            "product": product,
            "decisions": decisions,
            "milestones": milestones,
            "health": health,
            "activity": activity,
            "token_spend": token_spend,
        }
