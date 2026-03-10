"""SuperAgent document management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import (
    add_super_agent_document,
    delete_super_agent_document,
    get_super_agent_document,
    get_super_agent_documents,
    update_super_agent_document,
)
from .super_agents import SuperAgentPath

tag = Tag(name="super-agent-documents", description="SuperAgent document operations")
super_agent_documents_bp = APIBlueprint(
    "super_agent_documents", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class DocumentPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    doc_id: int = Field(..., description="Document ID")


@super_agent_documents_bp.get("/<super_agent_id>/documents")
def list_documents(path: SuperAgentPath):
    """List all documents for a super agent."""
    documents = get_super_agent_documents(path.super_agent_id)
    return {"documents": documents}, HTTPStatus.OK


@super_agent_documents_bp.post("/<super_agent_id>/documents")
def create_document(path: SuperAgentPath):
    """Create a document for a super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    doc_type = data.get("doc_type")
    if not doc_type:
        return error_response("BAD_REQUEST", "doc_type is required", HTTPStatus.BAD_REQUEST)

    title = data.get("title")
    if not title:
        return error_response("BAD_REQUEST", "title is required", HTTPStatus.BAD_REQUEST)

    doc_id = add_super_agent_document(
        super_agent_id=path.super_agent_id,
        doc_type=doc_type,
        title=title,
        content=data.get("content", ""),
    )
    if doc_id is None:
        return error_response(
            "BAD_REQUEST", "Invalid doc_type or failed to create document", HTTPStatus.BAD_REQUEST
        )

    return {"message": "Document created", "document_id": doc_id}, HTTPStatus.CREATED


@super_agent_documents_bp.get("/<super_agent_id>/documents/<int:doc_id>")
def get_document_endpoint(path: DocumentPath):
    """Get a document by ID."""
    doc = get_super_agent_document(path.doc_id)
    if not doc:
        return error_response("NOT_FOUND", "Document not found", HTTPStatus.NOT_FOUND)
    return doc, HTTPStatus.OK


@super_agent_documents_bp.put("/<super_agent_id>/documents/<int:doc_id>")
def update_document_endpoint(path: DocumentPath):
    """Update a document."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    if not update_super_agent_document(
        path.doc_id,
        title=data.get("title"),
        content=data.get("content"),
    ):
        return error_response(
            "NOT_FOUND", "Document not found or no changes made", HTTPStatus.NOT_FOUND
        )

    return {"message": "Document updated"}, HTTPStatus.OK


@super_agent_documents_bp.delete("/<super_agent_id>/documents/<int:doc_id>")
def delete_document_endpoint(path: DocumentPath):
    """Delete a document."""
    if not delete_super_agent_document(path.doc_id):
        return error_response("NOT_FOUND", "Document not found", HTTPStatus.NOT_FOUND)
    return {"message": "Document deleted"}, HTTPStatus.OK
