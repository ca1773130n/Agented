"""Agent management service."""

import json
import threading
from http import HTTPStatus
from typing import Optional, Tuple

from ..database import (
    add_agent,
    count_agents,
    delete_agent,
    get_agent,
    get_all_agents,
    update_agent,
)
from ..db.agents import VALID_BACKENDS
from .execution_service import ExecutionService


class AgentService:
    """Service for agent CRUD operations and execution."""

    @staticmethod
    def list_agents(limit: Optional[int] = None, offset: int = 0) -> Tuple[dict, HTTPStatus]:
        """Get all agents with optional pagination."""
        total_count = count_agents()
        agents = get_all_agents(limit=limit, offset=offset)
        # Parse JSON fields for each agent
        for agent in agents:
            AgentService._parse_agent_json_fields(agent)
        return {"agents": agents, "total_count": total_count}, HTTPStatus.OK

    @staticmethod
    def get_agent_detail(agent_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a single agent with parsed JSON fields."""
        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

        AgentService._parse_agent_json_fields(agent)
        return agent, HTTPStatus.OK

    @staticmethod
    def create_agent(data: dict) -> Tuple[dict, HTTPStatus]:
        """Create a new agent."""
        name = data.get("name")
        if not name:
            return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

        description = data.get("description")
        role = data.get("role")
        goals = data.get("goals")
        context = data.get("context")
        backend_type = data.get("backend_type", "claude")
        skills = data.get("skills")
        documents = data.get("documents")
        system_prompt = data.get("system_prompt")
        creation_conversation_id = data.get("creation_conversation_id")

        if backend_type not in VALID_BACKENDS:
            return {
                "error": f"backend_type must be one of: {', '.join(VALID_BACKENDS)}"
            }, HTTPStatus.BAD_REQUEST

        # Validate JSON fields if provided as strings
        if goals and isinstance(goals, list):
            goals = json.dumps(goals)
        if skills and isinstance(skills, list):
            skills = json.dumps(skills)
        if documents and isinstance(documents, list):
            documents = json.dumps(documents)

        agent_id = add_agent(
            name=name,
            description=description,
            role=role,
            goals=goals,
            context=context,
            backend_type=backend_type,
            skills=skills,
            documents=documents,
            system_prompt=system_prompt,
            creation_conversation_id=creation_conversation_id,
            creation_status="completed",
        )

        if agent_id:
            return {
                "message": "Agent created",
                "agent_id": agent_id,
                "name": name,
            }, HTTPStatus.CREATED
        else:
            return {"error": "Failed to create agent"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def update_agent_data(agent_id: str, data: dict) -> Tuple[dict, HTTPStatus]:
        """Update an agent."""
        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

        # Convert lists to JSON strings if needed
        goals = data.get("goals")
        skills = data.get("skills")
        documents = data.get("documents")

        if goals and isinstance(goals, list):
            goals = json.dumps(goals)
        if skills and isinstance(skills, list):
            skills = json.dumps(skills)
        if documents and isinstance(documents, list):
            documents = json.dumps(documents)

        success = update_agent(
            agent_id,
            name=data.get("name"),
            description=data.get("description"),
            role=data.get("role"),
            goals=goals if goals else data.get("goals"),
            context=data.get("context"),
            backend_type=data.get("backend_type"),
            enabled=data.get("enabled"),
            skills=skills if skills else data.get("skills"),
            documents=documents if documents else data.get("documents"),
            system_prompt=data.get("system_prompt"),
        )

        if success:
            return {"message": "Agent updated"}, HTTPStatus.OK
        else:
            return {"error": "No changes made"}, HTTPStatus.BAD_REQUEST

    @staticmethod
    def delete_agent_by_id(agent_id: str) -> Tuple[dict, HTTPStatus]:
        """Delete an agent."""
        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

        success = delete_agent(agent_id)
        if success:
            return {"message": "Agent deleted"}, HTTPStatus.OK
        else:
            return {"error": "Failed to delete agent"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def run_agent(agent_id: str, message: str = "") -> Tuple[dict, HTTPStatus]:
        """Execute an agent with the given message."""
        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

        if not agent.get("enabled"):
            return {"error": "Agent is disabled"}, HTTPStatus.BAD_REQUEST

        # Build the full prompt for the agent
        full_prompt = AgentService.build_agent_prompt(agent, message)

        # Create a pseudo-trigger dict for execution service compatibility
        pseudo_trigger = {
            "id": agent_id,
            "name": agent.get("name"),
            "prompt_template": full_prompt,
            "backend_type": agent.get("backend_type", "claude"),
            "skill_command": None,  # Skills are already in the prompt
            # Entity attribution: ensures run_trigger records tokens as agent, not trigger
            "_entity_type": "agent",
            "_entity_id": agent_id,
        }

        # Shared mutable container to capture execution_id from background thread
        result = {"execution_id": None}

        def _run_agent_trigger():
            result["execution_id"] = ExecutionService.run_trigger(
                pseudo_trigger, message, event=None, trigger_type="manual"
            )

        # Run in background thread (run_trigger handles start_execution internally)
        thread = threading.Thread(target=_run_agent_trigger, daemon=True)
        thread.start()
        # Wait briefly for execution_id to be created
        thread.join(timeout=2.0)

        execution_id = result["execution_id"]

        return {
            "message": f"Agent '{agent.get('name')}' started",
            "agent_id": agent_id,
            "execution_id": execution_id,
            "status": "running",
        }, HTTPStatus.ACCEPTED

    @staticmethod
    def build_agent_prompt(agent: dict, message: str) -> str:
        """Build the full prompt for an agent including context, skills, etc."""
        parts = []

        # Add system prompt if present
        if agent.get("system_prompt"):
            parts.append(agent["system_prompt"])

        # Add role
        if agent.get("role"):
            parts.append(f"## Your Role\n{agent['role']}")

        # Add goals
        goals = agent.get("goals")
        if goals:
            try:
                goals_list = json.loads(goals) if isinstance(goals, str) else goals
                if goals_list:
                    goals_text = "\n".join(f"- {g}" for g in goals_list)
                    parts.append(f"## Your Goals\n{goals_text}")
            except json.JSONDecodeError:
                parts.append(f"## Your Goals\n{goals}")

        # Add context
        if agent.get("context"):
            parts.append(f"## Context\n{agent['context']}")

        # Add skills
        skills = agent.get("skills")
        if skills:
            try:
                skills_list = json.loads(skills) if isinstance(skills, str) else skills
                if skills_list:
                    skills_text = ", ".join(skills_list)
                    parts.append(f"## Available Skills\n{skills_text}")
            except json.JSONDecodeError:
                parts.append(f"## Available Skills\n{skills}")

        # Add the user's message
        if message:
            parts.append(f"## Task\n{message}")

        return "\n\n".join(parts)

    @staticmethod
    def _parse_agent_json_fields(agent: dict) -> None:
        """Parse JSON string fields into Python objects."""
        for field in ["goals", "skills", "documents"]:
            if agent.get(field):
                try:
                    agent[field] = json.loads(agent[field])
                except (json.JSONDecodeError, TypeError):
                    pass  # Keep as string if not valid JSON
