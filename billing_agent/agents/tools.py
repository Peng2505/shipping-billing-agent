"""Read-only Agent tools. Each tool reaches the current DocumentIndex via ToolRuntime context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from billing_agent.agents.document_index import DocumentIndex
from billing_agent.business.charge_normalizer import lookup_alias


@dataclass
class ExtractionContext:
    """Runtime context injected into create_agent(...).invoke(..., context=...)."""

    index: DocumentIndex
    tool_trace: list


def _index(runtime: ToolRuntime[ExtractionContext]) -> DocumentIndex:
    return runtime.context.index


def _trace(runtime: ToolRuntime[ExtractionContext], name: str, args: dict, result) -> None:
    runtime.context.tool_trace.append({"tool": name, "args": args, "result_preview": str(result)[:500]})


@tool
def list_blocks(
    runtime: ToolRuntime[ExtractionContext],
) -> str:
    """List every source block available in the current document tree.

    Use this first to see block_ids, origins (native / text_layer / ocr_api),
    and which file each block came from (including e-mail attachments).
    """
    rows = _index(runtime).inventory()
    _trace(runtime, "list_blocks", {}, f"{len(rows)} blocks")
    return json.dumps(rows, ensure_ascii=False)


@tool
def search_document(
    query: Annotated[str, Field(description="Keyword or short phrase to find in the document")],
    runtime: ToolRuntime[ExtractionContext],
    limit: Annotated[int, Field(description="Max hits to return", ge=1, le=20)] = 8,
) -> str:
    """Search all source blocks for a keyword or phrase and return matching snippets with block_ids."""
    hits = _index(runtime).search(query, limit=limit)
    _trace(runtime, "search_document", {"query": query, "limit": limit}, hits)
    if not hits:
        return json.dumps({"hits": [], "message": "No matches"}, ensure_ascii=False)
    return json.dumps({"hits": hits}, ensure_ascii=False)


@tool
def get_block(
    block_id: Annotated[str, Field(description="Block id from list_blocks or search_document")],
    runtime: ToolRuntime[ExtractionContext],
) -> str:
    """Return the full text (and table, if any) of one source block."""
    block = _index(runtime).get(block_id)
    if block is None:
        result = {"error": "unknown_block_id", "block_id": block_id}
        _trace(runtime, "get_block", {"block_id": block_id}, result)
        return json.dumps(result, ensure_ascii=False)
    result = {
        "block_id": block.block_id,
        "kind": block.kind.value,
        "origin": block.origin.value,
        "page": block.page,
        "text": block.text,
        "table": block.table,
        "meta": block.meta,
    }
    _trace(runtime, "get_block", {"block_id": block_id}, f"chars={len(block.text)}")
    return json.dumps(result, ensure_ascii=False)


@tool
def lookup_charge_alias(
    raw_name: Annotated[str, Field(description="Original charge name as printed on the document")],
    runtime: ToolRuntime[ExtractionContext],
) -> str:
    """Look up the deterministic charge-name dictionary. Returns MAPPED or UNKNOWN.

    Does not invent mappings. Context rules (e.g. Carrier Free H/C) are applied
    later by Python and must still be considered by the agent when classifying nature.
    """
    result = lookup_alias(raw_name)
    _trace(runtime, "lookup_charge_alias", {"raw_name": raw_name}, result)
    return json.dumps(result, ensure_ascii=False)


@tool
def verify_evidence(
    block_id: Annotated[str, Field(description="Source block id")],
    quote: Annotated[str, Field(description="Exact or near-exact quote that must appear in the block")],
    runtime: ToolRuntime[ExtractionContext],
) -> str:
    """Verify that a quote actually appears in the given source block before citing it as evidence."""
    result = _index(runtime).verify_quote(block_id, quote)
    _trace(runtime, "verify_evidence", {"block_id": block_id, "quote": quote[:80]}, result)
    return json.dumps(result, ensure_ascii=False)


EXTRACTION_TOOLS = [list_blocks, search_document, get_block, lookup_charge_alias, verify_evidence]
