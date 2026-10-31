"""Pydantic models shared across the pipeline.

Phase 1 covers the parsing layer (ParsedDocument and friends). Extraction and
business models are added in later phases.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocType(str, Enum):
    EML = "eml"
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    TIFF = "tiff"
    XLSX = "xlsx"
    XLS = "xls"
    DOCX = "docx"
    DOC = "doc"
    JSON = "json"
    UNKNOWN = "unknown"


IMAGE_TYPES = {DocType.PNG, DocType.JPG, DocType.TIFF}
OCR_TYPES = IMAGE_TYPES | {DocType.PDF}


class SourceOrigin(str, Enum):
    NATIVE = "native"          # structure of the file itself (mail body, cells, paragraphs, JSON)
    TEXT_LAYER = "text_layer"  # embedded PDF text layer; this is NOT OCR
    OCR_API = "ocr_api"        # real response of the assignment OCR API


class BlockKind(str, Enum):
    EMAIL_HEADER = "email_header"
    EMAIL_BODY = "email_body"
    PAGE_TEXT = "page_text"
    TABLE = "table"
    PARAGRAPHS = "paragraphs"
    SHEET = "sheet"
    JSON = "json"
    OCR_RESULT = "ocr_result"


class ParseStatus(str, Enum):
    PARSED = "PARSED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    SKIPPED = "SKIPPED"


class OcrStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SourceBlock(BaseModel):
    block_id: str
    kind: BlockKind
    origin: SourceOrigin
    page: int | None = None
    text: str = ""
    table: list[list[str]] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EmailMeta(BaseModel):
    subject: str | None = None
    sender: str | None = None
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    date: str | None = None
    message_id: str | None = None
    body_plain_present: bool = False
    body_html_present: bool = False


class OcrOutcome(BaseModel):
    status: OcrStatus
    endpoint: str | None = None
    task: str | None = None
    task_type: str | None = None
    storage_provider: str | None = None
    object_key_hash: str | None = None
    http_status: int | None = None
    elapsed_ms: int | None = None
    requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    raw_response: dict[str, Any] | None = None


class ParsedDocument(BaseModel):
    doc_id: str
    file_name: str
    source_chain: list[str]
    declared_type: DocType
    detected_type: DocType
    declared_mime: str | None = None
    sha256: str
    size_bytes: int
    status: ParseStatus = ParseStatus.PARSED
    email: EmailMeta | None = None
    blocks: list[SourceBlock] = Field(default_factory=list)
    ocr: OcrOutcome | None = None
    children: list[ParsedDocument] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def next_block_id(self, prefix: str) -> str:
        return f"{self.doc_id}:{prefix}{len(self.blocks) + 1}"

    def add_block(
        self,
        kind: BlockKind,
        origin: SourceOrigin,
        prefix: str,
        text: str = "",
        *,
        page: int | None = None,
        table: list[list[str]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> SourceBlock:
        block = SourceBlock(
            block_id=self.next_block_id(prefix),
            kind=kind,
            origin=origin,
            page=page,
            text=text,
            table=table,
            meta=meta or {},
        )
        self.blocks.append(block)
        return block

    def iter_documents(self) -> Iterator[ParsedDocument]:
        """Depth-first iteration over this document and every nested attachment."""
        yield self
        for child in self.children:
            yield from child.iter_documents()

    def blocks_by_origin(self, origin: SourceOrigin) -> list[SourceBlock]:
        return [b for b in self.blocks if b.origin == origin]

    def text_by_origin(self, origin: SourceOrigin) -> str:
        return "\n".join(b.text for b in self.blocks_by_origin(origin) if b.text)


ParsedDocument.model_rebuild()


# ---------------------------------------------------------------------------
# Phase 2: LLM extraction models
# ---------------------------------------------------------------------------


class ChargeNature(str, Enum):
    ACTUAL = "actual"
    CONDITIONAL = "conditional"
    INFORMATIONAL = "informational"
    TOTAL = "total"
    TAX = "tax"
    WAIVED = "waived"


class EvidenceRef(BaseModel):
    """Pointer from an extracted value back into a SourceBlock."""

    block_id: str
    quote: str


class EvidencedValue(BaseModel):
    value: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ExtractedCharge(BaseModel):
    raw_name: str
    nature: ChargeNature
    amount: str | None = None
    currency: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    payment_term_raw: str | None = None
    charge_code: str | None = None
    line_hint: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    notes: str | None = None


class ChangeRequest(BaseModel):
    field: str
    new_value: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Structured output produced by the extraction Agent (pre-grounding)."""

    document_type: EvidencedValue | None = None
    reference_no: EvidencedValue | None = None
    document_date_raw: EvidencedValue | None = None
    issuer: EvidencedValue | None = None
    recipient: EvidencedValue | None = None
    bl_no: EvidencedValue | None = None
    booking_no: EvidencedValue | None = None
    house_bl_no: EvidencedValue | None = None
    container_nos: list[EvidencedValue] = Field(default_factory=list)
    charges: list[ExtractedCharge] = Field(default_factory=list)
    excluded: list[ExtractedCharge] = Field(default_factory=list)
    document_total: EvidencedValue | None = None
    currency: EvidencedValue | None = None
    payment_term_raw: EvidencedValue | None = None
    change_requests: list[ChangeRequest] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GroundingIssue(BaseModel):
    path: str
    reason: str
    block_id: str | None = None
    quote: str | None = None


class GroundedExtraction(BaseModel):
    """ExtractionResult after Python evidence verification and OCR charge filtering."""

    result: ExtractionResult
    issues: list[GroundingIssue] = Field(default_factory=list)
    actual_charges: list[ExtractedCharge] = Field(default_factory=list)
    excluded_charges: list[ExtractedCharge] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    model_name: str | None = None
    structured_strategy: str | None = None
    elapsed_ms: int | None = None


# ---------------------------------------------------------------------------
# Phase 3: business decision models
# ---------------------------------------------------------------------------


class OperationType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"
    PENDING_REVIEW = "PENDING_REVIEW"


class PostingType(str, Enum):
    AR = "AR"
    AP = "AP"


class BillRecord(BaseModel):
    """Existing or proposed bill line. Delivery JSON uses a subset of these fields."""

    bill_id: str | None = None
    document_type: str | None = None
    reference_no: str | None = None
    document_date: str | None = None
    issuer: str | None = None
    recipient: str | None = None
    bl_no: str | None = None
    booking_no: str | None = None
    house_bl_no: str | None = None
    container_nos: list[str] = Field(default_factory=list)
    charge_item: str | None = None
    charge_item_raw: str | None = None
    amount: str | None = None  # decimal string for precision; serialized to number on output
    currency: str | None = None
    payment_term: str | None = None
    payment_term_raw: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    accounting_entity: str | None = None
    posting_type: str | None = None
    fingerprint: str | None = None
    synthetic: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class MatchLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    NONE = "NONE"


class MatchResult(BaseModel):
    level: MatchLevel
    status: str  # matched | ambiguous | none | skipped_chain
    bill_id: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None


class FieldChange(BaseModel):
    field: str
    old_value: Any = None
    new_value: Any = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    severity: str  # error | warning | info
    message: str
    path: str | None = None


class Decision(BaseModel):
    operation: OperationType
    bill: BillRecord
    matched_bill: BillRecord | None = None
    match: MatchResult | None = None
    changes: list[FieldChange] = Field(default_factory=list)
    posting_type: str | None = None
    posting_reason: list[str] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    audit_reasons: list[str] = Field(default_factory=list)
    fingerprint: str | None = None


class OutputRecord(BaseModel):
    """Strict delivery JSON shape (6 top-level blocks)."""

    operation: str
    document_info: dict[str, Any]
    transaction_party: dict[str, Any]
    charge_details: dict[str, Any]
    financial_attributes: dict[str, Any]
    audit_trail: dict[str, Any]


class ProcessingResult(BaseModel):
    decisions: list[Decision] = Field(default_factory=list)
    output_records: list[OutputRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
