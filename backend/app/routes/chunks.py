"""Chunked bot execution API endpoints with merge/dedup.

Splits large content into chunks, dispatches per-chunk bot invocations
in background threads, and serves merged/deduplicated results.

Per 08-RESEARCH.md Anti-Pattern: Never process chunks sequentially in
the request thread -- background threads with Semaphore(3) concurrency.
"""

import logging
import threading
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..db.chunk_results import (
    create_chunk_result,
    create_chunked_execution,
    get_chunk_results,
    get_chunked_execution,
    increment_completed_chunks,
    update_chunk_result,
    update_chunked_execution_status,
)
from ..db.triggers import get_trigger
from ..services.chunk_service import ChunkService

logger = logging.getLogger(__name__)

tag = Tag(name="chunks", description="Chunked bot execution with merge/dedup")
chunks_bp = APIBlueprint("chunks", __name__, url_prefix="/admin", abp_tags=[tag])

# Semaphore to limit concurrent chunk invocations (avoid overwhelming AI backend)
_chunk_semaphore = threading.Semaphore(3)


class BotPath(BaseModel):
    bot_id: str = Field(..., description="Bot/trigger ID")


class ChunkedExecutionPath(BaseModel):
    chunked_execution_id: str = Field(..., description="Chunked execution ID")


def _process_chunk(
    chunked_execution_id: str,
    chunk_result_id: str,
    chunk_content: str,
    total_chunks: int,
    bot_id: str,
):
    """Process a single chunk in a background thread.

    Acquires the semaphore to limit concurrency. On completion, updates
    the chunk result and checks if all chunks are done to trigger merge.
    """
    try:
        with _chunk_semaphore:
            # In a full implementation, this would invoke the bot via
            # ExecutionService.run_trigger() with chunk_content as the
            # prompt context. For now, we store the chunk as processed
            # since the actual bot invocation depends on the specific
            # bot configuration and CLI tool availability.
            #
            # The bot_output will be populated by the actual execution
            # pipeline when integrated with ExecutionService.
            bot_output = ""
            token_count = len(chunk_content) // 4  # Rough estimate

            try:
                from ..services.execution_service import ExecutionService

                bot = get_trigger(bot_id)
                if bot:
                    # Build a minimal prompt from chunk content
                    execution_id = ExecutionService.run_trigger(
                        trigger=bot,
                        message_text=chunk_content,
                        trigger_type="manual",
                    )
                    if execution_id:
                        # Wait for execution to complete and get output
                        import time

                        for _ in range(120):  # 2 min max wait
                            from ..services.execution_log_service import (
                                ExecutionLogService,
                            )

                            if not ExecutionLogService.is_running(execution_id):
                                log = ExecutionLogService.get_log(execution_id)
                                if log:
                                    bot_output = log.get("output", "")
                                    token_count = log.get("token_count", token_count)
                                break
                            time.sleep(1)
            except Exception as e:
                logger.warning("Bot execution for chunk %s failed: %s", chunk_result_id, e)
                bot_output = f"Error processing chunk: {e}"

            # Update chunk result
            update_chunk_result(chunk_result_id, bot_output, token_count)

    except Exception as e:
        logger.error("Chunk processing error for %s: %s", chunk_result_id, e)
        update_chunk_result(chunk_result_id, f"Error: {e}", 0, status="failed")

    # Check if all chunks complete
    try:
        completed = increment_completed_chunks(chunked_execution_id)
        if completed >= total_chunks:
            _finalize_chunked_execution(chunked_execution_id)
    except Exception as e:
        logger.error("Failed to check chunk completion: %s", e)


def _finalize_chunked_execution(chunked_execution_id: str):
    """Merge all chunk results when all chunks are complete."""
    try:
        results = get_chunk_results(chunked_execution_id)
        chunk_dicts = [
            {
                "chunk_index": r["chunk_index"],
                "bot_output": r.get("bot_output", ""),
                "chunk_content": r.get("chunk_content", ""),
                "token_count": r.get("token_count", 0),
            }
            for r in results
        ]

        merged = ChunkService.merge_chunk_results(chunk_dicts)

        update_chunked_execution_status(
            chunked_execution_id,
            status="completed",
            merged_output=merged["merged_output"],
            unique_findings_count=len(merged["unique_findings"]),
            duplicate_count=merged["duplicate_count"],
        )
        logger.info(
            "Chunked execution %s completed: %d unique findings, %d duplicates removed",
            chunked_execution_id,
            len(merged["unique_findings"]),
            merged["duplicate_count"],
        )
    except Exception as e:
        logger.error(
            "Failed to finalize chunked execution %s: %s",
            chunked_execution_id,
            e,
        )
        update_chunked_execution_status(chunked_execution_id, status="failed")


@chunks_bp.post("/bots/<bot_id>/run-chunked")
def run_chunked(path: BotPath):
    """Run a bot against chunked content with merge/dedup.

    Splits content via ChunkService, creates DB records for tracking,
    and dispatches per-chunk bot invocations in background threads.
    Returns immediately with the chunked execution ID.
    """
    bot = get_trigger(path.bot_id)
    if not bot:
        return {"error": "Bot not found"}, HTTPStatus.NOT_FOUND

    body = request.get_json(silent=True) or {}
    content = body.get("content")
    if not content:
        return {"error": "Missing required field: content"}, HTTPStatus.BAD_REQUEST

    max_chunk_chars = body.get("max_chunk_chars")

    # Split content into chunks
    chunks = ChunkService.chunk_code(content, max_chars=max_chunk_chars)

    # Create chunked execution record
    chunked_execution_id = create_chunked_execution(path.bot_id, len(chunks))
    if not chunked_execution_id:
        return {"error": "Failed to create chunked execution"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Create chunk result records and spawn background threads
    for idx, chunk_content in enumerate(chunks):
        chunk_result_id = create_chunk_result(chunked_execution_id, idx, chunk_content)
        if chunk_result_id:
            thread = threading.Thread(
                target=_process_chunk,
                args=(
                    chunked_execution_id,
                    chunk_result_id,
                    chunk_content,
                    len(chunks),
                    path.bot_id,
                ),
                daemon=True,
            )
            thread.start()

    return {
        "chunked_execution_id": chunked_execution_id,
        "bot_id": path.bot_id,
        "total_chunks": len(chunks),
        "status": "processing",
    }, HTTPStatus.CREATED


@chunks_bp.get("/chunked-executions/<chunked_execution_id>")
def get_chunked_execution_status(path: ChunkedExecutionPath):
    """Get the status of a chunked execution.

    Returns the execution details including completed chunk count and status.
    """
    execution = get_chunked_execution(path.chunked_execution_id)
    if not execution:
        return {"error": "Chunked execution not found"}, HTTPStatus.NOT_FOUND
    return execution, HTTPStatus.OK


@chunks_bp.get("/chunked-executions/<chunked_execution_id>/results")
def get_chunked_execution_results(path: ChunkedExecutionPath):
    """Get merged/deduplicated results for a chunked execution.

    Returns the merged output with unique findings and deduplication stats.
    Only available after all chunks have completed processing.
    """
    execution = get_chunked_execution(path.chunked_execution_id)
    if not execution:
        return {"error": "Chunked execution not found"}, HTTPStatus.NOT_FOUND

    if execution["status"] not in ("completed", "failed"):
        return {
            "error": "Chunked execution is still processing",
            "status": execution["status"],
            "completed_chunks": execution["completed_chunks"],
            "total_chunks": execution["total_chunks"],
        }, HTTPStatus.CONFLICT

    # Get individual chunk results
    results = get_chunk_results(path.chunked_execution_id)

    return {
        "chunked_execution_id": path.chunked_execution_id,
        "total_chunks": execution["total_chunks"],
        "unique_findings_count": execution.get("unique_findings_count", 0),
        "duplicate_count": execution.get("duplicate_count", 0),
        "merged_output": execution.get("merged_output", ""),
        "status": execution["status"],
        "chunk_results": results,
    }, HTTPStatus.OK
