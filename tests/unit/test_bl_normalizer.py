"""SCAC + B/L enrichment from document evidence."""

from __future__ import annotations

from billing_agent.agents.document_index import DocumentIndex
from billing_agent.business.bl_normalizer import enrich_bl_with_document_scac
from billing_agent.schemas import (
    BlockKind,
    DocType,
    EvidenceRef,
    EvidencedValue,
    ParseStatus,
    ParsedDocument,
    SourceBlock,
    SourceOrigin,
)


def _doc(text: str) -> DocumentIndex:
    doc = ParsedDocument(
        doc_id="D0",
        file_name="PDF示例账单1.pdf",
        source_chain=["PDF示例账单1.pdf"],
        declared_type=DocType.PDF,
        detected_type=DocType.PDF,
        sha256="c" * 64,
        size_bytes=10,
        status=ParseStatus.PARSED,
        blocks=[
            SourceBlock(
                block_id="D0:t1",
                kind=BlockKind.PAGE_TEXT,
                origin=SourceOrigin.TEXT_LAYER,
                text=text,
            )
        ],
    )
    return DocumentIndex.from_document(doc)


def test_enrich_chn_to_cmduchn_when_full_token_present():
    index = _doc("SCAC\nCMDU\nB/L #\nCHN4053601\nMaster: CMDUCHN4053601\n")
    bl = EvidencedValue(
        value="CHN4053601",
        evidence=[EvidenceRef(block_id="D0:t1", quote="CHN4053601")],
    )
    out = enrich_bl_with_document_scac(index, bl)
    assert out is not None
    assert out.value == "CMDUCHN4053601"
    assert any("CMDUCHN4053601" in (ev.quote or "") for ev in out.evidence)


def test_enrich_does_not_invent_scac_without_full_token():
    index = _doc("SCAC\nCMDU\nB/L #\nCHN4053601\n")
    bl = EvidencedValue(
        value="CHN4053601",
        evidence=[EvidenceRef(block_id="D0:t1", quote="CHN4053601")],
    )
    out = enrich_bl_with_document_scac(index, bl)
    assert out is not None
    assert out.value == "CHN4053601"
