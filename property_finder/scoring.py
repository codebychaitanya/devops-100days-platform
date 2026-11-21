"""Scores each shop out of 100 for a wok & kebab QSR and estimates its profit potential."""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Listing
from .parse import locality_group

# QSR assumptions for the profit check. Edit these to match your own numbers.
AVG_ORDER_VALUE = 320          # ₹ per order (wok bowl + kebab combo)
HEALTHY_RENT_SHARE = 0.12      # rent should be at most ~12% of monthly sales
OPEN_DAYS = 30

FRONTAGE_WORDS = ["main road", "road facing", "road-facing", "corner", "frontage", "high street",
                  "junction", "glass front", "visible", "highway"]
KITCHEN_WORDS = ["restaurant", "cafe", "café", "food", "kitchen", "exhaust", "chimney", "gas",
                 "qsr", "cloud kitchen", "hotel", "bakery", "eatery", "water", "3 phase", "three phase",
                 "power backup", "washroom", "drainage"]
BAD_WORDS = ["godown only", "warehouse", "basement", "no food", "non-veg not allowed",
             "veg only", "only office", "residential only", "no cooking"]


@dataclass
class Scored:
    listing: Listing
    score: float
    tier: str                       # "match" | "close" | "stretch"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)
    rent_psf: float | None = None
    orders_per_day_needed: int | None = None
    value_vs_market: float | None = None   # >1 means cheaper than the area's usual rent


def _rent_points(rent, cfg, s: Scored) -> float:
    lo, hi = cfg["rent"]["min"], cfg["rent"]["max"]
    sweet_lo, sweet_hi = cfg["rent"]["sweet_spot"]
    if rent is None:
        s.warnings.append("Rent not listed. Call to confirm.")
        return 8
    if sweet_lo <= rent <= sweet_hi:
        s.reasons.append(f"Rent ₹{rent:,} is in the sweet spot")
        return 20
    if lo <= rent <= hi:
        return 15 if rent < sweet_lo else 20 - 8 * (rent - sweet_hi) / (hi - sweet_hi)
    if rent < lo:
        s.warnings.append("Rent is below your floor. Check whether the shop is too small or poorly located.")
        return 8
    s.warnings.append(f"Rent ₹{rent:,} is over the ₹{hi:,} cap. Negotiate before visiting.")
    return max(0, 8 - 8 * (rent - hi) / (0.2 * hi))


def _area_points(area, cfg, s: Scored) -> float:
    lo = cfg["area_sqft"]["min"]
    ideal_lo, ideal_hi = cfg["area_sqft"]["ideal"]
    too_big = cfg["area_sqft"]["too_big"]
    if area is None:
        s.warnings.append("Area not listed. Measure it on the visit.")
        return 6
    if ideal_lo <= area <= ideal_hi:
        s.reasons.append(f"{area} sqft fits kitchen and seating")
        return 15
    if area < lo:
        s.warnings.append(f"Only {area} sqft, below your {lo} sqft minimum")
        return max(0, 15 * (area - 300) / (lo - 300))
    if area <= too_big:
        return 12
    s.warnings.append(f"{area} sqft is bigger than you need, so you would pay for space you don't use")
    return 7


def score(listing: Listing, cfg: dict) -> Scored:
    s = Scored(listing=listing, score=0, tier="stretch")
    t = listing.text
    b = s.breakdown

    b["rent"] = _rent_points(listing.rent, cfg, s)
    b["area"] = _area_points(listing.area_sqft, cfg, s)

    if listing.outdoor:
        b["outdoor"] = 15
        s.reasons.append("Has outdoor, sit-out or frontage space")
    elif listing.outdoor is None:
        b["outdoor"] = 5
    else:
        b["outdoor"] = 0
        s.warnings.append("No outdoor space")

    group = locality_group(listing.locality, cfg)
    b["location"] = {"primary": 15, "recommended": 11, "other": 3}[group]
    if group == "recommended":
        why = cfg["localities"]["recommended"][listing.locality].get("why", "")
        s.reasons.append(f"Recommended high-yield area ({listing.locality}): {why}")
    elif group == "other":
        s.warnings.append("Outside your target areas")

    vis = 0.0
    if listing.floor == "ground":
        vis += 7
        s.reasons.append("Ground floor")
    elif listing.floor:
        s.warnings.append(f"Floor {listing.floor}, not ground. Walk-in traffic will suffer.")
    if any(w in t for w in FRONTAGE_WORDS):
        vis += 4
        s.reasons.append("Main road, corner or frontage")
    hot = [w for w in cfg.get("hotspot_keywords", []) if w in t]
    if hot:
        vis += min(4, 2 * len(hot))
        s.reasons.append("Near " + ", ".join(hot[:3]))
    b["visibility"] = min(15, vis)

    kitchen = [w for w in KITCHEN_WORDS if w in t]
    b["kitchen_ready"] = min(10, 2.5 * len(kitchen))
    if kitchen:
        s.reasons.append("Kitchen-friendly: " + ", ".join(kitchen[:4]))

    # value vs locality benchmark rent per sqft
    b["value"] = 5
    if listing.rent and listing.area_sqft:
        s.rent_psf = round(listing.rent / listing.area_sqft, 1)
        bench = (cfg["localities"].get(group, {}).get(listing.locality, {}) or {}).get("benchmark_rent_psf")
        if bench:
            s.value_vs_market = round(bench / s.rent_psf, 2)
            b["value"] = max(0, min(10, 5 + 10 * (s.value_vs_market - 1)))
            if s.value_vs_market >= 1.1:
                s.reasons.append(f"₹{s.rent_psf}/sqft, below the ~₹{bench}/sqft usual for the area")
            elif s.value_vs_market < 0.85:
                s.warnings.append(f"₹{s.rent_psf}/sqft is pricey against the ~₹{bench}/sqft usual for the area")

    if listing.rent:
        sales_needed = listing.rent / HEALTHY_RENT_SHARE
        s.orders_per_day_needed = round(sales_needed / OPEN_DAYS / AVG_ORDER_VALUE)

    penalty = 0
    for w in BAD_WORDS:
        if w in t:
            penalty += 15
            s.warnings.append(f"Red flag: '{w}'")
    b["penalty"] = -penalty

    s.score = round(max(0, min(100, sum(b.values()))), 1)
    s.tier = classify(listing, cfg, group)
    return s


def classify(l: Listing, cfg: dict, group: str) -> str:
    """match   = meets every hard requirement
       close   = within ~10% of the limits or missing one data point (verify by phone)
       stretch = in or near the target areas but outside the limits; used to reach the minimum count"""
    lo, hi = cfg["rent"]["min"], cfg["rent"]["max"]
    amin = cfg["area_sqft"]["min"]
    in_area = group in ("primary", "recommended")
    rent_ok = l.rent is not None and lo <= l.rent <= hi
    area_ok = l.area_sqft is not None and l.area_sqft >= amin
    if in_area and rent_ok and area_ok:
        return "match"
    rent_near = l.rent is None or 0.9 * lo <= l.rent <= 1.1 * hi
    area_near = l.area_sqft is None or l.area_sqft >= 0.9 * amin
    if in_area and rent_near and area_near and (l.rent is not None or l.area_sqft is not None):
        return "close"
    return "stretch"


TIER_ORDER = {"match": 0, "close": 1, "stretch": 2}


def rank(listings: list[Listing], cfg: dict) -> list[Scored]:
    scored = [score(l, cfg) for l in listings]
    scored.sort(key=lambda s: (TIER_ORDER[s.tier], -s.score))
    return scored


def shortlist(scored: list[Scored], cfg: dict) -> list[Scored]:
    """All full matches, topped up with close and then stretch options until min_results is reached."""
    n = cfg.get("min_results", 10)
    matches = [s for s in scored if s.tier == "match"]
    if len(matches) >= n:
        return matches
    rest = [s for s in scored if s.tier != "match"]
    return matches + rest[: n - len(matches)]
