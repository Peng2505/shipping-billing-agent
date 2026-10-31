"""AR/AP from accounting_entity perspective. Document type alone never decides."""

from __future__ import annotations

from dataclasses import dataclass

from billing_agent.business.entity_names import entities_equal, normalize_entity
from billing_agent.schemas import BillRecord


@dataclass(frozen=True)
class ArApResult:
    posting_type: str | None  # AR | AP | None
    reasons: list[str]
    needs_review: bool


def classify_ar_ap(
    bill: BillRecord,
    accounting_entity: str | None,
    *,
    aliases: dict[str, str] | None = None,
    payee_hints: list[str] | None = None,
    payer_hints: list[str] | None = None,
    prefer_payment_hints: bool = False,
) -> ArApResult:
    reasons: list[str] = []
    if not accounting_entity or not str(accounting_entity).strip():
        return ArApResult(None, ["accounting_entity missing"], True)

    entity = accounting_entity.strip()
    reasons.append(f"accounting_entity={entity}")

    hint_payees = [p for p in (payee_hints or []) if p]
    hint_payers = [p for p in (payer_hints or []) if p]

    # Payment-direction evidence (Remit to / Please Pay / Consignee) outranks
    # issuer/recipient when present — LLM party roles are often wrong on notices.
    if prefer_payment_hints and (hint_payees or hint_payers):
        is_payee = any(entities_equal(entity, p, aliases) for p in hint_payees)
        is_payer = any(entities_equal(entity, p, aliases) for p in hint_payers)
        reasons.append(
            f"prefer_payment_hints payees={hint_payees} payers={hint_payers}"
        )
        if is_payee and is_payer:
            return ArApResult(
                None,
                reasons + [
                    "entity matches both payment-direction payee and payer evidence",
                    "document_type is not used as AR/AP authority",
                ],
                True,
            )
        if is_payee:
            return ArApResult(
                "AR",
                reasons + [
                    f"entity matches payment-direction payee evidence {hint_payees}",
                    "document_type not decisive",
                ],
                False,
            )
        if is_payer:
            return ArApResult(
                "AP",
                reasons + [
                    f"entity matches payment-direction payer evidence {hint_payers}",
                    "issuer/recipient ignored while payment-direction evidence is present",
                    "document_type not decisive",
                ],
                False,
            )
        # Strong cues but entity matches neither side → do not guess from issuer.
        return ArApResult(
            None,
            reasons + [
                f"payment-direction evidence present but entity matches neither "
                f"(payees={hint_payees}, payers={hint_payers})",
                "document_type alone cannot determine AR/AP",
            ],
            True,
        )

    payees = [p for p in [bill.issuer, *hint_payees] if p]
    payers = [p for p in [bill.recipient, *hint_payers] if p]

    is_payee = any(entities_equal(entity, p, aliases) for p in payees)
    is_payer = any(entities_equal(entity, p, aliases) for p in payers)

    if is_payee and is_payer:
        return ArApResult(
            None,
            reasons + [
                f"entity matches both payee candidates {payees} and payer candidates {payers}",
                "document_type is not used as AR/AP authority",
            ],
            True,
        )
    if is_payee:
        return ArApResult(
            "AR",
            reasons + [f"entity matches payee evidence {payees}", "document_type not decisive"],
            False,
        )
    if is_payer:
        return ArApResult(
            "AP",
            reasons + [f"entity matches payer evidence {payers}", "document_type not decisive"],
            False,
        )

    return ArApResult(
        None,
        reasons + [
            f"no reliable payee/payer match (payees={payees}, payers={payers})",
            f"normalized_entity={normalize_entity(entity)}",
            "document_type alone cannot determine AR/AP",
        ],
        True,
    )
