"""Conservative entity-name normalisation for matching / AR-AP (no fuzzy semantics)."""

from __future__ import annotations

import re

_SUFFIXES = re.compile(
    r"\b(limited|ltd|llc|inc|incorporated|co|company|corp|corporation|gmbh|plc|sa|pte|pty)\b\.?",
    re.I,
)


def normalize_entity(name: str | None) -> str | None:
    if not name:
        return None
    text = name.replace("\xa0", " ")
    text = re.sub(r"[^\w\s&+/]", " ", text, flags=re.UNICODE)
    text = _SUFFIXES.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text or None


def entities_equal(a: str | None, b: str | None, aliases: dict[str, str] | None = None) -> bool:
    na, nb = normalize_entity(a), normalize_entity(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if aliases:
        mapped_a = normalize_entity(aliases.get(na, aliases.get(a or "", ""))) or na
        mapped_b = normalize_entity(aliases.get(nb, aliases.get(b or "", ""))) or nb
        return mapped_a == mapped_b
    return False
