"""Product-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class Product(BaseModel):
    """Product entity."""

    id: str = Field(..., pattern=r"^prod-[a-z0-9]+$", examples=["prod-abc123"])
    name: str = Field(..., examples=["Core Platform"])
    description: Optional[str] = None
    status: str = Field(default="active")
    owner_team_id: Optional[str] = None
    owner_team_name: Optional[str] = None
    owner_agent_id: Optional[str] = None
    owner_agent_name: Optional[str] = None
    project_count: int = Field(default=0)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProductProject(BaseModel):
    """Simplified project for product detail."""

    id: str
    name: str
    status: str
    github_repo: Optional[str] = None
    created_at: Optional[str] = None


class ProductDetail(Product):
    """Product with full project list."""

    projects: List[ProductProject] = Field(default_factory=list)


class ProductListResponse(BaseModel):
    """Response for list products endpoint."""

    products: List[Product]


class CreateProductRequest(BaseModel):
    """Request body for creating a product."""

    name: str = Field(..., min_length=1, examples=["Core Platform"])
    description: Optional[str] = None
    status: Optional[str] = Field(default="active")
    owner_team_id: Optional[str] = None
    owner_agent_id: Optional[str] = None


class CreateProductResponse(BaseModel):
    """Response for create product endpoint."""

    message: str
    product: Product


class UpdateProductRequest(BaseModel):
    """Request body for updating a product."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_team_id: Optional[str] = None
    owner_agent_id: Optional[str] = None
