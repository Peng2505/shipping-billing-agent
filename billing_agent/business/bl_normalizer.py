"""Prefer SCAC+B/L concatenated form when the document literally prints it.

Does not invent prefixes: only upgrades an extracted B/L when the longer
token (e.g. CMDUCHN4053601) already appears in a source block.
"""

from __future__ import annotations

import re

from billing_agent.agents.document_index import DocumentIndex, normalize_for_match
from billing_agent.schemas import EvidenceRef, EvidencedValue


def enrich_bl_with_document_scac(
    index: DocumentIndex,
    bl: EvidencedValue | None,
) -> EvidencedValue | None:
    """If bl is a short body and SCAC+body exists in text, return the full form."""
    if bl is None or not bl.value:
        return bl
    raw = re.sub(r"[\s\-]", "", bl.value).upper()
    if not raw:
        return bl

    best: tuple[str, str, str] | None = None  # full, block_id, quote
    for block_id, block in index.blocks.items():
        text = block.text or ""
        if not text:
            continue
        upper = text.upper()
        # Prefer an explicit token: four-letter SCAC + extracted body (or already-full).
        for m in re.finditer(r"\b([A-Z]{4}" + re.escape(raw) + r")\b", upper):
            full = m.group(1)
            if full == raw:
                continue
            start = m.start(1)
            quote = text[start : start + len(full)] if start + len(full) <= len(text) else full
            if best is None or len(full) > len(best[0]):
                best = (full, block_id, quote)

    if best is None:
        return bl
    full, block_id, quote = best
    evidence = list(bl.evidence) + [EvidenceRef(block_id=block_id, quote=quote)]
    seen: set[tuple[str, str]] = set()
    deduped: list[EvidenceRef] = []
    for ev in evidence:
        key = (ev.block_id, normalize_for_match(ev.quote))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return EvidencedValue(value=full, evidence=deduped)
