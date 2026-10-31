from billing_agent.business.charge_normalizer import lookup_alias, normalize_charge_name


def test_required_aliases():
    cases = {
        "Handling Fee": "Handling Charge",
        "H/D Fee": "Handling Charge",
        "H/C": "Handling Charge",
        "H/C Fee": "Handling Charge",
        "Doc Fee": "Documentation Fee",
        "THC": "Terminal Handling Charge",
        "Trucking Fee": "Trucking Charge",
        "Customs Fee": "Customs Clearance Fee",
        "Storage Fee": "Storage Charge",
    }
    for raw, standard in cases.items():
        result = normalize_charge_name(raw)
        assert result.standard_name == standard, raw
        assert result.context_nature is None


def test_hc_actual_vs_carrier_free():
    actual = normalize_charge_name("H/C", surrounding_text="SHA pay TAR：H/C $50")
    assert actual.standard_name == "Handling Charge"
    assert actual.context_nature is None

    waived = normalize_charge_name("H/C", surrounding_text="Carrier Free H/C\nSHA pay TAR：H/C $50")
    # surrounding contains both; waived_context wins when "carrier free" is present
    assert waived.context_nature == "waived"
    assert waived.standard_name is None

    free_only = normalize_charge_name("H/C", surrounding_text="Carrier Free H/C")
    assert free_only.context_nature == "waived"


def test_lookup_alias_unknown():
    assert lookup_alias("Wharfage")["status"] == "UNKNOWN"
    assert lookup_alias("H/C")["status"] == "MAPPED"
    assert lookup_alias("H/C")["standard_name"] == "Handling Charge"


def test_conditional_context():
    result = normalize_charge_name(
        "SERVICE FEE",
        surrounding_text="A SERVICE FEE OF $25.00 PER CANCELLED I.T. WILL BE ASSESSED",
    )
    assert result.context_nature == "conditional"
