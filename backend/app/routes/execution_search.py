"""Execution log search API endpoints using FTS5 full-text search."""

from flask_openapi3 import APIBlueprint, Tag

from ..models.execution_search import SearchQuery, SearchResponse, SearchResult, SearchStats
from ..services.execution_search_service import ExecutionSearchService

tag = Tag(name="execution-search", description="Full-text search over execution logs")
execution_search_bp = APIBlueprint(
    "execution_search", __name__, url_prefix="/admin", abp_tags=[tag]
)


@execution_search_bp.get("/execution-search")
def search_execution_logs(query: SearchQuery):
    """Search execution logs using natural language queries with BM25 ranking."""
    results = ExecutionSearchService.search(
        query=query.q,
        limit=query.limit,
        trigger_id=query.trigger_id,
    )
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        total=len(results),
        query=query.q,
    ).model_dump()


@execution_search_bp.get("/execution-search/stats")
def search_stats():
    """Get statistics about the execution log search index."""
    stats = ExecutionSearchService.get_search_stats()
    return SearchStats(**stats).model_dump()
