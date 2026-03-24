"""Tracing API endpoints — traces and spans for observability."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.tracing import (
    count_traces,
    create_span,
    create_trace,
    delete_trace,
    end_span,
    end_trace,
    get_span,
    get_trace,
    get_trace_stats,
    get_trace_with_spans,
    list_spans,
    list_traces,
    update_span,
)
from ..models.tracing import (
    CreateSpanBody,
    CreateTraceBody,
    EndSpanBody,
    EndTraceBody,
    SpanPath,
    TracePath,
    TraceListQuery,
    TraceStatsQuery,
)

tag = Tag(name="tracing", description="Structured tracing — traces and spans for observability")
tracing_bp = APIBlueprint("tracing", __name__, url_prefix="/admin", abp_tags=[tag])


# --- Trace endpoints ---


@tracing_bp.get("/traces")
def list_all_traces(query: TraceListQuery):
    """List traces with optional filters."""
    traces = list_traces(
        entity_type=query.entity_type,
        entity_id=query.entity_id,
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )
    total = count_traces(
        entity_type=query.entity_type,
        entity_id=query.entity_id,
        status=query.status,
    )
    return {"traces": traces, "total": total}, HTTPStatus.OK


@tracing_bp.post("/traces")
def create_new_trace(body: CreateTraceBody):
    """Create a new trace."""
    trace = create_trace(
        name=body.name,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        execution_id=body.execution_id,
        input_data=body.input,
        metadata=body.metadata,
    )
    return trace, HTTPStatus.CREATED


@tracing_bp.get("/traces/stats")
def get_stats(query: TraceStatsQuery):
    """Get aggregate trace statistics."""
    stats = get_trace_stats(
        entity_type=query.entity_type,
        entity_id=query.entity_id,
    )
    return stats, HTTPStatus.OK


@tracing_bp.get("/traces/<trace_id>")
def get_trace_detail(path: TracePath):
    """Get a trace with its full span tree."""
    trace = get_trace_with_spans(path.trace_id)
    if not trace:
        return error_response("NOT_FOUND", "Trace not found", HTTPStatus.NOT_FOUND)
    return trace, HTTPStatus.OK


@tracing_bp.put("/traces/<trace_id>/end")
def end_trace_route(path: TracePath, body: EndTraceBody):
    """End a running trace."""
    trace = get_trace(path.trace_id)
    if not trace:
        return error_response("NOT_FOUND", "Trace not found", HTTPStatus.NOT_FOUND)
    updated = end_trace(
        trace_id=path.trace_id,
        status=body.status,
        output_data=body.output,
        error_message=body.error_message,
    )
    return updated, HTTPStatus.OK


@tracing_bp.delete("/traces/<trace_id>")
def delete_trace_route(path: TracePath):
    """Delete a trace and all its spans."""
    if not delete_trace(path.trace_id):
        return error_response("NOT_FOUND", "Trace not found", HTTPStatus.NOT_FOUND)
    return {"message": f"Trace {path.trace_id} deleted"}, HTTPStatus.OK


# --- Span endpoints ---


@tracing_bp.post("/traces/<trace_id>/spans")
def create_new_span(path: TracePath, body: CreateSpanBody):
    """Create a new span within a trace."""
    trace = get_trace(path.trace_id)
    if not trace:
        return error_response("NOT_FOUND", "Trace not found", HTTPStatus.NOT_FOUND)
    span = create_span(
        trace_id=path.trace_id,
        name=body.name,
        span_type=body.span_type,
        parent_span_id=body.parent_span_id,
        input_data=body.input,
        attributes=body.attributes,
        metadata=body.metadata,
    )
    return span, HTTPStatus.CREATED


@tracing_bp.get("/traces/<trace_id>/spans")
def list_trace_spans(path: TracePath):
    """List all spans in a trace."""
    trace = get_trace(path.trace_id)
    if not trace:
        return error_response("NOT_FOUND", "Trace not found", HTTPStatus.NOT_FOUND)
    spans = list_spans(path.trace_id)
    return {"spans": spans, "count": len(spans)}, HTTPStatus.OK


@tracing_bp.get("/traces/<trace_id>/spans/<span_id>")
def get_span_detail(path: SpanPath):
    """Get a single span."""
    span = get_span(path.span_id)
    if not span or span.get("trace_id") != path.trace_id:
        return error_response("NOT_FOUND", "Span not found", HTTPStatus.NOT_FOUND)
    return span, HTTPStatus.OK


@tracing_bp.put("/traces/<trace_id>/spans/<span_id>/end")
def end_span_route(path: SpanPath, body: EndSpanBody):
    """End a running span."""
    span = get_span(path.span_id)
    if not span or span.get("trace_id") != path.trace_id:
        return error_response("NOT_FOUND", "Span not found", HTTPStatus.NOT_FOUND)
    updated = end_span(
        span_id=path.span_id,
        status=body.status,
        output_data=body.output,
        error_message=body.error_message,
        attributes=body.attributes,
    )
    return updated, HTTPStatus.OK
