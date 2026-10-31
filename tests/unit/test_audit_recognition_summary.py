"""Audit recognition summary must count EML native blocks."""

from __future__ import annotations

from billing_agent.pipeline import DocumentOutcome, PipelineResult
from billing_agent.schemas import (
    BlockKind,
    DocType,
    ParseStatus,
    ParsedDocument,
    SourceBlock,
    SourceOrigin,
)
from billing_agent.ui.audit_view import _recognition_summary


def _empty_result(outcomes) -> PipelineResult:
    from billing_agent.business.json_builder import build_processing_result

    return PipelineResult(
        outcomes=outcomes,
        existing_bills=[],
        processing=build_processing_result([]),
        delivery_json=[],
        accounting_entity=None,
        demo_mode=False,
        service_status={},
    )


def test_eml_native_blocks_not_labelled_no_text():
    root = ParsedDocument(
        doc_id="D0",
        file_name="mail.eml",
        source_chain=["mail.eml"],
        declared_type=DocType.EML,
        detected_type=DocType.EML,
        sha256="d" * 64,
        size_bytes=10,
        status=ParseStatus.PARSED,
        blocks=[
            SourceBlock(
                block_id="D0:h1", kind=BlockKind.EMAIL_HEADER,
                origin=SourceOrigin.NATIVE, text="Subject: PRE-ALERT",
            ),
            SourceBlock(
                block_id="D0:b2", kind=BlockKind.EMAIL_BODY,
                origin=SourceOrigin.NATIVE, text="Dear LI MBL Telex",
            ),
            SourceBlock(
                block_id="D0:b3", kind=BlockKind.EMAIL_BODY,
                origin=SourceOrigin.NATIVE, text="HTML body text",
            ),
        ],
        children=[
            ParsedDocument(
                doc_id="D1",
                file_name="4055331281 MBL.pdf",
                source_chain=["mail.eml", "4055331281 MBL.pdf"],
                declared_type=DocType.PDF,
                detected_type=DocType.PDF,
                sha256="e" * 64,
                size_bytes=10,
                status=ParseStatus.PARTIAL,
                blocks=[
                    SourceBlock(
                        block_id="D1:t1", kind=BlockKind.PAGE_TEXT,
                        origin=SourceOrigin.TEXT_LAYER, text="MBL text",
                    )
                ],
            )
        ],
    )
    summary = _recognition_summary(_empty_result([DocumentOutcome(document=root)]))
    assert "mail.eml：邮件原文（3 块）" in summary
    assert "MBL.pdf" in summary
    assert "PDF 文本层" in summary
