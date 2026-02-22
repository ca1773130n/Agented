"""Marketplace-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class Marketplace(BaseModel):
    """Plugin marketplace entity."""

    id: str = Field(..., pattern=r"^mkt-[a-z0-9]+$", examples=["mkt-abc123"])
    name: str = Field(..., examples=["Harness Plugins"])
    url: str = Field(..., examples=["https://github.com/org/repo"])
    type: str = Field(default="git")  # git, http, local
    is_default: bool = Field(default=False)
    created_at: Optional[str] = None


class MarketplacePlugin(BaseModel):
    """Plugin installed from a marketplace."""

    id: str = Field(..., examples=["mktp-abc123"])
    marketplace_id: str
    plugin_id: Optional[str] = None
    remote_name: str = Field(..., examples=["my-plugin"])
    version: Optional[str] = None
    installed_at: Optional[str] = None


class MarketplaceListResponse(BaseModel):
    """Response for list marketplaces endpoint."""

    marketplaces: List[Marketplace]


class CreateMarketplaceRequest(BaseModel):
    """Request body for creating a marketplace."""

    name: str = Field(..., min_length=1, examples=["Harness Plugins"])
    url: str = Field(..., min_length=1, examples=["https://github.com/org/repo"])
    type: str = Field(default="git")
    is_default: bool = Field(default=False)


class CreateMarketplaceResponse(BaseModel):
    """Response for create marketplace endpoint."""

    message: str
    marketplace: Marketplace


class UpdateMarketplaceRequest(BaseModel):
    """Request body for updating a marketplace."""

    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    is_default: Optional[bool] = None


class MarketplacePluginsResponse(BaseModel):
    """Response for list marketplace plugins endpoint."""

    plugins: List[MarketplacePlugin]


class InstallPluginRequest(BaseModel):
    """Request body for installing a plugin from marketplace."""

    remote_name: str = Field(..., min_length=1)
    version: Optional[str] = None


class InstallPluginResponse(BaseModel):
    """Response for install plugin endpoint."""

    message: str
    plugin: MarketplacePlugin
