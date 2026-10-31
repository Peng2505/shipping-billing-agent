"""Generic JSON input. Existing-bill semantics are validated later by business.bill_store."""

from __future__ import annotations

import json

from billing_agent.schemas import BlockKind, ParsedDocument, SourceOrigin


def parse(doc: ParsedDocument, data: bytes, ctx) -> None:
    obj = json.loads(data.decode("utf-8-sig"))
    doc.meta["top_level"] = type(obj).__name__
    if isinstance(obj, list):
        doc.meta["record_count"] = len(obj)
        doc.meta["synthetic"] = any(isinstance(r, dict) and r.get("_synthetic") is True for r in obj)
    elif isinstance(obj, dict):
        doc.meta["synthetic"] = obj.get("_synthetic") is True
    doc.add_block(
        BlockKind.JSON, SourceOrigin.NATIVE, "j",
        json.dumps(obj, ensure_ascii=False, indent=2),
    )
