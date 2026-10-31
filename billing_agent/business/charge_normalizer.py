"""Deterministic charge-name normalisation with context-aware waived/conditional rules.

H/C maps to Handling Charge only when the surrounding context does not indicate
a free/waived mention (e.g. "Carrier Free H/C"). Currency symbols such as "$"
are never converted to ISO codes here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ALIAS_FILE = Path(__file__).with_name("charge_aliases.yaml")


def normalize_charge_key(name: str) -> str:
    text = name.upper().strip()
    text = text.replace("／", "/")
    text = re.sub(r"[\s._\-]+", " ", text)
    text = re.sub(r"\s*/\s*", "/", text)
    return text.strip()


@lru_cache(maxsize=1)
def _load_dict() -> dict[str, Any]:
    with _ALIAS_FILE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class NormalizeResult:
    raw_name: str
    standard_name: str | None
    matched_alias: str | None
    context_nature: str | None  # waived | conditional | None
    notes: str | None = None


def _match_patterns(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return None


def classify_context(raw_name: str, surrounding_text: str = "") -> str | None:
    """Return 'waived' / 'conditional' / None based on surrounding text + name."""
    haystack = f"{surrounding_text}\n{raw_name}"
    data = _load_dict()
    waived = _match_patterns(haystack, data.get("waived_context_patterns") or [])
    if waived:
        return "waived"
    conditional = _match_patterns(haystack, data.get("conditional_context_patterns") or [])
    if conditional:
        return "conditional"
    return None


def normalize_charge_name(raw_name: str, surrounding_text: str = "") -> NormalizeResult:
    context = classify_context(raw_name, surrounding_text)
    key = normalize_charge_key(raw_name)
    aliases: dict[str, str] = _load_dict().get("aliases") or {}
    # Exact key, then try without trailing FEE/CHARGE noise for short codes like H/C
    standard = aliases.get(key)
    matched = key if standard else None
    if standard is None:
        for alias, value in aliases.items():
            if key == alias or key.startswith(alias + " ") or key.endswith(" " + alias):
                standard, matched = value, alias
                break
    notes = None
    if context == "waived":
        notes = "Context indicates a free/waived mention; not an actual charge line."
    elif context == "conditional":
        notes = "Context indicates a conditional/potential fee; not an actual charge line."
    return NormalizeResult(
        raw_name=raw_name,
        standard_name=None if context == "waived" else standard,
        matched_alias=matched,
        context_nature=context,
        notes=notes,
    )


def lookup_alias(raw_name: str) -> dict[str, Any]:
    """Tool-friendly lookup: dictionary hit only, no context classification."""
    key = normalize_charge_key(raw_name)
    aliases: dict[str, str] = _load_dict().get("aliases") or {}
    if key in aliases:
        return {"status": "MAPPED", "raw": raw_name, "key": key, "standard_name": aliases[key]}
    for alias, value in aliases.items():
        if key == alias or re.fullmatch(re.escape(alias) + r"( FEE| CHARGE)?", key):
            return {"status": "MAPPED", "raw": raw_name, "key": alias, "standard_name": value}
    return {"status": "UNKNOWN", "raw": raw_name, "key": key, "standard_name": None}
