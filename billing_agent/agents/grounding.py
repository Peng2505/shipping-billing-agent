"""Python-side evidence verification and charge post-processing after the Agent runs."""

from __future__ import annotations

import json

from billing_agent.agents.document_index import DocumentIndex, normalize_for_match
from billing_agent.business.bl_normalizer import enrich_bl_with_document_scac
from billing_agent.business.charge_normalizer import normalize_charge_name
from billing_agent.business.ocr_charge_filter import filter_ocr_charge_list
from billing_agent.business.ocr_currency import (
    document_currency_from_ocr_payload,
    inherit_currency_onto_charges,
)
from billing_agent.schemas import (
    ChargeNature,
    EvidencedValue,
    ExtractedCharge,
    ExtractionResult,
    GroundedExtraction,
    GroundingIssue,
    SourceOrigin,
)


def _quote_ok(index: DocumentIndex, block_id: str, quote: str) -> bool:
    return index.verify_quote(block_id, quote).get("ok") is True


def _local_quote_context(index: DocumentIndex, block_id: str, quote: str) -> str:
    """Return the source line(s) that contain the evidence quote.

    Uses whole lines rather than a character radius so adjacent but distinct
    statements in the same e-mail body stay separable
    (e.g. "Carrier Free H/C" vs "SHA pay TAR：H/C $50").
    """
    block = index.get(block_id)
    if block is None or not quote:
        return quote or ""
    needle = quote.strip().lower()
    if not needle:
        return quote
    matched = []
    for line in (block.text or "").splitlines():
        if needle in line.lower() or (len(needle) >= 8 and needle[:24] in line.lower()):
            matched.append(line.strip())
    return "\n".join(matched) if matched else quote


def _ground_value(
    index: DocumentIndex,
    path: str,
    field: EvidencedValue | None,
    issues: list[GroundingIssue],
) -> EvidencedValue | None:
    if field is None:
        return None
    if field.value is None:
        return field
    if not field.evidence:
        issues.append(GroundingIssue(path=path, reason="missing_evidence"))
        return EvidencedValue(value=None, evidence=[])
    kept = []
    for ev in field.evidence:
        if _quote_ok(index, ev.block_id, ev.quote):
            kept.append(ev)
        else:
            issues.append(GroundingIssue(
                path=path, reason="quote_not_found", block_id=ev.block_id, quote=ev.quote,
            ))
    if not kept:
        return EvidencedValue(value=None, evidence=[])
    return EvidencedValue(value=field.value, evidence=kept)


def _ground_charge(
    index: DocumentIndex,
    path: str,
    charge: ExtractedCharge,
    issues: list[GroundingIssue],
) -> ExtractedCharge | None:
    if not charge.evidence:
        issues.append(GroundingIssue(path=path, reason="missing_evidence"))
        return None
    kept = []
    for ev in charge.evidence:
        if _quote_ok(index, ev.block_id, ev.quote):
            kept.append(ev)
        else:
            issues.append(GroundingIssue(
                path=path, reason="quote_not_found", block_id=ev.block_id, quote=ev.quote,
            ))
    if not kept:
        return None

    # Classify using the evidence quote (and a tight local window), NOT the whole
    # block — one e-mail body can contain both "Carrier Free H/C" and "H/C $50".
    primary = kept[0]
    local_context = _local_quote_context(index, primary.block_id, primary.quote)
    norm = normalize_charge_name(charge.raw_name, local_context)
    nature = charge.nature
    notes = charge.notes
    if norm.context_nature == "waived":
        nature = ChargeNature.WAIVED
        notes = norm.notes
    elif norm.context_nature == "conditional" and nature == ChargeNature.ACTUAL:
        nature = ChargeNature.CONDITIONAL
        notes = norm.notes

    # "$" / "￥" alone are not ISO currencies
    currency = charge.currency
    if currency and currency.strip() in {"$", "￥", "¥", "€", "£"}:
        issues.append(GroundingIssue(
            path=f"{path}.currency", reason="symbol_not_iso4217", quote=currency,
        ))
        currency = None

    return charge.model_copy(update={
        "evidence": kept,
        "nature": nature,
        "currency": currency,
        "notes": notes,
    })


def _parse_ocr_blocks(index: DocumentIndex) -> tuple[list[ExtractedCharge], list[ExtractedCharge], list[str]]:
    actuals: list[ExtractedCharge] = []
    excluded: list[ExtractedCharge] = []
    warnings: list[str] = []
    for block_id, block in index.blocks.items():
        if block.origin != SourceOrigin.OCR_API:
            continue
        try:
            item = json.loads(block.text)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        charge_list = item.get("chargeList") or []
        if not isinstance(charge_list, list):
            continue
        total = None
        # OCR responses observed so far do not carry an explicit total field on the item
        a, e, w = filter_ocr_charge_list(charge_list, block_id=block_id, document_total=total)
        actuals.extend(a)
        excluded.extend(e)
        warnings.extend(w)
    return actuals, excluded, warnings


def _amount_key(charge: ExtractedCharge) -> tuple:
    return (
        normalize_for_match(charge.raw_name),
        (charge.amount or "").replace(",", ""),
        charge.nature.value,
    )


def ground_extraction(
    raw: ExtractionResult,
    index: DocumentIndex,
    *,
    tool_trace: list | None = None,
    model_name: str | None = None,
    structured_strategy: str | None = None,
    elapsed_ms: int | None = None,
) -> GroundedExtraction:
    issues: list[GroundingIssue] = []
    grounded = ExtractionResult(
        document_type=_ground_value(index, "document_type", raw.document_type, issues),
        reference_no=_ground_value(index, "reference_no", raw.reference_no, issues),
        document_date_raw=_ground_value(index, "document_date_raw", raw.document_date_raw, issues),
        issuer=_ground_value(index, "issuer", raw.issuer, issues),
        recipient=_ground_value(index, "recipient", raw.recipient, issues),
        bl_no=_ground_value(index, "bl_no", raw.bl_no, issues),
        booking_no=_ground_value(index, "booking_no", raw.booking_no, issues),
        house_bl_no=_ground_value(index, "house_bl_no", raw.house_bl_no, issues),
        container_nos=[
            v for v in (
                _ground_value(index, f"container_nos[{i}]", c, issues)
                for i, c in enumerate(raw.container_nos)
            ) if v and v.value
        ],
        document_total=_ground_value(index, "document_total", raw.document_total, issues),
        currency=_ground_value(index, "currency", raw.currency, issues),
        payment_term_raw=_ground_value(index, "payment_term_raw", raw.payment_term_raw, issues),
        change_requests=raw.change_requests,  # validated below
        warnings=list(raw.warnings),
    )

    grounded.bl_no = enrich_bl_with_document_scac(index, grounded.bl_no)

    if grounded.currency and grounded.currency.value in {"$", "￥", "¥", "€", "£"}:
        issues.append(GroundingIssue(path="currency", reason="symbol_not_iso4217", quote=grounded.currency.value))
        grounded.currency = EvidencedValue(value=None, evidence=grounded.currency.evidence)

    # When the Agent left currency null, recover only from explicit OCR JSON fields.
    if grounded.currency is None or not grounded.currency.value:
        for block_id, block in index.blocks.items():
            if block.origin != SourceOrigin.OCR_API or not block.text:
                continue
            inferred = document_currency_from_ocr_payload(block.text, block_id=block_id)
            if inferred and inferred.value:
                grounded.currency = inferred
                break

    def _is_kept_line(nature: ChargeNature) -> bool:
        # Tax lines are kept (not unconditionally dropped). Totals / waived /
        # conditional / informational stay in excluded for audit.
        return nature in {ChargeNature.ACTUAL, ChargeNature.TAX}

    actuals: list[ExtractedCharge] = []
    excluded: list[ExtractedCharge] = []
    for i, charge in enumerate(raw.charges):
        g = _ground_charge(index, f"charges[{i}]", charge, issues)
        if g is None:
            continue
        if _is_kept_line(g.nature):
            actuals.append(g)
        else:
            excluded.append(g)
    for i, charge in enumerate(raw.excluded):
        g = _ground_charge(index, f"excluded[{i}]", charge, issues)
        if g is not None:
            excluded.append(g)

    # Merge OCR chargeList filter results (additive for audit; agent remains primary)
    ocr_kept, ocr_excluded, ocr_warnings = _parse_ocr_blocks(index)
    grounded.warnings.extend(ocr_warnings)
    if ocr_kept and all(c.currency is None for c in ocr_kept):
        grounded.warnings.append(
            "OCR chargeList has no explicit ISO currency "
            "(chargeCtr is container id, not currency); leaving currency null until evidenced"
        )
    seen = {_amount_key(c) for c in actuals}
    for c in ocr_kept:
        if _amount_key(c) not in seen and not actuals:
            # Auto-add OCR candidates only when the agent found no charge lines
            # (typical for image-only docs). Currency stays null unless OCR provided it.
            actuals.append(c)
            seen.add(_amount_key(c))
        elif _amount_key(c) not in seen:
            grounded.warnings.append(
                f"OCR candidate '{c.raw_name}' {c.amount} not confirmed by agent; left for review"
            )
            excluded.append(c)
    excluded.extend(ocr_excluded)

    actuals = inherit_currency_onto_charges(actuals, grounded.currency)
    grounded.charges = actuals
    grounded.excluded = excluded

    # change_requests: drop those whose evidence fails
    valid_changes = []
    for i, req in enumerate(raw.change_requests):
        ok_ev = [ev for ev in req.evidence if _quote_ok(index, ev.block_id, ev.quote)]
        if not ok_ev:
            issues.append(GroundingIssue(path=f"change_requests[{i}]", reason="quote_not_found"))
            continue
        valid_changes.append(req.model_copy(update={"evidence": ok_ev}))
    grounded.change_requests = valid_changes

    return GroundedExtraction(
        result=grounded,
        issues=issues,
        actual_charges=actuals,
        excluded_charges=excluded,
        tool_trace=tool_trace or [],
        model_name=model_name,
        structured_strategy=structured_strategy,
        elapsed_ms=elapsed_ms,
    )
