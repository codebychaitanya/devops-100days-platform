"""Turn messy portal text ("₹35K", "1.2 Lac", "650 sq.ft") into numbers."""
from __future__ import annotations

import re
from datetime import date, timedelta

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


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_posted_date(text: str, today: date | None = None) -> str:
    """'Posted on 18 Nov 2026', 'Updated: Nov 19', '2 days ago', 'today', '2026-11-18' -> ISO date or ''."""
    if not text:
        return ""
    today = today or date.today()
    t = str(text).lower()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", t)   # Indian dd/mm/yyyy
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            pass
    m = (re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3})[a-z]*,?\s*(\d{4})?", t)
         or re.search(r"\b([a-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?", t))
    if m:
        a, b, y = m.groups()
        day, mon = (a, b) if a.isdigit() else (b, a)
        if mon[:3] in MONTHS:
            year = int(y) if y else today.year
            try:
                d = date(year, MONTHS[mon[:3]], int(day))
                if not y and d > today:  # "Dec 30" seen in January means last year
                    d = d.replace(year=year - 1)
                return d.isoformat()
            except ValueError:
                pass
    if "today" in t or "just now" in t or re.search(r"\d+\s*(hour|hr|min)", t):
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*(day|week|month)s?\s*ago", t)
    if m:
        n = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
        return (today - timedelta(days=n)).isoformat()
    return ""


def find_posted_in_text(text: str) -> str:
    m = re.search(r"(?:posted|updated|listed|added)\s*(?:on|:)?\s*([^\n|]{0,30})", text, re.I)
    return parse_posted_date(m.group(1)) if m else ""
