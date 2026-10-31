"""Unit tests for change_request field / value normalization."""

from __future__ import annotations

from billing_agent.business.change_request_normalizer import (
    normalize_change_request,
    normalize_change_requests,
)
from billing_agent.schemas import ChangeRequest, EvidenceRef


def test_normalize_handling_charge_amount_alias():
    req = ChangeRequest(
        field="HANDLING CHARGE amount",
        new_value="125.50 USD",
        evidence=[EvidenceRef(block_id="b1", quote="amend ... to 125.50 USD")],
    )
    out = normalize_change_request(req)
    assert out is not None
    assert out.field == "amount"
    assert out.new_value == "125.50"


def test_normalize_rejects_unmapped_field():
    assert normalize_change_request(ChangeRequest(field="voyage", new_value="V1")) is None


def test_normalize_dedupes_by_field():
    out = normalize_change_requests(
        [
            ChangeRequest(field="amount", new_value="100"),
            ChangeRequest(field="HANDLING CHARGE amount", new_value="125.50 USD"),
        ]
    )
    assert len(out) == 1
    assert out[0].new_value == "125.50"
