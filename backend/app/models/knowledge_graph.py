"""Pydantic models for knowledge graph API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class KGEntityType(str, Enum):
    PERSON = "person"
    CONCEPT = "concept"
    TOOL = "tool"
    PROJECT = "project"
    ORGANIZATION = "organization"
    TECHNOLOGY = "technology"
    OTHER = "other"


class KGEntity(BaseModel):
    id: str
    agent_id: str
    name: str
    entity_type: str
    properties: dict = Field(default_factory=dict)
    mention_count: int = 1
    importance_score: float = 0.5
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None


class KGRelation(BaseModel):
    id: str
    agent_id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: dict = Field(default_factory=dict)
    confidence: float = 0.5
    mention_count: int = 1


class KGSubgraph(BaseModel):
    entities: list[KGEntity] = Field(default_factory=list)
    relations: list[KGRelation] = Field(default_factory=list)


class KGAgentPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")


class KGEntityPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")
    entity_id: str = Field(..., description="KG entity ID")


class KGGraphQuery(BaseModel):
    seed: str = Field(..., description="Seed entity name for graph traversal")
    hops: int = Field(1, ge=1, le=3, description="Traversal depth")


class KGStatsResponse(BaseModel):
    entity_count: int = 0
    relation_count: int = 0
    top_entities: list[dict] = Field(default_factory=list)
    last_extraction: Optional[str] = None
