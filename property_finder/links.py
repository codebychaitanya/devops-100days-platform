"""Ready-to-click searches for each locality, for use while logged in to your premium accounts."""
from __future__ import annotations

from urllib.parse import quote_plus

SITES = {
    "magicbricks": "magicbricks.com",
    "nobroker": "nobroker.in",
    "99acres": "99acres.com",
    "housing": "housing.com",
}


def search_links(cfg: dict) -> dict[str, dict[str, str]]:
    lo, hi = cfg["rent"]["min"], cfg["rent"]["max"]
    amin = cfg["area_sqft"]["min"]
    out: dict[str, dict[str, str]] = {}
    for group in ("primary", "recommended"):
        for loc in cfg["localities"][group]:
            q = f"commercial shop for rent {loc} Hyderabad {amin} sqft"
            links = {}
            for portal in cfg.get("portals", SITES):
                links[portal] = "https://www.google.com/search?q=" + quote_plus(f"{q} site:{SITES[portal]}")
            links["restaurant space"] = "https://www.google.com/search?q=" + quote_plus(
                f"restaurant space for rent {loc} Hyderabad rent {lo//1000}k-{hi//1000}k")
            out[loc] = links
    return out
