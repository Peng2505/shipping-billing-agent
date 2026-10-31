"""In-memory index of SourceBlocks for Agent tools and evidence grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from billing_agent.schemas import ParsedDocument, SourceBlock, SourceOrigin


def normalize_for_match(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


@dataclass
class DocumentIndex:
    root: ParsedDocument
    blocks: dict[str, SourceBlock] = field(default_factory=dict)
    block_docs: dict[str, ParsedDocument] = field(default_factory=dict)
    block_order: list[str] = field(default_factory=list)

    @classmethod
    def from_document(cls, root: ParsedDocument) -> DocumentIndex:
        index = cls(root=root)
        for doc in root.iter_documents():
            for block in doc.blocks:
                index.blocks[block.block_id] = block
                index.block_docs[block.block_id] = doc
                index.block_order.append(block.block_id)
        return index

    def get(self, block_id: str) -> SourceBlock | None:
        return self.blocks.get(block_id)

    def surrounding_text(self, block_id: str, radius: int = 1) -> str:
        if block_id not in self.blocks:
            return ""
        pos = self.block_order.index(block_id)
        start = max(0, pos - radius)
        end = min(len(self.block_order), pos + radius + 1)
        parts = []
        for bid in self.block_order[start:end]:
            block = self.blocks[bid]
            parts.append(block.text or "")
        return "\n".join(parts)

    def search(self, query: str, limit: int = 8) -> list[dict]:
        q = normalize_for_match(query)
        if not q:
            return []
        hits = []
        for block_id in self.block_order:
            block = self.blocks[block_id]
            hay = normalize_for_match(block.text)
            if q not in hay:
                continue
            # return a short window around the first match
            raw = block.text
            lower = raw.lower()
            # best-effort locate ignoring whitespace differences
            idx = lower.find(query.lower().strip()[:40]) if query.strip() else -1
            if idx < 0:
                snippet = raw[:240]
            else:
                left = max(0, idx - 80)
                right = min(len(raw), idx + len(query) + 80)
                snippet = raw[left:right]
            doc = self.block_docs[block_id]
            hits.append({
                "block_id": block_id,
                "kind": block.kind.value,
                "origin": block.origin.value,
                "page": block.page,
                "source_chain": doc.source_chain,
                "snippet": snippet,
            })
            if len(hits) >= limit:
                break
        return hits

    def verify_quote(self, block_id: str, quote: str) -> dict:
        block = self.blocks.get(block_id)
        if block is None:
            return {"ok": False, "reason": "unknown_block_id", "block_id": block_id}
        if not quote or not quote.strip():
            return {"ok": False, "reason": "empty_quote", "block_id": block_id}
        if normalize_for_match(quote) in normalize_for_match(block.text):
            return {"ok": True, "block_id": block_id, "origin": block.origin.value}
        # allow quote to match joined table cell text
        if block.table:
            flat = " ".join(" ".join(row) for row in block.table)
            if normalize_for_match(quote) in normalize_for_match(flat):
                return {"ok": True, "block_id": block_id, "origin": block.origin.value}
        return {
            "ok": False,
            "reason": "quote_not_found",
            "block_id": block_id,
            "origin": block.origin.value,
        }

    def inventory(self) -> list[dict]:
        rows = []
        for block_id in self.block_order:
            block = self.blocks[block_id]
            doc = self.block_docs[block_id]
            rows.append({
                "block_id": block_id,
                "kind": block.kind.value,
                "origin": block.origin.value,
                "page": block.page,
                "chars": len(block.text or ""),
                "source_chain": " > ".join(doc.source_chain),
            })
        return rows

    def ocr_only(self) -> bool:
        origins = {self.blocks[b].origin for b in self.block_order}
        return origins == {SourceOrigin.OCR_API} or (
            SourceOrigin.OCR_API in origins and SourceOrigin.NATIVE not in origins
            and SourceOrigin.TEXT_LAYER not in origins
        )
