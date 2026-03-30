"""Tests for the structured tracing system — traces and spans."""

import time

import pytest

from app.db.tracing import (
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


class TestTraces:
    """Trace CRUD operations."""

    def test_create_trace(self, isolated_db):
        trace = create_trace(
            name="Agent Run",
            entity_type="agent",
            entity_id="agent-test01",
        )
        assert trace["id"].startswith("trc-")
        assert trace["name"] == "Agent Run"
        assert trace["entity_type"] == "agent"
        assert trace["status"] == "running"
        assert trace["started_at"] is not None

    def test_create_trace_with_metadata(self, isolated_db):
        trace = create_trace(
            name="Test Trace",
            entity_type="bot",
            entity_id="bot-test",
            execution_id="exec-123",
            input_data={"prompt": "Hello"},
            metadata={"tags": ["test"]},
        )
        assert trace["execution_id"] == "exec-123"
        assert trace["input"]["prompt"] == "Hello"
        assert trace["metadata"]["tags"] == ["test"]

    def test_get_trace(self, isolated_db):
        created = create_trace("T", "agent", "agent-01")
        fetched = get_trace(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_nonexistent_trace(self, isolated_db):
        assert get_trace("trc-nonexistent") is None

    def test_end_trace(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        time.sleep(0.01)  # Ensure measurable duration
        ended = end_trace(
            trace["id"],
            status="completed",
            output_data={"result": "success"},
        )
        assert ended["status"] == "completed"
        assert ended["output"]["result"] == "success"
        assert ended["duration_ms"] is not None
        assert ended["duration_ms"] >= 0
        assert ended["finished_at"] is not None

    def test_end_trace_with_error(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        ended = end_trace(trace["id"], status="error", error_message="Something broke")
        assert ended["status"] == "error"
        assert ended["error_message"] == "Something broke"

    def test_list_traces(self, isolated_db):
        create_trace("T1", "agent", "agent-01")
        create_trace("T2", "agent", "agent-01")
        create_trace("T3", "bot", "bot-01")

        all_traces = list_traces()
        assert len(all_traces) == 3

        agent_traces = list_traces(entity_type="agent")
        assert len(agent_traces) == 2

        bot_traces = list_traces(entity_type="bot", entity_id="bot-01")
        assert len(bot_traces) == 1

    def test_count_traces(self, isolated_db):
        create_trace("T1", "agent", "agent-01")
        create_trace("T2", "agent", "agent-01")
        assert count_traces(entity_type="agent") == 2
        assert count_traces(entity_type="bot") == 0

    def test_delete_trace(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        assert delete_trace(trace["id"]) is True
        assert get_trace(trace["id"]) is None
        assert delete_trace(trace["id"]) is False


class TestSpans:
    """Span CRUD operations."""

    def test_create_span(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        span = create_span(
            trace_id=trace["id"],
            name="Execution",
            span_type="EXECUTION",
        )
        assert span["id"].startswith("span-")
        assert span["trace_id"] == trace["id"]
        assert span["span_type"] == "EXECUTION"
        assert span["status"] == "running"

    def test_create_span_with_parent(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        root = create_span(trace["id"], "Root", "AGENT_RUN")
        child = create_span(trace["id"], "Child", "EXECUTION", parent_span_id=root["id"])
        assert child["parent_span_id"] == root["id"]

    def test_create_span_with_attributes(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        span = create_span(
            trace["id"],
            "Tool",
            "TOOL_CALL",
            input_data={"tool": "search"},
            attributes={"tool_name": "web_search", "success": True},
            metadata={"version": "1.0"},
        )
        assert span["input"]["tool"] == "search"
        assert span["attributes"]["tool_name"] == "web_search"
        assert span["metadata"]["version"] == "1.0"

    def test_end_span(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        span = create_span(trace["id"], "S", "GENERIC")
        time.sleep(0.01)
        ended = end_span(
            span["id"],
            status="completed",
            output_data={"done": True},
        )
        assert ended["status"] == "completed"
        assert ended["output"]["done"] is True
        assert ended["duration_ms"] >= 0

    def test_end_span_merges_attributes(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        span = create_span(trace["id"], "S", "TOOL_CALL", attributes={"tool": "search"})
        ended = end_span(span["id"], attributes={"success": True})
        assert ended["attributes"]["tool"] == "search"
        assert ended["attributes"]["success"] is True

    def test_update_span(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        span = create_span(trace["id"], "S", "GENERIC")
        updated = update_span(span["id"], attributes={"key": "value"})
        assert updated["attributes"]["key"] == "value"

    def test_list_spans(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        create_span(trace["id"], "S1", "AGENT_RUN")
        create_span(trace["id"], "S2", "EXECUTION")
        spans = list_spans(trace["id"])
        assert len(spans) == 2

    def test_span_cascade_delete(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        create_span(trace["id"], "S1", "AGENT_RUN")
        delete_trace(trace["id"])
        assert list_spans(trace["id"]) == []


class TestTraceWithSpans:
    """Trace retrieval with span tree."""

    def test_get_trace_with_spans_tree(self, isolated_db):
        trace = create_trace("T", "agent", "agent-01")
        root = create_span(trace["id"], "Agent Run", "AGENT_RUN")
        create_span(trace["id"], "Prompt Build", "PROMPT_BUILD", parent_span_id=root["id"])
        create_span(trace["id"], "Execution", "EXECUTION", parent_span_id=root["id"])

        result = get_trace_with_spans(trace["id"])
        assert result["span_count"] == 3
        assert len(result["spans"]) == 1  # Only root at top level
        assert result["spans"][0]["name"] == "Agent Run"
        assert len(result["spans"][0]["children"]) == 2


class TestTraceStats:
    """Trace statistics."""

    def test_stats_empty(self, isolated_db):
        stats = get_trace_stats()
        assert stats["total_traces"] == 0

    def test_stats_with_data(self, isolated_db):
        t1 = create_trace("T1", "agent", "agent-01")
        t2 = create_trace("T2", "agent", "agent-01")
        t3 = create_trace("T3", "agent", "agent-01")
        end_trace(t1["id"], "completed")
        end_trace(t2["id"], "completed")
        end_trace(t3["id"], "error", error_message="fail")

        stats = get_trace_stats(entity_type="agent")
        assert stats["total_traces"] == 3
        assert stats["completed"] == 2
        assert stats["errors"] == 1
