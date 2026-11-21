"""Turn messy portal text ("₹35K", "1.2 Lac", "650 sq.ft") into numbers."""
from __future__ import annotations

import re

OUTDOOR_WORDS = [
    "outdoor", "open space", "open area", "sit out", "sitout", "sit-out", "terrace",
    "frontage", "front space", "front open", "cellar parking", "courtyard", "lawn",
    "setback", "set back", "verandah", "veranda", "patio", "rooftop", "roof top",
]
NO_OUTDOOR_WORDS = ["no outdoor", "no open space", "no frontage"]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_money(value) -> int | None:
    """'₹ 35,000', '35k', '0.45 lakh', '1.2 Lac', 45000 -> int rupees."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).lower().replace("rs.", "").replace("rs", "").replace("₹", "").replace("inr", "")
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(k|thousand|lakh|lac|l\b|cr|crore)?", s)
    if not m:
        return None
    n, unit = _num(m.group(1)), (m.group(2) or "").strip()
    if unit in ("k", "thousand"):
        n *= 1_000
    elif unit in ("lakh", "lac", "l"):
        n *= 100_000
    elif unit in ("cr", "crore"):
        n *= 10_000_000
    return int(n)


def parse_area(value) -> int | None:
    """'650 sqft', '650 sq. ft.', '60 sq m', '650' -> sqft."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).lower()
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(sq\.?\s*m\b|sqm|square met|sq\.?\s*y|sq\.?\s*yd|yards?|gaj)?", s)
    if not m:
        return None
    n, unit = _num(m.group(1)), (m.group(2) or "")
    if unit.startswith(("sq m", "sq. m", "sqm", "square met")):
        n *= 10.764
    elif unit and ("y" in unit or "gaj" in unit):
        n *= 9
    return int(round(n))


def detect_outdoor(text: str) -> bool | None:
    t = text.lower()
    if any(w in t for w in NO_OUTDOOR_WORDS):
        return False
    if any(w in t for w in OUTDOOR_WORDS):
        return True
    return None


def detect_floor(text: str) -> str:
    t = text.lower()
    if re.search(r"\bground\b|\bg\s*floor\b|\bgf\b|\bg\+", t):
        return "ground"
    m = re.search(r"(\d+)(?:st|nd|rd|th)?\s*floor", t)
    return m.group(1) if m else ""


def find_rent_in_text(text: str) -> int | None:
    m = re.search(r"(?:rent|₹|rs\.?|inr)\s*[:\-]?\s*(\d[\d,]*\.?\d*\s*(?:k|lakh|lac|l\b)?)", text, re.I)
    if m:
        return parse_money(m.group(1))
    m = re.search(r"(\d[\d,]*\.?\d*\s*(?:k|lakh|lac))\s*(?:/|per)?\s*(?:month|pm|p\.m)", text, re.I)
    return parse_money(m.group(1)) if m else None


def find_area_in_text(text: str) -> int | None:
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(sq\.?\s*ft|sqft|sft|square feet|sq\.?\s*m|sqm|sq\.?\s*yd|yards)", text, re.I)
    return parse_area(m.group(0)) if m else None


def match_locality(text: str, config: dict) -> str:
    """Return canonical locality name when any alias appears in the text."""
    t = text.lower()
    for group in ("primary", "recommended"):
        for name, info in config["localities"][group].items():
            for alias in [name.lower(), *info.get("aliases", [])]:
                if re.search(r"\b" + re.escape(alias) + r"\b", t):
                    return name
    return ""


def locality_group(name: str, config: dict) -> str:
    for group in ("primary", "recommended"):
        if name in config["localities"][group]:
            return group
    return "other"
