"""Four-level existing-bill matching. Amount is never the sole disambiguator."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from billing_agent.business.charge_normalizer import normalize_charge_key, normalize_charge_name
from billing_agent.business.entity_names import entities_equal, normalize_entity
from billing_agent.schemas import BillRecord, MatchLevel, MatchResult


def _dec(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace(",", "").strip())
    except InvalidOperation:
        return None


def _charge_key(bill_or_name: BillRecord | str | None) -> str | None:
    if bill_or_name is None:
        return None
    if isinstance(bill_or_name, BillRecord):
        name = bill_or_name.charge_item or bill_or_name.charge_item_raw
    else:
        name = bill_or_name
    if not name:
        return None
    mapped = normalize_charge_name(name).standard_name or name
    return normalize_charge_key(mapped)


def _norm_id(value: str | None) -> str | None:
    if not value:
        return None
    return re_sub_id(value)


def re_sub_id(value: str) -> str:
    import re
    return re.sub(r"[\s\-]", "", value).upper()


def _containers(bill: BillRecord) -> set[str]:
    return {_norm_id(c) for c in bill.container_nos if _norm_id(c)}


def _l1(candidate: BillRecord, incoming: BillRecord) -> bool:
    return bool(
        _norm_id(candidate.reference_no)
        and _norm_id(candidate.reference_no) == _norm_id(incoming.reference_no)
        and _charge_key(candidate) == _charge_key(incoming)
    )


def _l2(candidate: BillRecord, incoming: BillRecord) -> bool:
    return bool(
        _norm_id(candidate.bl_no)
        and _norm_id(candidate.bl_no) == _norm_id(incoming.bl_no)
        and _charge_key(candidate) == _charge_key(incoming)
        and candidate.currency
        and incoming.currency
        and candidate.currency.upper() == incoming.currency.upper()
    )


def _l3(candidate: BillRecord, incoming: BillRecord) -> bool:
    return bool(
        _norm_id(candidate.booking_no)
        and _norm_id(candidate.booking_no) == _norm_id(incoming.booking_no)
        and _charge_key(candidate) == _charge_key(incoming)
        and candidate.currency
        and incoming.currency
        and candidate.currency.upper() == incoming.currency.upper()
    )


def _l4(candidate: BillRecord, incoming: BillRecord) -> bool:
    c_set, i_set = _containers(candidate), _containers(incoming)
    if not c_set or not i_set or c_set.isdisjoint(i_set):
        return False
    parties_ok = (
        entities_equal(candidate.issuer, incoming.issuer)
        and entities_equal(candidate.recipient, incoming.recipient)
    )
    if not parties_ok:
        return False
    if not candidate.document_date or not incoming.document_date:
        return False
    if candidate.document_date != incoming.document_date:
        return False
    ca, ia = _dec(candidate.amount), _dec(incoming.amount)
    return ca is not None and ia is not None and ca == ia


def _non_amount_tiebreak(candidates: list[BillRecord], incoming: BillRecord) -> list[BillRecord]:
    """Disambiguate using non-amount evidence only."""
    remaining = list(candidates)

    if incoming.container_nos:
        hit = [c for c in remaining if not _containers(c).isdisjoint(_containers(incoming))]
        if len(hit) == 1:
            return hit
        if hit:
            remaining = hit

    if incoming.bl_no:
        hit = [c for c in remaining if _norm_id(c.bl_no) == _norm_id(incoming.bl_no)]
        if len(hit) == 1:
            return hit
        if hit:
            remaining = hit

    if incoming.booking_no:
        hit = [c for c in remaining if _norm_id(c.booking_no) == _norm_id(incoming.booking_no)]
        if len(hit) == 1:
            return hit
        if hit:
            remaining = hit

    if incoming.document_date:
        hit = [c for c in remaining if c.document_date == incoming.document_date]
        if len(hit) == 1:
            return hit
        if hit:
            remaining = hit

    if incoming.payment_term:
        hit = [c for c in remaining if c.payment_term == incoming.payment_term]
        if len(hit) == 1:
            return hit
        if hit:
            remaining = hit

    # Explicit line hint stored in extra (synthetic tests / parsers)
    line_hint = (incoming.extra or {}).get("line_hint")
    if line_hint is not None:
        hit = [c for c in remaining if (c.extra or {}).get("line_hint") == line_hint]
        if len(hit) == 1:
            return hit

    return remaining


class BillMatcher:
    def __init__(self) -> None:
        self._claimed: set[str] = set()

    def reset_claims(self) -> None:
        self._claimed.clear()

    def match(
        self,
        incoming: BillRecord,
        existing: list[BillRecord],
    ) -> MatchResult:
        steps: list[dict] = []
        levels = [
            (MatchLevel.L1, "reference_no+charge", _l1,
             lambda b: bool(_norm_id(b.reference_no) and _charge_key(b))),
            (MatchLevel.L2, "bl_no+charge+currency", _l2,
             lambda b: bool(_norm_id(b.bl_no) and _charge_key(b) and b.currency)),
            (MatchLevel.L3, "booking_no+charge+currency", _l3,
             lambda b: bool(_norm_id(b.booking_no) and _charge_key(b) and b.currency)),
            (MatchLevel.L4, "container+parties+date+amount", _l4,
             lambda b: bool(_containers(b) and b.issuer and b.recipient and b.document_date and b.amount)),
        ]

        for level, label, pred, required in levels:
            if not required(incoming):
                steps.append({"level": level.value, "rule": label, "status": "SKIPPED",
                              "reason": "incoming missing required fields"})
                continue
            pool = [b for b in existing if b.bill_id not in self._claimed]
            hits = [b for b in pool if pred(b, incoming)]
            steps.append({
                "level": level.value, "rule": label, "status": "EVALUATED",
                "candidates": [b.bill_id for b in hits],
            })
            if not hits:
                continue
            if len(hits) == 1:
                bill = hits[0]
                self._claimed.add(bill.bill_id)  # type: ignore[arg-type]
                return MatchResult(
                    level=level, status="matched", bill_id=bill.bill_id,
                    candidate_ids=[bill.bill_id], steps=steps,
                    reason=f"Unique match at {level.value} ({label})",
                )
            # Multiple candidates: non-amount disambiguation only
            narrowed = _non_amount_tiebreak(hits, incoming)
            if len(narrowed) == 1:
                bill = narrowed[0]
                self._claimed.add(bill.bill_id)  # type: ignore[arg-type]
                steps.append({
                    "level": level.value, "status": "DISAMBIGUATED",
                    "by": "non_amount_evidence",
                    "candidates": [b.bill_id for b in hits],
                    "chosen": bill.bill_id,
                })
                return MatchResult(
                    level=level, status="matched", bill_id=bill.bill_id,
                    candidate_ids=[bill.bill_id], steps=steps,
                    reason=f"Disambiguated at {level.value} without using amount as sole key",
                )
            return MatchResult(
                level=level, status="ambiguous",
                candidate_ids=[b.bill_id for b in narrowed],
                steps=steps,
                reason=(
                    f"Multiple candidates at {level.value}; amount is not used as the sole "
                    f"disambiguator; pending review"
                ),
            )

        return MatchResult(
            level=MatchLevel.NONE, status="none", steps=steps,
            reason="No existing bill matched at L1–L4",
        )
