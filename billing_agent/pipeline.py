"""End-to-end orchestration: parse → extract → decide → JSON.

UI and CLI call this module only; they do not reimplement business rules.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from billing_agent.agents.extraction_agent import ExtractionAgent, ExtractionAgentError
from billing_agent.business.bill_store import BillStoreError, load_bills_json, load_bills_path
from billing_agent.business.decision_engine import decide_for_document
from billing_agent.business.json_builder import build_processing_result, to_delivery_json
from billing_agent.business.payment_direction import extract_payment_direction
from billing_agent.config import Settings, load_settings
from billing_agent.parsers.dispatcher import ParseContext, parse_bytes
from billing_agent.schemas import (
    BillRecord,
    Decision,
    GroundedExtraction,
    OperationType,
    ParsedDocument,
    ProcessingResult,
    SourceOrigin,
)
from billing_agent.security import SecurityError, check_size, sanitize_filename, sha256_hex
from billing_agent.services.llm_factory import LlmCapabilityError, LlmNotConfiguredError
from billing_agent.services.ocr_service import OcrService

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str, dict[str, Any]], None]


@dataclass
class UploadedFile:
    name: str
    data: bytes


@dataclass
class DocumentOutcome:
    document: ParsedDocument
    grounded: GroundedExtraction | None = None
    decisions: list[Decision] = field(default_factory=list)
    extract_error: str | None = None
    stage_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineResult:
    outcomes: list[DocumentOutcome]
    existing_bills: list[BillRecord]
    processing: ProcessingResult
    delivery_json: list[dict[str, Any]]
    accounting_entity: str | None
    demo_mode: bool
    service_status: dict[str, Any]
    stages: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_ms: int | None = None
    # none | uploaded | default_synthetic | provided
    bills_source: str = "none"
    bills_source_name: str | None = None

    @property
    def all_decisions(self) -> list[Decision]:
        return list(self.processing.decisions)

    def count_ops(self) -> dict[str, int]:
        counts = {op.value: 0 for op in OperationType}
        for d in self.all_decisions:
            counts[d.operation.value] = counts.get(d.operation.value, 0) + 1
        return counts


def service_status(settings: Settings) -> dict[str, Any]:
    """Non-secret configuration readiness for UI banners."""
    from billing_agent.services.file_url_factory import create_file_url_provider

    provider = create_file_url_provider(settings)
    return {
        "llm_configured": settings.llm.configured,
        "llm_model_set": bool(settings.llm.model),
        "llm_base_url_set": bool(settings.llm.base_url),
        "oss_configured": settings.oss.configured,
        "oss_missing": settings.oss.missing_fields(),
        "r2_worker_configured": settings.r2_worker.configured,
        "r2_worker_missing": settings.r2_worker.missing_fields(),
        "file_url_provider": settings.file_url_provider or "(auto)",
        "active_file_url_provider": getattr(provider, "name", None),
        "storage_configured": provider is not None,
        "ocr_endpoint_set": bool(settings.ocr.endpoint),
        "ocr_task": settings.ocr.task,
    }


class BillingPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        ocr_service: OcrService | None = None,
        extraction_agent: ExtractionAgent | None = None,
        on_stage: StageCallback | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.ocr_service = ocr_service if ocr_service is not None else OcrService.from_settings(self.settings)
        self.extraction_agent = extraction_agent
        self.on_stage = on_stage

    def _emit(self, stage: str, status: str, **detail: Any) -> None:
        event = {
            "stage": stage,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            **detail,
        }
        if self.on_stage:
            try:
                self.on_stage(stage, status, event)
            except Exception:  # UI callback must not break the pipeline
                logger.exception("stage callback failed")
        return

    def _ensure_agent(self) -> ExtractionAgent:
        if self.extraction_agent is None:
            self.extraction_agent = ExtractionAgent.from_settings(self.settings.llm)
        return self.extraction_agent

    def run(
        self,
        files: list[UploadedFile],
        *,
        existing_bills: list[BillRecord] | None = None,
        existing_bills_bytes: bytes | None = None,
        existing_bills_name: str = "bills.json",
        accounting_entity: str | None = None,
        entity_aliases: dict[str, str] | None = None,
        skip_extraction: bool = False,
        enable_ocr_upload: bool = False,
    ) -> PipelineResult:
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        stages: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        outcomes: list[DocumentOutcome] = []

        def track(stage: str, status: str, **detail: Any) -> None:
            event = {
                "stage": stage,
                "status": status,
                "at": datetime.now(timezone.utc).isoformat(),
                **detail,
            }
            stages.append(event)
            self._emit(stage, status, **detail)

        status = service_status(self.settings)
        track("init", "ok", service_status=status)

        bills = list(existing_bills or [])
        demo_mode = any(b.synthetic for b in bills)
        bills_source = "provided" if bills else "none"
        bills_source_name: str | None = None
        if existing_bills_bytes is not None:
            track("load_bills", "running", file_name=existing_bills_name)
            try:
                bills = load_bills_json(existing_bills_bytes, source_name=existing_bills_name)
                demo_mode = any(b.synthetic for b in bills)
                bills_source = "uploaded"
                bills_source_name = existing_bills_name
                track(
                    "load_bills",
                    "ok",
                    count=len(bills),
                    demo_mode=demo_mode,
                    bills_source=bills_source,
                    file_name=existing_bills_name,
                )
            except BillStoreError as exc:
                errors.append(f"Existing bills JSON invalid: {exc}")
                track("load_bills", "failed", error=str(exc))
        elif bills and all(b.synthetic for b in bills):
            bills_source = "default_synthetic"
            bills_source_name = "synthetic_existing_bills.json"
            demo_mode = True

        if not files:
            errors.append("No input files provided")
            empty = ProcessingResult(errors=errors)
            return PipelineResult(
                outcomes=[],
                existing_bills=bills,
                processing=empty,
                delivery_json=[],
                accounting_entity=accounting_entity,
                demo_mode=demo_mode,
                service_status=status,
                stages=stages,
                errors=errors,
                warnings=warnings,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                bills_source=bills_source,
                bills_source_name=bills_source_name,
            )

        total_bytes = sum(len(f.data) for f in files)
        try:
            check_size(total_bytes, self.settings.limits.max_total_bytes, "upload total")
        except SecurityError as exc:
            errors.append(str(exc))
            empty = ProcessingResult(errors=errors)
            return PipelineResult(
                outcomes=[],
                existing_bills=bills,
                processing=empty,
                delivery_json=[],
                accounting_entity=accounting_entity,
                demo_mode=demo_mode,
                service_status=status,
                stages=stages,
                errors=errors,
                warnings=warnings,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                bills_source=bills_source,
                bills_source_name=bills_source_name,
            )

        # OCR uploads private objects to OSS then sends a signed URL to a third-party
        # gateway. Default OFF until the operator explicitly authorizes the upload.
        ocr_for_run = self.ocr_service
        if not enable_ocr_upload:
            from billing_agent.services.ocr_client import OcrClient

            # Keep endpoint metadata but mark as intentionally not authorized —
            # do not report STORAGE_NOT_CONFIGURED when LocalTunnel/OSS is actually set.
            ocr_for_run = OcrService(
                OcrClient(self.settings.ocr),
                url_provider=None,
                disabled_reason="not_authorized",
            )
            warnings.append(
                "OCR upload disabled for this run (enable_ocr_upload=False). "
                "PDF text_layer may still be used and is labelled text_layer, not OCR. "
                "Authorize OCR on the Dashboard only after data-use approval."
            )
            track("ocr", "skipped", reason="enable_ocr_upload=false")

        ctx = ParseContext(
            limits=self.settings.limits,
            ocr_service=ocr_for_run,
            soffice_path=self.settings.soffice_path,
        )

        all_decisions: list[Decision] = []

        for uploaded in files:
            name = sanitize_filename(uploaded.name)
            track("parse", "running", file_name=name, size_bytes=len(uploaded.data))
            try:
                check_size(len(uploaded.data), self.settings.limits.max_file_bytes, name)
                document = parse_bytes(uploaded.data, name, ctx)
            except Exception as exc:
                msg = f"Parse failed for {name}: {type(exc).__name__}: {exc}"
                errors.append(msg)
                track("parse", "failed", file_name=name, error=msg)
                continue

            for w in document.warnings:
                warnings.append(f"{name}: {w}")
            for e in document.errors:
                errors.append(f"{name}: {e}")

            # Surface OCR status honestly (never pretend text_layer is OCR success).
            ocr_note = _ocr_status_note(document)
            if ocr_note:
                warnings.append(ocr_note)
                track("ocr", ocr_note.split(":")[0].strip().lower().replace(" ", "_"), file_name=name, note=ocr_note)

            track("parse", "ok", file_name=name, doc_id=document.doc_id, parse_status=document.status.value)

            outcome = DocumentOutcome(document=document)

            if skip_extraction:
                outcome.extract_error = "Extraction skipped"
                track("extract", "skipped", file_name=name)
            elif not self.settings.llm.configured and self.extraction_agent is None:
                outcome.extract_error = "LLM not configured (set LLM_API_KEY and LLM_MODEL)"
                errors.append(f"{name}: {outcome.extract_error}")
                track("extract", "blocked", file_name=name, error=outcome.extract_error)
            else:
                track("extract", "running", file_name=name)
                try:
                    agent = self._ensure_agent()
                    grounded = agent.extract(document)
                    outcome.grounded = grounded
                    track(
                        "extract",
                        "ok",
                        file_name=name,
                        model=grounded.model_name,
                        strategy=grounded.structured_strategy,
                        charges=len(grounded.actual_charges),
                        elapsed_ms=grounded.elapsed_ms,
                    )
                except (LlmNotConfiguredError, LlmCapabilityError, ExtractionAgentError) as exc:
                    outcome.extract_error = str(exc)
                    errors.append(f"{name}: extraction failed: {exc}")
                    track("extract", "failed", file_name=name, error=str(exc))
                except Exception as exc:
                    outcome.extract_error = f"{type(exc).__name__}: {exc}"
                    errors.append(f"{name}: extraction failed: {outcome.extract_error}")
                    track("extract", "failed", file_name=name, error=outcome.extract_error)

            if outcome.grounded is not None:
                track("decide", "running", file_name=name)
                try:
                    # Prefer native/text_layer payment cues; include OCR text only as fallback.
                    direction_text = "\n".join(
                        [
                            document.text_by_origin(SourceOrigin.NATIVE) or "",
                            document.text_by_origin(SourceOrigin.TEXT_LAYER) or "",
                            document.text_by_origin(SourceOrigin.OCR_API) or "",
                        ]
                    )
                    direction = extract_payment_direction(direction_text)
                    decisions = decide_for_document(
                        outcome.grounded,
                        bills,
                        accounting_entity=accounting_entity,
                        file_sha256=document.sha256,
                        entity_aliases=entity_aliases,
                        payee_hints=direction.payees or None,
                        payer_hints=direction.payers or None,
                        prefer_payment_hints=direction.strong,
                        change_requests=outcome.grounded.result.change_requests,
                    )
                    outcome.decisions = decisions
                    all_decisions.extend(decisions)
                    track("decide", "ok", file_name=name, decisions=len(decisions))
                except Exception as exc:
                    msg = f"{name}: decision failed: {type(exc).__name__}: {exc}"
                    errors.append(msg)
                    track("decide", "failed", file_name=name, error=msg)

            outcomes.append(outcome)

        processing = build_processing_result(all_decisions)
        processing.errors = list(errors)
        processing.warnings = list(warnings)
        delivery = to_delivery_json(processing) if all_decisions else []
        track("json", "ok" if delivery else "empty", records=len(delivery))

        finished_at = datetime.now(timezone.utc).isoformat()
        return PipelineResult(
            outcomes=outcomes,
            existing_bills=bills,
            processing=processing,
            delivery_json=delivery,
            accounting_entity=accounting_entity,
            demo_mode=demo_mode,
            service_status=status,
            stages=stages,
            errors=errors,
            warnings=warnings,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            bills_source=bills_source,
            bills_source_name=bills_source_name,
        )


def _ocr_status_note(document: ParsedDocument) -> str | None:
    """Human-readable OCR status; distinguishes text_layer fallback from OCR success."""
    notes: list[str] = []
    for doc in document.iter_documents():
        if doc.ocr is None:
            continue
        ocr = doc.ocr
        text_layer_count = len(doc.blocks_by_origin(SourceOrigin.TEXT_LAYER))
        ocr_count = len(doc.blocks_by_origin(SourceOrigin.OCR_API))
        label = "/".join(doc.source_chain) or doc.file_name
        if ocr.status.value == "SUCCESS":
            notes.append(f"OCR SUCCESS: {label} ({ocr_count} OCR blocks, {ocr.elapsed_ms} ms)")
        elif ocr.status.value == "FAILED":
            code = ocr.error_code or "UNKNOWN"
            http = f" HTTP {ocr.http_status}" if ocr.http_status else ""
            fallback = (
                f"; PDF text_layer available ({text_layer_count} blocks) — not OCR"
                if text_layer_count
                else ""
            )
            notes.append(f"OCR FAILED [{code}]{http}: {label}{fallback}")
        elif ocr.status.value == "NOT_APPLICABLE":
            code = ocr.error_code or "NOT_APPLICABLE"
            if text_layer_count:
                notes.append(
                    f"OCR SKIPPED [{code}]: {label}; "
                    f"PDF text_layer available ({text_layer_count} blocks) — not OCR"
                )
            else:
                notes.append(f"OCR SKIPPED [{code}]: {label}")
        elif ocr.status.value == "NOT_CONFIGURED":
            fallback = (
                f"; PDF text_layer available ({text_layer_count} blocks) — not OCR"
                if text_layer_count
                else ""
            )
            notes.append(f"OCR BLOCKED [NOT_CONFIGURED]: {label}{fallback}")
    return "; ".join(notes) if notes else None


def load_default_synthetic_bills() -> list[BillRecord]:
    path = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "synthetic" / "synthetic_existing_bills.json"
    if path.is_file():
        return load_bills_path(path)
    return []


def file_fingerprint(data: bytes) -> str:
    return sha256_hex(data)
