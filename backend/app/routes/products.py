"""Product management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_product,
    count_products,
    delete_product,
    get_all_products,
    get_product,
    get_product_detail,
    update_product,
)
from ..models.common import PaginationQuery

tag = Tag(name="products", description="Product management operations")
products_bp = APIBlueprint("products", __name__, url_prefix="/admin/products", abp_tags=[tag])


class ProductPath(BaseModel):
    product_id: str = Field(..., description="Product ID")


@products_bp.get("/")
def list_products(query: PaginationQuery):
    """List all products with project counts and optional pagination."""
    total_count = count_products()
    products = get_all_products(limit=query.limit, offset=query.offset or 0)
    return {"products": products, "total_count": total_count}, HTTPStatus.OK


@products_bp.post("/")
def create_product():
    """Create a new product."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    product_id = add_product(
        name=name,
        description=data.get("description"),
        status=data.get("status", "active"),
        owner_team_id=data.get("owner_team_id"),
    )
    if not product_id:
        return {"error": "Failed to create product"}, HTTPStatus.INTERNAL_SERVER_ERROR

    product = get_product(product_id)
    return {"message": "Product created", "product": product}, HTTPStatus.CREATED


@products_bp.get("/<product_id>")
def get_product_detail_endpoint(path: ProductPath):
    """Get product details with projects."""
    product = get_product_detail(path.product_id)
    if not product:
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND
    return product, HTTPStatus.OK


@products_bp.put("/<product_id>")
def update_product_endpoint(path: ProductPath):
    """Update a product."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_product(
        path.product_id,
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        owner_team_id=data.get("owner_team_id"),
    ):
        return {"error": "Product not found or no changes made"}, HTTPStatus.NOT_FOUND

    product = get_product(path.product_id)
    return product, HTTPStatus.OK


@products_bp.delete("/<product_id>")
def delete_product_endpoint(path: ProductPath):
    """Delete a product."""
    if not delete_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Product deleted"}, HTTPStatus.OK
