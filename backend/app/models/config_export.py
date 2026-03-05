"""Pydantic models for trigger config export/import."""

from typing import Optional

from pydantic import BaseModel, Field


class ConfigExportResponse(BaseModel):
    """Response model for exported trigger configuration."""

    version: str = Field(..., description="Config schema version")
    kind: str = Field(..., description="Resource kind (e.g. 'trigger')")
    metadata: dict = Field(..., description="Trigger metadata (name, type, etc.)")
    spec: dict = Field(..., description="Trigger specification (prompt, paths, etc.)")


class ConfigImportRequest(BaseModel):
    """Request model for importing a trigger configuration."""

    config: str = Field(..., description="YAML or JSON config string")
    format: str = Field("yaml", description="Config format: 'yaml' or 'json'")
    upsert: bool = Field(False, description="If true, update existing trigger by name match")


class ConfigImportResult(BaseModel):
    """Result model for a trigger import operation."""

    trigger_id: str = Field(..., description="ID of the created or updated trigger")
    name: str = Field(..., description="Name of the trigger")
    status: str = Field(..., description="'created' or 'updated'")
    message: str = Field(..., description="Human-readable result message")


class ConfigValidateRequest(BaseModel):
    """Request model for validating a trigger configuration without importing."""

    config: str = Field(..., description="YAML or JSON config string")
    format: str = Field("yaml", description="Config format: 'yaml' or 'json'")


class ConfigFormatQuery(BaseModel):
    """Query params for export format."""

    format: Optional[str] = Field("yaml", description="Export format: 'yaml' or 'json'")
